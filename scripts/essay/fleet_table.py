"""The German fleet table: which of 84.2 GW of listed German thermal and hydro capacity was in the
2025 day-ahead market, from public files only.

Inputs, all in one directory (names fixed; sha256 of each checked against MANIFEST.json):
  inventory_de.csv                    the inventory being classified: 518 rows, each one record of
                                      a public plant list (WRI GPPD 1.3.0 or OPSD 2020-10-01) by id
  global_power_plant_database.csv     WRI Global Power Plant Database 1.3.0
  conventional_power_plants_DE.csv    OPSD conventional power plants DE, 2020-10-01
  Kraftwerksliste_2026-06-26.xlsx     BNetzA Kraftwerksliste (status, closure year), 2026-06-26
  mastr_units_de.csv                  MaStR units >= 10 MW (extract_mastr.py on the 2026-06-06
                                      Gesamtdatenexport)
  a73_units_de_2025.csv               ENTSO-E A73 per-unit output 2025 (a73_units.py)
The BNetzA Verfahrensliste inländische Netzreserve (2025-03-10, a PDF) is transcribed in
rules.json. Every parameter is in rules.json.

Each inventory row is split into six classes (asserted to sum to its MW):
  market           stands for a register unit that was in the 2025 day-ahead market
  out_2025         stands for a unit in reserve, or closed, during 2025
  closed_pre_2025  stands for a unit closed before 2025
  duplicate        stands for units another inventory row already carries (the double count)
  unknown_2025     stands for a unit last seen operating in OPSD 2020, with no later register row
  no_register_row  stands for no register unit at all
"Not in the market" = out_2025 + closed_pre_2025 + duplicate.

Standard library, pandas and openpyxl (for the xlsx). Imports nothing else.

    python3 -I scripts/essay/fleet_table.py <inputs_dir> <out_dir> [--manifest MANIFEST.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RULES = json.loads((HERE / 'rules.json').read_text(encoding='utf-8'))
YEAR = RULES['year']
Y0, Y1 = pd.Timestamp(f'{YEAR}-01-01'), pd.Timestamp(f'{YEAR + 1}-01-01')
R_KM, SITE_KM, CAP_TOL = RULES['r_km'], RULES['site_km'], RULES['cap_tol']
A73_MARKET_CF = RULES['a73_market_cf']
COMPAT = {k: set(v) for k, v in RULES['compatible'].items()}
A73_FAM = {k: set(v) for k, v in RULES['a73_family'].items()}
STOP = set(RULES['name_stopwords'].split())
CLS = ['market', 'out_2025', 'closed_pre_2025', 'duplicate', 'unknown_2025', 'no_register_row']
FILES = ('inventory_de.csv', 'global_power_plant_database.csv', 'conventional_power_plants_DE.csv',
         'Kraftwerksliste_2026-06-26.xlsx', 'mastr_units_de.csv', 'a73_units_de_2025.csv')


# ---------------------------------------------------------------------------- helpers ---
def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '').lower())
    s = s.replace('ß', 'ss')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def tokens(s):
    return {t for t in norm(s).split() if len(t) >= 4 and not t.isdigit() and t not in STOP}


def hav(lat1, lon1, lat2, lon2):
    p = np.pi / 180
    a = (np.sin((lat2 - lat1) * p / 2) ** 2 +
         np.cos(lat1 * p) * np.cos(lat2 * p) * np.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


def kwl_class(v):
    if not isinstance(v, str):
        return None
    if v == 'InBetrieb':
        return 'market'
    if 'reserve' in v.lower() or 'netztechnisch' in v or 'gestreckte' in v:
        return 'reserve'
    if 'vorläufig' in v:
        return 'temporarily_closed'
    return 'closed'


def verfahrensliste_coverage():
    """MaStR unit -> (plant, share of the year inside a designation period)."""
    vl = RULES['verfahrensliste_2025_03_10']
    out = {}
    for plant, uids in vl['mastr_units'].items():
        days = set()
        for a, b in vl['periods'][plant]:
            a = max(pd.Timestamp(a), Y0)
            b = min(pd.Timestamp(b) if b else Y1, Y1 - pd.Timedelta(days=1))
            if a <= b:
                days |= set(pd.date_range(a, b, freq='D'))
        for u in uids:
            out['M:' + u] = (plant, len(days) / 365.0)
    return out


# ----------------------------------------------------------------------------- inputs ---
def read_inputs(d):
    d = Path(d)
    ms = pd.read_csv(d / 'mastr_units_de.csv', dtype=str, keep_default_na=True)
    ms['net_mw'] = ms.net_mw.astype(float)
    for c in ('Laengengrad', 'Breitengrad'):
        ms[c] = pd.to_numeric(ms[c], errors='coerce')
    for c in ('Inbetriebnahmedatum', 'DatumEndgueltigeStilllegung',
              'DatumBeginnVoruebergehendeStilllegung', 'DatumWiederaufnahmeBetrieb'):
        ms[c] = pd.to_datetime(ms[c], errors='coerce')
    kwl = pd.read_excel(d / 'Kraftwerksliste_2026-06-26.xlsx', sheet_name='Gesamtkraftwerksliste',
                        header=7)
    op = pd.read_csv(d / 'conventional_power_plants_DE.csv')
    gp = pd.read_csv(d / 'global_power_plant_database.csv', low_memory=False)
    a73 = pd.read_csv(d / 'a73_units_de_2025.csv', dtype={'eic': str, 'name': str})
    inv = pd.read_csv(d / 'inventory_de.csv', dtype={'source_id': str})
    return ms, kwl, op, gp, a73, inv


def inventory(inv, gp, op):
    """Each inventory line -> the public record it names: name, MW, coordinate."""
    gp = gp[gp.country == 'DEU']
    rows = []
    for _, r in inv.iterrows():
        if r.source == 'opsd_2020':
            h = op[op.id == r.source_id]
            nm, mw, la, lo = 'id', 'capacity_net_bnetza', 'lat', 'lon'
        else:
            h = gp[gp.gppd_idnr == r.source_id]
            nm, mw, la, lo = 'name', 'capacity_mw', 'latitude', 'longitude'
        # the k-th record under the id, in file order (OPSD carries two ids twice)
        k = int(r.source_occurrence)
        if len(h) <= k or (pd.notna(r.source_mw) and abs(h.iloc[k][mw] - r.source_mw) > 1e-6):
            raise SystemExit(f'inventory line {r.row}: no record {k} for {r.source} '
                             f'{r.source_id}, or its MW differs from the line')
        h = h.iloc[k]
        rows.append({'row': int(r.row), 'name': str(h[nm]), 'source': r.source,
                     'source_id': r.source_id, 'fam': r.fam, 'capacity_mw': float(h[mw]),
                     'lat': float(h[la]), 'lon': float(h[lo])})
    return pd.DataFrame(rows).set_index('row', drop=False)


# -------------------------------------------------------------------------- unit pool ---
def mastr_family(r):
    if r.file == 'storage':
        return 'psp' if r.Technologie_txt == 'Pumpspeicher' else 'battery'
    return RULES['mastr_family'].get(r.Energietraeger_txt, 'other')


def unit_pool(ms, kwl, op, a73_by_unit):
    ms = ms.copy()
    ms['fam'] = ms.apply(mastr_family, axis=1)
    ms = ms[ms.fam != 'battery'].copy()
    kst = dict(zip(kwl.EinheitMastrNummer, kwl.Kraftwerksstatus))
    kyr = dict(zip(kwl.EinheitMastrNummer, kwl['Jahr_Stilllegung**']))
    ms['kwl_status'] = ms.EinheitMastrNummer.map(kst)
    ms['kwl_class'] = ms.kwl_status.map(kwl_class)
    ms['kwl_closure_year'] = pd.to_numeric(ms.EinheitMastrNummer.map(kyr), errors='coerce')
    ms['uid'] = 'M:' + ms.EinheitMastrNummer
    ms['source'] = 'mastr'
    ms = ms.rename(columns={'Breitengrad': 'lat', 'Laengengrad': 'lon'})
    ms['station'] = ms.NameKraftwerk
    ms['block'] = ms.NameKraftwerksblock

    # BNA units MaStR does not carry (closed before MaStR began in 2019, or under another id)
    kn, weic = set(ms.Kraftwerksnummer.dropna()), set(ms.Weic.dropna())
    only = op[~op.id.isin(kn) & ~op.eic_code_block.isin(weic)].copy()
    only['fam'] = only.energy_source.map(RULES['opsd_family']).fillna('other')
    only.loc[only.technology.fillna('').str.contains('Pumped storage'), 'fam'] = 'psp'
    only = pd.DataFrame({
        'uid': 'O:' + only.id, 'source': 'opsd_2020', 'Kraftwerksnummer': only.id,
        'Weic': only.eic_code_block, 'fam': only.fam, 'net_mw': only.capacity_net_bnetza,
        'lat': only.lat, 'lon': only.lon, 'station': only.name_bnetza, 'block': only.block_bnetza,
        'opsd_status': only.status, 'opsd_shutdown': only.shutdown,
        'Inbetriebnahmedatum': pd.NaT, 'DatumEndgueltigeStilllegung': pd.NaT})
    # a unit OPSD lists as shut down is a site's closed unit (reachable by position); one it lists
    # as operating in 2020 that MaStR does not number is reachable by its own BNA number only
    only['positional'] = only.opsd_status == 'shutdown'
    ms['positional'] = True
    pool = pd.concat([ms, only], ignore_index=True, sort=False).set_index('uid', drop=False)
    vl = verfahrensliste_coverage()

    def cls(r):
        a = a73_by_unit.get(r.uid, {})
        a73cf = a.get('cf') if a.get('block_specific', True) else None
        if r.source == 'opsd_2020':
            if r.opsd_status == 'shutdown' and pd.notna(r.opsd_shutdown) and r.opsd_shutdown < YEAR:
                return 'closed_pre_2025', 'OPSD 2020 shutdown year'
            return 'unknown_2025', f'OPSD 2020 status {r.opsd_status}; no later register row'
        if r.EinheitBetriebsstatus_txt == 'In Planung' or (pd.notna(r.Inbetriebnahmedatum)
                                                           and r.Inbetriebnahmedatum >= Y1):
            return 'not_yet', 'commissioned after 2025 / in planning'
        end = r.DatumEndgueltigeStilllegung
        if pd.notna(end) and end < Y0:
            return 'closed_pre_2025', 'MaStR final closure date'
        if r.uid in vl and vl[r.uid][1] >= 0.5 and r.kwl_class == 'reserve':
            return 'out_2025', (f'grid reserve: Verfahrensliste 2025-03-10 ({vl[r.uid][0]}, '
                                f'{vl[r.uid][1]:.2f} of 2025) and Kraftwerksliste {r.kwl_status}')
        if a73cf is not None and a73cf >= A73_MARKET_CF:
            return 'market', 'A73 2025 CF >= 0.10'
        mid = Y0 + (Y1 - Y0) / 2
        if pd.notna(end) and end < Y1:
            if end >= mid:
                return 'market', 'MaStR final closure in the second half of 2025'
            return 'out_2025', 'MaStR final closure during 2025 (first half)'
        tmp = r.DatumBeginnVoruebergehendeStilllegung
        if pd.notna(tmp) and tmp < Y1 and pd.isna(r.DatumWiederaufnahmeBetrieb):
            if tmp >= mid:
                return 'market', 'MaStR temporary closure in the second half of 2025'
            return 'out_2025', 'MaStR temporarily closed from before mid-2025, no resumption'
        if r.kwl_class in ('reserve', 'temporarily_closed'):
            return 'out_2025', f'Kraftwerksliste status: {r.kwl_status}'
        if r.kwl_class == 'closed':
            yr = r.kwl_closure_year
            if pd.notna(yr) and yr < YEAR:
                return 'closed_pre_2025', 'Kraftwerksliste closure year'
            if pd.notna(yr) and yr == YEAR:
                return 'out_2025', 'Kraftwerksliste closure year 2025'
            return 'market', f'Kraftwerksliste closed {yr}: after 2025'
        return 'market', 'in service, Kraftwerksliste InBetrieb' if r.kwl_class == 'market' \
            else 'in service (MaStR dates)'
    cc = pool.apply(cls, axis=1, result_type='expand')
    pool['cls'], pool['cls_why'] = cc[0], cc[1]
    pool['a73_twh_2025'] = pool.uid.map(lambda u: a73_by_unit.get(u, {}).get('twh'))
    pool['a73_cf_2025'] = pool.uid.map(lambda u: a73_by_unit.get(u, {}).get('cf'))
    return pool


def a73_units(a73, pool):
    """A73 unit -> MaStR units: exact EIC; else the alias; else every distinctive name token of
    the A73 name in the MaStR text of a compatible family, all hits within 5 km."""
    m = pool[(pool.source == 'mastr') & (pool.cls != 'not_yet')]
    toks = m.apply(lambda r: tokens(f'{r.station or ""} {r.block or ""} '
                                    f'{r.NameStromerzeugungseinheit or ""} {r.Ort or ""}'), axis=1)
    out = []
    for _, u in a73.iterrows():
        fams = A73_FAM.get(u.psr, set())
        hit = m[m.Weic == u.eic]
        meth = 'eic'
        if not len(hit):
            al = next((v for k, v in RULES['a73_alias'].items() if u['name'].startswith(k + ' ')),
                      None)
            if al:
                hit, meth = m[(m.station == al) & m.fam.isin(fams)], 'alias'
            else:
                tk = tokens(u['name'])
                c = m[m.fam.isin(fams)]
                hit = c[toks[c.index].map(lambda t: bool(tk & t))] if tk else c.iloc[0:0]
                meth = 'name'
                if len(hit) and hav(hit.lat.values[:, None], hit.lon.values[:, None],
                                    hit.lat.values[None, :], hit.lon.values[None, :]).max() > SITE_KM:
                    hit, meth = hit.iloc[0:0], 'ambiguous'
        if not len(hit) and meth in ('name', 'eic'):
            meth = 'unmatched'
        out.append({'eic': u.eic, 'a73_name': u['name'], 'psr': u.psr, 'twh': u.twh,
                    'max_mw': u.max_mw, 'method': meth, 'units': list(hit.index)})
    am = pd.DataFrame(out)
    by_unit = {}
    for _, r in am.iterrows():
        if not r.units:
            continue
        tot = float(pool.loc[r.units, 'net_mw'].sum())
        for uid in r.units:
            mw = float(pool.at[uid, 'net_mw'])
            d = by_unit.setdefault(uid, {'twh': 0.0, 'eic': [], 'block_specific': True})
            d['twh'] += r.twh * mw / tot
            d['eic'].append(r.eic)
            # a station aggregate spread over its blocks says nothing about any one block
            if r.method not in ('eic',) and len(r.units) > 1:
                d['block_specific'] = False
    for uid, d in by_unit.items():
        d['cf'] = d['twh'] * 1e6 / (float(pool.at[uid, 'net_mw']) * 8760)
    return am, by_unit


# -------------------------------------------------------------- inventory row -> units ---
def identity(fl, pool, op):
    opi = op.set_index('id')
    cand_all = pool[pool.cls != 'not_yet']
    rows, owner = [], {}
    for i, p in fl.iterrows():
        rec = {'row': i, 'name': p['name'], 'fam': p.fam, 'mw': float(p.capacity_mw),
               'lat': p.lat, 'lon': p.lon, 'source': p.source, 'source_id': p.source_id,
               'is_bna': bool(re.match(RULES['bna_row_pattern'], str(p['name']))),
               'method': None, 'units': [], 'duplicate_of': None}
        compat = COMPAT.get(p.fam, set())
        if rec['is_bna']:
            bna = p['name']
            hit = cand_all[(cand_all.source == 'mastr') & (cand_all.Kraftwerksnummer == bna)]
            meth = 'bna_number'
            if not len(hit) and bna in opi.index and isinstance(opi.at[bna, 'eic_code_block'], str):
                hit = cand_all[(cand_all.source == 'mastr') &
                               (cand_all.Weic == opi.at[bna, 'eic_code_block'])]
                meth = 'opsd_block_eic'
            if not len(hit):
                c = cand_all[(cand_all.source == 'mastr') & cand_all.fam.isin(compat)]
                c = c[hav(p.lat, p.lon, c.lat.values, c.lon.values) <= R_KM]
                ok = np.abs(c.net_mw.values - p.capacity_mw) <= CAP_TOL * p.capacity_mw
                if ok.any():
                    dd = hav(p.lat, p.lon, c.lat.values, c.lon.values)
                    j = int(np.argmin(np.where(ok, dd, np.inf)))
                    hit, meth = c.iloc[[j]], 'position_and_capacity'
                else:   # a block MaStR registers as GT + DT units of one station
                    for _st, g in c[c.station.notna()].groupby('station'):
                        if abs(g.net_mw.sum() - p.capacity_mw) <= CAP_TOL * p.capacity_mw:
                            hit, meth = g, 'position_and_capacity_station'
                            break
            if not len(hit) and f'O:{bna}' in pool.index:
                hit, meth = pool.loc[[f'O:{bna}']], 'opsd_record'
            if not len(hit):
                meth = 'none'
            rec['method'], rec['units'] = meth, list(hit.index)
            key = ('bna', bna)
            if key in owner:
                rec['duplicate_of'], rec['units'], rec['method'] = owner[key], [], 'duplicate_bna'
            else:
                owner[key] = f"{p['name']}#{i}"
        else:
            c = cand_all[cand_all.fam.isin(compat) & cand_all.positional]
            c = c[c.lat.notna()]
            d = hav(p.lat, p.lon, c.lat.values, c.lon.values)
            hit = c[d <= R_KM]
            rec['method'] = 'position_2km' if len(hit) else 'none'
            if not len(hit):     # a coordinate off the site: the site's own name, within 5 km
                tk = tokens(p['name'])
                c5 = c[d <= SITE_KM]
                hit = c5[c5.station.map(lambda s: bool(tk & tokens(s)))] if tk else c5.iloc[0:0]
                if len(hit):
                    rec['method'] = 'name_5km'
            rec['units'] = list(hit.index)
        rows.append(rec)
    mm = pd.DataFrame(rows).set_index('row', drop=False)
    # a station row still without units: compatible units within 5 km that nobody claims
    taken = set().union(*mm.units.map(set))
    for i, r in mm[(mm.method == 'none') & ~mm.is_bna].iterrows():
        c = cand_all[cand_all.fam.isin(COMPAT.get(r.fam, set())) & cand_all.positional &
                     ~cand_all.index.isin(taken)]
        c = c[c.lat.notna()]
        hit = c[hav(r.lat, r.lon, c.lat.values, c.lon.values) <= SITE_KM]
        if len(hit):
            mm.at[i, 'method'], mm.at[i, 'units'] = 'unclaimed_5km', list(hit.index)
            taken |= set(hit.index)
    # the same site under another fuel: thermal units within 0.5 km nobody claims (recorded)
    therm = set(RULES['same_site_families'])
    for i, r in mm[(mm.method == 'none') & ~mm.is_bna & mm.fam.isin(therm)].iterrows():
        c = cand_all[cand_all.fam.isin(therm) & cand_all.positional & ~cand_all.index.isin(taken)]
        c = c[c.lat.notna()]
        hit = c[hav(r.lat, r.lon, c.lat.values, c.lon.values) <= RULES['same_site_other_fuel_km']]
        if len(hit):
            mm.at[i, 'method'], mm.at[i, 'units'] = 'site_other_fuel', list(hit.index)
            taken |= set(hit.index)
    return mm


def partition(mm, pool):
    owned = {}
    for i, r in mm[mm.is_bna].iterrows():
        for u in r.units:
            owned.setdefault(u, []).append(i)
    claims = {}
    for i, r in mm[~mm.is_bna].iterrows():
        for u in r.units:
            if u not in owned:
                claims.setdefault(u, []).append(i)
    parts = []
    for i, r in mm.iterrows():
        rec = {k: 0.0 for k in CLS}
        M = r.mw
        if r.method == 'duplicate_bna':
            rec['duplicate'] = M
        elif r.is_bna and r.units:
            share = {}
            for uid, ur in pool.loc[r.units].iterrows():
                n = len(owned.get(uid, [i]))
                share[ur.cls] = share.get(ur.cls, 0.0) + float(ur.net_mw) / n
            tot = sum(share.values())
            scale = min(1.0, M / tot) if tot > 0 else 0.0
            for k, v in share.items():
                rec[k] += v * scale
            rec['no_register_row'] = max(0.0, M - tot)
        elif not r.is_bna and r.units:
            share = {}
            for uid in [u for u in r.units if u not in owned]:
                w = M / float(mm.loc[claims[uid], 'mw'].sum())
                share[pool.at[uid, 'cls']] = share.get(pool.at[uid, 'cls'], 0.0) + \
                    float(pool.at[uid, 'net_mw']) * w
            dup_mw = float(pool.loc[[u for u in r.units if u in owned], 'net_mw'].sum())
            share['duplicate'] = dup_mw
            left = M
            for k in RULES['class_order_for_station_rows']:
                take = min(left, share.get(k, 0.0))
                rec[k] += take
                left -= take
            if dup_mw > 0:      # a station row on a site a unit row carries: the double count
                rec['duplicate'] += left
                left = 0.0
            rec['no_register_row'] = left
        else:
            rec['no_register_row'] = M
        assert abs(sum(rec.values()) - M) < 1e-6, (r['name'], rec, M)
        parts.append(rec)
    return pd.concat([mm, pd.DataFrame(parts, index=mm.index)], axis=1), owned, claims


# ------------------------------------------------------------------------------- main ---
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('inputs')
    ap.add_argument('out')
    ap.add_argument('--manifest', help='MANIFEST.json: refuse any input whose sha256 differs')
    a = ap.parse_args()
    inp, out = Path(a.inputs), Path(a.out)
    hashes = {f: sha256(inp / f) for f in FILES}
    if a.manifest:
        man = json.loads(Path(a.manifest).read_text())['files']
        bad = [f for f in FILES if man.get(f, {}).get('sha256') != hashes[f]]
        if bad:
            raise SystemExit(f'sha256 differs from the manifest: {bad}')
    ms, kwl, op, gp, a73, inv = read_inputs(inp)
    fl = inventory(inv, gp, op)

    pool0 = unit_pool(ms, kwl, op, {})              # pass 1: classes without A73
    am, a73u = a73_units(a73, pool0)
    pool = unit_pool(ms, kwl, op, a73u)             # pass 2: a unit's own 2025 output decides
    am2, _ = a73_units(a73, pool)
    assert am2.units.map(tuple).tolist() == am.units.map(tuple).tolist()   # the join is stable

    mm = identity(fl, pool, op)
    mm, owned, claims = partition(mm, pool)
    pool['claimed_by'] = pool.uid.map(lambda u: ';'.join(map(str, owned.get(u, claims.get(u, [])))))

    tot = mm[CLS + ['mw']].sum()
    table = pd.DataFrame({'class': CLS + ['total'],
                          'mw': [round(float(tot[c]), 1) for c in CLS] + [round(float(tot.mw), 1)]})
    table['share_of_total'] = (table.mw / float(tot.mw)).round(4)
    not_market = float(tot[['out_2025', 'closed_pre_2025', 'duplicate']].sum())
    by_fam = mm.groupby('fam')[CLS + ['mw']].sum().round(1)

    out.mkdir(parents=True, exist_ok=True)
    table.to_csv(out / 'table.csv', index=False)
    by_fam.to_csv(out / 'table_by_family.csv')
    p = mm.copy()
    p['units'] = p.units.map(';'.join)
    p.drop(columns=['is_bna']).to_csv(out / 'plants.csv', index=False)
    keep = ['uid', 'source', 'EinheitMastrNummer', 'Kraftwerksnummer', 'Weic', 'fam', 'net_mw',
            'lat', 'lon', 'station', 'block', 'Ort', 'Inbetriebnahmedatum',
            'DatumEndgueltigeStilllegung', 'kwl_status', 'kwl_closure_year', 'opsd_status',
            'opsd_shutdown', 'cls', 'cls_why', 'a73_twh_2025', 'a73_cf_2025', 'claimed_by']
    pool[keep].to_csv(out / 'units.csv', index=False)
    am.assign(units=am.units.map(';'.join)).to_csv(out / 'a73_match.csv', index=False)
    summary = {'inputs_sha256': hashes, 'rules_sha256': sha256(HERE / 'rules.json'),
               'inventory': {'rows': int(len(mm)), 'mw': round(float(tot.mw), 1),
                             'by_source_mw': mm.groupby('source').mw.sum().round(1).to_dict()},
               'table_mw': dict(zip(table['class'], table.mw)),
               'not_in_market_mw': round(not_market, 1),
               'not_in_market_share': round(not_market / float(tot.mw), 4),
               'not_in_market_def': 'out_2025 + closed_pre_2025 + duplicate, of the inventory total',
               'units_in_pool': int(len(pool)),
               'a73_match_by_method': am.method.value_counts().to_dict()}
    (out / 'summary.json').write_text(json.dumps(summary, indent=1, default=str))
    print(table.to_string(index=False))
    print(f'not in the market: {not_market:,.1f} MW = {not_market / float(tot.mw):.1%} of '
          f'{float(tot.mw):,.1f} MW')


if __name__ == '__main__':
    main()
