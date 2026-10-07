#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
str-csv.py -- build lang/*.lng from docs/str.csv

The CSV has three columns:  STRING, ENGLISH, SIMPLIFIED CHINESE.
A row whose first cell starts with '#' is a comment and is copied through as a
bare string ID (so the generated language files stay readable).

Usage:
    python3 str-csv.py docs/str.csv
"""

import csv
import os
import sys


def load(path):
    rows = []
    with open(path, mode="r", newline="", encoding="utf-8-sig") as handle:
        for row in csv.reader(handle):
            if not row:
                continue
            # pad so the column indices below are always valid
            while len(row) < 3:
                row.append("")
            rows.append(row)
    return rows


def write_language(path, lang_id, rows, column, header):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("##grflangid %s\n" % lang_id)
        for row in rows:
            key = row[0].strip()
            if not key:
                continue
            if key.startswith("#"):
                handle.write(key + "\n")
                continue
            default = row[1]
            value = row[column]
            if not value:
                # fall back to English when the translation is missing, but
                # only when English itself carries a value
                if default:
                    value = default
                else:
                    handle.write(key + "\n")
                    continue
            handle.write("%-48s :%s\n" % (key, value))


def main(argv):
    if len(argv) < 2:
        print("Please input the path of the csv file.")
        return 1
    path = argv[1]
    rows = load(path)

    if not os.path.exists("lang/"):
        os.makedirs("lang/")

    write_language("lang/english.lng", "0x01", rows, 1, "ENGLISH")
    write_language("lang/simplified_chinese.lng", "0x56", rows, 2, "SIMPLIFIED CHINESE")

    print("str-csv: %d string rows -> lang/english.lng, lang/simplified_chinese.lng"
          % len([r for r in rows if r[0].strip() and not r[0].strip().startswith("#")]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
