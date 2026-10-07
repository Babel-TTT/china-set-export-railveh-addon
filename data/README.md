# The data tables

Everything about a vehicle — its ID, its switch chains, its spritesets, its
position in the purchase menu and its language strings — is derived from the
CSV files in this folder.  `src/<folder>/<id>.pnml`, `src/vehiclefiles.pnml`,
`src/vehicleid.pnml` and `src/vehiclesort.pnml` are generated and must never be
edited by hand.

> **Starting state: empty.**  Every table below currently contains only its
> documentation header and its column header — no vehicle rows.  The project
> is a complete, compiling skeleton with no rolling stock in it, ready for real
> data.  `make gen` writes the empty index files and `make` produces a GRF
> that defines the parameters, railtypes and cargotypes but no vehicles.

```
python3 genpnml.py --data data --out src --vox   # write the PNML and placeholder models
python3 genpnml.py --strings                     # refresh docs/str.csv
python3 genpnml.py --check                       # verify the string table
python3 genpnml.py --clean                       # remove the generated PNML
make gen                                         # the first of the above, via make

python3 tools/vehicle_row.py add    <table> id=... key=value ...   # add a row
python3 tools/vehicle_row.py copy   <table> <from> <to> key=value ...
python3 tools/vehicle_row.py remove <table> <id> [--prune]         # remove a row
python3 tools/vehicle_row.py columns <table>                       # list the columns
python3 tools/clear_vehicle_data.py [--apply]                      # empty all tables
```

`tools/vehicle_row.py` is the safe way to edit these files: it writes through
the csv module, so a value containing a comma can never shift the following
columns.  `tools/clear_vehicle_data.py` empties every table and deletes the
placeholder models, which is how the current empty state was produced.

`#` starts a comment.  A comment may appear anywhere, including between data
rows.  List valued cells use `|` as the separator so that the CSV stays
readable, for example `bitmask(CC_BULK|CC_COVERED)` and `[PASS|TOUR]`; a comma
works too but then the cell has to be quoted.

## Files

| file                  | contents                                                     |
| --------------------- | ------------------------------------------------------------ |
| `locomotives.csv`     | locomotives and multiple unit head cars                      |
| `coaches.csv`         | passenger coaches                                            |
| `wagons.csv`          | freight wagons                                               |
| `unit_wagons.csv`     | multiple unit trailers                                       |
| `liveries.csv`        | paint schemes (optional, any vehicle)                        |
| `cargo_variants.csv`  | freight appearance per cargo class (optional, wagons only)   |

## Vehicle columns

| column | meaning |
| ------ | ------- |
| `id` | NML identifier **and** sprite basename.  Lower case, `[a-z0-9_]`, unique. |
| `name_string` | the name shown in the depot.  A plain name such as `CKD4A (Export)` is mapped onto `STR_NAME_<ID>` by the generator, so the translation lives in `docs/str.csv`. |
| `category` | which ID band and engine class to use.  One of `steam`, `diesel`, `electric`, `multipower`, `1500v_dc`, `dmu`, `emu`, `1500_emu`, `750_emu`, `third_emu`, `multi_mu`, `mono_mu`, `mglv_mu`, `cargo_dmu`, `cargo_emu`, `multi_cargo_mu`.  Ignored in `coaches.csv`, `wagons.csv` and `unit_wagons.csv`, where it is implied. |
| `folder` | sub folder of `gfx/` holding the model, and the first argument of the sprite templates. |
| `model` | `single` for a one piece vehicle, `triple` for a vehicle that is repeated by the articulated parts callback (the usual case: all stock is 2-<body>-2 in OpenTTD terms). |
| `parts` | section lengths, `\|` separated, e.g. `2\|8\|2`.  For `model=single` only the first value is used. |
| `power_section` | index of the section that carries the body sprite, the power and the capacity. |
| `intro_year`, `intro_month`, `intro_day` | introduction date. |
| `model_life` | `VEHICLE_NEVER_EXPIRES` or a number of years. |
| `retire_early` | years of early retirement, or empty. |
| `vehicle_life` | life of a single vehicle in years. |
| `track_type` | a label from `src/railtypetable.pnml`. |
| `climates_available` | usually `ALL_CLIMATES`. |
| `speed` | km/h. |
| `power`, `power_unit` | power value and its unit, `kW` or `hp`.  Locomotives only. |
| `weight` | tonnes. |
| `tractive_effort_coefficient` | 0.0 … 0.4, locomotives only. |
| `cost_factor` | purchase cost factor. |
| `running_cost_factor` | running cost factor; it is multiplied by `runningcostfactor()`. |
| `purchase_running_cost_factor` | value shown in the depot; defaults to three times the running cost factor. |
| `purchase_cost_display` | cost factor shown in the depot; defaults to `cost_factor`. |
| `reliability_decay` | locomotives only. |
| `purchase_speed`, `purchase_power` | optional figures shown in the depot. |
| `refittable_cargo_classes` | e.g. `bitmask(CC_PASSENGERS)` or `bitmask(CC_BULK\|CC_COVERED)`. |
| `non_refittable_cargo_classes` | usually `0`. |
| `cargo_allow_refit` | whitelist, e.g. `[VEHI\|ENSP]` or `[]`. |
| `cargo_disallow_refit` | blacklist, e.g. `[YETI\|YETY]` or `[]`. |
| `default_cargo_type` | e.g. `PASS`, `COAL`, or `DEFAULT_CARGO_FIRST_REFITTABLE`. |
| `ai_special_flag` | `AI_FLAG_PASSENGER` or `AI_FLAG_CARGO`. |
| `capacity` | units carried.  Locomotives use `1` (the engine itself). |
| `capacity_by_cargo` | optional `LABEL=value` pairs joined with `\|`; makes the capacity depend on the cargo. |
| `loading_speed` | base loading speed, the GRF parameter multiplies it. |
| `cargo_age_period` | base cargo age period. |
| `wagon_decay` | `1` makes the wagon decay parameter apply as well. |
| `ac_supply` | `1` if the vehicle feeds the train (head end power).  Locomotives and generator cars. |
| `airconditioned` | `1` if the vehicle needs head end power, which is what makes comfort and running cost depend on the locomotive. |
| `restaurant` | `1` for restaurant cars; modifies the cost and decay of the consist. |
| `mu` | `1` for multiple unit vehicles, which adds `TRAIN_FLAG_MU` and a start/stop length check. |
| `name_callback` | `1` to show the series name in the depot (locomotives). |
| `train_flags` | extra `TRAIN_FLAG_*` values, `\|` separated. |
| `additional_text` | the depot description.  Leave empty and the generator builds the standard export text (`STR_DESC_EXPORT`); fill it in to supply the *inner arguments* of a `string(...)` call yourself.  `{FULL_NAME}` expands to `STR_FULL_NAME_<ID>`. |
| `comment` | ignored, for whoever reads the table. |

