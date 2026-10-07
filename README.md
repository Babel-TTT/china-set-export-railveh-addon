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
make clean      # remove build outputs
```

The build pipeline is the same one the parent sets use:

```
data/*.csv ──genpnml.py──> src/usercode.pnml, src/vehicleid.pnml, src/vehiclesort.pnml
gfx/**/*.vox ──renderobject──> gfx/**/*_32bpp.png
docs/str.csv ──str-csv.py──> lang/*.lng
chinasettrainsexport.pnml ──gcc -E──> chinasettrainsexport.nml ──nmlc──> chinasettrainsexport.grf
```

## 3. Adding a vehicle

Vehicles are **data**, not code.  To add one:

1. add a row to `data/locomotives.csv`, `data/coaches.csv`, `data/wagons.csv`
   or `data/unit_wagons.csv` (see [data/README.md](data/README.md) for every
   column),
2. optionally add livery rows to `data/liveries.csv` and appearance rows to
   `data/cargo_variants.csv`,
3. run `make gen` — the ID, the switch chains, the spritesets, the menu order
   and the language strings are all derived automatically,
4. drop the model into `gfx/<folder>/<id>.vox`; if the vehicle has liveries or
   cargo variants, one `.vox` per sprite basename is needed.  `make gen`
   already writes a placeholder model for each of them, so the project builds
   before any artwork exists.

Nothing in `src/usercode.pnml`, `src/vehicleid.pnml` or `src/vehiclesort.pnml`
is meant to be edited by hand — those files are overwritten on every build.

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
