# German power plants, counted once: a derived dataset and its reproduction kit

Our own work in this folder is licensed CC BY 4.0 (`LICENSE`, which also lists the attribution
lines every redistribution carries); the scripts are MIT (`scripts/LICENSE`). Each third-party input
keeps its publisher's licence (below). [Venue and author line: Paul decides.]

This folder goes with the essay *How to count a German power plant twice*. It holds two things:

1. **`dataset/`: the derived table.** For each of the 518 rows of a German thermal and hydro plant
   inventory (84.2 GW, built from the WRI Global Power Plant Database and OPSD's list of
   conventional plants), which register units it stands for, which of seven classes each part of it
   falls in for 2025 (in the day-ahead market; reserve or closed during 2025; closed before 2025;
   counted twice; status unknown; no register entry), and which matching rule decided it. Plus one
   row per register unit, the sites counted twice, the 7.0 GW the registers cannot classify, and the
   hard-coal bridge. `REPORT.md` explains how it was made and what each column is.
2. **`snapshot/` and `scripts/`: the kit.** The inputs whose licences allow redistribution, the
   scripts, and the hashes of the inputs you have to download yourself. Run it and you get the
   dataset and every number in the essay, byte for byte.

Nothing here contains, or needs, the model the essay describes. The essay's model section is
recomputed from the model's published hourly series for Germany (`snapshot/series/`); you can
check the arithmetic and set the series against ENTSO-E's own, but not re-run the model.

## Licences and attribution

Each input keeps its publisher's licence. `LICENCES.json` quotes each one from the publisher's own
page (retrieved 2026-11-02) and says what follows. In short:

