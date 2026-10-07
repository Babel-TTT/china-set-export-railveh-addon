#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check that every section count and length a table may use still compiles.

The ``length`` property is the one place a section count reaches NML directly.
``src/functions.pnml`` predefines only the shapes the parent set uses
(``switch_length_2_<body>_2`` with a body of 1..8, plus a few asymmetric ones),
so any other count used to be emitted as a name that does not exist and nmlc
stopped with ``Unrecognized identifier`` -- ``parts=2|10|2`` did exactly that.
The generator writes an inline switch for the rest; this checks that it does,
for a spread of shapes, by actually compiling each one.

The tables and the generated file are restored afterwards, so it is safe to run
in a dirty working copy:

    python3 tools/check_section_lengths.py
"""

from __future__ import annotations

import csv
import io
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCO = ROOT / "data" / "locomotives.csv"

# body lengths inside and outside the predefined 1..8, asymmetric ends, and
# counts other than three
CASES = [
    "2|8|2",
    "2|1|2",
    "2|10|2",
    "2|16|2",
    "3|8|3",
    "2|1|1",
    "2|8|6",
    "2|8|2|2",
    "2|8",
    "6",
]

failures = []

# the bytes this run last wrote into data/locomotives.csv, so the restore can tell
# its own edit apart from one that arrived while it was running (the workbench may
# be open in a browser)
WRITTEN = None


def check(label, condition, detail=""):
    print(("  ok  " if condition else " FAIL ") + label + (" :: " + detail if detail else ""))
    if not condition:
        failures.append(label)


def run(command, **kwargs):
    return subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False, **kwargs)


def main() -> int:
    backup = LOCO.read_bytes()
    pnml = None
    try:
        reader = list(csv.reader(io.StringIO(backup.decode("utf-8-sig"))))
        head = next(index for index, row in enumerate(reader)
                    if row and row[0].strip() == "id")
        header, body = reader[head], reader[head + 1:]
        if not body:
            print("no vehicle rows to test with")
            return 1
        pnml = ROOT / "src" / (body[0][header.index("folder")].strip() or "diesel") \
            / (body[0][0].strip() + ".pnml")

        for parts in CASES:
            for row in body:
                row[header.index("parts")] = parts
            buffer = io.StringIO()
            writer = csv.writer(buffer, lineterminator="\n")
            for row in reader[:head + 1] + body:
                writer.writerow(row)
            LOCO.write_bytes(buffer.getvalue().encode("utf-8"))
            global WRITTEN
            WRITTEN = buffer.getvalue().encode("utf-8")

            generated = run([sys.executable, "genpnml.py", "--data", "data", "--out", "src"])
            if generated.returncode != 0:
                check("parts=%-10s generates" % parts, False,
                      (generated.stderr or generated.stdout).strip()[-160:])
                continue
            check("parts=%-10s generates" % parts, True)

            text = pnml.read_text(encoding="utf-8")
            line = next((l.strip() for l in text.splitlines()
                         if l.strip().startswith("length:")), "")
            spelled = line.replace("length:", "").strip().rstrip(";").strip()
            if len(parts.split("|")) == 1:
                # a one part vehicle states its length as a number
                check("parts=%-10s length is a number" % parts, spelled.isdigit(), spelled)
            else:
                check("parts=%-10s length is declared" % parts,
                      "switch (FEAT_TRAINS, SELF, %s," % spelled in
                      (ROOT / "src" / "functions.pnml").read_text(encoding="utf-8")
                      or "switch (FEAT_TRAINS, SELF, %s," % spelled
                      in pnml.read_text(encoding="utf-8"),
                      spelled)

            built = run(["make"])
            check("parts=%-10s compiles" % parts, built.returncode == 0,
                  "\n".join(line for line in (built.stdout + built.stderr).splitlines()
                            if "ERROR" in line)[:200])
    finally:
        # Only undo our own edit: a row saved through the workbench while this ran
        # must not be thrown away by restoring the old copy
        if WRITTEN is not None and LOCO.read_bytes() != WRITTEN:
            print("NOTE: data/locomotives.csv changed while this ran (workbench?), "
                  "leaving it as it is instead of restoring the old copy")
        else:
            LOCO.write_bytes(backup)
        run([sys.executable, "genpnml.py", "--data", "data", "--out", "src",
             "--sprite-manifest", "gfx/.workbench-sprites.json"])

    print()
    print("FAILURES:", failures if failures else "none")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
