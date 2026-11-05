"""Repo side: data/essay/MANIFEST.json, the hash of every file the essay rests on.

  files     the six fleet-table inputs by their fixed names (fleet_table.py --manifest reads this)
  raw       the public originals they come from: where to get them and the sha256 of the copy used
  kit       every script and rules.json in scripts/essay/
  shipped   every file under data/essay/ (inputs, series, expected outputs, figure tables),
            except release/ (make_release.py, which reads this manifest)

    .venv/bin/python scripts/essay/make_manifest.py <dir holding the six fleet-table inputs>
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KIT, DATA = ROOT / 'scripts' / 'essay', ROOT / 'data' / 'essay'
LICENCES = json.loads((DATA / 'LICENCES.json').read_text(encoding='utf-8'))


def LIC(key, item=None):
    """The audit's verdict for an input (data/essay/LICENCES.json, ES1 amendment 1)."""
    e = LICENCES['inputs'][key]
    v = e['items'][item]['verdict'] if item else e['verdict']
    return f'{v} (LICENCES.json: {key}, retrieved {LICENCES["retrieved"]})'


RAW = {
    'globalpowerplantdatabasev130.zip': {
        'publisher': 'World Resources Institute, Global Power Plant Database 1.3.0',
        'url': 'https://datasets.wri.org/datasets/global-power-plant-database',
        'sha256': '59f3e57312a85eec3c281608e5f3c8f993d8fdad5dde179430dca42f2ac6ce99',
        'gives': 'global_power_plant_database.csv (unzip)',
        'checked': '2026-10-31: the file served at the URL has this sha256',
        'licence': LIC('wri_gppd')},
    'conventional_power_plants_DE.csv': {
        'publisher': 'Open Power System Data, conventional power plants, version 2020-10-01',
        'url': 'https://data.open-power-system-data.org/conventional_power_plants/2020-10-01/'
               'conventional_power_plants_DE.csv',
        'sha256': '111067815dfe8e6452910423394a647079f9fd749285ad7f154349647665896f',
        'checked': '2026-10-31 and 2026-11-02: the file served at the URL has this sha256',
        'licence': LIC('opsd')},
    'Kraftwerksliste_2026-06-26.xlsx': {
        'publisher': 'Bundesnetzagentur, Kraftwerksliste, Datenstand 26.06.2026 (its stated '
                     'source is the Marktstammdatenregister)',
        'url': 'https://www.bundesnetzagentur.de/DE/Fachthemen/ElektrizitaetundGas/'
               'Versorgungssicherheit/Erzeugungskapazitaeten/Kraftwerksliste/_DL/Kraftwerksliste.xlsx',
        'sha256': 'ed796691504e72d89520972adb953a758449f22a92b9b87b1a85b86befc912ad',
        'checked': '2026-10-31 and 2026-11-02 (redirected to ?__blob=publicationFile&v=17): the '
                   'file served at the URL has this sha256; the URL serves the latest edition, so '
                   'a later download may differ',
        'licence': LIC('kraftwerksliste')},
    'Gesamtdatenexport_20260606.zip': {
        'publisher': 'Bundesnetzagentur, Marktstammdatenregister, Gesamtdatenexport of 2026-06-06',
        'url': 'https://www.marktstammdatenregister.de/MaStR/Datendownload',
        'sha256': '572fc54c0a1a77ce49061484794b142cbe934babb8c5cd1eb0365fea86a66d15',
        'bytes': 3019709491,
        'gives': 'mastr_units_de.csv (extract_mastr.py), shipped',
        'checked': 'not re-downloadable: the page serves the current export only; '
                   'inputs/mastr_units_de.csv is shipped so the table re-runs without it',
        'licence': LIC('mastr')},
    'Verfahrensliste_inlaendische_Netzreserve_2025-03-10.pdf': {
        'publisher': 'Bundesnetzagentur, Verfahrensliste inländische Netzreserve, 2025-03-10',
        'url': 'https://www.bundesnetzagentur.de/DE/Beschlusskammern/BK08/BK8_07_Kraftwerksth/'
               '71_Inlaend_Netzreserve/Downloads/Verfahrensliste%20inl%C3%A4ndische%20Netzreserve'
               '_10.03.2025.pdf?__blob=publicationFile&v=6',
        'sha256': '7367d428732b4bc4a389d64132db6902e95d491b893e3a5e74a36ab29c93bb90',
        'gives': 'transcribed by hand into scripts/essay/rules.json (verfahrensliste_2025_03_10)',
        'checked': '2026-11-02: the file served at the URL has this sha256',
        'licence': LIC('verfahrensliste_netzreserve')},
    'ENTSO-E A73 (16.1.A) 2025, DE_TENNET DE_50HZ DE_AMPRION DE_TRANSNET': {
        'publisher': 'ENTSO-E Transparency Platform, actual generation per generation unit',
        'url': 'https://transparency.entsoe.eu (API; needs the reader\'s own token)',
        'gives': 'a73_units_de_2025.csv (fetch_a73.py, then a73_units.py); shipped in the '
                 'repo-side kit, not in release/',
        'checked': 'raw day files are not hashed here (their bytes depend on the library that '
                   'writes them); the derived per-unit table is',
        'licence': LIC('entsoe', '16.1.A A73 generation per unit')},
    'ENTSO-E A68 (14.1.A) installed capacity per production type, DE_LU, 2025': {
        'publisher': 'ENTSO-E Transparency Platform',
        'url': 'https://transparency.entsoe.eu (Generation > Installed Capacity per Production '
               'Type, DE-LU, 2025)',
        'value_used': {'Fossil Hard coal': 15951.0},
        'checked': 'one published number, read off the platform; this kit does not fetch it',
        'licence': LIC('entsoe', '14.1.A A68 installed capacity per production type')},
    'ENTSO-E A75 (16.1.B&C) actual generation per production type, DE_LU, 2025': {
        'publisher': 'ENTSO-E Transparency Platform',
        'url': 'https://transparency.entsoe.eu (API; needs the reader\'s own token)',
        'gives': 'series/de_generation_a75_hourly.csv (export_series.py from the repo cache; '
                 'fetch_a75.py from the API gave the same bytes on 2026-11-02)',
        'licence': LIC('entsoe', '16.1.B&C A75 generation per production type')},
    'ENTSO-E 12.1.G physical flows, Germany and its ten neighbours, 2025': {
        'publisher': 'ENTSO-E Transparency Platform',
        'url': 'https://transparency.entsoe.eu (API; needs the reader\'s own token)',
        'gives': 'actual_physical_mw of series/de_net_export_hourly.csv, shipped',
        'licence': LIC('entsoe', '12.1.G physical flows')},
}


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 20), b''):
            h.update(c)
    return h.hexdigest()


