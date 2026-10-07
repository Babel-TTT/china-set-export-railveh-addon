#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/clear_vehicle_data.py -- reset the project to an empty vehicle list

Removes every data row from the vehicle tables (the documentation header of
each file is kept, including the column reference comment), empties the livery
and cargo appearance tables, and deletes the placeholder voxel models together
with their rendered PNGs.

The shared library files (src/header.pnml, template, functions, railtypetable,
cargotable) and the generator itself are left alone, so `make` still works and
the project compiles to a GRF containing no vehicles until rows are added
again.

    python3 tools/clear_vehicle_data.py            # show what would happen
    python3 tools/clear_vehicle_data.py --apply    # do it
"""

from __future__ import annotations

import csv
import os
import sys

VEHICLE_TABLES = ("locomotives.csv", "coaches.csv", "wagons.csv", "unit_wagons.csv")
AUX_TABLES = ("liveries.csv", "cargo_variants.csv")
RENDER_SUFFIXES = ("_32bpp.png", "_8bpp.png", "_mask.png")


def read_table(path):
    """Return (comment lines, header, number of data rows)."""
    comments, header, rows = [], None, 0
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for line in handle:
            if line.lstrip().startswith("#"):
                comments.append(line.rstrip("\n"))
            elif line.strip():
                if header is None:
                    header = next(csv.reader([line]))
                else:
                    rows += 1
    return comments, header, rows


def rewrite_table(path, comments, header):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for line in comments:
            handle.write(line + "\n")
        csv.writer(handle, lineterminator="\n").writerow(header)


def main(argv):
    apply = "--apply" in argv
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root)

    print("=== data tables ===")
    for name in VEHICLE_TABLES + AUX_TABLES:
        path = os.path.join("data", name)
        if not os.path.exists(path):
            print("  %-22s missing, skipped" % name)
            continue
        comments, header, rows = read_table(path)
        print("  %-22s %2d columns, %3d rows -> 0 rows%s"
              % (name, len(header or []), rows, "" if apply else "  (dry run)"))
        if apply:
            rewrite_table(path, comments, header)

    print("=== placeholder models ===")
    vox, png = [], []
    for folder, _dirs, files in os.walk("gfx"):
        for name in files:
            path = os.path.join(folder, name)
            if name.endswith(".vox"):
                vox.append(path)
            elif name.endswith(RENDER_SUFFIXES):
                png.append(path)
    print("  %d .vox, %d rendered .png%s"
          % (len(vox), len(png), "" if apply else "  (dry run)"))
    if apply:
        for path in vox + png:
            os.remove(path)
        for entry in sorted(os.listdir("gfx")):
            path = os.path.join("gfx", entry)
            if os.path.isdir(path) and not os.listdir(path):
                os.rmdir(path)
                print("  removed empty folder %s" % path)

    print()
    if apply:
        print("done.  next steps:")
        print("  make gen      # write the empty index files")
        print("  make          # build a GRF that contains no vehicles yet")
    else:
        print("dry run only -- re-run with --apply to delete")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
