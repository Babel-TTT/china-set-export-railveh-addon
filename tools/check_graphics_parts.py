#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check that every shape a ``graphics_parts`` cell may take compiles.

A cell is split on ``;`` into one piece per section and each piece on ``|`` into
rules, and a rule is a path ``条件=条件=…=贴图基名``.  The emitter turns that
into nested NML switches, which is the part worth testing for real: a tree that
looks right can still be NML nmlc refuses, and the consist variables are only
allowed as a switch *selector*, never inside a condition.

Each accepted cell is generated and then compiled, so the check is about the
generated NML and not about the parser alone.  The refused cells are checked for
a clear message rather than for silence, because a rule tree that cannot be
expressed is exactly what the author needs to be told about.

The tables and the generated file are restored afterwards, so it is safe to run
in a dirty working copy:

    python3 tools/check_graphics_parts.py
"""

from __future__ import annotations

import csv
import io
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVERIES = ROOT / "data" / "liveries.csv"
LOCO = ROOT / "data" / "locomotives.csv"

sys.path.insert(0, str(ROOT))
import genpnml  # noqa: E402 -- the parser the workbench editor also uses

# every cell here is written for a three section vehicle (parts = 2|8|2)
ACCEPTED = [
    # nothing at all, and the usual "two invisible ends" shape
    "",
    ";;",
    ";body;",
    # one sheet per section, no conditions
    "a;b;c",
    # a flat chain: each new condition continues from the previous default
    ";consist<=6=h_s | consist<=10=h_m | h_l;",
    # a chain may change variable, which is how a whole train gets head and tail
    ";pos<=2=set_head | tailpos<=2=set_tail | set_mid;",
    # a real tree: one condition holds two branches
    ";consist<=6=pos<=2=h_s | consist<=6=h_l | b_l;",
    ";pos==0=a | pos<=2=b | c;",
    # the full NML spelling of a variable works as well as the short one
    ";position_in_consist <= 2 = a | position_in_consist > 2 = b;",
    # the same condition twice with the same sheet is one branch
    ";consist<=6=a | consist<=6=a;",
    # a rule may select on which section of the vehicle this is
    ";unitpos==1=a;",
    # a branch may hold a whole sub tree
    ";consist<=6=pos<=2=a | consist<=6=pos>2=b | consist<=6=c | d;",
]

# cells that must be refused, with a fragment of the message that explains why
REFUSED = [
    # a trailing ';' is a fourth section for a three section vehicle
    ("a;b;c;", "4 段"),
    # two sections where the vehicle has three
    (";a;b;", "3 段"),
    # a variable may not be selected on twice along one path
    (";pos<=2=tailpos<=2=pos<=2=a;", "重复使用"),
    (";pos<=2=a | tailpos<=2=b | pos<=3=c;", "重复使用"),
    # a case that a sibling already covers never shows
    (";consist<=10=a | consist<=6=b | c;", "永远不会生效"),
    # one case cannot show two different sheets
    (";consist<=6=a | consist<=6=b;", "同时指定了模型"),
    # a sheet name has to be a NML friendly identifier
    (";consist<=6=a-b;", "无法解析"),
    # the variables the generator knows about are the only ones available
    (";speed<=6=a;", "无法解析"),
]

failures = []

# the bytes this run last wrote into data/liveries.csv, so the restore can tell
# its own edit apart from one that arrived while it was running
WRITTEN = None
# the bytes of the real sheet the placeholder copies were made from
SOURCE_BYTES = b""


def check(label, condition, detail=""):
    print(("  ok  " if condition else " FAIL ") + label
          + (" :: " + detail if detail else ""))
    if not condition:
        failures.append(label)


def run(command, **kwargs):
    return subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False, **kwargs)


def write_cell(rows, head, column, value):
    """Write the test cell, and remember what was written.

    The workbench may be open in a browser while this runs, so the restore in
    ``main`` compares the file against this and refuses to undo an edit that
    arrived from somewhere else.  A test tool must never eat a human's change.
    """
    global WRITTEN
    rows[head + 1][column] = value
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerows(rows)
    WRITTEN = buffer.getvalue().encode("utf-8")
    LIVERIES.write_bytes(WRITTEN)


def compile_all():
    """Preprocess the index and compile it, exactly as `make code` does."""
    index = ROOT / "chinasettrainsexport.pnml"
    nml = ROOT / "graphics_parts_check.nml"
    pre = run(["gcc", "-E", "-x", "c", index.name,
               "-D", "REPO_REVISION=0", "-D", "VERSION_STRING=check",
               "-D", "MIN_COMPATIBLE_VERSION=0"])
    if pre.returncode != 0:
        return pre
    nml.write_text(pre.stdout, encoding="utf-8", newline="")
    result = run(["nmlc", "-c", nml.name, "-o", "graphics_parts_check.grf"])
    nml.unlink(missing_ok=True)
    (ROOT / "graphics_parts_check.grf").unlink(missing_ok=True)
    return result


def error_lines(result):
    text = (result.stdout or "") + (result.stderr or "")
    lines = [line.strip() for line in text.splitlines() if "ERROR" in line.upper()]
    return "\n".join(lines)[:300] or text.strip()[-300:]


def _signature(rules):
    """A comparable dump of a parsed graphics_parts value, nesting included."""
    def node(item):
        return (item.selector, item.case, item.basename, item.selector_below,
                tuple(node(child) for child in item.children))
    return tuple(tuple(node(root) for root in section) for section in rules)


def make_test_sheets(folder, source_basename, basenames):
    """Copy one real sheet so every basename the cells name actually exists.

    nmlc resolves each path a spriteset names, so a cell using ``a`` would fail
    to compile for a reason with nothing to do with the rule tree.  The copies
    are removed again in the ``finally`` of ``main``.
    """
    global SOURCE_BYTES
    made = []
    source = ROOT / "gfx" / folder / ("%s_32bpp.png" % source_basename)
    SOURCE_BYTES = source.read_bytes()
    for basename in basenames:
        for suffix in ("_32bpp.png", "_8bpp.png", "_mask.png"):
            target = ROOT / "gfx" / folder / (basename + suffix)
            if not target.exists():
                shutil.copyfile(source, target)
                made.append(target)
    return made


def main() -> int:
    livery_backup = LIVERIES.read_bytes()
    loco_backup = LOCO.read_bytes()
    made = []
    try:
        rows = list(csv.reader(io.StringIO(livery_backup.decode("utf-8-sig"))))
        head = next(index for index, row in enumerate(rows)
                    if row and row[0].strip() == "id")
        column = rows[head].index("graphics_parts")
        if len(rows) <= head + 1:
            print("no livery rows to test with")
            return 1

        # the sheets a test cell may name have to exist, so borrow the real ones
        loco = list(csv.reader(io.StringIO(loco_backup.decode("utf-8-sig"))))
        loco_head = next(index for index, row in enumerate(loco)
                         if row and row[0].strip() == "id")
        vehicle = loco[loco_head + 1][0].strip()
        folder = loco[loco_head + 1][loco[loco_head].index("folder")].strip()
        # every sheet name the cells use has to resolve, or the compile fails for
        # a reason that has nothing to do with the rule tree.  The conditions are
        # stripped first, longest variable name first, so that
        # "position_in_consist <= 2" leaves nothing behind for the name scan.
        variables = ("position_in_consist_from_end|position_in_articulated_veh|"
                     "position_in_consist|num_vehs_in_consist|"
                     "tailpos|consist|unitpos|pos")
        conditions = re.compile(r"\b(?:%s)\s*[=<>!]+\s*[0-9]+" % variables)
        known = {"pos", "tailpos", "consist", "unitpos"}
        sheets = sorted({basename
                         for cell in ACCEPTED
                         for basename in re.findall(r"[a-z0-9_]+",
                                                    conditions.sub("", cell))
                         if basename not in known})
        made = make_test_sheets(folder, vehicle + "-korea-1", sheets)

        print("accepted cells (generate + compile)")
        for cell in ACCEPTED:
            write_cell(rows, head, column, cell)
            generated = run([sys.executable, "genpnml.py", "--data", "data",
                             "--out", "src",
                             "--sprite-manifest", "gfx/.workbench-sprites.json"])
            if generated.returncode != 0:
                check("%-48r generates" % cell, False,
                      error_lines(generated))
                continue
            check("%-48r generates" % cell, True)
            built = compile_all()
            check("%-48r compiles" % cell, built.returncode == 0,
                  error_lines(built))

        print("refused cells (clear message, no build)")
        for cell, fragment in REFUSED:
            write_cell(rows, head, column, cell)
            generated = run([sys.executable, "genpnml.py", "--data", "data",
                             "--out", "src",
                             "--sprite-manifest", "gfx/.workbench-sprites.json"])
            text = (generated.stdout or "") + (generated.stderr or "")
            check("%-48r refused" % cell, generated.returncode != 0,
                  "the generator accepted it")
            if generated.returncode != 0:
                check("%-48r explains why" % cell, fragment in text,
                      "" if fragment in text else "%r missing" % fragment)

        # The workbench editor builds a switch tree and asks the server to write
        # it back as a cell.  If that round trip is not exact, editing in the
        # workbench would silently change what the vehicle draws, so it is
        # checked for every accepted cell right here rather than trusted.
        print("round trip (parse -> render -> parse)")
        for cell in ACCEPTED:
            try:
                first = genpnml.parse_graphics_parts(cell, 3)
            except Exception as error:  # noqa: BLE001 -- reported as a failure
                check("%-48r parses" % cell, False, str(error))
                continue
            rendered = genpnml.render_graphics_parts(first)
            try:
                again = genpnml.parse_graphics_parts(rendered, 3)
            except Exception as error:  # noqa: BLE001
                check("%-48r re-parses what it wrote" % cell, False,
                      "%r -> %s" % (rendered, error))
                continue
            check("%-48r round trips" % cell, _signature(first) == _signature(again),
                  "wrote %r" % rendered)

        # the sheets the test cells name have to be real ones, or the compile
        # above would have failed for the wrong reason
        for basename in sheets:
            check("test sheet %r exists" % basename,
                  (ROOT / "gfx" / folder / (basename + "_32bpp.png")).exists())
    finally:
        # Only undo our own edit.  If the workbench saved a row while this ran,
        # the file is no longer what we wrote and putting the old copy back would
        # throw that change away -- so say so and leave it alone.
        if WRITTEN is not None and LIVERIES.read_bytes() != WRITTEN:
            print("NOTE: data/liveries.csv changed while this ran (workbench?), "
                  "leaving it as it is instead of restoring the old copy")
        else:
            LIVERIES.write_bytes(livery_backup)
        LOCO.write_bytes(loco_backup)
        for path in made:
            # delete only the copies this run made: a file the author has since
            # replaced with real artwork must survive
            if path.exists() and path.read_bytes() == SOURCE_BYTES:
                path.unlink(missing_ok=True)
        run([sys.executable, "genpnml.py", "--data", "data", "--out", "src",
             "--sprite-manifest", "gfx/.workbench-sprites.json"])
        (ROOT / "graphics_parts_check.nml").unlink(missing_ok=True)

    print()
    print("FAILURES:", failures if failures else "none")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
