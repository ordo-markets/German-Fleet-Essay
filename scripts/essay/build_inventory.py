"""Repo side, run once: the inventory the essay classifies, as a list of public record ids.

The model's German thermal and hydro inventory on EU-W (518 plants, 84,248.4 MW; the rows S47's
partition classifies, `data/reference/s47/xw_model.parquet`) is written as one line per plant:
which public dataset the row is (WRI Global Power Plant Database 1.3.0, or OPSD
conventional_power_plants_DE 2020-10-01), its id there, which record under that id it is (0 for the
first in file order; OPSD carries two ids twice) and the fuel family the model gave it. Name and
position are NOT written: the kit reads them from the public file, and this script asserts that
they agree with the model's to the MW and to the metre, so the list loses nothing. The capacity is
written for WRI rows only (CC BY 4.0, a cross-check); OPSD states no licence for its data, so an
OPSD row carries its id and nothing of OPSD's (ES1 amendment 1, licence audit).

Not part of the kit (it reads model-side tables). Output: data/essay/inputs/inventory_de.csv.

    .venv/bin/python scripts/essay/build_inventory.py <repo-with-data>
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parents[2] / 'data' / 'essay' / 'inputs' / 'inventory_de.csv'


def model_family(c):
    if c.startswith('gas_'):
        return 'gas'
    if c == 'hydro_pumped_storage':
        return 'psp'
    if c.startswith('hydro_'):
        return 'hydro'
    return c


def main(repo):
    repo = Path(repo)
    mm = pd.read_parquet(repo / 'data/reference/s47/xw_model.parquet')
    fl = pd.read_parquet(repo / 'data/reference/s46/model_fleet_de.parquet').reset_index(drop=True)
    gp = pd.read_csv(repo / 'data/raw/global_power_plant_database.csv', low_memory=False)
    gp = gp[gp.country == 'DEU']
    op = pd.read_csv(repo / 'data/reference/s47/raw/opsd/conventional_power_plants_DE_2020-10-01.csv')
    rows = []
    mm = mm.reset_index(drop=True)
    assert mm.model_idx.is_monotonic_increasing   # the order S47 iterated in
    for _, r in mm.iterrows():
        p = fl.loc[r.model_idx]
        assert p['name'] == r['name']
        o = op[(op.id == p['name']) & (np.abs(op.capacity_net_bnetza - p.capacity_mw) < 1e-6)
               & np.isclose(op.lat, p.lat) & np.isclose(op.lon, p.lon)]
        g = gp[(gp.name == p['name']) & (np.abs(gp.capacity_mw - p.capacity_mw) < 1e-6)
               & np.isclose(gp.latitude, p.lat) & np.isclose(gp.longitude, p.lon)]
        assert len(o) + len(g) == 1, (p['name'], len(o), len(g))
        if len(o):
            src, sid, smw = 'opsd_2020', o.id.iloc[0], None
            occ = int((op.index[op.id == sid] < o.index[0]).sum())
        else:
            src, sid, smw = 'gppd_1_3_0', g.gppd_idnr.iloc[0], float(g.capacity_mw.iloc[0])
            occ = 0
        rows.append({'row': len(rows), 'source': src, 'source_id': sid, 'source_occurrence': occ,
                     'source_mw': smw, 'fam': model_family(p.audit_class)})
    t = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    t.to_csv(OUT, index=False)
    print(t.groupby('source').size())
    print(t.groupby('fam').size())
    print('rows', len(t), '->', OUT)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '.')
