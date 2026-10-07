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

- **A livery row could not be deleted.**  `liveries.csv` had no key: a row was
  identified by all four editable cells at once (`id`, `sprite_suffix`,
  `from_year`, `to_year`), and the browser built that key with `|| ''` defaults
  while the server built it without them.  Editing any one of the four made the
  row unfindable, so the workbench answered "liveries.csv 中找不到该行" for a row
  that was plainly in the table.  An auxiliary row is now identified by its
  **position**, exactly like a vehicle row: the browser sends the `_index` it
  rendered and the server takes that row, falling back to key matching only when
  no index is available.

- `docs/str.csv` lost hand written rows on every `make gen`.  `render_strings()`
  only preserved the third column of the rows it generates itself, so a livery
  pointing at a constant that is neither in `STATIC_STRINGS` nor derived from a
  vehicle was silently dropped by the next build.  It now keeps any row it does
  not generate, as long as that row has text in it.

- The cargo variant rows were saved and deleted through the same broken key
  scheme; they are index identified now as well.

- `GET /api/state` answered `400` on every browser refresh, because
  `ConnectionAbortedError` is an `OSError` and was caught by the generic handler
  as a real failure.  A client that hangs up is now ignored, and a real failure
  logs its type and traceback.

### Added — nested `gfx` folders and dashes in a sprite suffix

The `folder` column may be a multi level path of up to four segments
(`diesel/df4c`, `export/dprk/df4c`).  `gfx/` and `src/` follow it, `make sprites`
collects one to four levels deep, and `genpnml.py --vox` writes the per folder
`manifest.json` and `ttd_palette.json`.

This needed three fixes that only a nested path exposes:

- A sprite template's first parameter has to be the folder **path as a string**,
  not an identifier, because NML identifiers may not contain `/`.  The parameter
  is called `folder` now instead of `a`, and the generator passes the path
  through whole.  `subst()` is not an option: nmlc 0.9.0 reports
  `'subst' is not defined as a function`.
- `make sprites` used three levels of `$(wildcard)`; it now covers four, and the
  comment records why `find` is not used (on stock Windows it is `find.exe`, the
  text search tool).
- A suffix is a file name fragment and may legitimately contain dashes
  (`korea-1` makes the sheet `df4c-korea-1`), but spriteset and switch names may
  not.  Runs of non alphanumerics are folded into one underscore, so the sheet
  keeps its dashes and the identifier becomes `spriteset_df4c_korea_1`.  A
  suffix that starts with a dash — the old way of writing a whole-basename
  suffix — no longer produces a double dash.

The workbench's folder validation follows: it normalises backslashes to
slashes, rejects absolute paths, `.`/`..`/empty segments and more than four
segments, and reports which segment is at fault.

### Removed — dead weight, and a landmine under `parts`

Dead code, all of it unreachable:

- `Vehicle.model`, the `model != "triple"` check and `model=` in `_build_vehicle`.
  The column was dropped from the tables long ago, so `row.get("model", "")`
  always returned `""` and the check always passed.
- `Vehicle.graphics_parts` and the vehicle-wide fallback in `load_vehicles()`.
  The cell is empty in every table, so the branch could never fire.
- `Vehicle.body_part` (never called), `Vehicle.vox_part` (written, never read).
- `Vehicle.is_articulated`, which had become a constant: every vehicle is 3+
  sections, so the five branches that tested it are now unconditional.
- The dead `graphics_parts` validation in the workbench, and
  `data/*.csv`'s `graphics_parts` column via
  `tools/migrate_drop_vehicle_graphics_parts.py` (the tables are back to
  **46 columns**).

And one real defect the cleanup uncovered:

- **`parts` with a body length outside 1..8 produced a compile error.**
  `length_switch` built `switch_length_2_<body>_2` for *any* three section
  shape, but `src/functions.pnml` only declares those for a body of 1..8, so
  `parts=2|10|2` generated a reference to a block that does not exist and nmlc
  stopped with `Unrecognized identifier 'switch_length_2_10_2'`.  Any other
  section count emitted no `length` property at all.

  The generator now names a shared switch only when one exists and otherwise
  emits `switch_<id>_length` for that vehicle.  It cannot be an inline switch in
  the property: NML answers `Syntax error, unexpected token "switch"`, which is
  how the first attempt at this fix failed.
  `tools/check_section_lengths.py` compiles a spread of shapes
  (`2|8|2`, `2|1|2`, `2|10|2`, `2|16|2`, `3|8|3`, `2|1|1`, `2|8|6`, `2|8|2|2`,
  `2|8`, `6`) and restores the tables afterwards.

