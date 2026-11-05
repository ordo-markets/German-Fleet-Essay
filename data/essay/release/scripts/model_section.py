"""Every number in the essay's model section, recomputed from the published series only.

This script does not need the model. It reads:
  series/de_generation_by_family_hourly.csv   Germany's hourly generation by fuel family (MW):
                                              the model before the fleet repair, with Germany's
                                              repaired (de_only), with every zone's repaired
                                              (after)
  series/de_generation_a75_hourly.csv         the same columns for the ENTSO-E A75 actual, on the
                                              same hours (a release does not ship it: fetch_a75.py
                                              writes it from the reader's own API token)
  series/de_price_setter_hourly.csv           which family set Germany's price each hour, before
                                              and after ('border' = it was set outside Germany)
  series/de_net_export_hourly.csv             Germany's net export (MW, + = export) on its
                                              borders with AT BE CH CZ DK FR NL NO PL SE: model
                                              before/after, and ENTSO-E physical flows
  series/inventory_generation_before.csv      'before' generation and price-setting hours per
                                              inventory row
  <fleet table out>/plants.csv                fleet_table.py's classes per inventory row
All files are checked against series/SHA256SUMS. Hours: the 8,679 UTC hours of 2025 both runs
cleared (81 of 8,760 are missing on both sides and on the actual side too).

    python3 -I scripts/essay/model_section.py <series_dir> <fleet_table_out_dir> [<out.json>]
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

NOT_MARKET = ['out_2025', 'closed_pre_2025', 'duplicate']


def check(series):
    for line in (series / 'SHA256SUMS').read_text().splitlines():
        want, name = line.split()
        if not (series / name).exists():
            raise SystemExit(f'{name} is missing' + (': fetch it with fetch_a75.py (README)'
                                                     if 'a75' in name else ''))
        got = hashlib.sha256((series / name).read_bytes()).hexdigest()
        if got != want:
            raise SystemExit(f'{name}: sha256 differs from SHA256SUMS')


def main(series, fleet, out=None):
    series, fleet = Path(series), Path(fleet)
    check(series)
    gen = pd.concat([pd.read_csv(series / f, parse_dates=['ts_utc'])
                     for f in ('de_generation_by_family_hourly.csv', 'de_generation_a75_hourly.csv')],
                    ignore_index=True)
    st = pd.read_csv(series / 'de_price_setter_hourly.csv')
    net = pd.read_csv(series / 'de_net_export_hourly.csv', parse_dates=['ts_utc'])
    per = pd.read_csv(series / 'inventory_generation_before.csv')
    pl = pd.read_csv(fleet / 'plants.csv')
    assert (per.row.values == pl.row.values).all()
    hours = len(st)
    r = {'hours': hours}

    # 1. what the capacity that was not in the 2025 market generated in the 'before' run
    w = pl[NOT_MARKET].sum(axis=1) / pl.mw
    r['inventory_twh_before'] = round(float(per.twh_before.sum()), 2)
    r['not_in_market_mw'] = round(float(pl[NOT_MARKET].sum().sum()), 1)
    r['not_in_market_twh_before'] = round(float((per.twh_before * w).sum()), 2)
    r['not_in_market_share_of_inventory_twh'] = round(r['not_in_market_twh_before'] /
                                                      r['inventory_twh_before'], 3)
    dom = int((st.setter_before != 'border').sum())
    r['domestic_price_setting_hours_before'] = dom
    r['not_in_market_price_setting_hours_before'] = round(float((per.price_setting_hours_before * w)
                                                                .sum()), 1)
    r['not_in_market_by_class_twh_before'] = {
        c: round(float((per.twh_before * pl[c] / pl.mw).sum()), 2) for c in NOT_MARKET}

    # 2. lignite and hard coal: model energy over A75 energy, on the same hours
    tot = gen.groupby('series')[['lignite', 'hard_coal', 'gas']].sum() / 1e6
    r['twh'] = tot.round(3).to_dict(orient='index')
    r['ratio_to_a75'] = {s: {f: round(float(tot.at[s, f] / tot.at['actual_a75', f]), 3)
                             for f in ('lignite', 'hard_coal', 'gas')}
                         for s in ('model_before', 'model_de_only', 'model_after')}

    # 3. Germany's net position: mean MW over the hours both sides have, x 8,760 h, in TWh
    cols = ['model_before_mw', 'model_de_only_mw', 'model_after_mw', 'actual_physical_mw']
    ok = net[cols].notna().all(axis=1)
    r['net_position_hours'] = int(ok.sum())
    r['net_position_twh_per_year'] = {
        c.replace('_mw', ''): round(float(net.loc[ok, c].mean()) * 8760 / 1e6, 2)
        for c in cols}

    # 4. hours in which each family set Germany's price
    r['price_setter_hours'] = {
        s: {k: int(v) for k, v in st[f'setter_{s}'].value_counts().items()}
        for s in ('before', 'de_only', 'after')}
    if out:
        Path(out).write_text(json.dumps(r, indent=1))
    print(json.dumps(r, indent=1))
    return r


if __name__ == '__main__':
    main(*sys.argv[1:4])
