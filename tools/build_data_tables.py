#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/build_data_tables.py -- create the small auxiliary data tables

> **The vehicle tables are NOT written by this script.**  `data/locomotives.csv`,
> `coaches.csv`, `wagons.csv` and `unit_wagons.csv` hold the project's real
> vehicle data and are edited with `tools/vehicle_row.py` or by hand.  This
> helper only creates the two optional auxiliary tables, whose cells frequently
> contain commas and are therefore easy to get wrong when typed by hand:
>
>   * `data/liveries.csv`        paint schemes
>   * `data/cargo_variants.csv`  freight appearance per cargo
>
> It is a *starter*: it writes a documented example of each table.  Once the
> file exists, edit it directly -- re-running this script overwrites it.

    python3 tools/build_data_tables.py            # write the auxiliary tables
    python3 tools/build_data_tables.py --check    # only report what exists
"""

from __future__ import annotations

import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

LIVERY_COLUMNS = ("id", "sprite_suffix", "string", "from_year", "to_year",
                  "purchase_suffix", "templates")
VARIANT_COLUMNS = ("id", "variant", "sprite_suffix", "cargo_classes", "cargo_types",
                   "from_index", "to_index", "template")

# --------------------------------------------------------------------------
# example livery table, showing the shape the generator expects
# --------------------------------------------------------------------------
# id, sprite suffix, livery label, first build year, last build year
LIVERIES = [
    ("ckd4a", "", "STR_BUILD_YEAR", 0, 9999),
    ("ckd8f", "", "STR_BUILD_YEAR", 0, 2009),
    ("ckd8f", "exblue", "STR_EXPORT_BLUE", 2010, 9999),
    ("df4bex", "", "STR_BUILD_YEAR", 0, 9999),
    ("df4bex", "dprk", "STR_DPRK_LIVERY", 0, 9999),
    ("df4bex", "ukraine", "STR_UKRAINE_LIVERY", 0, 9999),
    ("yz25tex", "", "STR_BUILD_YEAR", 0, 2014),
    ("yz25tex", "green", "STR_EXPORT_GREEN", 2015, 9999),
    ("c70ex", "", "STR_BUILD_YEAR", 0, 9999),
    ("c70ex", "gray", "STR_EXPORT_GRAY", 0, 9999),
]

# --------------------------------------------------------------------------
# example freight appearance table
# --------------------------------------------------------------------------
# id, variant, sprite suffix, cargo class selector, cargo type list,
# first cargo_count of the partial load, last cargo_count of the partial load
VARIANTS = [
    ("c70ex", "coal", "c70ex-coal", "bitmask(CC_BULK)", "", 6, 45),
    ("c70ex", "cont", "c70ex-container", "bitmask(CC_MAIL)", "", 6, 40),
    ("c70ex", "cover", "c70ex-cover", "bitmask(CC_COVERED)", "", 0, 0),
    ("p70ex", "metal", "p70ex-metal", "",
     "ALUM|COPR|CSTI|IRON|METL|PIPE|STEL|STAL|STST|STCB|STSE|STSH|STWR|ZINC", 6, 40),
    ("p70ex", "goods", "p70ex-goods", "",
     "GOOD|GRAI|WOOD|WHEA|FOOD|FRUT|MAIZ|SAND|CMNT|FERT|CLAY|KAOL|SALT|SUGR", 6, 38),
    ("jsq5ex", "vehi", "jsq5ex-vehi", "", "VEHI", 3, 10),
]

VEHICLE_TABLES = ("locomotives.csv", "coaches.csv", "wagons.csv", "unit_wagons.csv")

# The authoritative column order of the four vehicle tables.  This script never
# writes them, but the list is kept here so that the schema can be checked
# against the real files (see tools/check_data_schema.py).  Every column is read
# by genpnml.py -- in particular `capacity_by_cargo` and `train_flags` used to be
# missing from the header, so the generator silently never saw them.
VEHICLE_COLUMNS = (
    "id", "name_string", "category", "folder", "model", "parts", "power_section",
    "intro_year", "intro_month", "intro_day", "model_life", "retire_early",
    "vehicle_life", "track_type", "climates_available", "speed", "power",
    "power_unit", "weight", "tractive_effort_coefficient", "cost_factor",
    "running_cost_factor", "purchase_running_cost_factor", "purchase_cost_display",
    "reliability_decay", "purchase_speed", "purchase_power",
    "refittable_cargo_classes", "non_refittable_cargo_classes", "cargo_allow_refit",
    "cargo_disallow_refit", "default_cargo_type", "ai_special_flag", "capacity",
    "capacity_by_cargo", "loading_speed", "cargo_age_period", "train_flags",
    "ac_supply", "airconditioned", "restaurant", "mu", "name_callback",
    "wagon_decay", "additional_text", "comment",
)


def write_liveries(path):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("# China Set: Export Rail Vehicles Add-on -- livery table\n#\n")
        handle.write("# One row per paint scheme.  The row order for one vehicle defines the\n")
        handle.write("# livery index used by the refit menu: index 0 is the automatic choice\n")
        handle.write("# and switches on build_year, index 1+ can be picked explicitly.\n")
        handle.write("# A vehicle with no row here gets one default livery whose sprite\n")
        handle.write("# basename is just its id.\n")
        handle.write("# See data/README.md for the column reference.\n#\n")
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(LIVERY_COLUMNS)
        previous = None
        for cid, suffix, label, from_year, to_year in LIVERIES:
            if previous is not None and cid != previous:
                writer.writerow([])
            previous = cid
            writer.writerow([cid, suffix, label, from_year, to_year, "", ""])


def write_variants(path):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("# China Set: Export Rail Vehicles Add-on -- freight appearance table\n#\n")
        handle.write("# Describes how a wagon looks depending on what it carries and how full\n")
        handle.write("# it is.  The generator builds this chain for every row group:\n#\n")
        handle.write("#   switch_<id>_empty         cargo_count < 5    ->  empty sprite\n")
        handle.write("#   switch_<id>_cargo_class   cargo_classes      ->  one entry per row\n")
        handle.write("#   switch_<id>_cargo_type    cargo_type_in_veh ->  rows with cargo_types\n")
        handle.write("#   switch_<id>_<variant>_stage  cargo_count    ->  partial / full load\n#\n")
        handle.write("# A row whose sprite_suffix is empty means \"unloaded, use the livery\n")
        handle.write("# sprite itself\".  See data/README.md for the column reference.\n#\n")
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(VARIANT_COLUMNS)
        previous = None
        for cid, variant, suffix, classes, types, from_index, to_index in VARIANTS:
            if previous is not None and cid != previous:
                writer.writerow([])
            previous = cid
            writer.writerow([cid, variant, suffix, classes, types,
                             from_index, to_index, ""])


def main(argv):
    check_only = "--check" in argv

    print("=== auxiliary tables ===")
    for name, writer in (("liveries.csv", write_liveries),
                         ("cargo_variants.csv", write_variants)):
        path = os.path.join(ROOT, "data", name)
        if check_only:
            state = "exists" if os.path.exists(path) else "missing"
            print("  %-22s %s" % (name, state))
        else:
            writer(path)
            print("  %-22s written (overwrites any existing file)" % name)

    print("=== vehicle tables (never touched by this script) ===")
    for name in VEHICLE_TABLES:
        path = os.path.join(ROOT, "data", name)
        rows = 0
        if os.path.exists(path):
            with open(path, encoding="utf-8-sig", newline="") as handle:
                header_seen = False
                for line in handle:
                    if line.lstrip().startswith("#") or not line.strip():
                        continue
                    if not header_seen:
                        header_seen = True
                        continue
                    rows += 1
        print("  %-22s %3d vehicle rows" % (name, rows))
    print()
    print("Use tools/vehicle_row.py to add, copy or remove a vehicle row.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