### Removed — the generator no longer writes placeholder voxel models

`genpnml.py --vox`, `build_placeholder_vox()`, `write_vox()`, `VOX_PALETTE` and
`SUFFIX_COLOUR` are gone, and `make gen` no longer passes `--vox`.  A placeholder
is a file you have to notice and delete before your own model can be trusted, and
the "kept existing .vox" guard added earlier only made that less predictable.

What replaces it is a report.  The generator still prepares each `gfx/<folder>/`
(the `manifest.json` and `ttd_palette.json` that gorender/renderobject read, and
the folder itself, so a nested `folder` value needs no manual setup) and then
says what is missing:

```
genpnml: 1 vehicles -> 4 files (0 removed), 1 gfx folder(s) prepared
genpnml: 1 model(s) still to be drawn:
  gfx/dprk/df4c/df4c-korea-2.vox
```

`tools/verify_assets.py` lists the same gaps.  The workbench lost its
「只写占位模型」 action and its 「占位模型 / 精灵图」 panel is just a sprite
preview now.

`collect_sprite_basenames()` also stopped listing the bare `<id>`
unconditionally.  It is the spriteset a livery with **no** suffix uses, so it is
listed when such a livery exists — otherwise the missing-model report named a
file the generated code never referenced, which is how `--vox` first hid the
problem: `df4c.pnml` references only `df4c-korea-1`, yet `df4c.vox` was expected.

The four placeholder models that were in the repository are deleted along with
their renders.  The seven real `.vox` models are untouched.

### Added — a check that the gorender manifest and palette are the canonical ones

`make sprites` reads a `manifest.json` and a `ttd_palette.json` from the folder
each `.vox` lives in, and `src/template.pnml` crops the sheets with exactly the
rectangles the manifest describes, so one stray copy silently changes how a
model is rendered — or how it is cut out.  `tools/check_gfx_config.py` compares
every copy in `gfx/` against what `genpnml.write_manifest()` produces and
against a China-Set-Trains checkout:

```
manifests on disk: 3      all match the generator (8 views, 36/120/192 px)
palettes on disk: 4       all the same content
reference: 78 palettes    the commonest one is in 69 of them -> matches
reference: 77 manifests   2 distinct contents -> matches the common one
```

Both files already were the standard China-Set-Trains ones: the manifest is the
variant used by 76 of 77 reference copies, and the palette is the one used by 69
of 78.  The comparison ignores line endings on purpose — this project is LF
(`.gitattributes`) while China-Set-Trains is CRLF, which is the whole of the
16142 vs 14653 byte difference — and the tool prints both the raw and the
content digest, because confusing the two is exactly what made a matching file
look like a stray one.

The 1 reference manifest that differs is `gfx/steam/extralength/manifest.json`
(256 px wide cells for extra-long steam locomotives), which is a deliberate
special case rather than the standard sheet.

### Added — a reused livery label is now visible

A livery is identified in the refit menu by its **string**, so two schemes of
one vehicle sharing a label are listed as two identical entries and the player
cannot tell them apart — the only thing distinguishing the rows is then a file
name, which is exactly the coupling the string is supposed to replace.  This is
surfaced in three places:

- the livery row carries a `名称与另外 N 行重复` badge when its label is shared
  inside the same vehicle;
- the string table shows how many livery rows use a label, and marks it
  `同车重名` in the case that actually breaks the menu.  A label shared across
  *different* vehicles is normal, because the refit menu is per vehicle, so the
  count is kept per vehicle and only that case is flagged;
- saving such a row reports it as a warning.

It is deliberately a **warning, not an error**: delivering one scheme in several
models is a legitimate thing to want.  It only has to be said out loud, because
otherwise nothing distinguishes the menu entries.

### Fixed — a write is refused when the file changed while it was being read

