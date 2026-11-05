"""Repo side: data/essay/release/, the folder that may be published beside the essay (ES1
amendment 1). It holds only what data/essay/LICENCES.json clears for redistribution:

  dataset/          shape (a), the derived table: derived_dataset.py on a kit run
  snapshot/inputs/  shape (b), the inputs that may be redistributed: the inventory (ids; WRI MW),
                    the two MaStR extracts (dl-de/by-2-0)
  snapshot/raw/     the WRI zip (CC BY 4.0) and the Netzreserve list PDF (CC BY-ND 4.0), unmodified
  snapshot/series/  the model series and Germany's net position from ENTSO-E 12.1.G flows
                    (CC BY 4.0); NOT the A75 actual, which the reader fetches (fetch_a75.py)
  scripts/          the kit, as run
  expected/         the outputs a reader's run must give: shipped where they carry nothing that is
                    not cleared, and the sha256 of every output in expected/SHA256SUMS
  MANIFEST.json     every input: shipped or fetched, its sha256, where from, its licence verdict
  LICENCES.json     the audit;  REPORT.md  the report (docs/essays/ES1_DATASET_REPORT_*.md)
  SHA256SUMS        every file in the folder
README.md is written by hand and is not overwritten. The run directory must hold a full kit run
(fleet_table.py, fleet_details.py into out/, model_section.py into out/model_section.json,
plots.py into fig/) on the full inputs (inputs/).

    .venv/bin/python scripts/essay/make_release.py <run_dir> <report.md>
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KIT, DATA = ROOT / 'scripts' / 'essay', ROOT / 'data' / 'essay'
REL = DATA / 'release'
SCRIPTS = ('fleet_table.py', 'fleet_details.py', 'derived_dataset.py', 'model_section.py',
           'plots.py', 'fetch_a73.py', 'a73_units.py', 'fetch_a75.py', 'extract_mastr.py',
           'rules.json')
SHIPPED_INPUTS = ('inventory_de.csv', 'mastr_units_de.csv', 'mastr_units_de_nonbattery.csv.gz')
RAW = {'globalpowerplantdatabasev130.zip': ROOT / 'data/raw/globalpowerplantdatabasev130.zip',
       'Verfahrensliste_inlaendische_Netzreserve_2025-03-10.pdf':
           DATA / 'raw' / 'Verfahrensliste_inlaendische_Netzreserve_2025-03-10.pdf'}
SERIES = ('de_generation_by_family_hourly.csv', 'de_price_setter_hourly.csv',
          'de_net_export_hourly.csv', 'inventory_generation_before.csv', 'series_meta.json',
          'SHA256SUMS')
# outputs that carry a field not cleared for redistribution: hashed in expected/SHA256SUMS only
NOT_SHIPPED = {'plants.csv', 'units.csv', 'a73_match.csv', 'summary.json',
               'details/duplicate_rows_side_by_side.csv', 'details/duplicate_sites.csv',
               'details/duplicates.json', 'details/hard_coal.json', 'details/hard_coal_bridge.csv',
               'details/kwl_compare.json', 'details/kwl_totals.csv', 'details/unresolved.json',
               'details/unresolved_rows.csv'}
FETCH = {
    'global_power_plant_database.csv': 'unzip snapshot/raw/globalpowerplantdatabasev130.zip',
    'conventional_power_plants_DE.csv':
        'download https://data.open-power-system-data.org/conventional_power_plants/2020-10-01/'
        'conventional_power_plants_DE.csv (OPSD states no licence for its data: not shipped)',
    'Kraftwerksliste_2026-06-26.xlsx':
        'download https://www.bundesnetzagentur.de/DE/Fachthemen/ElektrizitaetundGas/'
        'Versorgungssicherheit/Erzeugungskapazitaeten/Kraftwerksliste/_DL/Kraftwerksliste.xlsx and '
        'rename (licence not established: not shipped; the URL serves the latest edition only)',
    'a73_units_de_2025.csv':
        'fetch_a73.py then a73_units.py with your own ENTSO-E token (16.1.A is not on ENTSO-E\'s '
        'free re-use list: not shipped)',
    'inventory_de.csv': 'shipped (snapshot/inputs)',
    'mastr_units_de.csv': 'shipped (snapshot/inputs)'}


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def put(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)


def main(run, report):
    run, report = Path(run), Path(report)
    for sub in ('dataset', 'snapshot', 'scripts', 'expected'):
        shutil.rmtree(REL / sub, ignore_errors=True)
    sys.path.insert(0, str(KIT))
    import derived_dataset
    derived_dataset.main(run / 'inputs', run / 'out', REL / 'dataset')
    for f in SHIPPED_INPUTS:
        put(DATA / 'inputs' / f, REL / 'snapshot' / 'inputs' / f)
    for f, src in RAW.items():
        put(src, REL / 'snapshot' / 'raw' / f)
    for f in SERIES:
        put(DATA / 'series' / f, REL / 'snapshot' / 'series' / f)
    for f in SCRIPTS:
        put(KIT / f, REL / 'scripts' / f)

    # keyed by the path under the reader's work/ directory: out/ (the kit's outputs), fig/ (the
    # figures' data tables); shipped files sit at the same paths under expected/
    outs = sorted(p.relative_to(run / 'out').as_posix() for p in (run / 'out').rglob('*')
                  if p.is_file())
    exp = REL / 'expected'
    sums = {}
    for f in outs:
        sums[f'out/{f}'] = sha256(run / 'out' / f)
        if f not in NOT_SHIPPED:
            put(run / 'out' / f, exp / 'out' / f)
    for p in sorted((run / 'fig').glob('*.csv')):
        sums[f'fig/{p.name}'] = sha256(p)
        put(p, exp / 'fig' / p.name)
    (exp / 'SHA256SUMS').write_text(''.join(f'{v}  {k}\n' for k, v in sums.items()))

    lic = json.loads((DATA / 'LICENCES.json').read_text())['inputs']
    man = json.loads((DATA / 'MANIFEST.json').read_text())
    files = {f: dict(man['files'][f], how=FETCH[f]) for f in man['files']}
    a75 = [ln.split() for ln in (DATA / 'series' / 'SHA256SUMS').read_text().splitlines()]
    files['de_generation_a75_hourly.csv (series)'] = {
        'sha256': dict((n, h) for h, n in a75)['de_generation_a75_hourly.csv'],
        'how': 'fetch_a75.py with your own ENTSO-E token (16.1.B&C is not on ENTSO-E\'s free '
               're-use list: not shipped)'}
    rel_man = {'what': 'every input of the essay\'s kit: shipped here, or fetched by the reader, by '
                       'sha256; licence verdicts from LICENCES.json (retrieved ' +
                       json.loads((DATA / 'LICENCES.json').read_text())['retrieved'] + ')',
               'files': files,
               'raw': man['raw'],
               'licence_verdicts': {k: v.get('verdict') for k, v in lic.items()}}
    (REL / 'MANIFEST.json').write_text(json.dumps(rel_man, indent=1, ensure_ascii=False) + '\n')
    put(DATA / 'LICENCES.json', REL / 'LICENCES.json')
    put(report, REL / 'REPORT.md')

    every = [f for f in sorted(p.relative_to(REL).as_posix() for p in REL.rglob('*')
                               if p.is_file()) if f != 'SHA256SUMS']
    (REL / 'SHA256SUMS').write_text(''.join(f'{sha256(REL / f)}  {f}\n' for f in every))
    print(f'{len(every)} files -> {REL}')


if __name__ == '__main__':
    main(*sys.argv[1:3])
