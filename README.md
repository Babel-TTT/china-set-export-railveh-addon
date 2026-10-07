# China Set: Export Rail Vehicles Add-on

READ IN ENGLISH | [CHINESE](./README-zh.md)

1. [General Information](#1-general-information)
2. [Building](#2-building)
3. [Adding a vehicle](#3-adding-a-vehicle)
4. [License](#4-license)

## 1. General Information

China Set: Export Rail Vehicles Add-on is the export sector of the China Set of
OpenTTD.  It contains the locomotives, multiple units, coaches and wagons that
the Chinese rolling stock industry built for railways abroad, plus the
international through-coaches that ran from China into neighbouring countries.

The add-on is designed to be loaded **together with** [China Set:
Trains](https://github.com/OpenTTD-China-Set/China-Set-Trains) and China Set:
Narrow Gauge Add-on.  Stock of the three sets can be coupled to each other;
the GRF IDs are cross-checked in `src/functions.pnml` for that purpose.

Everything here is standard gauge, Russian broad gauge (1520 mm), dual gauge or
metre gauge, because that is what the export market used, and the railtype
labels follow the semi-standardised scheme of the parent set:

| prefix | gauge            | typical use                          |
| ------ | ---------------- | ------------------------------------ |
| `S`    | 1435 mm          | most of the world                    |
| `B`    | 1520 mm          | Russia, Central Asia, Mongolia       |
| `D`    | 1435 / 1520 mm   | gauge changing stock, "套轨"          |
| `N`    | 1067 / 1000 mm   | South East Asia, Africa              |
| `n`    | 762 / 600 mm     | industrial and light railways        |

List of available parameters:

| Name                                                  | Function                                                                        | Default |
| ----------------------------------------------------- | ------------------------------------------------------------------------------- | ------- |
| Loading speed                                         | Change wagon loading speed                                                      | Normal  |
| Purchase cost                                         | Change purchase cost                                                            | 25%     |
| Running cost                                          | Change running cost                                                             | 25%     |
| Cargo age period                                      | Change the rate cargo gets aged                                                 | Standard|
| Cargo age period for freight wagons                   | Change the rate cargo in mail and freight wagons gets aged, independently       | Standard|
| Export stock built after a paint scheme change uses the new scheme | Whether a livery change applies automatically to newly built stock | Yes |

## 2. Building

The tools needed are `nml`, `make`, `gcc`, `python3` and `gorender` (or
`renderobject`).  On Windows, scoop is the easiest way:

```powershell
scoop bucket add main
scoop bucket add openttd https://github.com/WenSimEHRP/OpenTTD-Bucket
scoop install python
scoop install make
scoop install openttd/nml
scoop install openttd/gorender
scoop install mingw
```

On Linux or WSL:

```bash
sudo apt install python3 make gcc
pip3 install nml
```

Then simply:

```bash
make            # generate code, render sprites, build lang files, compile
make -j 8       # the same, eight tasks at a time (first build is slow)
make gen        # only regenerate the PNML code from data/
make sprites    # only render the voxel models
make workbench  # start the local browser workbench
make clean      # remove build outputs
```

The build pipeline is the same one the parent sets use:

```
data/*.csv ──genpnml.py──> src/<folder>/<id>.pnml + vehicleid/vehiclefiles/vehiclesort
gfx/**/*.vox ──renderobject──> gfx/**/*_32bpp.png
docs/str.csv ──str-csv.py──> lang/*.lng
chinasettrainsexport.pnml ──gcc -E──> chinasettrainsexport.nml ──nmlc──> chinasettrainsexport.grf
```

## Workbench

`make workbench` serves a local visual workbench at
<http://127.0.0.1:4174/workbench/>: a fleet ledger, the 46 column vehicle form,
livery and freight appearance tables, cropped previews of the rendered sprites,
the string and asset consistency checks, and the GRF build with live output.
It edits `data/` with the same validation the generator applies and never
reimplements the generation itself — see
[web/workbench/README.md](web/workbench/README.md).

## 3. Adding a vehicle

> **The tables start empty.**  The project currently defines no vehicles: the
> generator, the shared library, the build system, the railtype and cargo
> tables and the documentation are all in place, but every row has been
> removed so that real data can be entered from scratch.  `make` already
> produces a valid GRF (parameters, railtypes and cargotypes, no vehicles);
> add a row and it grows from there.

Vehicles are **data**, not code.  To add one:

1. add a row to `data/locomotives.csv`, `data/coaches.csv`, `data/wagons.csv`
   or `data/unit_wagons.csv` (see [data/README.md](data/README.md) for every
   column).  `tools/vehicle_row.py` writes the row with correct CSV quoting:

   ```bash
   python3 tools/vehicle_row.py add data/locomotives.csv \
       id=ckd4a name_string="CKD4A (Export)" category=diesel folder=diesel \
       model=single parts=4 power_section=0 intro_year=1993 track_type=BACN \
       speed=100 power=1000 power_unit=kW weight=92 \
       tractive_effort_coefficient=0.25 cost_factor=45 running_cost_factor=40 \
       capacity=1 ac_supply=1

   # or start from a row that already exists
   python3 tools/vehicle_row.py copy data/locomotives.csv ckd4a ckd4b \
       name_string="CKD4B (Export)" speed=120
   ```

2. optionally add livery rows to `data/liveries.csv` and appearance rows to
   `data/cargo_variants.csv`,
3. run `make gen` — the ID, the switch chains, the spritesets, the menu order
   and the language strings are all derived automatically,
4. drop the model into `gfx/<folder>/<id>.vox`; if the vehicle has liveries or
   cargo variants, one `.vox` per sprite basename is needed.  `make gen`
   already writes a placeholder model for each of them, so the project builds
   before any artwork exists.

`make gen` creates `gfx/<folder>/manifest.json` and `ttd_palette.json` the
first time a vehicle needs them, so a new folder needs no manual setup.

**One vehicle, one file.**  Each vehicle gets its own generated file at
`src/<folder>/<id>.pnml`, listed by `src/vehiclefiles.pnml` and included from
`chinasettrainsexport.pnml`, exactly like the parent set.  Changing a vehicle
therefore touches exactly one file, and `make gen` deletes the file again when
the row is removed.

Never edit the generated files by hand — `src/<folder>/*.pnml`,
`src/vehiclefiles.pnml`, `src/vehicleid.pnml` and `src/vehiclesort.pnml` are all
overwritten on every build.  They are tracked in git on purpose, so that a
checkout can be compiled without running python and so that changes to
generated code show up in review.

`make check` verifies that every string the code uses exists in `docs/str.csv`
and that no row of `docs/str.csv` is dead.

## 4. License

```text
China Set: Export Rail Vehicles Add-on

Copyright (C) 2025 China Set Team

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License along
with this program; if not, please check
https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html
```