Every table write is a read-modify-write of the whole file.  `read_table()`
records the file's modification time and `write_table()` refuses to proceed if
the file moved on in between, answering `409` with `reload: true`; the browser
then re-reads the repository and the change can be repeated.  Before this, a
change landing inside that window was destroyed without a word.

### Fixed — the string table emptied itself after a save or a delete

Saving or deleting a string made the whole list vanish, so the page had to be
reopened from the sidebar.  Three separate defects added up to that:

- `/api/strings` published **two** lists: `strings` (with the `kind`
  classification) and `rows` (without it).  The browser rendered `rows` while
  filtering on `kind`, so after a reload nothing matched the kind filter and the
  list came out empty.  There is one list now, and it carries `kind`.
- `string_table_rows()` did not skip the CSV header, so
  `STRING,ENGLISH,SIMPLIFIED CHINESE` was published as a string row.  `STRING`
  is only five characters and does not match `STR_[A-Z0-9_]+`, so the generator
  never kept it — the editor showed a row that could not be saved ("字符串表里没有
  STRING") and that the next `make gen` removed.  The header is now recognised in
  one shared helper used by the workbench and by `genpnml.py`
  (`render_strings()` and `load_string_table()` had the same gap).
- `genpnml.py --check` reported that phantom row as `STRING is defined but never
  used`.

`tools/check_string_table.py` guards all of it: the two readers must agree, the
header must never be published, the generator must see exactly the published
constants, and a save must not change the row count.  It starts its own server
on a free port, so it runs standalone.

### Changed — the section index is about the body, not the power

Power and weight have been whole vehicle properties since the callback was
removed, so the column that used to say "the section carrying the body sprite,
the power and the capacity" was describing something that no longer exists.
`power_section` still drives four things — which section carries the load, which
section draws the body sprite when a scheme names no per section rules, where
the head end power visual appears, and how long the placeholder model is — so
the column stays, but it is labelled **车身段索引** now and both the label and
the help text say what it actually does.

The stale documentation went with it: `data/README.md` claimed `parts` and
`power_section` carried "the power", `docs/pnml-generation.md` documented
`switch_<id>_weight` ("整备重量按段均分") and `switch_<id>_power`, neither of
which has been generated for some time, and the guide still listed a `model`
column in its column reference.

### Fixed — an unbalanced quote in a comment hid a whole table row

`data/locomotives.csv` and `data/cargo_variants.csv` carried comment lines with
an odd number of double quotes (`use ""|"" as the separator`, `means "unloaded,
use the livery sprite itself"`).  Python's csv module tracks quoting across line
breaks, so such a comment swallows the following lines into one record: the
vehicle row after it vanished, the workbench listed zero vehicles while still
listing their liveries, and nothing reported an error.  The comments are fixed
and `data/README.md` now states the rule.

### Fixed — `--vox` no longer overwrites a real model with a placeholder

`genpnml.py --vox` wrote a coloured placeholder over every basename it needed,
including the ones that already held somebody's artwork, so running `make gen`
after adding a livery silently replaced the models of the other liveries with
11388 byte cubes.  An existing `.vox` is kept now and the run reports how many
it kept; `--force-vox` restores the old behaviour for the case where the
placeholders are genuinely wanted.

The per folder `ttd_palette.json` is also copied as text with LF endings now,
because a binary copy of a CRLF checkout left the file showing as modified for
ever without any content difference.

### Fixed — a legacy livery label no longer breaks the build

Renaming the six livery labels to `STR_LV_*` left every table that still wrote
`STR_ORIGINAL` pointing at a constant that no longer exists, which `--check`
reported as missing and nmlc rejected.  Those six names are now mapped across to
their `STR_LV_` equivalents, so an older table keeps resolving to the same text
instead of failing.

### Changed — `graphics_parts` belongs to the paint scheme

Per section graphics used to be a column of the vehicle tables, which was wrong:
the artwork that depends on the train's shape is exactly the artwork that
distinguishes the paint schemes, so a blue and a grey unit need different cab
faces.  Every scheme now carries its own `graphics_parts` in `liveries.csv`.

- Each scheme gets its own switch chain, and the scheme index is part of every
  switch name, so two schemes of one vehicle cannot collide:
  `switch_<id>_graphics` selects by `cargo_subtype`,
  `switch_<id>_section_<scheme>` selects by `position_in_articulated_veh`, and
  `switch_<id>_<scheme>_<section>_s0` selects by the consist variable.
- A scheme with no rules keeps the plain behaviour: only the body section draws
  and the ends stay invisible.  Older vehicles with several schemes used to get
  a `switch_<id>_livery` for the year and cargo selection; the new dispatch
  replaces it, so it is only emitted when it is actually referenced (otherwise
  nmlc reported it as an orphan block).
- The vehicle-wide `graphics_parts` column was kept at first as a **deprecated
  fallback**, and has since been dropped: the column is empty in every table, so
  the fallback was a branch nothing could reach and a column nothing could fill.
- Two schemes may share a section graphic by naming the same basename; the
  spriteset is then declared once.  Naming one basename with two different
  `templates` is now refused, because a single file cannot be drawn two ways.
- A malformed rule now names the scheme it came from
  (`df4c 涂装 #1（green）第 2 段：…`) instead of only the vehicle.

### Changed — livery labels are `LV_` names, and the string table filters

A livery label was written as a bare `STR_<NAME>`, which buried it among a
hundred other constants.  It is written `LV_<NAME>` now and mapped onto
`STR_LV_<NAME>`, so every paint scheme label sorts together:

- `docs/str.csv` ships `STR_LV_ORIGINAL`, `STR_LV_BUILD_YEAR`,
  `STR_LV_EXPORT_BLUE`, `STR_LV_EXPORT_GREEN`, `STR_LV_EXPORT_GRAY` and
  `STR_LV_DPRK`.  A bare `STR_<NAME>` cell is still accepted.
- `tools/migrate_lv_labels.py` renames an older table's six constants in place,
  keeping their translations.
- The workbench's string table gained **kind filters** (涂装 `LV_` / 车辆名 /
  界面) with counts, opens on the livery group, and shows the short `LV_` form
  in the livery name picker.  Search still covers all three columns.

