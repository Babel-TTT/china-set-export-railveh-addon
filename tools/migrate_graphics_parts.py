"""One-off: drop the model column and add graphics_parts to the vehicle tables.

Every vehicle is three sections now, so `model` carries no information.  The new
`graphics_parts` column goes next to `parts` and `power_section`, where the rest
of the section handling lives.
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
    if "model" not in header:
        print("%-18s already migrated" % name)
        continue
    header = [column for column in header if column != "model"]
    # put graphics_parts right after power_section, next to the section columns
    target = header.index("power_section") + 1
    header.insert(target, "graphics_parts")
    for record in body:
        record.pop("model", None)
        record.setdefault("graphics_parts", "")
    write(path, comments, header, body)
    print("%-18s %d columns, %d rows migrated" % (name, len(header), len(body)))