| input | licence | in this folder |
|---|---|---|
| WRI Global Power Plant Database 1.3.0 | CC BY 4.0 | shipped, unmodified (`snapshot/raw/`) |
| Marktstammdatenregister (Bundesnetzagentur), export of 2026-06-06 | Datenlizenz Deutschland – Namensnennung – 2.0 | two extracts shipped (`snapshot/inputs/`): changed (rows and columns selected) |
| Verfahrensliste inländische Netzreserve, 10.03.2025 (Bundesnetzagentur) | CC BY-ND 4.0 (the site's rule for its content) | shipped, unmodified (`snapshot/raw/`); transcribed in `scripts/rules.json` |
| ENTSO-E physical flows (12.1.G) | CC BY 4.0 (ENTSO-E's list of data free for re-use) | Germany's hourly net position, summed from the flows (changed), in `snapshot/series/` |
| OPSD conventional power plants, 2020-10-01 | none stated | **not shipped**: you download it; the dataset carries OPSD ids only |
| Kraftwerksliste, 26.06.2026 (Bundesnetzagentur) | the site names a "Version 4.0" of the Datenlizenz Deutschland, whose text could not be found | **not shipped**: you download it |
| ENTSO-E generation per unit (16.1.A) and per type (16.1.B&C) | not on ENTSO-E's list of data free for re-use | **not shipped**: you fetch them with your own token |

Attribution lines:

- World Resources Institute, Global Power Plant Database, version 1.3.0, CC BY 4.0. Changed: rows
  selected and matched.
- Datenquelle: Bundesnetzagentur, Marktstammdatenregister, Gesamtdatenexport vom 06.06.2026,
  dl-de/by-2-0 (https://www.govdata.de/dl-de/by-2-0),
  https://www.marktstammdatenregister.de/MaStR/Datendownload. Daten geändert: Auswahl von Einheiten
  und Spalten, Klassifikation ergänzt.
- Bundesnetzagentur, Verfahrensliste inländische Netzreserve (Stand: 10.03.2025), CC BY-ND 4.0.
- Source of publication: ENTSO-E Transparency Platform (physical flows, 12.1.G), CC BY 4.0.
  Changed: summed over Germany's borders into a net position. No endorsement by ENTSO-E is implied.
- Open Power System Data. 2020. Data Package Conventional power plants. Version 2020-10-01.
  https://doi.org/10.25832/conventional_power_plants/2020-10-01. (Primary data from various
  sources, for a complete list see URL.) Only its ids appear here.

## What you need

- Python 3.10 or later with `pandas`, `openpyxl` and `matplotlib`. Run the scripts with
  `python3 -I` (isolated mode).
- For the two ENTSO-E inputs: `entsoe-py` and **your own** ENTSO-E Transparency Platform API token
  (free: register at https://transparency.entsoe.eu and request API access), in the environment
  variable `ENTSOE_API_KEY`. This folder contains no token, and no script prints yours.

## 1. Check what you have

```
shasum -a 256 -c SHA256SUMS          # or: sha256sum -c SHA256SUMS
```

## 2. Put the inputs together

```
mkdir -p work/inputs
cp snapshot/inputs/* work/inputs/
unzip -j snapshot/raw/globalpowerplantdatabasev130.zip global_power_plant_database.csv -d work/inputs
curl -L -o work/inputs/conventional_power_plants_DE.csv \
  https://data.open-power-system-data.org/conventional_power_plants/2020-10-01/conventional_power_plants_DE.csv
curl -L -o work/inputs/Kraftwerksliste_2026-06-26.xlsx \
  https://www.bundesnetzagentur.de/DE/Fachthemen/ElektrizitaetundGas/Versorgungssicherheit/Erzeugungskapazitaeten/Kraftwerksliste/_DL/Kraftwerksliste.xlsx
ENTSOE_API_KEY=<your token> python3 scripts/fetch_a73.py work/a73
python3 -I scripts/a73_units.py work/a73 work/inputs/a73_units_de_2025.csv
cp -r snapshot/series work/series
ENTSOE_API_KEY=<your token> python3 scripts/fetch_a75.py work/series
```

Then compare: `MANIFEST.json` → `files` gives the sha256 of every input under the name the scripts
expect, and `snapshot/series/SHA256SUMS` lists the A75 file you just fetched.

Two inputs can change under you. The Kraftwerksliste URL always serves the latest edition: on
2026-11-02 it still served the edition of 26.06.2026 (`ed796691504e...`); a later edition will hash
differently and may move the table. ENTSO-E revises published data from time to time: on
2026-11-02 a fresh A75 fetch gave the same bytes as the kit's. If a hash differs, the scripts
refuse to run with `--manifest`; drop it to run on what you have, and the difference is then a
change in the published record, not in the method.

## 3. Run it

```
python3 -I scripts/fleet_table.py work/inputs work/out --manifest MANIFEST.json
python3 -I scripts/fleet_details.py work/inputs work/out
python3 -I scripts/model_section.py work/series work/out work/out/model_section.json
python3 -I scripts/plots.py work/series work/out work/fig
python3 -I scripts/derived_dataset.py work/inputs work/out work/dataset
```

## 4. Compare

```
(cd work && shasum -a 256 -c ../expected/SHA256SUMS)
(cd work/dataset && shasum -a 256 -c ../../dataset/SHA256SUMS)
```

`expected/SHA256SUMS` lists every output of the run (`out/`) and every figure's data table
(`fig/`). Those that carry nothing from an input this folder may not ship are also in `expected/`
in full, at the same paths. The dataset you build must equal `dataset/` byte for byte.

## What the dataset is not

- It is not a register. It says what public registers say about 2025, for one inventory's rows,
  under the rules in `scripts/rules.json`, which are choices: a 2 km radius, a 15 % capacity
  tolerance, a 10 MW floor, a capacity factor of 0.10 for "in the market", one name alias added
  after looking at the data.
- 7.0 GW of the 84.2 has no clear 2025 status in the registers. It is reported as such.
- It calls nobody's data wrong. Each source is right about what it says it is; the double count
  comes from using two of them as one list.