### Changed — the workbench is one workspace instead of three screens

The vehicle, its paint schemes and its per-section artwork are one thing in
three layers, not three parallel pages, so the workbench now presents them on
one page in dependency order:

1. **车辆属性** — what the vehicle is (the four vehicle tables);
2. **涂装管理** — which paint schemes it has, each showing the resolved model
   file `gfx/<folder>/<id>[-<suffix>].vox` and that file's state, with add /
   edit / copy / delete / reorder;
3. **分节图像** — for the selected scheme, what each section shows and where
   (`graphics_parts`), parsed into a rule table with every referenced basename
   and its file state.

The old `车辆明细`, `涂装方案` and `模型与精灵图` stages are gone; `车队账本`
became `车队总览`, and a new **字符串表** stage edits `docs/str.csv` directly —
adding a constant no longer means leaving the page, which is what made a livery's
`STR_` reference hard to follow.

- Livery rows can now be reordered from the workbench.  A row's position in
  `liveries.csv` *is* the refit menu index, so moving a row is an edit; the
  arrows refuse to cross into another vehicle's block.
- The livery `string` field is a dropdown that shows the resolved text
  underneath and turns red when the constant is undefined.
- `POST /api/move`, `POST /api/string` and `POST /api/string-delete` were added;
  `GET /api/strings` now publishes the whole language table including its
  comments.
- Two livery rows of one vehicle that resolve to the same `.vox` basename are
  now rejected: the generator would declare the same sprite sheet twice.
  Overlapping year ranges are only a warning — nmlc picks the earliest case, so
  it compiles, it is just rarely what was meant.

### Fixed

- `data/locomotives.csv`, `coaches.csv`, `wagons.csv` and `unit_wagons.csv`
  were missing the `capacity_by_cargo` and `train_flags` columns that
  `genpnml.py` already read, so both silently never had any effect.  They are
  now columns 35 and 38 of all four tables (46 columns total), matching what
  `data/README.md` documented.

- Cargo capacity is now supplied by the `cargo_capacity` graphics callback
  instead of a plain number in the property block.  NML rejects
  `cargo_capacity: 0`, which made a locomotive with `capacity = 0` impossible,
  and a plain number forced the same capacity onto every articulated section.
  The callback switches on `position_in_articulated_veh`, returns the load for
  the section named by `power_section` and `0` for the others, and falls back
  to `cargo_type_in_veh` when `capacity_by_cargo` is set.  A single section
  vehicle gets the same callback.  This is the pattern China Set: Trains
  (`switch_g70_capacity`) and JPengines both use.

