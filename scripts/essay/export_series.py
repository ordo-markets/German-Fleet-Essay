"""Repo side, run once: the published series behind the essay's model section.

Reads two STORED full-year re-clears (no model run):
  before  EU-W, row md5 15cd752fb11155dcaf7181a2c279772b: data/reference/s46/run_fullyear_*.parquet
          (S46, code 23c4836), net position from data/session42/eu_atlas_fullyear_b3*.parquet
          (the same row, the same clearing: DE net import equal in every hour, asserted)
  de_only EU-X, row md5 f0bdd5977dd6974dc11e82658c4b7a84: the German fleet repaired, the rest of
          Europe as before: data/reference/s48/atlas_run_*.parquet (S48 Part A), net position from
          data/session47/eu_atlas_fullyear_b3*.parquet (the same clearing, asserted)
  after   EU-Y, row md5 8770315fddfbbd59c16f7eedaaebb408: EU-X plus 24 other zones' fleets repaired
          the same way: data/reference/s48/arm_b3/atlas_run_*.parquet (S48), net position from
          data/session48/eu_atlas_fullyear_b3*.parquet
and the published record: ENTSO-E A75 generation per production type, DE_LU, 2025
(data/cache/api/entsoe_gen_full_DE_LU_2025.parquet; written to de_generation_a75_hourly.csv, apart
from the model rows) and ENTSO-E 12.1.G physical flows on the
model's German borders (scripts/analysis/trade_position.py, the trade limb's own real side).

Writes data/essay/series/*.csv and SHA256SUMS. The CSVs name no part of the model: a class is a
fuel family, a setter is a family or 'border' (the price was set outside Germany).

    .venv/bin/python scripts/essay/export_series.py <repo-with-data>
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parents[2] / 'data' / 'essay' / 'series'
EU_W, EU_X, EU_Y = ('15cd752fb11155dcaf7181a2c279772b', 'f0bdd5977dd6974dc11e82658c4b7a84',
                    '8770315fddfbbd59c16f7eedaaebb408')
FAMS = ['lignite', 'hard_coal', 'gas', 'oil', 'psp', 'hydro', 'biomass', 'waste', 'solar',
        'wind_onshore', 'wind_offshore']
A75_FAM = {'Fossil Brown coal/Lignite': 'lignite', 'Fossil Hard coal': 'hard_coal',
           'Fossil Gas': 'gas', 'Fossil Oil': 'oil', 'Fossil Coal-derived gas': 'other',
           'Hydro Pumped Storage': 'psp', 'Hydro Run-of-river and poundage': 'hydro',
           'Hydro Water Reservoir': 'hydro', 'Biomass': 'biomass', 'Waste': 'waste',
           'Solar': 'solar', 'Wind Onshore': 'wind_onshore', 'Wind Offshore': 'wind_offshore',
           'Geothermal': 'other', 'Other': 'other', 'Other renewable': 'other'}
VRE = {'__VRE_solar': 'solar', '__VRE_onshore': 'wind_onshore', '__VRE_offshore': 'wind_offshore'}
SETTER_BY_TYPE = {'solar': 'solar', 'onshore': 'wind', 'offshore': 'wind', 'hydro': 'hydro',
                  'gas': 'gas', 'oil': 'oil', 'biomass': 'biomass', 'waste': 'waste'}


def fleet_family(audit_class):
    c = audit_class
    if c.startswith('gas_'):
        return 'gas'
    if c == 'hydro_pumped_storage':
        return 'psp'
    if c.startswith('hydro_'):
        return 'hydro'
    return {'wind': 'wind_onshore', 'offshore': 'wind_offshore'}.get(c, c)


def base_name(n, names):
    n = str(n).strip()
    return n if n in names else n.split('__')[0].strip()


def utc(s):
    s = pd.to_datetime(s)
    return s.dt.tz_localize('UTC') if s.dt.tz is None else s.dt.tz_convert('UTC')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main(repo):
    repo = Path(repo)
    s46, s48 = repo / 'data/reference/s46', repo / 'data/reference/s48/arm_b3'
    s48x = repo / 'data/reference/s48'
    assert json.loads((s46 / 'run_fullyear.json').read_text())['world_md5'] == EU_W
    assert json.loads((s48x / 'atlas_run.json').read_text())['world_md5'] == EU_X
    assert json.loads((s48 / 'atlas_run.json').read_text())['world_md5'] == EU_Y

    # ---------------------------------------------------- before (EU-W): blocks -> family
    fl = pd.read_parquet(s46 / 'model_fleet_de.parquet')
    fl['fam'] = fl.audit_class.map(fleet_family)
    names = set(fl['name'])
    share = (fl.groupby(['name', 'fam']).capacity_mw.sum()
             .groupby(level=0).transform(lambda s: s / s.sum()))
    b = pd.read_parquet(s46 / 'run_fullyear_de_blocks.parquet')
    b['base'] = [VRE.get(x) and x or base_name(x, names) for x in b.block]
    b['ts'] = utc(b.ts_utc)
    # a name carried by plants of two families is split across them by capacity
    sh = share.rename('s').reset_index().rename(columns={'name': 'base'})
    sh = pd.concat([sh, pd.DataFrame({'base': list(VRE), 'fam': list(VRE.values()), 's': 1.0})])
    bb = b.groupby(['ts', 'base'], as_index=False).mw.sum().merge(sh, on='base', how='left')
    assert bb.fam.notna().all(), sorted(set(bb.base[bb.fam.isna()]))
    bb['mw'] = bb.mw * bb.s
    gw = bb.pivot_table(index='ts', columns='fam', values='mw', aggfunc='sum').fillna(0.0)

    zw = pd.read_parquet(s46 / 'run_fullyear_zone_hours.parquet')
    zw = zw[zw.zone == 'DE'].copy()
    zw['ts'] = utc(zw.ts_utc)
    zw = zw.set_index('ts').sort_index()

    # ---------------------------------------------------- de_only (EU-X), after (EU-Y)
    def atlas(d):
        zf = pd.read_parquet(d / 'atlas_run_zone_family.parquet')
        zf = zf[zf.zone == 'DE'].copy()
        zf['fam'] = zf.fam.map(lambda f: 'gas' if f.startswith('gas_') else 'psp' if
                               f == 'hydro_psp' else 'hydro' if f.startswith('hydro_') else f)
        zf['ts'] = utc(zf.ts_utc)
        g = zf.pivot_table(index='ts', columns='fam', values='mw', aggfunc='sum').fillna(0.0)
        z = pd.read_parquet(d / 'atlas_run_zone_hours.parquet')
        z = z[z.zone == 'DE'].copy()
        z['ts'] = utc(z.ts_utc)
        return g, z.set_index('ts').sort_index()
    gx, zx = atlas(s48x)
    gy, zy = atlas(s48)
    assert zw.index.equals(zy.index) and zw.index.equals(zx.index), 'the re-clears differ in hours'
    hours = zw.index
    assert len(hours) == 8679

    # ---------------------------------------------------- the published record (A75)
    a75 = pd.read_parquet(repo / 'data/cache/api/entsoe_gen_full_DE_LU_2025.parquet')
    a75.index = a75.index.tz_convert('UTC')
    a75 = a75.T.groupby(a75.columns.map(A75_FAM)).sum().T.reindex(hours)

    OUT.mkdir(parents=True, exist_ok=True)
    gen = []
    for label, g in (('model_before', gw), ('model_de_only', gx), ('model_after', gy),
                     ('actual_a75', a75)):
        g = g.reindex(hours)
        for f in FAMS:
            if f not in g:
                g[f] = 0.0 if label != 'actual_a75' else np.nan
        gen.append(g[FAMS].assign(series=label))
    gen = pd.concat(gen).rename_axis('ts_utc').reset_index()
    gen = gen[['ts_utc', 'series'] + FAMS]
    # the A75 rows in a file of their own: ENTSO-E's generation data (16.1.B&C) is not on its list
    # of data free for re-use, so a release ships the model rows and the reader fetches these
    # (fetch_a75.py writes the same file from the API; ES1 amendment 1, licence audit)
    act = gen.series == 'actual_a75'
    gen[~act].to_csv(OUT / 'de_generation_by_family_hourly.csv', index=False, float_format='%.3f')
    gen[act].to_csv(OUT / 'de_generation_a75_hourly.csv', index=False, float_format='%.3f')

    # ---------------------------------------------------- who set Germany's price
    tf = pd.read_parquet(s48 / 'atlas_thermal_fleet_eu_x.parquet')
    tf = tf[tf.zone == 'DE']
    fam_y = dict(zip(tf['name'].str.strip(), tf.fam))
    fam_w = fl.groupby('name').fam.agg(lambda s: s.iloc[0]).to_dict()

    def setter(z, fam_of):
        out = []
        for n, t in zip(z.marg_name, z.marg_type):
            if n is None or (isinstance(n, float) and np.isnan(n)):
                out.append('border')
                continue
            nb = base_name(n, set(fam_of))
            f = fam_of.get(nb)
            if t == 'coal':
                f = f if f in ('lignite', 'hard_coal') else 'hard_coal_unlisted'
            elif f not in ('gas', 'oil'):
                f = SETTER_BY_TYPE.get(t, t)
            out.append('hydro' if f == 'psp' else f)
        return out
    st = pd.DataFrame({'ts_utc': hours, 'setter_before': setter(zw, fam_w),
                       'setter_de_only': setter(zx, fam_y), 'setter_after': setter(zy, fam_y)})
    for c in ('setter_before', 'setter_de_only', 'setter_after'):
        assert 'hard_coal_unlisted' not in set(st[c]), c
    st.to_csv(OUT / 'de_price_setter_hourly.csv', index=False)

    # ---------------------------------------------------- net position
    sys.path.insert(0, str(repo / 'scripts' / 'analysis'))
    import trade_position as TP
    nets = {}
    for label, path, z in (('before', repo / 'data/session42/eu_atlas_fullyear_b3.parquet', zw),
                           ('de_only', repo / 'data/session47/eu_atlas_fullyear_b3.parquet', zx),
                           ('after', repo / 'data/session48/eu_atlas_fullyear_b3.parquet', zy)):
        ts, rows_ = TP.eu_frames(path)
        r = rows_['DE']
        tsu = pd.DatetimeIndex(ts).tz_localize('UTC') if ts.tz is None else ts
        assert tsu.equals(hours)
        a = pd.read_parquet(path)
        a = a[a.zone == 'DE'].set_index('ts_utc').net_import_mw
        assert np.allclose(a.reindex(ts).values, z.net_import_mw.values)   # the same clearing
        nets[f'model_{label}'] = r['flow']['model']
        nets[f'real_{label}'] = r['flow']['real']
        nets['borders'] = r['flow']['measurable']
    assert np.array_equal(nets['real_before'], nets['real_after'], equal_nan=True)
    assert np.array_equal(nets['real_before'], nets['real_de_only'], equal_nan=True)
    net = pd.DataFrame({'ts_utc': hours, 'model_before_mw': nets['model_before'],
                        'model_de_only_mw': nets['model_de_only'],
                        'model_after_mw': nets['model_after'],
                        'actual_physical_mw': nets['real_before']})
    net.to_csv(OUT / 'de_net_export_hourly.csv', index=False, float_format='%.3f')

    # ---------------------------------------------------- before: per inventory row
    inv = pd.read_csv(Path(__file__).resolve().parents[2] / 'data/essay/inputs/inventory_de.csv')
    mm = pd.read_parquet(repo / 'data/reference/s47/xw_model.parquet').reset_index(drop=True)
    assert len(inv) == len(mm)
    cap = fl.groupby('name').capacity_mw.sum()
    b['base0'] = b.block.str.split('__').str[0]          # S47 part A's rule, unchanged
    twh = b.groupby('base0').mw.sum() / 1e6
    marg = zw.marg_name.dropna().str.split('__').str[0].value_counts()
    per = pd.DataFrame({'row': inv.row, 'name': mm['name'],
                        'share_of_name': mm.model_mw.values / cap.reindex(mm['name']).values})
    per['twh_before'] = [float(twh.get(n, 0.0)) * s for n, s in zip(per['name'], per.share_of_name)]
    per['price_setting_hours_before'] = [float(marg.get(n, 0)) * s
                                         for n, s in zip(per['name'], per.share_of_name)]
    per.to_csv(OUT / 'inventory_generation_before.csv', index=False, float_format='%.6f')

    sums = {p.name: sha(p) for p in sorted(OUT.glob('*.csv'))}
    (OUT / 'SHA256SUMS').write_text(''.join(f'{v}  {k}\n' for k, v in sums.items()))
    meta = {'before': {'row_md5': EU_W, 'world': 'EU-W'},
            'de_only': {'row_md5': EU_X, 'world': 'EU-X',
                        'what': 'the German fleet repaired; every other zone as before'},
            'after': {'row_md5': EU_Y, 'world': 'EU-Y',
                      'what': 'EU-X plus 24 other zones repaired the same way'},
            'hours': len(hours), 'first_hour_utc': str(hours[0]), 'last_hour_utc': str(hours[-1]),
            'net_position_borders': nets['borders'], 'files': sums}
    (OUT / 'series_meta.json').write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta, indent=1))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '.')
