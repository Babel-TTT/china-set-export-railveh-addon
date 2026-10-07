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
python3 genpnml.py --data data --out src           # write the PNML
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
voxel models, which is how the current empty state was produced.

`#` starts a comment.  A comment may appear anywhere, including between data
rows.  List valued cells use `|` as the separator so that the CSV stays
readable, for example `bitmask(CC_BULK|CC_COVERED)` and `[PASS|TOUR]`; a comma
works too but then the cell has to be quoted.

**Keep comment lines free of double quotes**, or use them in pairs on one line.
The tables are read with Python's csv module, which tracks quoting across lines:
one unbalanced `"` in a comment swallows the following lines into a single
record, and the vehicle row after it silently disappears from the workbench and
from `genpnml.py`.

### Yes/no flags

The flag columns (`ac_supply`, `airconditioned`, `restaurant`, `mu`,
`name_callback`, `wagon_decay`) are read through `_bool()` in `genpnml.py`:

* **`1` means true, `0` means false.**  Write those two, as the column
  reference below and the web workbench both do.
* An **empty cell** falls back to the generator's default for that column, which
  differs per column — `name_callback` is on for locomotives and off for
  coaches and wagons, `wagon_decay` is on for `wagons.csv` and off elsewhere.
  Leave it empty when you want the default rather than spelling it out.
* The reader also accepts `y`, `yes`, `true`, `t` and `on` (upper or lower case,
  surrounding spaces ignored) as true.  They are legal but unused in this
  project; prefer `1`.
