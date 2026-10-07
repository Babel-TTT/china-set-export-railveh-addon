#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Drop the vehicle-level ``graphics_parts`` column.

Per section graphics belong to the paint scheme, so the cell moved to
``liveries.csv``.  The vehicle tables kept an empty column as a fallback for
projects written before the move; nothing uses it any more, and an empty column
that only exists for a migration nobody needs is just a trap.

    python3 tools/migrate_drop_vehicle_graphics_parts.py --dry-run
    python3 tools/migrate_drop_vehicle_graphics_parts.py
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
TABLES = ("locomotives.csv", "coaches.csv", "wagons.csv", "unit_wagons.csv")
COLUMN = "graphics_parts"
BACKUP_SUFFIX = ".column-migration.bak"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    touched = 0
    for name in TABLES:
        path = ROOT / "data" / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8-sig")
        lines = text.splitlines()
        comments = [line for line in lines if line.lstrip().startswith("#")]
        records = list(csv.reader(line for line in lines if line.strip()
                                  and not line.lstrip().startswith("#")))
        if not records:
            continue
        header = [cell.strip() for cell in records[0]]
        if COLUMN not in header:
            print("%-18s no %s column" % (name, COLUMN))
            continue
        index = header.index(COLUMN)
        filled = [row for row in records[1:]
                  if len(row) > index and row[index].strip()]
        if filled:
            print("%-18s REFUSING: %d row(s) still use the column, move them to "
                  "liveries.csv first" % (name, len(filled)))
            return 1
        header.pop(index)
        body = []
        for row in records[1:]:
            row = list(row)
            if len(row) > index:
                row.pop(index)
            body.append(row)
        print("%-18s dropping %s (%d data rows)" % (name, COLUMN, len(body)))
        touched += 1
        if args.dry_run:
            continue
        shutil.copyfile(path, path.with_name(path.name + BACKUP_SUFFIX))
        buffer = io.StringIO()
        for line in comments:
            buffer.write(line + "\n")
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(header)
        for row in body:
            writer.writerow(row)
        temporary = path.with_name(path.name + ".migration.tmp")
        temporary.write_text(buffer.getvalue(), encoding="utf-8", newline="")
        os.replace(temporary, path)

    if args.dry_run:
        print("\ndry run: %d table(s) would change" % touched)
        return 0
    print("\nupdated %d table(s)" % touched)
    return 0


if __name__ == "__main__":
    sys.exit(main())
