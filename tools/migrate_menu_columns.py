"""Add the purchase menu columns to the four vehicle tables.

``variant_group`` names the vehicle a row is folded under in the purchase menu,
``menu_order`` is where it sits in that list, and ``series_string`` is the STR a
group header shows.  All three go next to ``comment``, since they are about how
the depot window presents the row rather than about the vehicle itself.

``menu_order`` is filled in from the order the menu already had (the tables in
their documented order, then the row order), numbered in tens so a row can be
moved between two others without renumbering the rest.  Leave the cell empty and
the row sorts after every row that sets it.

Columns are added one at a time, so running this again after a new column is
introduced adds only what is missing.  The comment header is kept.

    python3 tools/migrate_menu_columns.py
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = ("locomotives.csv", "coaches.csv", "wagons.csv", "unit_wagons.csv")
# the order they are inserted in, right before "comment"
NEW_COLUMNS = ("variant_group", "menu_order", "series_string")


def read(path: Path):
    """Comments, header and body rows, with the header located by its "id"."""
    comments: list[str] = []
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.lstrip().startswith("#"):
            comments.append(line)
        elif line.strip():
            lines.append(line)
    records = list(csv.reader(lines))
    header = [cell.strip() for cell in records[0]]
    body = [dict(zip(header, row + [""] * (len(header) - len(row))))
            for row in records[1:] if row and row[0].strip()]
    return comments, header, body


def write(path: Path, comments, header, body) -> None:
    buffer = io.StringIO()
    for line in comments:
        buffer.write(line + "\n")
    writer = csv.DictWriter(buffer, fieldnames=header, lineterminator="\n")
    writer.writeheader()
    for record in body:
        writer.writerow({key: record.get(key, "") for key in header})
    path.write_text(buffer.getvalue(), encoding="utf-8", newline="")


def main() -> int:
    # Read every table first: the numbering below runs across all of them, so it
    # must not depend on which file happens to need a column.
    tables = []
    for name in TABLES:
        path = ROOT / "data" / name
        comments, header, body = read(path)
        tables.append((name, path, comments, header, body))

    order = 0
    for name, path, comments, header, body in tables:
        missing = [column for column in NEW_COLUMNS if column not in header]
        if not missing:
            print("%-18s already migrated" % name)
            continue
        target = header.index("comment") if "comment" in header else len(header)
        for column in NEW_COLUMNS:
            if column not in header:
                header.insert(target, column)
                target += 1
        for record in body:
            for column in missing:
                record[column] = record.get(column, "")
            if "menu_order" in missing:
                order += 10
                record["menu_order"] = record["menu_order"] or str(order)
        write(path, comments, header, body)
        print("%-18s added %s (%d columns, %d rows)"
              % (name, ", ".join(missing), len(header), len(body)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
