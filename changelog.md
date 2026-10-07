# Changelog

## 0.0.1 (unreleased)

Skeleton of the export rail vehicles add-on, starting from an empty fleet.

--------------------

### State

The vehicle tables are **empty**.  The project is a complete, compiling
skeleton with no rolling stock in it: the generator, the shared library, the
build system, the railtype and cargo tables and the documentation are all in
place and `make` produces a valid GRF that defines the parameters, railtypes
and cargotypes but no vehicles.  Real data is entered from here.

### Added

- `genpnml.py`, a generator that turns the declarative tables in `data/` into
  NML/PNML code:

  - `src/<folder>/<id>.pnml` — one file per vehicle, holding that vehicle's
    switches, spritesets and item block;
  - `src/vehiclefiles.pnml` — the include list of those files, in purchase menu
    order;
  - `src/vehicleid.pnml` — vehicle IDs, assigned automatically inside the band
    of each category;
  - `src/vehiclesort.pnml` — the purchase menu order;
  - `docs/str.csv` — every language string the generated code references,
    preserving existing translations;
  - placeholder voxel models for every sprite basename, so the project builds
    before any artwork exists.

- Shared library files `src/header.pnml`, `src/template.pnml`,
  `src/railtypetable.pnml`, `src/cargotable.pnml` and `src/functions.pnml`,
  following the conventions of the parent set.  The railtype table covers
  standard gauge, 1520 mm broad gauge, dual gauge (套轨), metre gauge and
  narrow gauge, which is what export stock ran on.

- Livery support: `cargo_subtype` refit menu, automatic selection from the
  build year, and per livery sprite sheets.

- Freight appearance support: switches on cargo class and on the exact cargo,
  with partial and full load stages.

- `tools/vehicle_row.py` — add, copy and remove table rows with correct CSV
  quoting, so a value containing a comma can never shift the following
  columns.
- `tools/clear_vehicle_data.py` — empty every table and delete the placeholder
  models (dry run by default, `--apply` to act).
- `tools/verify_assets.py` — check that every sprite sheet the generated code
  references exists on disk.
- `make check` and `genpnml.py --check` — verify that every string the code
  uses is defined in `docs/str.csv` and that none is dead.
- `docs/guide-zh.md` — a Chinese step by step operating manual.

### Notes

- `tools/build_data_tables.py` no longer writes the vehicle tables; it only
  creates the optional auxiliary tables (`liveries.csv`,
  `cargo_variants.csv`) and reports the state of the vehicle tables.

- `genpnml.py`, a generator that turns the declarative tables in `data/` into
  NML/PNML code:

  - `src/<folder>/<id>.pnml` — one file per vehicle, holding that vehicle's
    switches, spritesets and item block;
  - `src/vehiclefiles.pnml` — the include list of those files, in purchase menu
    order;
  - `src/vehicleid.pnml` — vehicle IDs, assigned automatically inside the band
    of each category;
  - `src/vehiclesort.pnml` — the purchase menu order;
  - `docs/str.csv` — every language string the generated code references,
    preserving existing translations;
  - placeholder voxel models for every sprite basename, so the project builds
    before any artwork exists;
  - `--sprite-manifest <file>`, which records which sprite basename every row
    needs; the web workbench reads it instead of reimplementing the suffix
    rules.

- Shared library files `src/header.pnml`, `src/template.pnml`,
  `src/railtypetable.pnml`, `src/cargotable.pnml` and `src/functions.pnml`,
  following the conventions of the parent set.  The railtype table covers
  standard gauge, 1520 mm broad gauge, dual gauge (套轨), metre gauge and
  narrow gauge, which is what export stock ran on.

- Livery support: `cargo_subtype` refit menu, automatic selection from the
  build year, and per livery sprite sheets.

- Freight appearance support: switches on cargo class and on the exact cargo,
  with partial and full load stages.

### Added — visual workbench

- `web/workbench/`, a local browser workbench modelled on
  `openttd-newgrf-builder`'s `web/workbench`: a Python standard library HTTP
  server plus plain JavaScript, started with `make workbench` and opened at
  `http://127.0.0.1:4174/workbench/`.

  - `server.py` reads `data/*.csv`, inspects `src/` and `gfx/`, and shells out
    to the existing tools — it reimplements no generation logic.
  - `schema.py` is the single source of column metadata; the browser renders
    every form from it, so adding a column means editing one file.
  - Eight stages: fleet ledger, vehicle detail, livery schemes, freight
    appearance, models and sprites, consistency check, GRF build, and the
    in-repository guide.
  - Sprite preview crops the real `_32bpp.png` using the per view rectangles
    derived from `manifest.json` and the PNG header, because renderobject's
    strip is not a uniform grid (36 / 120 / 192 px cells, 8 px padding, each
    view centred vertically).  These rectangles match the coordinates hand
    written in `src/template.pnml`.
  - Build and check runs stream their output incrementally, so a long `make`
    does not block the page.
  - Writes are validated with the same rules the generator enforces, applied
    atomically through a temporary file, and the previous table is kept as
    `data/<table>.csv.workbench.bak`.  A save merges into the row that was
    read, so a column the browser does not know about is never lost.

- `tools/clear_vehicle_data.py`, a dry-run-by-default helper that empties every
  vehicle table and removes the placeholder models.

### Fixed

- `data/locomotives.csv`, `coaches.csv`, `wagons.csv` and `unit_wagons.csv`
  were missing the `capacity_by_cargo` and `train_flags` columns that
  `genpnml.py` already read, so both silently never had any effect.  They are
  now columns 35 and 38 of all four tables (46 columns total), matching what
  `data/README.md` documented.

### Notes

- The performance figures in `data/*.csv` are reasonable engineering estimates
  and still need to be checked against the builders' plates.
- The voxel models are placeholders generated by `genpnml.py`; they are
  correctly shaped and coloured but are not artwork.
- Placeholder renders show an opaque white block under the model.  It comes
  from `renderobject` on the generated placeholder `.vox`, is outside every
  rectangle `src/template.pnml` crops, and is expected to disappear once a real
  model replaces the placeholder.  It is visible in the workbench on purpose.