def main(inputs):
    inputs = Path(inputs)
    names = ('inventory_de.csv', 'global_power_plant_database.csv',
             'conventional_power_plants_DE.csv', 'Kraftwerksliste_2026-06-26.xlsx',
             'mastr_units_de.csv', 'a73_units_de_2025.csv')
    files = {n: {'sha256': sha(inputs / n), 'bytes': (inputs / n).stat().st_size} for n in names}
    for n in ('inventory_de.csv', 'mastr_units_de.csv', 'a73_units_de_2025.csv'):
        assert files[n]['sha256'] == sha(DATA / 'inputs' / n), n
    man = {'what': 'every file the German fleet essay rests on, by sha256',
           'files': files, 'raw': RAW,
           'kit': {p.name: sha(p) for p in sorted(KIT.iterdir())
                   if p.suffix in ('.py', '.json')},
           'shipped': {str(p.relative_to(DATA)): sha(p) for p in sorted(DATA.rglob('*'))
                       if p.is_file() and p.name not in ('MANIFEST.json', '.gitignore')
                       and p.relative_to(DATA).parts[0] != 'release'}}
    (DATA / 'MANIFEST.json').write_text(json.dumps(man, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps(man['files'], indent=1))


if __name__ == '__main__':
    main(sys.argv[1])
