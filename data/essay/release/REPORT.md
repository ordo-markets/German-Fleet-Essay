<!-- DRAFT for Paul. Not published. Shipped in the release folder as REPORT.md
(data/essay/release/). Every number is read from a file in that folder; open points in [square
brackets]. -->

# German power plants, counted once: what the dataset is and how it was made

[title and licence of our own work: Paul decides]

## 1. What it is

A crosswalk. It takes one inventory of German thermal and hydro plants, 518 rows and 84,248.4 MW,
and says for every row which register units it stands for and what those units did in 2025.

The inventory is the one an hourly market model would start from: the German conventional and
hydro rows of two good public lists, the World Resources Institute's Global Power Plant Database
1.3.0 (298 rows) and Open Power System Data's conventional power plants of 2020-10-01 (220 rows).
The registers are the Bundesnetzagentur's Marktstammdatenregister (export of 2026-06-06), its
Kraftwerksliste (26.06.2026) and its list of grid-reserve procedures (10.03.2025), plus ENTSO-E's
record of what each large unit generated in 2025.

The dataset has these files (`dataset/`):

| file | rows | one row per |
|---|---|---|
| `crosswalk_rows.csv` | 518 | inventory row: its id, the match rule that fired, the register units it claims, its six class MW and shares |
| `crosswalk_units.csv` | 1,489 | register unit: 1,102 Marktstammdatenregister units ≥ 10 MW and 387 OPSD units the register does not number; its 2025 class and the rule that decided it |
| `duplicate_sites.csv` | 70 | site where inventory rows overlap |
| `duplicate_rows.csv` | 208 | inventory row at such a site |
| `unresolved_rows.csv` | 648 | part of a row in the last two classes, with what the registers can say about it |
| `hard_coal_bridge.csv` | 82 | hard-coal register unit, from "in operation" to "in the 2025 market" |
| `table.csv`, `table_by_family.csv` | 7, 6 | the totals |
| `COLUMNS.csv` | 90 | column: where it comes from and under which licence |

## 2. The six classes

Each row's MW is split into six classes that sum to it (asserted to 1e-6 MW):

| class | what it means for 2025 |
|---|---|
| in the market | the row stands for a register unit that was in the 2025 day-ahead market |
| reserve or closed during 2025 | it stands for a unit held in the grid reserve, or closed, during 2025 |
| closed before 2025 | it stands for a unit closed before 2025 |
| counted twice | it stands for units another inventory row already carries |
| status unknown | it stands for a unit last seen operating in OPSD 2020, with no later register entry |
| no register entry | it stands for no register unit at all |

## 3. Every rule

All parameters are in one file, `scripts/rules.json`. They were written before the results were
read, with one exception, marked in the file.

- **Matching a station row.** A row that names a station claims the register units of a
  compatible fuel family within **2 km** of its coordinate. With none there, it may take units
  within **5 km** that carry a word of its name, or that no other row claims. Units of another
  thermal fuel within 0.5 km that nobody claims are taken last and recorded as such.
- **Matching a unit row.** A row carrying a Bundesnetzagentur unit number takes the register unit
  with that number, else the one with its block EIC code, else one compatible unit within 2 km
  whose net MW is within **15 %** of the row's, else a station's units that add up to it within
  15 %, else the OPSD record itself (a unit the register does not number).
