"""Optional: fetch ENTSO-E 16.1.A (A73), actual generation per generation unit, 2025, for the four
German control areas, one parquet per area and day: <out>/<AREA>/<YYYY-MM-DD>.parquet.

This step needs YOUR OWN ENTSO-E Transparency Platform token (free; register at
https://transparency.entsoe.eu and request API access), read from the environment variable
ENTSOE_API_KEY. The kit contains no token, and this script never prints the token.
It also needs the `entsoe-py` package (this kit's files were fetched with entsoe-py 0.6.x;
columns are written as 'name|production type|kind|EIC').

If you skip this step, `inputs/a73_units_de_2025.csv` (shipped, sha256 in MANIFEST.json) is the
same table this kit derived from the files it fetched; `a73_units.py` re-derives it.

    ENTSOE_API_KEY=... python3 scripts/essay/fetch_a73.py <out_dir>
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pandas as pd

AREAS = ('DE_TENNET', 'DE_50HZ', 'DE_AMPRION', 'DE_TRANSNET')   # DE_LU returns nothing for A73
TZ = 'Europe/Brussels'


def main(out):
    from entsoe import EntsoePandasClient
    from entsoe.exceptions import NoMatchingDataError
    key = os.environ.get('ENTSOE_API_KEY')
    if not key:
        raise SystemExit('set ENTSOE_API_KEY to your own ENTSO-E token')
    c = EntsoePandasClient(api_key=key, retry_count=3, retry_delay=10, timeout=120)
    for day in pd.date_range('2025-01-01', '2025-12-31', freq='D'):
        for area in AREAS:
            d = Path(out) / area
            d.mkdir(parents=True, exist_ok=True)
            p = d / f'{day:%Y-%m-%d}.parquet'
            if p.exists() or p.with_suffix('.empty').exists():
                continue
            s = pd.Timestamp(day, tz=TZ)
            try:
                df = c.query_generation_per_plant(area, start=s, end=s + pd.Timedelta(days=1),
                                                  include_eic=True)
            except NoMatchingDataError:
                p.with_suffix('.empty').write_text('NoMatchingDataError\n')
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = ['|'.join(str(x) for x in col) for col in df.columns]
            df.to_parquet(p)
            time.sleep(0.2)
        print(day.date(), flush=True)


if __name__ == '__main__':
    main(sys.argv[1])