### Notes

- The performance figures in `data/*.csv` are reasonable engineering estimates
  and still need to be checked against the builders' plates.
- The voxel models are placeholders generated by `genpnml.py`; they are
  correctly shaped and coloured but are not artwork.
- Placeholder renders show an opaque white block under the model.  It comes
  from `renderobject` on the generated placeholder `.vox`, is outside every
  rectangle `src/template.pnml` crops, and is expected to disappear once a real
  model replaces the placeholder.  It is visible in the workbench on purpose.

### Changed — `graphics_parts` is a switch tree

The cell was a flat list of `condition=basename` rules with a callback list of its
own.  It is now one piece per section separated by `;` (**a trailing `;` is a real
section**, so the piece count has to match the number of `parts`), each piece one
rule per `|`, and a rule is a **path**: every condition on the way down, then the
sprite sheet basename, all joined with `=`, e.g.
`consist<=6=pos<=2=h_s | consist<=6=h_l | b_l`.  A condition may name its variable
by the short table name (`pos`, `tailpos`, `consist`, `unitpos`) or by the NML name
(`position_in_consist`, …), and spaces around the operator are optional.

The generator merges the paths into a tree and compiles it into **nested NML
switches**, one condition per level:

- rules on one variable are several cases of one switch, tried top to bottom, so
  `pos<=2=a | pos>2=b` is one switch with `0..2` and `3..255`;
- a rule on another variable becomes the **default** of the switch before it, so
  the chain continues one level down:
  `pos<=2=set_head | tailpos<=2=set_tail | set_mid` is two switches in series;
- a rule that stops part way down is the default of the level where it stopped:
  `consist<=6=pos<=2=h_s | consist<=6=h_l | b_l` means "up to six parts: `pos<=2`
  shows `h_s`, the rest `h_l`; anything longer shows `b_l`";
- a bare basename is the section's catch-all, the default of the deepest switch;
- a single case is **not** folded away: its default is what makes the case
  conditional, and only a section that names no condition at all is just a
  spriteset.

A section shows a sheet only where a rule says so: an empty piece and a value no
rule matches are both `empty_sprites`, and the scheme's own whole-car sheet is used
only when the cell is empty entirely.

Refused, each with the message that explains it: a piece count that does not match
`parts` (`graphics_parts 需要 N 段（与 parts 相同），当前 M 段`), one variable
selected twice along one path (`同一条路径上的每个条件要换一个变量`), one case
naming two different sheets (`同时指定了模型 … 一个截面上只有一个模型`), a case an
earlier sibling already covers (`被前面的条件完全覆盖，永远不会生效`), and anything
that is not `变量 比较 数字` (`!=`, `!`, `&` inside one condition, arithmetic, an
unknown variable).

`tools/check_graphics_parts.py` generates and compiles a spread of accepted cells
with nmlc and checks each refused cell for its message.  The workbench's 分节图像
tier draws the tree as indented rows and parses a cell through the generator's own
parser (`GET /api/rules`, 250 ms debounce), reloading `genpnml.py` when it changes
on disk, so the preview cannot disagree with the build.

`parts` whose section count is not a multiple of three is reported as a
**warning**: "invisible head + cargo body + invisible tail", three sections per
group (`2|8|2`, or `2|8|2|2|8|2`), is the convention this set follows, but
`position_in_articulated_veh % N` works for any N, so it is a rule about the
artwork and not a hard NewGRF requirement.

### Changed — the workbench edits rules as switch blocks

The 分节图像规则 field of a paint scheme is now a graphical switch-block editor
rather than a bare text box.  Each section is 隐形 / 一张图 / 按条件分; a block is
one switch (its variable is a dropdown), a row is one case (operator plus value),
and a row's target is either a model or 「再筛一层」, which is a nested switch.  The
outermost switch's 兜底 may also be 「再筛一层」, which is the chain continuing into
the next switch.  The text view is still there under 「直接编辑文本」, and the two
views refresh each other.