### Things that are deliberately not columns

* **The vehicle ID.**  It is assigned automatically inside the band of the
  category (`src/vehicleid.pnml` records the bands), so two vehicles can never
  collide and adding a row never renumbers anything else.
* **`sprite_id`.**  Every vehicle uses `SPRITE_ID_NEW_TRAIN`, exactly like the
  parent set; it is not an ID space.
* **Switch names and sprite set names.**  They are derived from the `id` and
  the suffix columns.

## `liveries.csv`

| column | meaning |
| ------ | ------- |
| `id` | vehicle the scheme belongs to. |
| `sprite_suffix` | appended to the sprite basename: suffix `green` means the model is `gfx/<folder>/<id>-green.vox`.  Empty means the plain `<id>` model. |
| `string` | the label in the refit menu, e.g. `STR_EXPORT_BLUE` (add it to `docs/str.csv`). |
| `from_year`, `to_year` | the build years during which this scheme was delivered.  `0` and `9999` mean "always". |
| `purchase_suffix` | optional separate basename suffix for the depot sprite. |
| `templates` | optional `\|` separated list of template names, one per section. |

The **row order matters**: the first row for an `id` is index 0, the automatic
choice, and the rest are indices the player can select.  If any scheme carries
a real year range the automatic choice switches on `build_year`, and the
earliest scheme becomes the default.

## `cargo_variants.csv`

| column | meaning |
| ------ | ------- |
| `id` | vehicle the appearance belongs to, must exist in `wagons.csv`. |
| `variant` | short name used to build the switch identifiers. |
| `sprite_suffix` | sprite basename for this appearance.  Empty means "unloaded", which uses the livery sprite directly. |
| `cargo_classes` | cargo class selector, e.g. `bitmask(CC_BULK)`. |
| `cargo_types` | optional `\|` separated cargo labels; when present the row is chosen by `cargo_type_in_veh` instead of by class. |
| `from_index`, `to_index` | cargo counts between which the partial load sprite is shown.  `0, 0` means a single sprite with no partial stage. |
| `template` | sprite template, defaults to `template_standard`. |

The generator builds this chain:

```
switch_<id>_empty            cargo_count < 5     ->  loaded or livery sprite
switch_<id>_cargo_class      cargo_classes       ->  one entry per class row
switch_<id>_cargo_type       cargo_type_in_veh   ->  only for rows with cargo_types
switch_<id>_<variant>_stage  cargo_count         ->  partial load / full load
```

When a wagon has several liveries every switch name carries the livery suffix
and both chains are independent.

## Sprite files

For every basename the generator records (`<id>`, `<id>-<livery>`,
`<variant>-<livery>`, …) a file `gfx/<folder>/<basename>.vox` is needed.
`genpnml.py --vox` writes a coloured placeholder for each of them, so a new row
builds immediately; replacing a `.vox` with real artwork is all that is left to
do.  `renderobject` turns `<basename>.vox` into `<basename>_32bpp.png`, which is
the file the PNML references.

Each `gfx/<folder>/` needs its own `manifest.json` and `ttd_palette.json`,
because that is where the renderer looks for them.  `genpnml.py --vox` writes
both.
