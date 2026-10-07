#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Move every livery label to the LV_ convention.

A livery label used to be written as a bare ``STR_<NAME>`` cell, which put it
in the same namespace as the interface strings.  It is now written ``LV_<NAME>``
in ``data/liveries.csv`` and becomes ``STR_LV_<NAME>`` in the code, so this
script renames the existing constants and rewrites the cells that point at them.

Usage:
    python3 tools/migrate_lv_labels.py --dry-run     # show what would change
    python3 tools/migrate_lv_labels.py               # write the changes
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANG_CSV = ROOT / "docs" / "str.csv"
LIVERY_CSV = ROOT / "data" / "liveries.csv"
BACKUP_SUFFIX = ".lv-migration.bak"

# the labels the generator ships in STATIC_STRINGS: these are the ones that may
# safely be renamed, because a project that never used them loses nothing
RESERVED = {
    "STR_BUILD_YEAR": "STR_LV_BUILD_YEAR",
    "STR_ORIGINAL": "STR_LV_ORIGINAL",
    "STR_EXPORT_BLUE": "STR_LV_EXPORT_BLUE",
    "STR_EXPORT_GREEN": "STR_LV_EXPORT_GREEN",
    "STR_EXPORT_GRAY": "STR_LV_EXPORT_GRAY",
    "STR_DPRK_LIVERY": "STR_LV_DPRK",
}


def read_lang():
    comments, rows = [], []
    with LANG_CSV.open(encoding="utf-8-sig", newline="") as handle:
        for raw in csv.reader(handle):
            if not raw or not raw[0].strip():
                continue
            if raw[0].lstrip().startswith("#"):
                comments.append(raw)
                continue
            cells = [cell.strip() for cell in raw] + ["", "", ""]
            if cells[0] == "STRING" and cells[1] == "ENGLISH":
                continue
            rows.append([cells[0], cells[1], cells[2]])
    return comments, rows


def write_lang(comments, rows) -> None:
    shutil.copyfile(LANG_CSV, LANG_CSV.with_name(LANG_CSV.name + BACKUP_SUFFIX))
    buffer = io.StringIO()
    for raw in comments:
        buffer.write(",".join(raw) + "\n")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["STRING", "ENGLISH", "SIMPLIFIED CHINESE"])
    for row in rows:
        writer.writerow(row)
    temporary = LANG_CSV.with_name(LANG_CSV.name + ".migration.tmp")
    temporary.write_text(buffer.getvalue(), encoding="utf-8", newline="")
    os.replace(temporary, LANG_CSV)


def main(argv) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv[1:])

    comments, rows = read_lang()
    renamed = []
    for row in rows:
        if row[0] in RESERVED:
            renamed.append((row[0], RESERVED[row[0]], row[2]))
            row[0] = RESERVED[row[0]]

    _, livery_rows = [], []
    with LIVERY_CSV.open(encoding="utf-8-sig", newline="") as handle:
        livery_rows = list(csv.reader(handle))

    header_index = next((index for index, row in enumerate(livery_rows)
                         if row and row[0].strip() == "id"), None)
    touched = []
    if header_index is not None:
        header = livery_rows[header_index]
        if "string" not in header:
            print("liveries.csv has no string column", file=sys.stderr)
            return 1
        column = header.index("string")
        for row in livery_rows[header_index + 1:]:
            if len(row) <= column:
                continue
            cell = row[column].strip()
            # a cell that already carries the LV_ prefix is left alone: the
            # generator maps it, so there is nothing to rewrite
            if cell in RESERVED:
                touched.append((row[0], cell, RESERVED[cell]))
                row[column] = RESERVED[cell]

    print("livery labels renamed in docs/str.csv: %d" % len(renamed))
    for old, new, chinese in renamed:
        print("  %-22s -> %-24s %s" % (old, new, chinese))
    print("liveries.csv cells rewritten: %d" % len(touched))
    for vehicle, old, new in touched:
        print("  %-12s %-22s -> %s" % (vehicle, old, new))

    if args.dry_run:
        print("\ndry run: nothing written")
        return 0

    write_lang(comments, rows)
    shutil.copyfile(LIVERY_CSV, LIVERY_CSV.with_name(LIVERY_CSV.name + BACKUP_SUFFIX))
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    for row in livery_rows:
        writer.writerow(row)
    temporary = LIVERY_CSV.with_name(LIVERY_CSV.name + ".migration.tmp")
    temporary.write_text(buffer.getvalue(), encoding="utf-8", newline="")
    os.replace(temporary, LIVERY_CSV)
    print("\nwrote docs/str.csv and data/liveries.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
