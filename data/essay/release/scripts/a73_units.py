"""Step 2 of the fleet table: one row per A73 generation unit with its 2025 output.

Reads the per-area, per-day A73 files (`fetch_a73.py`'s output: <dir>/<AREA>/<day>.parquet) and
writes eic, name, production type, control areas, TWh in 2025, hours reported and max MW.

Each file is put on the UTC hour by the mean of the MW values inside the hour (= MWh in that
hour). A unit-hour with no value stays missing, never zero. A unit published by two control
areas in the same hour is counted once (the larger value). The year is the UTC hours
2024-12-31 23:00 .. 2025-12-31 22:00 (German local 2025).

    python3 -I scripts/essay/a73_units.py <a73_dir> <out.csv>
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

AREAS = ('DE_TENNET', 'DE_50HZ', 'DE_AMPRION', 'DE_TRANSNET')


def main(raw, out_csv):
    raw = Path(raw)
    parts, meta = [], {}
    for area in AREAS:
        for p in sorted((raw / area).glob('*.parquet')):
            df = pd.read_parquet(p)
            if df.empty:
                continue
            df.index = df.index.tz_convert('UTC')
            h = df.resample('1h').mean()
            for col in h.columns:
                name, psr, _kind, eic = col.split('|')
                meta.setdefault(eic, {'name': name, 'psr': psr, 'areas': set()})
                meta[eic]['areas'].add(area)
            h.columns = [c.split('|')[3] for c in h.columns]
            h = h.T.groupby(level=0).max().T          # one EIC twice in a file: the larger
            s = h.stack(future_stack=True).dropna()
            s.index.names = ['ts_utc', 'eic']
            parts.append(s.rename('mw').reset_index())
    long = pd.concat(parts, ignore_index=True)
    long = long.groupby(['ts_utc', 'eic'], as_index=False).mw.max()   # two areas: once
    long = long[(long.ts_utc >= '2024-12-31 23:00') & (long.ts_utc < '2025-12-31 23:00')]
    g = long.groupby('eic').mw
    u = pd.DataFrame({'twh': g.sum() / 1e6, 'hours_reported': g.size(), 'max_mw': g.max()})
    u['name'] = u.index.map(lambda e: meta[e]['name'])
    u['psr'] = u.index.map(lambda e: meta[e]['psr'])
    u['areas'] = u.index.map(lambda e: ','.join(sorted(meta[e]['areas'])))
    u = u.reset_index()[['eic', 'name', 'psr', 'areas', 'twh', 'hours_reported', 'max_mw']]
    u.sort_values('eic').to_csv(out_csv, index=False)
    print('A73 units', len(u), 'TWh', round(u.twh.sum(), 3), '->', out_csv)


if __name__ == '__main__':
    main(*sys.argv[1:3])