Every edit posts the tree to `POST /api/graphics-parts`, which renders it into a
cell with `genpnml.py` and parses that cell again before answering: the editor can
therefore not produce a rule the generator would reject, and what the author sees
is the table's content rather than the browser's idea of it.  A tree the cell
language cannot express (a nested switch that is itself a nested default) is
refused with the reason.

### Changed — GRF ID

The GRF ID is now `\5F\5F\03\09`; it was `\5F\5F\03\01`.  Both places that hold it
are updated: the `grfid:` property in `src/header.pnml`, and the `onlyallowcst`
callback in `src/functions.pnml`, which is what lets this set's stock attach to
this set's multiple unit head cars.  Changing one without the other would make the
set refuse to couple to its own vehicles.

A GRF ID is how a savegame identifies the set, so savegames made with the old ID
report it as missing and drop its vehicles; change over before relying on a save.
Version bumps do **not** need an ID change -- the version travels in Action 14
(`version: REPO_REVISION`, generated from git), which is exactly why the ID has to
stay stable.

### Added — the purchase menu can be grouped and ordered

OpenTTD 13's *vehicle variants in expandable purchase list* (`variant_group`, the
NML property of the same name) is wired up, and the purchase menu order is data
now instead of an accident of the row order:

- Three new columns in all four vehicle tables, just before `comment`:
  **`variant_group`** (the **id** of the vehicle this row folds under, empty for
  an entry of its own), **`menu_order`** (the position in the purchase menu,
  empty sorting last) and **`series_string`** (the `STR_` the folded row shows).
  The vehicle tables are **49 columns** now.
  `tools/migrate_menu_columns.py` adds only the columns a table is missing, so it
  is safe to run again.

- `variant_group` names another vehicle **by id**, not by engine number, and
  reaches the item's `property` block verbatim; NML resolves the identifier to
  the ID itself, so a grouping survives any change in how IDs are handed out.
  It is **per vehicle, not per livery**: two paint schemes of one vehicle are
  chosen inside the refit menu (`cargo_subtype`) and can never become two
  purchase menu entries.

- The order is a column rather than a reordered row because `assign_ids()` walks
  the tables in row order: dragging a row past another changes which engine ID a
  vehicle gets, and engine IDs are what a savegame stores.  The generator sorts
  on `(menu_order or +infinity, table and row index)` and writes
  `src/vehiclesort.pnml` from that, leaving the row order -- and every engine
  ID -- alone.  An empty cell sorts after every row that sets one, in table
  order.

- A vehicle that sets `series_string` gets a name switch of its own
  (`switch_<id>_name`), using the same selector as China Set: Trains.  Slot 0
  answers with the series string and every other slot with `CB_RESULT_NO_TEXT`,
  so the collapsed row reads as the series while the row inside the group keeps
  the vehicle's own `name` property.  A vehicle without one keeps sharing
  `switch_name_series` from `src/functions.pnml`.

- `genpnml.check_variant_groups()` validates the grouping: the parent must exist
  **in the same table**, must not be the vehicle itself, and the links must not
  form a cycle.  A parent that is itself grouped is a **warning** rather than an
  error, because nesting works but is experimental upstream.  The workbench
  calls the same function, so it cannot accept a grouping the build would
  refuse.

- `series_string` joined `collect_referenced_strings()`, so `--check` reports a
  constant that is not in `docs/str.csv` as `MISSING` instead of leaving nmlc to
  answer `Unknown string`.  That scan walks `src/` recursively, which is where
  the generated per vehicle files live (`src/<folder>/<id>.pnml`).

- The workbench's 车队总览 is now shown in purchase menu order, and each card
  edits the three columns: ▲/▼ move the vehicle in that order (renumbering the
  whole list in tens, so a later insert fits between two rows), 折叠到 lists the
  legal parents (same table, never the vehicle itself, never one of its own
  descendants) and 折叠项名称 takes the series constant, flagging an unknown one
  as 「字符串不存在」.  Everything saves through `POST /api/fleet-menu`
  (`{"rows": [{"table", "id", "variant_group", "menu_order", "series_string"}]}`):
  a key that is absent is left alone, an unknown key is refused, and every
  affected table is validated before any of them is written.

- `tools/check_variant_menu.py` creates a temporary second locomotive, folds it
  under `df4c`, builds the whole GRF and checks the grouping, the name callback,
  the two different names and the sort order, then restores the tables.

