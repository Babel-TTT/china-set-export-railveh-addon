#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check the depot sprite override (``purchase_suffix``) end to end.

China Set: Trains gives every vehicle a purchase spriteset of its own, drawn from
a sheet the author picks -- usually the scheme's own, sometimes another scheme's
or even another vehicle's.  This package has one column for that, and the choice
has to reach the **file** nmlc resolves: renaming the block is not enough, because
the depot preview is the one purchase spriteset that is always returned
(``graphics { purchase: ... }`` takes the first scheme of the vehicle).

Every case below compiles a real GRF, so "it works" means nmlc accepted it:

  * borrowing another scheme's sheet changes the sheet the item block asks for;
  * a scheme whose own artwork does not exist can still be the default scheme by
    pointing its depot sprite at a sheet that is drawn -- that is the case that
    unblocks a build;
  * a borrowed sheet that does not exist is reported as a missing model by
    ``tools/verify_assets.py``, not only by nmlc;
  * ``purchase_suffix`` on any row but the first warns, because only the first
    scheme's purchase spriteset is ever returned.

``data/liveries.csv`` is restored afterwards, and only if it still holds what this
run wrote -- the workbench may be open in a browser.

    python3 tools/check_purchase_sprite.py
"""

from __future__ import annotations

import csv
import io
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIV = ROOT / "data" / "liveries.csv"
LOCO = ROOT / "data" / "locomotives.csv"

failures: list[str] = []
# the bytes this run last wrote into the table, so the restore can tell its own
# edit apart from one that arrived while it was running
WRITTEN: bytes | None = None


def check(label, condition, detail=""):
    print(("  ok  " if condition else " FAIL ") + label
          + (" :: " + detail if detail and not condition else ""))
    if not condition:
        failures.append(label)


def note(text):
    print("  --  " + text)


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


def write_cells(path: Path, comments, header, rows) -> None:
    global WRITTEN
    buffer = io.StringIO()
    for line in comments:
        buffer.write(line + "\n")
    writer = csv.DictWriter(buffer, fieldnames=header, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in header})
    WRITTEN = buffer.getvalue().encode("utf-8")
    path.write_bytes(WRITTEN)


def run(command):
    return subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False)


def generate():
    return run([sys.executable, "genpnml.py", "--data", "data", "--out", "src"])


def compile_all():
    """Preprocess the index and compile it, exactly as `make code` does."""
    index = ROOT / "chinasettrainsexport.pnml"
    if not index.is_file():
        raise SystemExit("ERROR: %s is missing; run this from the repository root"
                         % index)
    nml = ROOT / "purchase_sprite_check.nml"
    pre = run(["gcc", "-E", "-x", "c", index.name,
               "-D", "REPO_REVISION=0", "-D", "VERSION_STRING=check",
               "-D", "MIN_COMPATIBLE_VERSION=0"])
    if pre.returncode:
        return pre
    nml.write_text(pre.stdout, encoding="utf-8", newline="")
    result = run(["nmlc", "-c", nml.name, "-o", "purchase_sprite_check.grf"])
    for name in (nml.name, "purchase_sprite_check.grf"):
        (ROOT / name).unlink(missing_ok=True)
    return result


def errors_of(result) -> str:
    lines = [line.strip() for line in (result.stdout + result.stderr).splitlines()
             if "ERROR" in line.upper()]
    return " | ".join(lines)[:300] or (result.stdout + result.stderr).strip()[-300:]


def spriteset_name(vehicle_id: str, suffix: str) -> str:
    """The name the generator gives a purchase spriteset, rebuilt here.

    Independently of ``genpnml._livery_purchase_name`` on purpose: an expectation
    computed with the function under test would agree with it by construction.
    """
    if suffix:
        folded = re.sub(r"[^A-Za-z0-9]+", "_", suffix).strip("_")
        return "spriteset_%s_purchase_%s" % (vehicle_id, folded)
    return "spriteset_%s_purchase" % vehicle_id


def basename_of(vehicle_id: str, suffix: str) -> str:
    return "%s-%s" % (vehicle_id, suffix) if suffix else vehicle_id


def sheet(folder: str, basename: str) -> Path:
    return ROOT / "gfx" / folder / ("%s_32bpp.png" % basename)


def pnml_text(vehicle_id: str, folder: str) -> str:
    path = ROOT / "src" / folder / (vehicle_id + ".pnml")
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def item_purchase_line(vehicle_id: str, folder: str) -> str:
    for line in pnml_text(vehicle_id, folder).splitlines():
        if line.strip().startswith("purchase:"):
            return line.strip()
    return ""


def spriteset_block(vehicle_id: str, folder: str, name: str) -> str:
    text = pnml_text(vehicle_id, folder)
    at = text.find("spriteset (%s," % name)
    if at < 0:
        return ""
    end = text.find("\n}", at)
    return text[at:end + 2] if end > 0 else ""


def vehicles() -> list[dict]:
    """Every vehicle row with its livery rows, read from the tables as they are."""
    _comments, _header, rows = read_cells(LOCO)
    _lc, _lh, liveries = read_cells(LIV)
    return [{"id": row["id"], "folder": row["folder"],
             "liveries": [item for item in liveries if item["id"] == row["id"]]}
            for row in rows]


def main() -> int:
    backup = LIV.read_bytes()
    global WRITTEN
    try:
        comments, header, original = read_cells(LIV)
        candidates = [v for v in vehicles() if len(v["liveries"]) >= 2]
        if not candidates:
            note("no vehicle has two livery rows; nothing to check")
            return 0
        subject = candidates[0]
        mine = subject["liveries"]
        own = basename_of(subject["id"], mine[0]["sprite_suffix"])
        donor_suffix = mine[1]["sprite_suffix"]
        borrowed = basename_of(subject["id"], donor_suffix)
        print("subject: %s, first scheme %s, borrowing %s"
              % (subject["id"], own, borrowed))

        def apply(rows):
            write_cells(LIV, comments, header, rows)

        def scheme_rows():
            rows = [dict(row) for row in original]
            return rows

        # Does the tree compile at all as it stands?  A scheme whose artwork has
        # not been drawn yet makes every full build fail, so only the cases that
        # change that can be judged on compiling.
        apply(scheme_rows())
        generate()
        baseline = compile_all()
        buildable = baseline.returncode == 0
        if not buildable:
            note("the tables as they are do not compile: %s" % errors_of(baseline)[:90])
            note("so only the rescuing case below is judged on compiling")

        # 1. borrowing another scheme's sheet
        rows = scheme_rows()
        [row for row in rows if row["id"] == subject["id"]][0]["purchase_suffix"] = donor_suffix
        apply(rows)
        built = generate()
        check("the generator accepts purchase_suffix", built.returncode == 0,
              errors_of(built))
        name = spriteset_name(subject["id"], donor_suffix)
        line = item_purchase_line(subject["id"], subject["folder"])
        check("the item block asks for the borrowed spriteset", name in line,
              "purchase line is %r, expected %s" % (line, name))
        block = spriteset_block(subject["id"], subject["folder"], name)
        check("...and that spriteset draws the borrowed sheet",
              '"%s"' % borrowed in block, block.replace("\n", " ")[:180] or "no block")
        if buildable:
            compiled = compile_all()
            check("the whole GRF compiles with the borrowed depot sprite",
                  compiled.returncode == 0, errors_of(compiled))

        # 2. a borrowed sheet that does not exist has to be reported
        rows = scheme_rows()
        [row for row in rows if row["id"] == subject["id"]][0]["purchase_suffix"] = "zz-no-such-sheet"
        apply(rows)
        generate()
        report = run([sys.executable, "tools/verify_assets.py"])
        wanted = "gfx/%s/%s-zz-no-such-sheet_32bpp.png" % (subject["folder"], subject["id"])
        text = (report.stdout + report.stderr).replace("\\", "/")
        check("a missing borrowed sheet is reported as a missing model",
              wanted in text, "verify_assets did not mention %s" % wanted)

        # 3. the column only means something on the first row
        rows = scheme_rows()
        by_id = [row for row in rows if row["id"] == subject["id"]]
        by_id[0]["purchase_suffix"] = donor_suffix
        by_id[1]["purchase_suffix"] = mine[0]["sprite_suffix"]
        apply(rows)
        built = generate()
        check("purchase_suffix away from the first row warns",
              "只对第一行有意义" in (built.stdout + built.stderr),
              (built.stdout + built.stderr).strip()[-200:])

        # 4. the case that unblocks a build: the first scheme's own artwork does
        #    not exist, another scheme's does, and the depot sprite borrows it
        apply(scheme_rows())
        generate()
        rescue = None
        for vehicle in vehicles():
            first = vehicle["liveries"][0]
            if sheet(vehicle["folder"],
                     basename_of(vehicle["id"], first["sprite_suffix"])).exists():
                continue
            donors = [row for row in vehicle["liveries"][1:]
                      if sheet(vehicle["folder"],
                               basename_of(vehicle["id"], row["sprite_suffix"])).exists()]
            if donors:
                rescue = (vehicle, first, donors[0])
                break
        if not rescue:
            note("no scheme needs rescuing (every default scheme has artwork)")
        else:
            vehicle, first, donor = rescue
            missing = basename_of(vehicle["id"], first["sprite_suffix"])
            before = compile_all()
            check("without the override %s does not build" % vehicle["id"],
                  before.returncode != 0, "it compiled; there is nothing to rescue")
            rows = scheme_rows()
            [row for row in rows if row["id"] == vehicle["id"]][0]["purchase_suffix"] = \
                donor["sprite_suffix"]
            apply(rows)
            generate()
            after = compile_all()
            check("purchase_suffix lets %s build without drawing %s.vox"
                  % (vehicle["id"], missing), after.returncode == 0, errors_of(after))
    finally:
        # Only undo our own edit.  If the workbench saved a row while this ran, the
        # file is no longer what we wrote and putting the old copy back would throw
        # that change away -- so say so and leave it alone.
        if WRITTEN is not None and LIV.read_bytes() != WRITTEN:
            print("NOTE: data/liveries.csv changed while this ran (workbench?), "
                  "leaving it as it is instead of restoring the old copy")
        else:
            LIV.write_bytes(backup)
        run([sys.executable, "genpnml.py", "--data", "data", "--out", "src"])
        (ROOT / "purchase_sprite_check.nml").unlink(missing_ok=True)

    print()
    print("FAILURES:", failures if failures else "none")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
