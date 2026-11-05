"""The fleet table, itemised: the capacity it cannot place, the double count side by side, the hard
coal bridge, and the Bundesnetzagentur's own count beside ours.

Reads fleet_table.py's inputs and outputs, plus (items 1 and 3) the MaStR units of every size:
  extract_mastr.py <zip> mastr_units_de_all.csv 0   ->  <inputs>/mastr_units_de_all.csv
or, when that export is not at hand, the shipped <inputs>/mastr_units_de_nonbattery.csv.gz: the
same rows without the battery storage units (every storage unit but pumped hydro), which no item
reads. make_nonbattery() below writes it.
Writes, under <out>/details/:
  unresolved_rows.csv, unresolved.json   item 1: the unknown_2025 and no_register_row MW, by tier
  duplicate_sites.csv, duplicates.json   item 2: every site with a double count; one-source sites
  hard_coal_bridge.csv, hard_coal.json   item 3: MaStR 'In Betrieb' -> 2025 market, unit by unit
  kwl_totals.csv, kwl_compare.json       item 4: the Kraftwerksliste's own totals beside ours

Nothing found here moves capacity between the table's columns: the table stands as computed.

    python3 -I scripts/essay/fleet_details.py <inputs_dir> <fleet_table_out_dir>
    python3 -I scripts/essay/fleet_details.py --make-nonbattery <inputs_dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fleet_table as FT    # noqa: E402  the same rules, the same helpers

CLS = FT.CLS


def load(inp, out):
    pl = pd.read_csv(out / 'plants.csv', dtype={'source_id': str})
    pl['units'] = pl.units.fillna('').map(lambda s: [x for x in s.split(';') if x])
    un = pd.read_csv(out / 'units.csv', dtype={'claimed_by': str, 'Kraftwerksnummer': str})
    un['claimed_by'] = un.claimed_by.fillna('')
    return pl, un


NONBATTERY = 'mastr_units_de_nonbattery.csv.gz'


def nonbattery(u):
    return u[(u.file != 'storage') | (u.Technologie_txt == 'Pumpspeicher')]


def all_units(inp):
    p = inp / 'mastr_units_de_all.csv'
    u = pd.read_csv(p if p.exists() else inp / NONBATTERY, dtype=str)
    return nonbattery(u).copy()


def make_nonbattery(inp):
    """<inputs>/mastr_units_de_all.csv -> <inputs>/mastr_units_de_nonbattery.csv.gz (mtime 0)"""
    import gzip
    u = nonbattery(pd.read_csv(inp / 'mastr_units_de_all.csv', dtype=str))
    with gzip.GzipFile(inp / NONBATTERY, 'wb', mtime=0) as f:
        f.write(u.to_csv(index=False).encode('utf-8'))


# ------------------------------------------------------------------ item 1: unresolved ---
def unresolved(inp, pl, un, ms, kwl, op):
    """P2's tiers, fixed in docs/essays/ES1_PREREGISTRATION_2026-10-31.md before the run. A
    candidate unit is used once (greedy, in inventory order); units another row already carries
    are not used for a no_register_row remainder (that would count them twice)."""
    small = all_units(inp)
    small['net_mw'] = small.net_mw.astype(float)
    small = small[small.net_mw < FT.RULES['min_net_mw']].copy()
    for c in ('Laengengrad', 'Breitengrad'):
        small[c] = pd.to_numeric(small[c], errors='coerce')
    for c in ('Inbetriebnahmedatum', 'DatumEndgueltigeStilllegung',
              'DatumBeginnVoruebergehendeStilllegung', 'DatumWiederaufnahmeBetrieb'):
        small[c] = pd.to_datetime(small[c], errors='coerce')
    sp = FT.unit_pool(small, kwl, op, {})
    sp = sp[(sp.source == 'mastr') & (sp.cls != 'not_yet') & sp.lat.notna()]
    big = un[(un.cls != 'not_yet') & un.lat.notna()].drop_duplicates('uid').set_index('uid')
    left = {**{u: float(m) for u, m in sp.net_mw.items()},
            **{u: float(m) for u, m in big.net_mw.items()}}
    rows, cls_mw = [], {}

    def take(r, cands, tier, rem):
        got = []
        for uid, c in cands.iterrows():
            if rem <= 1e-9:
                break
            t = min(rem, left.get(uid, 0.0))
            if t <= 0:
                continue
            left[uid] -= t
            rem -= t
            got.append((uid, c.cls, t))
            cls_mw[(tier, c.cls)] = cls_mw.get((tier, c.cls), 0.0) + t
        return got, rem

    for _, r in pl.iterrows():
        compat = FT.COMPAT.get(r.fam, set())
        # tier 1: an OPSD-2020 unit MaStR does not number -> a MaStR unit at its position
        if r.unknown_2025 > 0:
            o = big.loc[[u for u in r.units if u.startswith('O:')]]
            for uid, ou in o.iterrows():
                c = big[(big.source == 'mastr') & big.fam.isin(compat)]
                d = FT.hav(ou.lat, ou.lon, c.lat.values, c.lon.values)
                ok = (d <= FT.R_KM) & (np.abs(c.net_mw.values - ou.net_mw) <= FT.CAP_TOL * ou.net_mw)
                mw = min(float(ou.net_mw), r.unknown_2025)
                if ok.any():
                    j = int(np.argmin(np.where(ok, d, np.inf)))
                    m = c.iloc[j]
                    k = 'carried by another inventory row' if m.claimed_by else m.cls
                    cls_mw[('1_mastr_at_opsd_position', k)] = \
                        cls_mw.get(('1_mastr_at_opsd_position', k), 0.0) + mw
                    rows.append({'row': r.row, 'name': r['name'], 'fam': r.fam, 'part': 'unknown_2025',
                                 'tier': '1_mastr_at_opsd_position', 'cls': k, 'mw': mw,
                                 'register_unit': c.index[j], 'station': m.station})
                else:
                    rows.append({'row': r.row, 'name': r['name'], 'fam': r.fam, 'part': 'unknown_2025',
                                 'tier': 'unresolved', 'cls': 'no MaStR unit at the OPSD position',
                                 'mw': mw, 'register_unit': uid, 'station': ou.station})
        rem = float(r.no_register_row)
        if rem <= 1e-6:
            continue
        # the remainder of a unit row whose MW exceeds its register unit's: the register has no
        # such MW (a capacity disagreement), recorded before any tier looks for more units
        if FT.re.match(FT.RULES['bna_row_pattern'], str(r['name'])) and r.units:
            rows.append({'row': r.row, 'name': r['name'], 'fam': r.fam, 'part': 'no_register_row',
                         'tier': 'unresolved', 'cls': 'unit row MW above its register unit MW',
                         'mw': rem, 'register_unit': ';'.join(r.units), 'station': None})
            continue
        # tier 2: MaStR units below 10 MW, compatible, within 2 km
        c = sp[sp.fam.isin(compat)]
        c = c[FT.hav(r.lat, r.lon, c.lat.values, c.lon.values) <= FT.R_KM]
        got, rem = take(r, c, '2_mastr_below_10mw_2km', rem)
        # tier 3: unclaimed units (any size), compatible, within 5 km, sharing a name token
        tk = FT.tokens(r['name'])
        c = pd.concat([x for x in (big[(big.claimed_by == '') & big.fam.isin(compat)],
                                   sp[sp.fam.isin(compat)]) if len(x)])
        c = c[FT.hav(r.lat, r.lon, c.lat.values, c.lon.values) <= FT.SITE_KM]
        hit = np.array([bool(tk & FT.tokens(s)) for s in c.station], dtype=bool)
        c = c[hit] if tk else c.iloc[0:0]
        got3, rem = take(r, c[c.source == 'mastr'], '3_mastr_name_5km', rem)
        # tier 4: an unclaimed OPSD-only record within 2 km: shut down by 2024 -> closed
        c = big[(big.source == 'opsd_2020') & (big.claimed_by == '') & big.fam.isin(compat)]
        c = c[(FT.hav(r.lat, r.lon, c.lat.values, c.lon.values) <= FT.R_KM) &
              (c.cls == 'closed_pre_2025')]
        got4, rem = take(r, c, '4_opsd_record_2km', rem)
        for tier, g in (('2_mastr_below_10mw_2km', got), ('3_mastr_name_5km', got3),
                        ('4_opsd_record_2km', got4)):
            for uid, k, t in g:
                rows.append({'row': r.row, 'name': r['name'], 'fam': r.fam,
                             'part': 'no_register_row', 'tier': tier, 'cls': k, 'mw': t,
                             'register_unit': uid, 'station': None})
        if rem > 1e-6:
            why = ('station row larger than the units at its site' if r.units else
                   'no compatible register unit within 5 km of the listed coordinate')
            rows.append({'row': r.row, 'name': r['name'], 'fam': r.fam, 'part': 'no_register_row',
                         'tier': 'unresolved', 'cls': why, 'mw': rem, 'register_unit': None,
                         'station': None})
    t = pd.DataFrame(rows)
    # POST HOC, not graded: tier 1 asked for ONE unit within 15%. A register that files a plant
    # as many engines (Kiel: 20 modules under 10 MW) fails it. The sensitivity: every compatible
    # MaStR unit, any size, within 2 km of the OPSD position, if their sum is within 15%.
    allp = pd.concat([x for x in (sp, big[big.source == 'mastr']) if len(x)])
    post = []
    for _, r in t[(t.part == 'unknown_2025') & (t.tier == 'unresolved')].iterrows():
        ou = big.loc[r.register_unit]
        c = allp[allp.fam.isin(FT.COMPAT.get(r.fam, set()))]
        c = c[FT.hav(ou.lat, ou.lon, c.lat.values, c.lon.values) <= FT.R_KM]
        if len(c) and abs(c.net_mw.sum() - ou.net_mw) <= FT.CAP_TOL * ou.net_mw:
            for k, g in c.groupby('cls'):
                post.append({'name': r['name'], 'cls': k,
                             'mw': r.mw * float(g.net_mw.sum()) / float(c.net_mw.sum())})
    post = pd.DataFrame(post, columns=['name', 'cls', 'mw'])
    den = float(pl.unknown_2025.sum() + pl.no_register_row.sum())
    classified = float(t[t.tier != 'unresolved'].mw.sum())
    summary = {
        'denominator_mw': round(den, 1),
        'denominator_def': 'unknown_2025 + no_register_row of the fleet table',
        'classified_mw': round(classified, 1), 'classified_share': round(classified / den, 4),
        'by_tier_and_class_mw': {f'{a} | {b}': round(v, 1) for (a, b), v in sorted(cls_mw.items())},
        'unresolved_by_reason_mw': t[t.tier == 'unresolved'].groupby('cls').mw.sum().round(1).to_dict(),
        'unresolved_by_family_mw': t[t.tier == 'unresolved'].groupby('fam').mw.sum().round(1).to_dict(),
        'largest_unresolved': t[t.tier == 'unresolved'].sort_values('mw', ascending=False)
        .head(15)[['name', 'fam', 'mw', 'cls']].round(1).to_dict('records'),
        'post_hoc_unit_groups_at_opsd_position': {
            'not_graded': 'tier 1 with a group of MaStR units (any size) instead of one unit',
            'rows': int(post.name.nunique()), 'mw': round(float(post.mw.sum()), 1),
            'by_class_mw': post.groupby('cls').mw.sum().round(1).to_dict(),
            'classified_share_if_added': round((classified + float(post.mw.sum())) / den, 4)}}
    return t, summary


# ----------------------------------------------------------------- item 2: duplicates ---
def duplicates(inp, pl, un, op):
    """Every site where two inventory rows carry the same register units. A component = rows
    linked by a shared register unit (or one OPSD id). Cross-source vs one-source; and an MW test:
    the rows' MW over the MW of the register units they jointly carry."""
    g = pd.read_csv(inp / 'global_power_plant_database.csv', low_memory=False)
    g = g[g.country == 'DEU'].set_index('gppd_idnr')
    unit = un.drop_duplicates('uid').set_index('uid')
    parent = {i: i for i in pl.row}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    by_unit = {}
    for _, r in pl.iterrows():
        for u in r.units:
            by_unit.setdefault(u, []).append(r.row)
    for rs in by_unit.values():
        for x in rs[1:]:
            parent[find(x)] = find(rs[0])
    for _, grp in pl.groupby('name'):          # one OPSD id on two rows
        if grp.source.iloc[0] == 'opsd_2020' and len(grp) > 1:
            for x in grp.row.iloc[1:]:
                parent[find(x)] = find(grp.row.iloc[0])
    pl = pl.assign(comp=pl.row.map(find))
    out, rec = [], []
    for c, grp in pl.groupby('comp'):
        if len(grp) < 2:
            continue
        units = sorted({u for us in grp.units for u in us})
        umw = float(unit.loc[units, 'net_mw'].sum()) if units else 0.0
        srcs = sorted(set(grp.source))
        one = {s: int((grp.source == s).sum()) for s in srcs}
        one_source = [s for s, n in one.items() if n > 1 and (
            # two rows of one source that share a unit, or one OPSD id twice
            any(len({x for x in by_unit.get(u, []) if pl.set_index('row').at[x, 'source'] == s}) > 1
                for u in units) or grp[grp.source == s].name.duplicated().any())]
        dup = float(grp.duplicate.sum())
        rec.append({'site_rows': '; '.join(grp.name), 'sources': '+'.join(srcs),
                    'rows': len(grp), 'rows_mw': round(float(grp.mw.sum()), 1),
                    'register_units': len(units), 'register_mw': round(umw, 1),
                    'ratio': round(float(grp.mw.sum()) / umw, 2) if umw else None,
                    'duplicate_mw_in_table': round(dup, 1),
                    'one_source_overlap': ','.join(one_source)})
        for _, r in grp.iterrows():
            src_name = (g.at[r.source_id, 'name'] if r.source == 'gppd_1_3_0' else
                        op[op.id == r.source_id].block_bnetza.iloc[0])
            src_of_src = g.at[r.source_id, 'source'] if r.source == 'gppd_1_3_0' else 'BNetzA list'
            out.append({'site': grp.name.iloc[0], 'row': r.row, 'source': r.source,
                        'source_id': r.source_id, 'name': src_name,
                        'listed_by_source_as_from': src_of_src, 'mw': r.mw,
                        'method': r.method, 'duplicate_mw': round(r.duplicate, 1),
                        'register_units': ' | '.join(
                            f"{unit.at[u, 'station']} {unit.at[u, 'block'] or ''} "
                            f"{unit.at[u, 'net_mw']:.0f} MW {unit.at[u, 'cls']}".replace(' nan ', ' ')
                            for u in r.units)})
    sites = pd.DataFrame(rec).sort_values('duplicate_mw_in_table', ascending=False)
    side = pd.DataFrame(out)
    dsites = sites[sites.duplicate_mw_in_table > 0]
    one = sites[sites.one_source_overlap != '']
    summary = {
        'sites_with_duplicate_mw': int(len(dsites)),
        'duplicate_mw_by_source_mix': dsites.groupby('sources').duplicate_mw_in_table.sum()
        .round(1).to_dict(),
        'p4_literal_one_source_sites': int(len(one)),
        'p4_literal_by_source': one.one_source_overlap.value_counts().to_dict(),
        'p4_one_source_sites_with_rows_mw_ge_1_5x_register_mw': int((one.ratio >= 1.5).sum()),
        'one_source_sites': one[['site_rows', 'sources', 'rows_mw', 'register_mw', 'ratio',
                                 'duplicate_mw_in_table']].to_dict('records'),
        'gppd_rows_in_duplicate_sites_by_their_own_source':
            side[(side.source == 'gppd_1_3_0') & (side.duplicate_mw > 0)]
            .groupby('listed_by_source_as_from').mw.sum().round(1).to_dict()}
    return sites, side, summary


