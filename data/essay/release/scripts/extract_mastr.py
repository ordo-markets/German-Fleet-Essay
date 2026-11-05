"""Step 1 of the fleet table: the German unit register (MaStR) at 10 MW and above.

Reads the Marktstammdatenregister Gesamtdatenexport zip (the public bulk export of the
Bundesnetzagentur, https://www.marktstammdatenregister.de/MaStR/Datendownload; this kit used the
export of 2026-06-06) and writes one CSV row per combustion, hydro, biomass, nuclear and storage
unit with net capacity >= 10 MW. Catalogue codes are decoded with the zip's own Katalogwerte.xml.

Standard library and pandas only. Nothing else is read.

    python3 -I scripts/essay/extract_mastr.py <Gesamtdatenexport.zip> <out.csv> [min_net_mw]

The optional third argument lowers the floor (0 = every unit); the fleet table uses 10 MW, the
itemisation of the unresolved capacity (fleet_details.py) reads the units below it.
"""
from __future__ import annotations

import hashlib
import io
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pandas as pd

MIN_NET_MW = 10.0
UNIT_FILES = {'EinheitenVerbrennung.xml': 'combustion', 'EinheitenWasser.xml': 'hydro',
              'EinheitenBiomasse.xml': 'biomass', 'EinheitenKernkraft.xml': 'nuclear'}
STORAGE_PREFIX = 'EinheitenStromSpeicher_'   # the storage export is split across many files
TAGS = {'EinheitenVerbrennung': 'EinheitVerbrennung', 'EinheitenWasser': 'EinheitWasser',
        'EinheitenBiomasse': 'EinheitBiomasse', 'EinheitenKernkraft': 'EinheitKernkraft',
        'EinheitenStromSpeicher': 'EinheitStromSpeicher'}
KEEP = ('EinheitMastrNummer', 'NameKraftwerk', 'NameKraftwerksblock', 'NameStromerzeugungseinheit',
        'Kraftwerksnummer', 'Weic', 'Energietraeger', 'Technologie', 'Inbetriebnahmedatum',
        'DatumEndgueltigeStilllegung', 'DatumBeginnVoruebergehendeStilllegung',
        'DatumWiederaufnahmeBetrieb', 'EinheitBetriebsstatus', 'SicherheitsbereitschaftAbDatum',
        'NetzreserveAbDatum', 'Laengengrad', 'Breitengrad', 'Ort')
CODED = ('Energietraeger', 'Technologie', 'EinheitBetriebsstatus')


def _iter(zf, name, tag):
    with zf.open(name) as raw:
        text = io.TextIOWrapper(raw, encoding='utf-16')
        for _, el in ET.iterparse(text, events=('end',)):
            if el.tag == tag:
                yield {c.tag: c.text for c in el}
                el.clear()


def main(zip_path, out_csv, min_net_mw=MIN_NET_MW):
    zip_path, out_csv, min_net_mw = Path(zip_path), Path(out_csv), float(min_net_mw)
    h = hashlib.sha256()
    with open(zip_path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 24), b''):
            h.update(chunk)
    print('zip sha256', h.hexdigest(), flush=True)
    rows = []
    with zipfile.ZipFile(zip_path) as zf:
        cat = {r.get('Id'): r.get('Wert') for r in _iter(zf, 'Katalogwerte.xml', 'Katalogwert')}
        files = dict(UNIT_FILES)
        files.update({n: 'storage' for n in sorted(zf.namelist()) if n.startswith(STORAGE_PREFIX)})
        for fname, kind in files.items():
            tag = TAGS[fname.split('.')[0].split('_')[0]]
            for r in _iter(zf, fname, tag):
                try:
                    net = float(r.get('Nettonennleistung') or 0) / 1000.0   # kW -> MW
                except ValueError:
                    net = 0.0
                if net < min_net_mw:
                    continue
                d = {k: r.get(k) for k in KEEP}
                d['net_mw'] = net
                for k in CODED:
                    if d.get(k) is not None:
                        d[k + '_txt'] = cat.get(d[k], d[k])
                d['file'] = kind
                rows.append(d)
            print(fname, len(rows), flush=True)
    df = pd.DataFrame(rows)
    df = df.drop(columns=[c for c in CODED if c in df.columns])
    # rows stay in the export's own order: the position-and-capacity rule picks the first of two
    # equally near units (fleet_table.py), so the order is part of the result (5 rows, 11.5 MW)
    df = df.reset_index(drop=True)
    df.to_csv(out_csv, index=False)
    print('units', len(df), '->', out_csv)


if __name__ == '__main__':
    main(*sys.argv[1:4])
