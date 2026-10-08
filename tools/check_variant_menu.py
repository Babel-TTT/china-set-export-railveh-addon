#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check the purchase menu chain end to end, then put everything back.

Creates a temporary second locomotive that folds under ``df4c`` and gives it a
series string, builds the whole GRF, and checks the generated code carries the
grouping, the per-vehicle name callback and the sort entry.  This is the only
check that exercises all three columns together, and it compiles a real GRF
rather than inspecting text, so it also proves the emitted NML is accepted.

Every file it touches is restored, and a file that changed underneath it is left
alone rather than reverted -- the workbench may be open in a browser.

    python3 tools/check_variant_menu.py
"""
from __future__ import annotations

import csv
import dataclasses
import io
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import genpnml  # noqa: E402  (the path has to be set up first)

# the workbench's own module, so the two can be compared directly
sys.path.insert(0, str(ROOT / "web" / "workbench"))
import server  # noqa: E402

LOCO = ROOT / "data" / "locomotives.csv"
LIV = ROOT / "data" / "liveries.csv"
LANG = ROOT / "docs" / "str.csv"
GFX = ROOT / "gfx" / "dprk" / "df4c"
# the documented table order, and every table the sort block covers
TABLES = ("locomotives.csv", "coaches.csv", "wagons.csv", "unit_wagons.csv")
TEST = "df4ctest"

failures: list[str] = []


def check(label, condition, detail=""):
    print(("  ok  " if condition else " FAIL ") + label
          + (" :: " + detail if detail and not condition else ""))
    if not condition:
        failures.append(label)


def read_cells(path: Path):
    comments, lines = [], []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.lstrip().startswith("#"):
            comments.append(line)
        elif line.strip():
            lines.append(line)
    records = list(csv.reader(lines))
    header = [cell.strip() for cell in records[0]]
    rows = [dict(zip(header, raw + [""] * (len(header) - len(raw))))
            for raw in records[1:] if raw and raw[0].strip()]
    return comments, header, rows


def write_cells(path: Path, comments, header, rows) -> bytes:
    buffer = io.StringIO()
    for line in comments:
        buffer.write(line + "\n")
    writer = csv.DictWriter(buffer, fieldnames=header, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in header})
    data = buffer.getvalue().encode("utf-8")
    path.write_bytes(data)
    return data


def declared_menu_order() -> list[str]:
    """The purchase order the tables ask for, by the rule the sort block states.

    Read from data/ rather than hardcoded: adding a vehicle to the tables must not
    fail this check -- the tables and the emitted block *disagreeing* must.  The
    rule is the one printed above the block: ``menu_order`` wins and a row that
    leaves it empty comes last, with the table and then the row order as the tie
    breaker.
    """
    ordered = []
    for table_index, name in enumerate(TABLES):
        _comments, _header, rows = read_cells(ROOT / "data" / name)
        for row_index, row in enumerate(rows):
            raw = (row.get("menu_order") or "").strip()
            try:
                key = int(float(raw))
            except ValueError:
                key = 0
            ordered.append((key if key > 0 else 10 ** 6,
                            table_index * 1000 + row_index, row["id"]))
    ordered.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in ordered]


def compile_all():
    """Preprocess the index and compile it, exactly as `make code` does.

    The language files have to exist already (`make` or `make lang`), because this
    deliberately does not run the string step -- see the note in main().
    """
    index = ROOT / "chinasettrainsexport.pnml"
    if not index.is_file():
        # say so instead of letting gcc's "No such file or directory" be reported
        # as "the GRF does not compile", which reads like a code problem
        raise SystemExit("ERROR: %s is missing; run the check from the repository "
                         "root, or check the Makefile's INDEX_FILE" % index)
    nml = ROOT / "variant_menu_check.nml"
    pre = subprocess.run(["gcc", "-E", "-x", "c", index.name,
                          "-D", "REPO_REVISION=0", "-D", "VERSION_STRING=check",
                          "-D", "MIN_COMPATIBLE_VERSION=0"],
                         cwd=str(ROOT), capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    if pre.returncode != 0:
        return pre
    nml.write_text(pre.stdout, encoding="utf-8", newline="")
    result = subprocess.run(["nmlc", "-c", nml.name, "-o", "variant_menu_check.grf"],
                            cwd=str(ROOT), capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    for name in (nml.name, "variant_menu_check.grf"):
        (ROOT / name).unlink(missing_ok=True)
    return result


def main() -> int:
    loco_backup, liv_backup = LOCO.read_bytes(), LIV.read_bytes()
    lang_backup = LANG.read_bytes()
    made: list[Path] = []
    written: dict[Path, bytes] = {}
    try:
        # the two missing sheets: the second df4c livery has no artwork yet and
        # the test vehicle needs its own, so copy the one sheet that exists
        for basename in ("df4c-korean-2", TEST + "-korea-1"):
            for suffix in ("_32bpp.png", "_8bpp.png", "_mask.png"):
                target = GFX / (basename + suffix)
                if not target.exists():
                    shutil.copyfile(GFX / ("df4c-korea-1" + suffix), target)
                    made.append(target)

        comments, header, rows = read_cells(LOCO)
        template = next(row for row in rows if row["id"] == "df4c")
        extra = dict(template)
        # name_string and additional_text both point at STRs that already exist:
        # a new one would need a row in docs/str.csv, and make's --strings step
        # would then leave that row behind when this script restores the tables.
        # The two menu levels stay distinguishable because the name callback
        # returns STR_EXPORT_SERIES for the group row.
        extra.update({"id": TEST, "name_string": "STR_NAME_DF4C",
                      "additional_text": "STR_CAT_LOCO",
                      "variant_group": "df4c", "menu_order": "5",
                      "series_string": "STR_EXPORT_SERIES"})
        rows.append(extra)
        written[LOCO] = write_cells(LOCO, comments, header, rows)

        comments, header, rows = read_cells(LIV)
        rows.append({"id": TEST, "sprite_suffix": "korea-1", "string": "LV_DPRK",
                     "from_year": "0", "to_year": "9999", "purchase_suffix": "",
                     "templates": "", "graphics_parts": ""})
        written[LIV] = write_cells(LIV, comments, header, rows)

        # Generate and compile directly rather than through `make`: make runs
        # `genpnml.py --strings`, which rewrites docs/str.csv, and this script has
        # no business editing the language table.
        step = subprocess.run([sys.executable, "genpnml.py", "--data", "data",
                               "--out", "src"],
                              cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        check("the generator accepts the grouping", step.returncode == 0,
              (step.stderr or step.stdout).strip()[-300:])
        built = compile_all()
        check("the whole GRF compiles with a variant group", built.returncode == 0,
              "\n".join(line for line in (built.stdout + built.stderr).splitlines()
                        if "ERROR" in line.upper())[:300])

        pnml = (ROOT / "src" / "dprk" / "df4c" / (TEST + ".pnml"))
        text = pnml.read_text(encoding="utf-8") if pnml.is_file() else ""
        check("variant_group is emitted", "variant_group:                  df4c;" in text)
        check("the series name switch is emitted", "switch_%s_name" % TEST in text,
              "no per-vehicle name callback")
        check("it returns the series string", "return string(STR_EXPORT_SERIES)" in text)
        check("name: uses it", "name:                           switch_%s_name;" % TEST in text)
        check("...while the vehicle keeps its own name",
              "name:                           string(STR_NAME_DF4C);" in text,
              "the two menu levels would read the same")

        sort = (ROOT / "src" / "vehiclesort.pnml").read_text(encoding="utf-8")
        order = [line.strip().rstrip(",") for line in sort.splitlines()
                 if line.startswith("    ") and not line.strip().startswith("//")]
        expected = declared_menu_order()
        check("menu_order decides the sort block", order == expected,
              "emitted %s, the tables ask for %s" % (order, expected))

        # the workbench and the generator have to agree on what a series string
        # is: it is used verbatim as an NML string, so LV_<NAME> -- which is fine
        # for a livery -- must be refused by both
        for value, ok in (("STR_EXPORT_SERIES", True), ("LV_DPRK", False),
                          ("nonsense", False)):
            try:
                server._fleet_menu_edits({"rows": [{"table": "locomotives.csv",
                                                    "id": "df4c",
                                                    "series_string": value}]})
                accepted = True
            except ValueError:
                accepted = False
            check("the workbench %s series_string %r"
                  % ("accepts" if ok else "refuses", value), accepted == ok)
            check("the generator %s series_string %r"
                  % ("accepts" if ok else "refuses", value),
                  bool(genpnml.NML_STRING_RE.match(value)) == ok)

        # a vehicle with one gets a callback of its own, wired into graphics{},
        # while the string it returns lives in the switch block
        loaded = {item.id: item for item in genpnml.load_vehicles(str(ROOT / "data"))}
        series = dataclasses.replace(loaded[TEST], series_string="STR_EXPORT_SERIES")
        plain = dataclasses.replace(loaded[TEST], series_string="")
        check("name: points at the per-vehicle callback",
              "name:                           switch_%s_name;" % TEST
              in genpnml.render_item(series, "spr", None, ""))
        check("...and the property keeps the vehicle's own name",
              "name:                           string(STR_NAME_DF4C);"
              in genpnml.render_item(series, "spr", None, ""),
              "the two menu levels would read the same")
        emitter = genpnml.Emitter()
        genpnml.emit_name_switch(emitter, series)
        check("the callback returns the series string",
              any("return string(STR_EXPORT_SERIES)" in block
                  for block in emitter.blocks), str(emitter.blocks)[:200])
        emitter = genpnml.Emitter()
        genpnml.emit_name_switch(emitter, plain)
        check("a vehicle without one emits no callback", not emitter.blocks)

        for parent, ok in (("df4c", True), ("nosuch", False)):
            problems, _broken = genpnml.check_variant_groups({"df4c": "", TEST: parent})
            check("the grouping checker %s parent %r"
                  % ("accepts" if ok else "refuses", parent), (not problems) == ok)
        problems, _broken = genpnml.check_variant_groups({"df4c": "df4c"})
        check("a self reference is refused", bool(problems), str(problems))
        problems, _broken = genpnml.check_variant_groups({"a": "b", "b": "a"})
        check("a cycle is refused", len(problems) == 2, str(problems))
    finally:
        for path, data in written.items():
            if path.read_bytes() == data:
                if path is LOCO:
                    path.write_bytes(loco_backup)
                else:
                    path.write_bytes(liv_backup)
            else:
                print("NOTE: %s changed while this ran; leaving it alone" % path.name)
        # nothing here should have touched the language table, but if a step did,
        # put it back rather than leaving a row behind for the next `make`
        if LANG.read_bytes() != lang_backup:
            LANG.write_bytes(lang_backup)
            print("NOTE: docs/str.csv was restored after an unexpected change")
        for path in made:
            path.unlink(missing_ok=True)
        # nmlc caches the sprites it encoded; the temporary ones must not linger
        for cache in (ROOT / ".nmlcache").rglob(TEST + "*"):
            cache.unlink(missing_ok=True)
        subprocess.run([sys.executable, "genpnml.py", "--data", "data", "--out", "src",
                        "--sprite-manifest", "gfx/.workbench-sprites.json"],
                       cwd=str(ROOT), capture_output=True)
    print()
    print("FAILURES:", failures if failures else "none")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