- **Fuel families and compatibility.** Listed in the file (for example, a gas row may claim a
  register "heat" unit, because a combined-cycle plant's steam turbine is registered that way).
- **The floor.** Register units below **10 MW** net are not in the matching set. They are used only
  to describe the unresolved rows.
- **A register unit's 2025 class**, the first test that applies, in this order:
  1. commissioned after 2025, or still in planning → not counted;
  2. a final closure date in the register before 2025 → closed before 2025;
  3. at least half of 2025 inside a designation on the Bundesnetzagentur's grid-reserve list, and a
     reserve status in the Kraftwerksliste → reserve;
  4. its own 2025 output (ENTSO-E 16.1.A) a capacity factor of at least **0.10** → in the market;
  5. a final closure during 2025, or a temporary closure with no restart begun before 2026 →
     reserve or closed during 2025 if it began before mid-2025, in the market if after;
  6. a reserve or temporary-closure status in the Kraftwerksliste → reserve;
  7. a closure year in the Kraftwerksliste → closed before 2025, during it, or (after 2025) in the
     market;
  8. otherwise in service → in the market.

  A unit only OPSD lists is closed before 2025 if OPSD gives a shutdown year before 2025, and of
  unknown status otherwise.
- **The double count.** A station row on a site whose units a unit row already carries stands, for
  the remainder, for those same units: that remainder is "counted twice".
- **The one rule added after looking at the data.** ENTSO-E publishes Mannheim's units as "GKM";
  no register text carries that name, so `GKM → Grosskraftwerk Mannheim` was added by hand.

The grid-reserve list is a PDF. Its designations are transcribed by hand into `rules.json`; the
PDF is shipped unmodified beside it so the transcription can be checked.

## 4. Where each column comes from, and its licence

Each input keeps its publisher's licence. `LICENCES.json` quotes every one from the publisher's own
page, retrieved 2026-11-02, with the URL and the bytes read. A licence that could not be found
counts as not established, and that input's own values are not in any file here.

| input | licence (publisher's words) | what of it is in the dataset |
|---|---|---|
| WRI Global Power Plant Database 1.3.0 | CC BY 4.0 | name, capacity, coordinate of a WRI row |
| Marktstammdatenregister | Datenlizenz Deutschland – Namensnennung – Version 2.0 | unit number, name, place, net MW, coordinate, dates, operating status |
| OPSD conventional power plants 2020-10-01 | none stated; OPSD: "several data owners do not allow us" to publish under CC BY | only the row's id (its Bundesnetzagentur number). Its MW columns are blank; its six shares are ours |
| Kraftwerksliste 26.06.2026 | the Bundesnetzagentur's site names a "Version 4.0" of the Datenlizenz Deutschland; no text for it was found | nothing of its own; our classes derived with it, and the rule that fired, without the status text it read |
| Verfahrensliste Netzreserve 10.03.2025 | CC BY-ND 4.0 (the site's rule for its content) | the designated plant and the share of 2025 it covers, in the rule text [open point for Paul: whether this is adapted material] |
| ENTSO-E 16.1.A, generation per unit | not on ENTSO-E's list of data free for re-use | nothing of its own; our class "in the market" |
| ENTSO-E 12.1.G, physical flows | CC BY 4.0 (on that list) | not in the dataset; Germany's net position from it is in the kit's series |

`COLUMNS.csv` gives the same for each of the 90 columns. An OPSD row's MW comes back when you
multiply its six shares by the capacity in your own copy of the OPSD file. On the kit's run that
reproduces every class MW to 2.3e-13 MW.

## 5. The independence test

Two tests, both run from files outside the model.

1. **The table equals the model-side partition** (ES1, 2026-10-31). The standalone script, run on
   public files only, gave the same six class totals as the partition computed inside the model
   project: 0.0 MW apart in every class. The first run was 11.5 MW apart because of an ordering
   defect in the register extract; it was fixed and is itemised in the ES1 verification record.
2. **The published folder re-runs to the byte** (2026-11-02). The release folder was copied to an
   empty directory. OPSD's file and the Kraftwerksliste were downloaded from their URLs that day,
   and ENTSO-E's generation per type was fetched from its API that day. Following the README
   gave **20 of 20** listed outputs and **9 of 9** dataset files byte for byte. ENTSO-E's
   generation per unit (A73) is a year of 1,460 requests; a re-fetch that day was stopped after 85
   day files, all identical in every value to the files the table was built from.

## 6. Why it is better, as a measurement

Not "better than" any product. Better than the inventory it starts from, in a way anyone can
re-run: it says, row by row, what the public lists count that the 2025 market did not have.

| what the registers say about 2025 | MW | share of 84,248.4 MW |
|---|---|---|
| in the 2025 day-ahead market | 39,805.9 | 47.2 % |
| counted twice | 20,705.2 | 24.6 % |
| closed before 2025 | 9,181.5 | 10.9 % |
| reserve, or closed during 2025 | 7,593.3 | 9.0 % |
| status unknown (last seen operating in OPSD 2020) | 1,111.2 | 1.3 % |
| no register entry | 5,851.4 | 6.9 % |

**37,479.9 MW, 44.5 % of the inventory, was not in the 2025 market.** The largest part is the double
count: 20,705.2 MW at 50 sites, every MW of it where a WRI station row and OPSD unit rows stand for
the same units (`duplicate_sites.csv` puts them side by side). Hard coal shows the steps one unit
at a time: 15,003.8 MW listed as operating in the register (44 units) → 9,193.2 MW in the market,
the 5,810.6 MW between them being units in the grid reserve, each named
(`hard_coal_bridge.csv`).

The Bundesnetzagentur publishes its own count by fuel and status, the Kraftwerksliste. It is not an
independent count of the same thing: its own header names the Marktstammdatenregister as its
source, and it counts the register, not an inventory. The kit sets its totals beside ours
(`out/details/kwl_totals.csv` when you run the kit); they differ where the inventory
differs from the register, which is what this dataset measures.

To re-run it: `README.md`, sections 1–4.

## 7. Limits

- **The rules are choices.** Another radius, tolerance or capacity-factor line moves rows between
  classes.
- **7.0 GW is unresolved.** 6,962.6 MW sits in the last two classes. The registers classify 18.6 %
  of it (1,292.2 MW) through units below 10 MW or a name within 5 km. The rest, 4,944.6 MW of it
  gas, stays unresolved for four reasons: no compatible register unit within 5 km of the listed
  coordinate (1,956.0 MW), a unit row larger than its register unit (1,591.1 MW), no register unit
  at OPSD's position (1,111.2 MW), a station row larger than the units at its site (1,012.1 MW).
  None of it is moved into the market or the not-in-market totals.
- **Two inputs can change under a reader.** The Kraftwerksliste URL serves only its latest edition;
  ENTSO-E revises published data. Both are checked by hash, and on 2026-11-02 both gave the bytes
  the dataset was built from; so did the 85 day files of ENTSO-E's generation per unit re-fetched
  that day.
- **The register export is not re-downloadable.** The Marktstammdatenregister serves only its
  current export. The two extracts the kit uses are shipped; a reader who re-extracts a later
  export counts a later register.
- **It calls nobody's data wrong.** Each list is right about what it says it is. The double count
  comes from using two of them as one list.