# ------------------------------------------------------------------ item 3: hard coal ---
def hard_coal(inp, un, ms):
    m = ms.copy()
    m = m[m.Energietraeger_txt == 'Steinkohle']
    u = un.drop_duplicates('uid').set_index('uid')
    m['uid'] = 'M:' + m.EinheitMastrNummer
    for c in ('cls', 'cls_why', 'kwl_status', 'a73_cf_2025', 'claimed_by'):
        m[c] = m.uid.map(u[c])
    m['in_betrieb'] = m.EinheitBetriebsstatus_txt == 'In Betrieb'
    end = pd.to_datetime(m.DatumEndgueltigeStilllegung, errors='coerce')
    start = pd.to_datetime(m.Inbetriebnahmedatum, errors='coerce')
    m['in_service_2025'] = start.notna() & (start < FT.Y1) & (end.isna() | (end >= FT.Y0))
    # S46's figure: in service in 2025 and Kraftwerksliste 'InBetrieb' (2026-06-26), or an own
    # A73 2025 capacity factor >= 0.10
    m['s46_market'] = m.in_service_2025 & ((m.kwl_status == 'InBetrieb') |
                                           (m.a73_cf_2025.fillna(0) >= FT.A73_MARKET_CF))
    cols = ['EinheitMastrNummer', 'NameKraftwerk', 'NameKraftwerksblock', 'net_mw',
            'EinheitBetriebsstatus_txt', 'DatumEndgueltigeStilllegung', 'in_service_2025',
            'kwl_status', 'a73_cf_2025', 's46_market', 'cls', 'cls_why']
    t = m[cols].sort_values(['s46_market', 'net_mw'], ascending=[True, False])
    ib = m[m.in_betrieb]
    s = {
        'mastr_in_betrieb': {'units': int(len(ib)), 'net_mw': round(float(ib.net_mw.sum()), 1)},
        'mastr_in_service_2025': {'units': int(m.in_service_2025.sum()),
                                  'net_mw': round(float(m[m.in_service_2025].net_mw.sum()), 1)},
        's46_market': {'units': int(m.s46_market.sum()),
                       'net_mw': round(float(m[m.s46_market].net_mw.sum()), 1)},
        'mastr_min_net_mw_any_size': None,
        'reserve_date_fields_filled': None,
        'in_betrieb_not_s46_market_by_kwl_status_mw':
            ib[~ib.s46_market].groupby('kwl_status').net_mw.sum().round(1).to_dict(),
        'in_service_2025_not_in_betrieb_mw':
            m[m.in_service_2025 & ~m.in_betrieb].groupby('EinheitBetriebsstatus_txt').net_mw.sum()
            .round(1).to_dict(),
        'in_betrieb_by_2025_class_mw': ib.groupby('cls').net_mw.sum().round(1).to_dict(),
        'bridge_residual_mw': None}
    # the bridge, itemised: In Betrieb - (In Betrieb, not S46-market) + (in service 2025, not In
    # Betrieb, S46-market) = S46 market
    a = float(ib.net_mw.sum())
    minus = float(ib[~ib.s46_market].net_mw.sum())
    plus = float(m[~m.in_betrieb & m.s46_market].net_mw.sum())
    s['bridge'] = {'in_betrieb_mw': round(a, 1), 'minus_in_betrieb_not_market_mw': round(minus, 1),
                   'plus_closed_since_but_market_2025_mw': round(plus, 1),
                   'equals_mw': round(a - minus + plus, 1)}
    s['bridge_residual_mw'] = round(a - minus + plus - s['s46_market']['net_mw'], 3)
    allu = all_units(inp)
    hc = allu[allu.Energietraeger_txt == 'Steinkohle'].copy()
    hc['net_mw'] = hc.net_mw.astype(float)
    s['mastr_min_net_mw_any_size'] = round(float(hc.net_mw.min()), 3)
    s['mastr_hard_coal_units_below_10mw_in_betrieb'] = {
        'units': int(((hc.net_mw < 10) & (hc.EinheitBetriebsstatus_txt == 'In Betrieb')).sum()),
        'net_mw': round(float(hc[(hc.net_mw < 10) & (hc.EinheitBetriebsstatus_txt == 'In Betrieb')]
                              .net_mw.sum()), 1)}
    s['reserve_date_fields_filled'] = {c: int(hc[c].notna().sum()) for c in
                                       ('NetzreserveAbDatum', 'SicherheitsbereitschaftAbDatum')}
    return t, s


