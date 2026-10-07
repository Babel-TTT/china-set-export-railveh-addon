"""Add the min_cars column to the four vehicle tables.

min_cars is the shortest train an MU may be started as, counted in three car
units (one unit is one three section car).  0 means "no minimum", so a single
unit may run on its own.
"""
import csv
import os

ROOT = r"D:\CNS\CNST\local\china-set-export-railveh-addon"
TABLES = ("locomotives.csv", "coaches.csv", "wagons.csv", "unit_wagons.csv")


def read(path):
    comments, lines = [], []
    with open(path, encoding="utf-8-sig", newline="") as handle:
        for line in handle:
            if line.lstrip().startswith("#"):
                comments.append(line.rstrip("\r\n"))
            elif line.strip():
                lines.append(line)
    records = list(csv.reader(lines))
    header = [cell.strip() for cell in records[0]]
    body = []
    for raw in records[1:]:
        if raw and raw[0].strip():
            body.append(dict(zip(header, raw + [""] * (len(header) - len(raw)))))
    return comments, header, body


def write(path, comments, header, body):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for line in comments:
            handle.write(line + "\n")
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        for record in body:
            writer.writerow({key: record.get(key, "") for key in header})


for name in TABLES:
    path = os.path.join(ROOT, "data", name)
    comments, header, body = read(path)
    if "min_cars" in header:
        # a previous run appended it after comment; move it next to mu
        header.remove("min_cars")
    target = header.index("wagon_decay") + 1
    header.insert(target, "min_cars")
    for record in body:
        record.setdefault("min_cars", "")
    write(path, comments, header, body)
    print("%-18s now %d columns, %d rows, min_cars at %d"
          % (name, len(header), len(body), target))
