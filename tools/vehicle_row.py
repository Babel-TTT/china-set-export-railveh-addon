#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/vehicle_row.py -- add, copy or remove a row in a data table safely

Editing the CSV tables by hand is easy to get wrong, because several cells
legitimately contain commas and a missing pair of quotes silently shifts every
following column.  This helper writes the row through the csv module, so the
quoting is always correct.

Usage
-----
    # copy an existing vehicle and change a few cells
    python3 tools/vehicle_row.py copy data/locomotives.csv ckd4a ckd8w \
        name_string="CKD8W (Export)" intro_year=2022 \
        comment="Modern export diesel (estimate)"

    # add a row without a template (every column must be given)
    python3 tools/vehicle_row.py add data/wagons.csv \
        id=x70ex name_string="X70 (Export) (Flat Wagon)" category=wagon ...

    # remove a vehicle (its .pnml and .vox files are removed by `make gen`
    # and by the --prune flag of this tool)
    python3 tools/vehicle_row.py remove data/wagons.csv x70ex

    # show the columns of a table
    python3 tools/vehicle_row.py columns data/locomotives.csv
"""

from __future__ import annotations

import csv
import os
import sys

COMMENT_PREFIX = "#"
# tables whose first column is the vehicle id and which carry a header row
TABLES = ("locomotives.csv", "coaches.csv", "wagons.csv", "unit_wagons.csv")


def read(path):
    """Return (comment lines, header, records)."""
    comments, lines = [], []
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for line in handle:
            if line.lstrip().startswith(COMMENT_PREFIX):
                comments.append(line.rstrip("\n"))
            elif line.strip():
                lines.append(line)
    records = list(csv.reader(lines))
    if not records:
        raise SystemExit("%s: the table is empty" % path)
    header = [cell.strip() for cell in records[0]]
    body = []
    for row in records[1:]:
        if not row or not row[0].strip():
            continue
        body.append(dict(zip(header, row + [""] * (len(header) - len(row)))))
    return comments, header, body


def write(path, comments, header, body):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for line in comments:
            handle.write(line + "\n")
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        for record in body:
            writer.writerow({key: record.get(key, "") for key in header})


def parse_pairs(arguments):
    """Turn key=value arguments into a dict."""
    result = {}
    for argument in arguments:
        if "=" not in argument:
            raise SystemExit("expected key=value, got %r" % argument)
        key, _, value = argument.partition("=")
        result[key.strip()] = value
    return result


def find(body, vehicle_id):
    for index, record in enumerate(body):
        if record.get("id") == vehicle_id:
            return index
    return None


def prune_files(vehicle_id, folder_hint=""):
    """Remove the generated .pnml and the placeholder .vox of a vehicle."""
    removed = []
    for root, _dirs, files in os.walk("src"):
        for name in files:
            if name == "%s.pnml" % vehicle_id:
                os.remove(os.path.join(root, name))
                removed.append(os.path.join(root, name))
    for root, _dirs, files in os.walk("gfx"):
        for name in files:
            if name.startswith("%s" % vehicle_id) and name.endswith((".vox",)):
                path = os.path.join(root, name)
                os.remove(path)
                removed.append(path)
    for path in removed:
        print("removed %s" % path)
    return removed


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    command = argv[1]

    if command == "columns":
        _comments, header, _body = read(argv[2])
        for index, name in enumerate(header):
            print("%2d  %s" % (index, name))
        return 0

    if command == "copy":
        path, source, target = argv[2], argv[3], argv[4]
        changes = parse_pairs(argv[5:])
        comments, header, body = read(path)
        index = find(body, source)
        if index is None:
            raise SystemExit("%s: vehicle %r not found" % (path, source))
        if find(body, target) is not None:
            raise SystemExit("%s: vehicle %r already exists" % (path, target))
        record = dict(body[index])
        record["id"] = target
        record.update(changes)
        body.append(record)
        write(path, comments, header, body)
        print("%s: copied %r to %r" % (path, source, target))
        return 0

    if command == "add":
        path = argv[2]
        changes = parse_pairs(argv[3:])
        if "id" not in changes:
            raise SystemExit("add needs at least id=...")
        comments, header, body = read(path)
        if find(body, changes["id"]) is not None:
            raise SystemExit("%s: vehicle %r already exists" % (path, changes["id"]))
        record = {key: "" for key in header}
        unknown = set(changes) - set(header)
        if unknown:
            raise SystemExit("unknown columns: %s" % sorted(unknown))
        record.update(changes)
        body.append(record)
        write(path, comments, header, body)
        print("%s: added %r" % (path, changes["id"]))
        return 0

    if command == "remove":
        path, target = argv[2], argv[3]
        comments, header, body = read(path)
        index = find(body, target)
        if index is None:
            raise SystemExit("%s: vehicle %r not found" % (path, target))
        del body[index]
        write(path, comments, header, body)
        print("%s: removed %r" % (path, target))
        if "--prune" in argv:
            prune_files(target)
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