# ------------------------------------------------------------ item 4: the KWL's count ---
KWL_FAM = {'Braunkohle': 'lignite', 'Steinkohle': 'hard_coal', 'Erdgas': 'gas',
           'Mineraloelprodukte': 'oil', 'Pumpspeicher': 'psp', 'Wasser': 'hydro'}


def kwl_group(v):
    k = FT.kwl_class(v)
    return {'market': 'in operation', 'reserve': 'reserve', 'temporarily_closed':
            'temporarily closed', 'closed': 'closed'}.get(k, str(v))


def kwl_compare(kwl, pl, un):
    k = kwl[kwl.Land == 'Deutschland'].copy()
    k['fam'] = k.Energietraeger.map(KWL_FAM)
    k = k[k.fam.notna()]
    k['status'] = k.Kraftwerksstatus.map(kwl_group)
    k['row_type'] = k['Datensatztyp*']
    tot = k.pivot_table(index='fam', columns='status', values='Nettonennleistung_MW',
                        aggfunc='sum', fill_value=0).round(1)
    small = k[k.row_type == 'Kleinanlagen_aggregiert'].groupby('fam').Nettonennleistung_MW.sum()
    ours = pl.groupby('fam')[['market', 'out_2025', 'closed_pre_2025', 'duplicate',
                              'unknown_2025', 'no_register_row', 'mw']].sum().round(1)
    pool = un.drop_duplicates('uid')
    pool = pool[(pool.source == 'mastr') & pool.fam.isin(KWL_FAM.values())]
    reg = pool.pivot_table(index='fam', columns='cls', values='net_mw', aggfunc='sum',
                           fill_value=0).round(1)
    j = tot.join(ours.add_prefix('inventory_'), how='outer').join(reg.add_prefix('mastr_10mw_'),
                                                                 how='outer').fillna(0)
    j['kwl_small_aggregated_rows_mw'] = small.reindex(j.index).fillna(0).round(1)
    # unit by unit: each single-unit KWL row joined to the register unit of the same MaStR number
    one = k[k.row_type != 'Kleinanlagen_aggregiert'].copy()
    cls = dict(zip(pool.EinheitMastrNummer, pool.cls))
    one['class_2025'] = one.EinheitMastrNummer.map(cls).fillna('not in the >=10 MW register extract')
    x = one.pivot_table(index=['fam', 'status'], columns='class_2025',
                        values='Nettonennleistung_MW', aggfunc='sum', fill_value=0).round(1)
    return j, {'kwl_rows_germany': int(len(k)), 'kwl_def': 'Kraftwerksliste 2026-06-26, Land = '
               'Deutschland, net MW by Energietraeger x status (in operation / reserve / '
               'temporarily closed / closed); includes rows aggregating plants under 10 MW',
               'table': j.round(1).to_dict(orient='index'),
               'unit_join_def': 'single-unit KWL rows, by MaStR number, KWL status (2026-06-26) '
                                'x this kit\'s 2025 class, net MW (KWL)',
               'unit_join': {f'{a} | {b}': {c: v for c, v in r.items() if v}
                             for (a, b), r in x.to_dict(orient='index').items()}}


