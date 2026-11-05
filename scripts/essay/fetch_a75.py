"""Fetch ENTSO-E 16.1.B&C (A75), actual generation per production type, DE_LU, 2025, and write
series/de_generation_a75_hourly.csv: the hourly MW by fuel family on the essay's 8,679 hours.

ENTSO-E's terms put this data item outside its list of data free for re-use (CC BY 4.0), so the
release does not ship it: you fetch it. This step needs YOUR OWN ENTSO-E Transparency Platform
token (free; register at https://transparency.entsoe.eu and request API access), read from the
environment variable ENTSOE_API_KEY. The kit contains no token, and this script never prints it.
It also needs the `entsoe-py` package.

The hours are read from series/de_price_setter_hourly.csv (the model's hours). The file you get
should have the sha256 in series/SHA256SUMS. ENTSO-E revises published data from time to time, so a
later fetch can differ; model_section.py then refuses to run, and the difference is a revision of
the published record, not of the essay's arithmetic.

    ENTSOE_API_KEY=... python3 scripts/essay/fetch_a75.py <series_dir>
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

FAMS = ['lignite', 'hard_coal', 'gas', 'oil', 'psp', 'hydro', 'biomass', 'waste', 'solar',
        'wind_onshore', 'wind_offshore']
A75_FAM = {'Fossil Brown coal/Lignite': 'lignite', 'Fossil Hard coal': 'hard_coal',
           'Fossil Gas': 'gas', 'Fossil Oil': 'oil', 'Fossil Coal-derived gas': 'other',
           'Hydro Pumped Storage': 'psp', 'Hydro Run-of-river and poundage': 'hydro',
           'Hydro Water Reservoir': 'hydro', 'Biomass': 'biomass', 'Waste': 'waste',
           'Solar': 'solar', 'Wind Onshore': 'wind_onshore', 'Wind Offshore': 'wind_offshore',
           'Geothermal': 'other', 'Other': 'other', 'Other renewable': 'other'}
TZ = 'Europe/Berlin'


def main(series):
    from entsoe import EntsoePandasClient
    series = Path(series)
    key = os.environ.get('ENTSOE_API_KEY')
    if not key:
        raise SystemExit('set ENTSOE_API_KEY to your own ENTSO-E token')
    c = EntsoePandasClient(api_key=key, retry_count=3, retry_delay=10, timeout=120)
    gen = c.query_generation('DE_LU', start=pd.Timestamp('2025-01-01', tz=TZ),
                             end=pd.Timestamp('2026-01-01', tz=TZ), psr_type=None)
    # generation only: drop the 'Actual Consumption' columns of storage
    if isinstance(gen.columns, pd.MultiIndex):
        gen = gen.loc[:, [col for col in gen.columns if col[1] == 'Actual Aggregated']]
        gen.columns = [col[0] for col in gen.columns]
    gen = gen.resample('1h').mean()
    gen.index = gen.index.tz_convert('UTC')
    hours = pd.DatetimeIndex(pd.read_csv(series / 'de_price_setter_hourly.csv').ts_utc)
    fam = gen.T.groupby(gen.columns.map(A75_FAM)).sum().T.reindex(hours)
    for f in FAMS:
        if f not in fam:
            fam[f] = np.nan
    out = fam[FAMS].assign(series='actual_a75').rename_axis('ts_utc').reset_index()
    out = out[['ts_utc', 'series'] + FAMS]
    out.to_csv(series / 'de_generation_a75_hourly.csv', index=False, float_format='%.3f')
    print('wrote', series / 'de_generation_a75_hourly.csv', len(out), 'hours')


if __name__ == '__main__':
    main(sys.argv[1])
