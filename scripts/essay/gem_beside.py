"""Repo side, reported beside P2 and never counted (pre-registration): what the GEM Global Integrated
Power Tracker (release 2026-03) has within 2 km of each inventory row the registers left unresolved.

Reads fleet_details.py's unresolved_rows.csv, fleet_table.py's plants.csv and the GEM file; prints
MW by the status of the GEM units nearby ('operating' if any compatible GEM unit there operates).

    .venv/bin/python scripts/essay/gem_beside.py <fleet_table_out_dir> <gem_gipt_2026_03.parquet>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

FUEL = {'Gas': 'gas', 'Oil': 'oil', 'Coal': 'coal', 'Hydro': 'hydro', 'Biomass': 'biomass'}
COMPAT = {'gas': {'gas', 'oil'}, 'oil': {'oil', 'gas'}, 'hard_coal': {'coal'}, 'lignite': {'coal'},
          'hydro': {'hydro'}, 'psp': {'hydro'}}


def hav(a, b, c, d):
    a, b, c, d = map(np.radians, (a, b, c, d))
    return 6371 * 2 * np.arcsin(np.sqrt(np.sin((c - a) / 2) ** 2 +
                                        np.cos(a) * np.cos(c) * np.sin((d - b) / 2) ** 2))


def main(out, gem):
    out = Path(out)
    pl = pd.read_csv(out / 'plants.csv')
    g = pd.read_parquet(gem)
    g = g[(g.country == 'Germany') & g.gem_type.isin(['oil/gas', 'coal', 'bioenergy', 'hydropower'])]
    g = g.assign(f=g.primary_fuel.map(FUEL))
    r = pd.read_csv(out / 'details' / 'unresolved_rows.csv')
    u = r[r.tier == 'unresolved'].groupby(['row', 'name', 'fam']).mw.sum().reset_index()
    u = u.merge(pl[['row', 'lat', 'lon']], on='row', how='left')
    status = []
    for _, x in u.iterrows():
        c = g[g.f.isin(COMPAT.get(x.fam, set()))]
        c = c[hav(x.lat, x.lon, c.latitude.values.astype(float),
                  c.longitude.values.astype(float)) <= 2.0]
        status.append('no GEM unit within 2 km' if c.empty else
                      'operating' if (c.status == 'operating').any() else str(c.status.iloc[0]))
    u['gem_status_within_2km'] = status
    res = {'unresolved_mw': round(float(u.mw.sum()), 1),
           'by_gem_status_mw': u.groupby('gem_status_within_2km').mw.sum().round(1).to_dict()}
    print(json.dumps(res, indent=1))


if __name__ == '__main__':
    main(*sys.argv[1:3])