* **Anything else is false, without warning.**  `no`, `off` and `false` are
  *false*, which is what you would expect, but a typo such as `nope` is quietly
  false as well.  If a flag seems to have no effect, check the spelling first.

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
| `folder` | sub folder of `gfx/` holding the model, and the first argument of the sprite templates.  May be a nested path of up to four segments (`export/dprk/df4c`).  See [sprite files](#sprite-files). |
| `parts` | the section lengths, `\|` separated: `<short>\|<body>\|<short>`, normally `2\|8\|2`.  The **number of values is the number of sections** the vehicle has, and one value is a plain non-articulated vehicle.  The unit is 4 px, so `8` is about 32 px long.  The short sections at the ends exist to make the vehicle fit the track; the body section carries the sprite and the load.  The count is **normally a multiple of three** — invisible head, cargo body, invisible tail — so a longer unit repeats that group (`2\|8\|2\|2\|8\|2`).  A count that is not a multiple of three is reported as a **warning** and still generates and compiles: `position_in_articulated_veh % N` works for any N, so this is a convention about the artwork (and what `min_cars` and the shared `switch_length_2_<body>_2` switch assume), **not a NewGRF requirement**. |
| `power_section` | index of the **body** section: the one that carries the load, draws the body sprite when a scheme names no per section rules, and shows the head end power effect.  `1` for the standard three section layout.  The column keeps its historical name; **power and weight are whole vehicle properties and are not distributed across sections** — see [capacity and sections](#capacity-and-sections). |
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
| `capacity` | units carried.  **`0` is valid** — a locomotive carries nothing.  NML rejects `cargo_capacity: 0` in the property block, so the generator always emits the value through the `cargo_capacity` graphics callback instead and leaves a non-zero fallback in the property block.  See [capacity and sections](#capacity-and-sections). |
| `capacity_by_cargo` | optional `LABEL=value` pairs joined with `\|`; makes the capacity depend on the cargo.  Cargos that are not listed use `capacity`. |
| `loading_speed` | base loading speed, the GRF parameter multiplies it. |
| `cargo_age_period` | base cargo age period. |
| `wagon_decay` | `1` makes the wagon decay parameter apply as well. |
| `ac_supply` | `1` if the vehicle feeds the train (head end power).  Locomotives and generator cars. |
| `airconditioned` | `1` if the vehicle needs head end power, which is what makes comfort and running cost depend on the locomotive. |
| `restaurant` | `1` for restaurant cars; modifies the cost and decay of the consist. |
| `mu` | `1` for multiple unit vehicles, which adds `TRAIN_FLAG_MU` and a start/stop length check. |
| `min_cars` | shortest train a multiple unit may leave the depot as, counted in three car units (one unit is one vehicle).  Empty or `0` means no minimum, so a single unit may run alone.  Only read when `mu` is set. |
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

### Capacity and sections

A vehicle never carries cargo in every section.  On stock that OpenTTD treats
as 2-&lt;body&gt;-2 the load belongs to one section, and a locomotive carries
nothing at all.  NML does not accept `cargo_capacity: 0` in the property block,
so the generator supplies the value through the **`cargo_capacity` graphics
callback** and gives the `position_in_articulated_veh` switch one case per
section:

```
switch (FEAT_TRAINS, SELF, switch_<id>_capacity, position_in_articulated_veh % 3) {
    1: return 62;     // the section named by power_section carries the load
    return 0;         // every other section carries nothing
}

item (FEAT_TRAINS, <id>) {
    property {
        cargo_capacity: 1;            // non-zero fallback; NML rejects 0
    }
    graphics {
        cargo_capacity: switch_<id>_capacity;
    }
}
```

This is the pattern China Set: Trains and JPengines both use, for example
`switch_g70_capacity`.  Consequences for the tables:

* `capacity = 0` is meaningful and safe: the vehicle carries nothing, which is
  what a locomotive should report.
* The section that carries the load is `power_section`; the others always
  report `0`, so a two-section vehicle cannot count its load twice.
* With `capacity_by_cargo` the section switch falls back to a
  `cargo_type_in_veh` switch, so the load follows the cargo.  Cargos that are
  not listed use `capacity`.

**Power and weight are not distributed.**  Both are plain properties, shared by
the whole vehicle including every articulated section, so the generator writes a
single `power: 2165 kW;` and `weight: 92 ton;` with no switch involved.  This is
what the parent set does too.  Only `cargo_capacity` is read per section by
OpenTTD, which is why it is the only value that needs the callback above.

## Per section graphics

A vehicle is normally three sections (`2|8|2`), so the two short ends are
normally invisible and only the body section (`power_section`) draws.
`graphics_parts` lets a section pick its sprite from **where the car sits in the
whole train**, which is how a real EMU set is built: the cab cars at either end,
the pantograph car in the middle, and so on.

**`graphics_parts` lives in `liveries.csv`**, one cell per paint scheme.  The
artwork that depends on the train's shape is exactly the artwork that differs
between schemes -- an export blue unit and a grey unit want different cab
faces -- so each scheme decides for itself.  A scheme whose cell is empty keeps
the plain behaviour: the body section draws the scheme's own sheet and the ends
stay invisible.

### The cell: one piece per section

The cell is split into **one piece per section** with `;`, so a three section
vehicle needs exactly three pieces.  A trailing `;` is a real fourth piece, not
punctuation, and is refused:

```
consist<=6=emu_face_s | emu_face_l ; emu_body ;
```

Those three pieces are section 1's rules, section 2's sheet, and an **empty
piece**, which leaves section 3 invisible (`empty_sprites`).  Only an entirely
empty cell takes the no-rules path above, where the body section falls back to the
scheme's own sheet.

Each piece is split on `|` into **rules**, and a rule is a *path*: one or more
conditions joined with `=`, then the sprite sheet basename, for example
`consist<=6=pos<=2=h_s`.  A condition itself contains `=` (`<=`, `==`), so the
parser walks the path from the left, cuts off the longest valid condition each
time, and what is left has to be a basename of `[a-z0-9_]+`.  A rule that is
nothing but conditions, with no basename, is refused.

| variable | means |
| -------- | ----- |
| `pos` | `position_in_consist` — which vehicle part this is, counting from the front |
| `tailpos` | `position_in_consist_from_end` — the same counting from the rear |
| `consist` | `num_vehs_in_consist` — how many parts the whole train has |
| `unitpos` | `position_in_articulated_veh` — which section of *this* car it is |

Both spellings work: the short name above is a convenience alias for the NML
variable next to it (`pos<=2` and `position_in_consist <= 2` are the same
condition), and spaces around the operator are optional.

Each condition must be a simple comparison of one variable with an unsigned
number: `consist <= 6`, `pos == 0`, `tailpos >= 3`, `unitpos == 1`.  Operators are
`==`, `<`, `<=`, `>`, `>=`.  `!=` and `!` are refused, as is a `&` inside one
condition, an unknown variable, an upper case variable name and arithmetic such as
`pos / 3 == 1` -- use `pos == 3` or rearrange the rules instead.  `unitpos` is
legal, but the section switch already selects on
`position_in_articulated_veh % <sections>`, and which section a rule belongs to is
written by its position in the cell, so a condition on it is usually redundant.

### Rules become nested switches

Rules are read in the order they are written and merged into one switch tree per
section:

* several rules on **one variable** are several cases of one switch, tried top to
  bottom: `pos<=2=a | pos>2=b` is one switch with the cases `0..2` and `3..255`;
* a rule on a **different variable** becomes the `default` of the switch before
  it, so the chain continues one level down:
  `pos<=2=set_head | tailpos<=2=set_tail | set_mid` is two switches in series;
* a rule that **stops part way down** is the default of the level where it
  stopped: `consist<=6=pos<=2=h_s | consist<=6=h_l | b_l` reads "on a train of up
  to six parts the parts with `pos<=2` show `h_s` and the rest `h_l`; any other
  consist length shows `b_l`";
* a **bare basename** (no condition at all) is the section's catch-all: it is the
  default of the deepest switch.

A variable may be selected on **at most once along one path**: once a switch has
branched on `pos`, a deeper condition on `pos` could never say anything new, so
the parser refuses it
(`第 N 段里重复使用了 <variable>；同一条路径上的每个条件要换一个变量`).  Two
rules naming one condition with **different** sheets are refused
(`同时指定了模型 … 一个截面上只有一个模型`), because one value cannot show two
sheets, and a case an earlier sibling **fully covers** is refused too
(`被前面的条件完全覆盖，永远不会生效`) -- write the narrower range first.  A
switch is emitted even with a single case, because its default is what makes the
case conditional; only a section that names no condition at all is just a
spriteset.

A section shows a sheet only where a rule says so: an empty piece, and a value no
rule matches, are both `empty_sprites`.

**Why the conditions are so plain.**  NewGRF only exposes these variables as the
*selector* of a switch, never inside a condition.  Writing
`switch (..., 1) { num_vehs_in_consist <= 6: ... }` makes nmlc stop with
`Unrecognized identifier`, and a switch can only select on one variable, so each
condition becomes one selector level and the levels nest, exactly the way China
Set: Trains writes its EMUs by hand:

```
switch (FEAT_TRAINS, SELF, switch_<id>_<scheme>_<section>, num_vehs_in_consist) {
    0..6: return switch_<id>_<scheme>_<section>_0;   // consist<=6=pos<=2=h_s
    return spriteset_<id>_gfx_b_l;                   // the bare basename
}
switch (FEAT_TRAINS, SELF, switch_<id>_<scheme>_<section>_0, position_in_consist) {
    0..2: return spriteset_<id>_gfx_h_s;
    return spriteset_<id>_gfx_h_l;                   // consist<=6=h_l
}
```

The scheme index is part of every switch name, so two schemes of one vehicle
cannot collide:

```
switch_<id>_graphics                cargo_subtype   ->  one case per scheme
switch_<id>_section_<scheme>        position_in_articulated_veh % <sections>
switch_<id>_<scheme>_<section>      the section's first condition
switch_<id>_<scheme>_<section>_<n>  a nested condition
switch_<id>_<scheme>_<section>_next the chain continuing on another variable
```

Two schemes may share a section graphic by naming the same basename; the
spriteset is then declared once.  Naming the same basename with different
`templates` is refused, because one file cannot be drawn two ways.

Every basename named here needs a model of its own, exactly like any other
sprite; the generator reports the ones that do not exist yet.
`tools/check_graphics_parts.py` generates and compiles a spread of accepted cells
with nmlc, and checks that each refused cell produces the message that explains
why.

## Multiple unit train length

A multiple unit car is bought as one three section vehicle.  A train is built by
coupling those vehicles, so the length of an EMU is always a whole number of
three car units.  `start_stop` enforces exactly that, and nothing else:

```
switch (FEAT_TRAINS, SELF, switch_<id>_whole_units,
        (num_vehs_in_consist % 3) != 0) {
    1: return string(STR_MUST_BE_MULTIPLE_OF_3);
    return CB_RESULT_NO_TEXT;
}
```

With `min_cars` set, that switch is nested behind a length check:

```
switch (FEAT_TRAINS, SELF, switch_<id>_start_stop, num_vehs_in_consist < 6) {
    1: return string(STR_MUST_BE_4_TO_24_CARS);
    return switch_<id>_whole_units;
}
```

`min_cars = 2` is the example above: six sections, so two units.  Consequences:

* `min_cars` empty or `0` means a single unit may be started on its own.
* There is **no upper limit**.  The parent set capped a multiple unit at 24
  cars (`mu4to24car`); that cap is deliberately not applied here, because the
  point of coupling units is that the player decides how long the train is.
* The old shared `mu4to24car` switch in `src/functions.pnml` is unused by
  generated vehicles now.  It is kept only so hand written files that reference
  it still compile.

## `liveries.csv`
| column | meaning |
| ------ | ------- |
| `id` | vehicle the scheme belongs to. |
| `sprite_suffix` | appended to the sprite basename: suffix `green` means the model is `gfx/<folder>/<id>-green.vox`.  Empty means the plain `<id>` model. |
| `string` | the label in the refit menu, written `LV_<NAME>`.  The generator maps it onto the NML constant `STR_LV_<NAME>`, so the label is `LV_EXPORT_BLUE` and `docs/str.csv` holds `STR_LV_EXPORT_BLUE`.  A bare `STR_<NAME>` cell is still accepted. |
| `from_year`, `to_year` | the build years during which this scheme was delivered.  `0` and `9999` mean "always". |
| `purchase_suffix` | optional separate basename suffix for the depot sprite. |
| `templates` | optional `\|` separated list of template names, one per section. |
| `graphics_parts` | this scheme's per section sprite rules; see [per section graphics](#per-section-graphics).  Empty means only the body section draws and the ends stay invisible. |

The **row order matters**: the first row for an `id` is index 0, the automatic
choice, and the rest are indices the player can select.  If any scheme carries
a real year range the automatic choice switches on `build_year`, and the
earliest scheme becomes the default.

**The label, not the file name, is what identifies a scheme to the player.**  The
refit menu is generated per vehicle and each entry's text comes from that row's
`string`, so two schemes of one vehicle sharing a label are listed as two
identical entries and cannot be told apart — the only thing distinguishing them
is then a sprite file name, which is the coupling `LV_` labels exist to replace.
Give each scheme of a vehicle its own `LV_<NAME>`.  Sharing a label across
*different* vehicles is fine, because each vehicle has its own menu.

Reusing a label within one vehicle is reported as a **warning**, not an error:
delivering one scheme with several models is legitimate, it just has to be said
out loud.  The workbench badges such rows and the string table counts how many
rows use each label.

Two rows of one `id` may **not** resolve to the same basename: the generator
would declare the same sprite sheet twice.  Overlapping year ranges compile
(nmlc picks the earliest matching case) but are reported as a warning, because
the earlier row silently wins inside the overlap.

Because all four identifying cells are editable, the workbench addresses a
livery row by its position in this table rather than by its contents, and its
「涂装管理」 tier shows each row's resolved basename next to the suffix.  See
[web/workbench/README.md](../web/workbench/README.md).

### Livery labels and the string table

A livery label is deliberately kept out of the `STR_` crowd: writing
`LV_EXPORT_BLUE` in this table produces `STR_LV_EXPORT_BLUE` in
`docs/str.csv`, so every paint scheme label sorts together and the workbench's
string table can filter for exactly that family.

`docs/str.csv` ships six of them (`STR_LV_ORIGINAL`, `STR_LV_BUILD_YEAR`,
`STR_LV_EXPORT_BLUE`, `STR_LV_EXPORT_GREEN`, `STR_LV_EXPORT_GRAY`,
`STR_LV_DPRK`).  Any other `LV_<NAME>` has to be added to the table, either by
the workbench's 字符串表 page or by appending a row by hand; `make gen` keeps
hand written rows.  `genpnml.py --check` reports a label that is missing.

A project written before the convention existed can be converted with:

```bash
python3 tools/migrate_lv_labels.py --dry-run
python3 tools/migrate_lv_labels.py
```

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

For every basename your rows name (`<id>-<livery>`, `<variant>-<livery>`, the
basenames in a scheme's `graphics_parts`, …) you need a model
`gfx/<folder>/<basename>.vox`.  **The generator does not create models** — it
prepares each folder and then prints which models are still to be drawn:

```
genpnml: 1 vehicles -> 4 files (0 removed), 1 gfx folder(s) prepared
genpnml: 1 model(s) still to be drawn:
  gfx/dprk/df4c/df4c-korea-2.vox
```

`renderobject` (through `make sprites`) turns `<basename>.vox` into
`<basename>_32bpp.png`, which is the file the PNML references, so a model has to
exist before the project can compile.  `tools/verify_assets.py` lists the
missing ones the same way.

A vehicle whose schemes all carry a suffix does **not** need a plain `<id>.vox`:
that file is only the spriteset a scheme with an empty suffix uses.

Each `gfx/<folder>/` needs its own `manifest.json` and `ttd_palette.json`,
because that is where the renderer looks for them.  The generator writes both: the
manifest from `write_manifest()` (eight views, 36 / 120 / 192 px cells) and the
palette copied from `gfx/ttd_palette.json`.  It creates the folder too, so a new
nested `folder` value works without preparing anything by hand.

Both come from China-Set-Trains, and `src/template.pnml` crops the sheets with
exactly the rectangles the manifest describes — so a stray copy would silently
change how a model is rendered or cut out.  Check them with:

```bash
python3 tools/check_gfx_config.py
python3 tools/check_gfx_config.py --reference /path/to/China-Set-Trains
```

The manifest it compares against is the one 76 of the 77 copies in
China-Set-Trains use; the odd one out is `gfx/steam/extralength/`, which uses
256 px cells for extra-long steam locomotives.

### Nested folders

The `folder` column may be a **multi level path**, up to four segments, each
made of letters, digits, `_`, `.` and `-`:

```
diesel
diesel/df4c
export/dprk/df4c
```

Then `gfx/export/dprk/df4c/` holds the models, `src/export/dprk/df4c/` holds the
generated PNML, and `make sprites` renders every level (the Makefile collects
one to four levels deep — `find` is not used because on stock Windows it is
`find.exe`, the text search tool).

This works because a sprite template's first parameter is the folder **path as a
plain string**, not an identifier:

```
template template_standard (folder, b) {
    [0, 0, 36, 166, -14, -80, "gfx/"+folder+"/"+b+"_32bpp.png"]
    ...
}
spriteset (spriteset_df4c_origin, ZOOM_LEVEL_IN_4X, BIT_DEPTH_32BPP) {
    template_standard ("dprk/df4c", "df4c-origin")
}
```

Do not try to rewrite the path inside the template with `subst()`: nmlc 0.9.0
has no string functions and stops with `'subst' is not defined as a function`.
The path has to be passed through whole.

A suffix that is a file name fragment may contain dashes (`korea-1` gives the
sheet `df4c-korea-1`).  NML *identifiers* may not, so the generated spriteset
and switch names fold every run of non-alphanumerics into one underscore:
`spriteset_df4c_korea_1`.  The sprite sheet keeps its dashes.