def main(inp, out):
    inp, out = Path(inp), Path(out)
    det = out / 'details'
    det.mkdir(parents=True, exist_ok=True)
    pl, un = load(inp, out)
    ms, kwl, op, gp, a73, inv = FT.read_inputs(inp)
    t, s1 = unresolved(inp, pl, un, ms, kwl, op)
    t.to_csv(det / 'unresolved_rows.csv', index=False)
    (det / 'unresolved.json').write_text(json.dumps(s1, indent=1, default=str))
    sites, side, s2 = duplicates(inp, pl, un, op)
    sites.to_csv(det / 'duplicate_sites.csv', index=False)
    side.to_csv(det / 'duplicate_rows_side_by_side.csv', index=False)
    (det / 'duplicates.json').write_text(json.dumps(s2, indent=1, default=str))
    h, s3 = hard_coal(inp, un, ms)
    h.to_csv(det / 'hard_coal_bridge.csv', index=False)
    (det / 'hard_coal.json').write_text(json.dumps(s3, indent=1, default=str))
    k, s4 = kwl_compare(kwl, pl, un)
    k.to_csv(det / 'kwl_totals.csv')
    (det / 'kwl_compare.json').write_text(json.dumps(s4, indent=1, default=str))
    print(json.dumps({'unresolved': {x: s1[x] for x in ('denominator_mw', 'classified_mw',
                                                        'classified_share',
                                                        'unresolved_by_reason_mw')},
                      'duplicates': {x: s2[x] for x in ('sites_with_duplicate_mw',
                                                        'duplicate_mw_by_source_mix',
                                                        'p4_literal_one_source_sites',
                                                        'p4_one_source_sites_with_rows_mw_ge_1_5x_register_mw')},
                      'hard_coal': {x: s3[x] for x in ('mastr_in_betrieb', 's46_market', 'bridge',
                                                       'bridge_residual_mw')}},
                     indent=1, default=str))


if __name__ == '__main__':
    if sys.argv[1] == '--make-nonbattery':
        make_nonbattery(Path(sys.argv[2]))
    else:
        main(*sys.argv[1:3])
