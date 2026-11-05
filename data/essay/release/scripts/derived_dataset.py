"""The derived dataset (ES1 amendment 1, shape a): the crosswalk this kit computes, as a table that
may be redistributed. It is built from a fleet_table.py + fleet_details.py run, and it keeps only
what each input's licence allows (data/essay/LICENCES.json):

  ours        our own work: the classes, the match rule that fired, the shares, the families
  id          a publisher's identifier (WRI id, OPSD/BNetzA number, MaStR number, EIC)
  wri         WRI Global Power Plant Database 1.3.0, CC BY 4.0
  mastr       Marktstammdatenregister, dl-de/by-2-0
  names       an inventory row's name: WRI's for a WRI row, the BNetzA number (OPSD's id) otherwise
  row         a field of the inventory row's own record: kept for a WRI row, blank for an OPSD row
              (for a site: blank when any of its rows is OPSD's; its duplicate MW, when an OPSD
              row carries any of it)
  unit        a field of the register unit's own record: kept for a MaStR unit, blank for an OPSD one
  dropped     OPSD (no licence stated), Kraftwerksliste (licence not established), ENTSO-E A73
              (not on ENTSO-E's free re-use list): the column is not written

A row's six class MW sum to the capacity of its public record. For an OPSD row that capacity is
OPSD's, so its MW columns are blank and its six shares (our allocation) stay: multiply them by the
record's capacity_net_bnetza (your own download, matched by source_id and source_occurrence) to get
the MW back. fleet_table.py's own plants.csv does exactly that.

Writes <dataset>/crosswalk_rows.csv, crosswalk_units.csv, duplicate_sites.csv, duplicate_rows.csv,
unresolved_rows.csv, hard_coal_bridge.csv, table.csv, table_by_family.csv, COLUMNS.csv, SHA256SUMS.
Standard library and pandas.

    python3 -I scripts/essay/derived_dataset.py <inputs_dir> <fleet_table_out_dir> <dataset_dir>
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import pandas as pd

CLS = ['market', 'out_2025', 'closed_pre_2025', 'duplicate', 'unknown_2025', 'no_register_row']
OPSD = 'opsd_2020'

# file -> [(output column, input column, origin)]; an origin of 'dropped' is listed in COLUMNS.csv
ROWS = ([('row', 'row', 'ours'), ('source', 'source', 'ours'), ('source_id', 'source_id', 'id'),
         ('source_occurrence', 'source_occurrence', 'ours'), ('name', 'name', 'row'),
         ('lat', 'lat', 'row'), ('lon', 'lon', 'row'), ('fam', 'fam', 'ours'),
         ('match_rule', 'method', 'ours'), ('register_units', 'units', 'id'),
         ('duplicate_of', 'duplicate_of', 'ours'), ('mw', 'mw', 'row')] +
        [(f'mw_{c}', c, 'row') for c in CLS] + [(f'share_{c}', f'share_{c}', 'ours') for c in CLS])
UNITS = [('uid', 'uid', 'id'), ('source', 'source', 'ours'),
         ('EinheitMastrNummer', 'EinheitMastrNummer', 'id'),
         ('Kraftwerksnummer', 'Kraftwerksnummer', 'id'), ('Weic', 'Weic', 'id'),
         ('fam', 'fam', 'ours'), ('net_mw', 'net_mw', 'unit'), ('lat', 'lat', 'unit'),
         ('lon', 'lon', 'unit'), ('station', 'station', 'unit'), ('block', 'block', 'unit'),
         ('Ort', 'Ort', 'unit'), ('Inbetriebnahmedatum', 'Inbetriebnahmedatum', 'unit'),
         ('DatumEndgueltigeStilllegung', 'DatumEndgueltigeStilllegung', 'unit'),
         ('cls', 'cls', 'ours'), ('rule', 'cls_why', 'ours'), ('claimed_by', 'claimed_by', 'ours'),
         ('kwl_status', 'kwl_status', 'dropped'), ('kwl_closure_year', 'kwl_closure_year', 'dropped'),
         ('opsd_status', 'opsd_status', 'dropped'), ('opsd_shutdown', 'opsd_shutdown', 'dropped'),
         ('a73_twh_2025', 'a73_twh_2025', 'dropped'), ('a73_cf_2025', 'a73_cf_2025', 'dropped')]
DUP_SITES = [('site_rows', 'site_rows', 'names'), ('sources', 'sources', 'ours'),
             ('rows', 'rows', 'ours'), ('rows_mw', 'rows_mw', 'row'),
             ('register_units', 'register_units', 'ours'), ('register_mw', 'register_mw', 'mastr'),
             ('ratio', 'ratio', 'row'), ('duplicate_mw_in_table', 'duplicate_mw_in_table', 'row'),
             ('one_source_overlap', 'one_source_overlap', 'ours')]
DUP_ROWS = [('site', 'site', 'row'), ('row', 'row', 'ours'), ('source', 'source', 'ours'),
            ('source_id', 'source_id', 'id'), ('name', 'name', 'row'),
            ('listed_by_source_as_from', 'listed_by_source_as_from', 'row'), ('mw', 'mw', 'row'),
            ('match_rule', 'method', 'ours'), ('duplicate_mw', 'duplicate_mw', 'row'),
            ('register_units', 'units', 'id'), ('register_units_text', 'register_units', 'dropped')]
UNRESOLVED = [('row', 'row', 'ours'), ('name', 'name', 'row'), ('fam', 'fam', 'ours'),
              ('part', 'part', 'ours'), ('tier', 'tier', 'ours'), ('cls', 'cls', 'ours'),
              ('mw', 'mw', 'row'), ('register_unit', 'register_unit', 'id'),
              ('station', 'station', 'unit')]
BRIDGE = [('EinheitMastrNummer', 'EinheitMastrNummer', 'id'),
          ('NameKraftwerk', 'NameKraftwerk', 'mastr'),
          ('NameKraftwerksblock', 'NameKraftwerksblock', 'mastr'), ('net_mw', 'net_mw', 'mastr'),
          ('EinheitBetriebsstatus_txt', 'EinheitBetriebsstatus_txt', 'mastr'),
          ('DatumEndgueltigeStilllegung', 'DatumEndgueltigeStilllegung', 'mastr'),
          ('in_service_2025', 'in_service_2025', 'ours'), ('s46_market', 's46_market', 'ours'),
          ('cls', 'cls', 'ours'), ('rule', 'cls_why', 'ours'),
          ('kwl_status', 'kwl_status', 'dropped'), ('a73_cf_2025', 'a73_cf_2025', 'dropped')]
LICENCE = {'ours': '[our licence: open point for Paul]', 'id': 'identifier of the publisher named '
           'in source/uid', 'wri': 'CC BY 4.0 (WRI)', 'mastr': 'dl-de/by-2-0 (Bundesnetzagentur, '
           'MaStR)', 'names': 'CC BY 4.0 (WRI) names; OPSD rows by id only',
           'row': 'CC BY 4.0 (WRI) on a WRI row; blank on an OPSD row',
           'unit': 'dl-de/by-2-0 (MaStR) on a MaStR unit; blank on an OPSD unit',
           'dropped': 'not written'}


def rule(why):
    """The rule that fired, without the value it read from an input that is not shipped."""
    if not isinstance(why, str):
        return why
    m = re.match(r'grid reserve: (Verfahrensliste 2025-03-10 \(.*\)) and Kraftwerksliste .*', why)
    if m:
        return f'grid reserve: {m.group(1)} and a Kraftwerksliste reserve status'
    if why.startswith('Kraftwerksliste status: '):
        return 'Kraftwerksliste status: ' + ('temporarily closed' if 'vorläufig' in why
                                             else 'a reserve')
    if re.match(r'Kraftwerksliste closed .*: after \d+$', why):
        return 'Kraftwerksliste closure year: after 2025'
    if why == 'in service, Kraftwerksliste InBetrieb':
        return 'in service, Kraftwerksliste in operation'
    m = re.match(r'OPSD (\d+) status \S+; no later register row$', why)
    if m:
        return f'OPSD {m.group(1)} status not shut down; no later register row'
    return why


def project(df, spec, row_is_opsd=None, unit_is_opsd=None):
    out = pd.DataFrame(index=df.index)
    for col, src, origin in spec:
        if origin == 'dropped':
            continue
        v = df[src].copy()
        if origin == 'row' and row_is_opsd is not None:
            v = v.where(~row_is_opsd)
        if origin == 'unit' and unit_is_opsd is not None:
            v = v.where(~unit_is_opsd)
        out[col] = v
    return out


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main(inp, run, ds):
    inp, run, ds = Path(inp), Path(run), Path(ds)
    ds.mkdir(parents=True, exist_ok=True)
    inv = pd.read_csv(inp / 'inventory_de.csv', dtype={'source_id': str})
    pl = pd.read_csv(run / 'plants.csv', dtype={'source_id': str})
    assert (pl.row.values == inv.row.values).all() and (pl.source_id.values == inv.source_id.values).all()
    pl['source_occurrence'] = inv.source_occurrence.values
    for c in CLS:
        pl[f'share_{c}'] = pl[c] / pl.mw
    opsd_row = pl.source == OPSD
    project(pl, ROWS, opsd_row).to_csv(ds / 'crosswalk_rows.csv', index=False)

    un = pd.read_csv(run / 'units.csv', dtype=str, keep_default_na=False)
    un['cls_why'] = un.cls_why.map(rule)
    project(un, UNITS, unit_is_opsd=un.source == OPSD).to_csv(ds / 'crosswalk_units.csv',
                                                               index=False)

    d = run / 'details'
    si = pd.read_csv(d / 'duplicate_sites.csv', dtype=str, keep_default_na=False)
    side = pd.read_csv(d / 'duplicate_rows_side_by_side.csv', dtype={'source_id': str})
    out = project(si, DUP_SITES, si.sources.str.contains(OPSD))
    # a site's duplicate MW is a WRI station row's in all but a few sites: keep it there
    opsd_dup = set(side.site[(side.source == OPSD) & (side.duplicate_mw > 0)])
    site = si.site_rows.str.split('; ').str[0]
    out['duplicate_mw_in_table'] = si.duplicate_mw_in_table.where(~site.isin(opsd_dup))
    out.to_csv(ds / 'duplicate_sites.csv', index=False)
    side['units'] = side.row.map(dict(zip(pl.row, pl.units)))
    project(side, DUP_ROWS, side.source == OPSD).to_csv(ds / 'duplicate_rows.csv', index=False)
    ur = pd.read_csv(d / 'unresolved_rows.csv', dtype=str, keep_default_na=False)
    ur_opsd = ur.row.astype(int).map(dict(zip(pl.row, opsd_row)))
    out = project(ur, UNRESOLVED, ur_opsd)
    out['station'] = out.station.where(~ur.register_unit.str.startswith('O:'))
    out.to_csv(ds / 'unresolved_rows.csv', index=False)
    br = pd.read_csv(d / 'hard_coal_bridge.csv', dtype=str, keep_default_na=False)
    br['cls_why'] = br.cls_why.map(rule)
    project(br, BRIDGE).to_csv(ds / 'hard_coal_bridge.csv', index=False)
    for f in ('table.csv', 'table_by_family.csv'):
        (ds / f).write_bytes((run / f).read_bytes())

    cols = [{'file': f, 'column': col, 'from': src, 'origin': o, 'licence': LICENCE[o]}
            for f, spec in (('crosswalk_rows.csv', ROWS), ('crosswalk_units.csv', UNITS),
                            ('duplicate_sites.csv', DUP_SITES), ('duplicate_rows.csv', DUP_ROWS),
                            ('unresolved_rows.csv', UNRESOLVED), ('hard_coal_bridge.csv', BRIDGE))
            for col, src, o in spec]
    cols += [{'file': f, 'column': '*', 'from': 'fleet_table.py', 'origin': 'ours',
              'licence': LICENCE['ours']} for f in ('table.csv', 'table_by_family.csv')]
    pd.DataFrame(cols).to_csv(ds / 'COLUMNS.csv', index=False)
    files = sorted(p.name for p in ds.iterdir() if p.name != 'SHA256SUMS')
    (ds / 'SHA256SUMS').write_text(''.join(f'{sha256(ds / f)}  {f}\n' for f in files))
    print(f'{len(files)} files -> {ds}')


if __name__ == '__main__':
    main(*sys.argv[1:4])
