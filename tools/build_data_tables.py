#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/build_data_tables.py -- authoring helper for data/*.csv

The vehicle tables are declarative data, but several cells legitimately contain
commas (``bitmask(CC_MAIL, CC_BULK)``, ``[PASS, TOUR]``, a vehicle name such as
"C70 (Export) (Open Wagon)").  Editing those by hand is error prone, so the
tables in this repository are generated from the literal Python tuples below:

    python3 tools/build_data_tables.py

The result is plain CSV that can still be edited by hand afterwards -- this
script only exists to guarantee the quoting is right from the start.
"""

from __future__ import annotations

import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

COLUMNS = (
    "id name_string category folder model parts power_section intro_year intro_month "
    "intro_day model_life retire_early vehicle_life track_type climates_available speed "
    "power power_unit weight tractive_effort_coefficient cost_factor running_cost_factor "
    "purchase_running_cost_factor purchase_cost_display reliability_decay purchase_speed "
    "purchase_power refittable_cargo_classes non_refittable_cargo_classes cargo_allow_refit "
    "cargo_disallow_refit default_cargo_type ai_special_flag capacity loading_speed "
    "cargo_age_period ac_supply airconditioned restaurant mu name_callback wagon_decay "
    "additional_text comment"
).split()

# A row is given as a dict; missing keys take the default below.
DEFAULTS = {
    "category": "diesel",
    "folder": "diesel",
    "model": "single",
    "parts": "4",
    "power_section": "0",
    "intro_month": "1",
    "intro_day": "1",
    "model_life": "VEHICLE_NEVER_EXPIRES",
    "retire_early": "",
    "vehicle_life": "30",
    "track_type": "SACN",
    "climates_available": "ALL_CLIMATES",
    "speed": "120",
    "power": "0",
    "power_unit": "hp",
    "weight": "40",
    "tractive_effort_coefficient": "0.0",
    "cost_factor": "10",
    "running_cost_factor": "6",
    "purchase_running_cost_factor": "",
    "purchase_cost_display": "",
    "reliability_decay": "10",
    "purchase_speed": "",
    "purchase_power": "",
    "refittable_cargo_classes": "bitmask(CC_PASSENGERS)",
    "non_refittable_cargo_classes": "0",
    "cargo_allow_refit": "[]",
    "cargo_disallow_refit": "[]",
    "default_cargo_type": "PASS",
    "ai_special_flag": "AI_FLAG_PASSENGER",
    "capacity": "0",
    "loading_speed": "8",
    "cargo_age_period": "185",
    "ac_supply": "0",
    "airconditioned": "0",
    "restaurant": "0",
    "mu": "0",
    "name_callback": "0",
    "wagon_decay": "0",
    "additional_text": "",
    "comment": "",
}


def row(**kwargs) -> dict:
    record = dict(DEFAULTS)
    record.update(kwargs)
    unknown = set(record) - set(COLUMNS)
    if unknown:
        raise SystemExit("unknown columns: %s" % sorted(unknown))
    return {column: str(record.get(column, "")) for column in COLUMNS}


def loco(cid, name, category, folder, model, parts, section, year,
         speed, power, unit, weight, te, cost, run, **extra) -> dict:
    base = dict(
        id=cid, name_string=name, category=category, folder=folder, model=model,
        parts=parts, power_section=section, intro_year=year, speed=speed,
        power=power, power_unit=unit, weight=weight,
        tractive_effort_coefficient=te, cost_factor=cost,
        running_cost_factor=run, name_callback="1",
        refittable_cargo_classes="bitmask(CC_PASSENGERS)", capacity="1",
        cargo_allow_refit="[]", cargo_disallow_refit="[]",
        default_cargo_type="PASS", ai_special_flag="AI_FLAG_PASSENGER",
    )
    base.update(extra)
    return row(**base)


HEADER_NOTE = {
    "locomotives.csv": "locomotive / multiple unit head table",
    "coaches.csv": "passenger coach table",
    "wagons.csv": "freight wagon table",
    "unit_wagons.csv": "multiple unit trailer table",
}

# --------------------------------------------------------------------------
# locomotives
# --------------------------------------------------------------------------

DIESEL = [
    loco("ckd4a", "CKD4A (Export)", "diesel", "diesel", "single", "4", "0", "1993",
         100, 1000, "kW", 92, 0.25, 45, 40, model_life="40", retire_early="20",
         vehicle_life="25", track_type="BACN", purchase_running_cost_factor="120",
         purchase_cost_display="45", reliability_decay="12",
         ac_supply="1", comment="Single-section export diesel for South East Asia (estimate)"),
    loco("ckd4b", "CKD4B (Export)", "diesel", "diesel", "single", "4", "0", "1995",
         120, 1200, "kW", 92, 0.25, 48, 44, model_life="40", retire_early="20",
         vehicle_life="25", track_type="BACN", purchase_running_cost_factor="132",
         purchase_cost_display="48", reliability_decay="12",
         ac_supply="1", comment="Single-section export diesel for South East Asia (estimate)"),
    loco("ckd4c", "CKD4C (Export)", "diesel", "diesel", "single", "4", "0", "1998",
         120, 1320, "kW", 92, 0.25, 50, 46, model_life="40", retire_early="20",
         vehicle_life="25", track_type="SACN", purchase_running_cost_factor="138",
         purchase_cost_display="50", reliability_decay="12",
         ac_supply="1", comment="Single-section export diesel, metre and standard gauge (estimate)"),
    loco("ckd6e", "CKD6E (Export)", "diesel", "diesel", "single", "5", "0", "2005",
         120, 1500, "kW", 120, 0.24, 55, 50, track_type="BACN",
         purchase_running_cost_factor="150", purchase_cost_display="55",
         ac_supply="1", comment="Co-Co export diesel (estimate)"),
    loco("ckd7a", "CKD7A (Export)", "diesel", "diesel", "triple", "2|4|2", "1", "2000",
         100, 1400, "kW", 138, 0.23, 58, 52, track_type="BACN",
         purchase_running_cost_factor="156", purchase_cost_display="58",
         ac_supply="1", comment="Twin-section export diesel (estimate)"),
    loco("ckd7b", "CKD7B (Export)", "diesel", "diesel", "triple", "2|4|2", "1", "2003",
         100, 1500, "kW", 138, 0.23, 60, 54, track_type="BACN",
         purchase_running_cost_factor="162", purchase_cost_display="60",
         ac_supply="1", comment="Twin-section export diesel (estimate)"),
    loco("ckd8a", "CKD8A (Export)", "diesel", "diesel", "single", "6", "0", "1998",
         120, 1800, "kW", 138, 0.24, 62, 56, purchase_running_cost_factor="168",
         purchase_cost_display="62", ac_supply="1", comment="Heavy export diesel (estimate)"),
    loco("ckd8b", "CKD8B (Export)", "diesel", "diesel", "single", "6", "0", "2000",
         120, 2000, "kW", 138, 0.24, 66, 58, purchase_running_cost_factor="174",
         purchase_cost_display="66", ac_supply="1", comment="Heavy export diesel (estimate)"),
    loco("ckd8c", "CKD8C (Export)", "diesel", "diesel", "single", "6", "0", "2002",
         120, 2200, "kW", 138, 0.24, 70, 60, purchase_running_cost_factor="180",
         purchase_cost_display="70", ac_supply="1", comment="Heavy export diesel (estimate)"),
    loco("ckd8d", "CKD8D (Export)", "diesel", "diesel", "single", "6", "0", "2004",
         120, 2400, "kW", 138, 0.25, 74, 62, purchase_running_cost_factor="186",
         purchase_cost_display="74", ac_supply="1", comment="Heavy export diesel (estimate)"),
    loco("ckd8e", "CKD8E (Export)", "diesel", "diesel", "single", "6", "0", "2006",
         120, 2400, "kW", 138, 0.25, 74, 62, track_type="BACN",
         purchase_running_cost_factor="186", purchase_cost_display="74",
         ac_supply="1", comment="Broad gauge heavy export diesel (estimate)"),
    loco("ckd8f", "CKD8F (Export)", "diesel", "diesel", "single", "6", "0", "2008",
         120, 2600, "kW", 138, 0.25, 78, 64, track_type="BACN",
         purchase_running_cost_factor="192", purchase_cost_display="78",
         ac_supply="1", comment="Broad gauge heavy export diesel (estimate)"),
    loco("ckd8g", "CKD8G (Export)", "diesel", "diesel", "single", "6", "0", "2010",
         120, 2600, "kW", 138, 0.25, 78, 64, purchase_running_cost_factor="192",
         purchase_cost_display="78", ac_supply="1", comment="Heavy export diesel (estimate)"),
    loco("ckd8h", "CKD8H (Export)", "diesel", "diesel", "single", "6", "0", "2012",
         120, 2800, "kW", 138, 0.26, 84, 66, purchase_running_cost_factor="198",
         purchase_cost_display="84", ac_supply="1", comment="Heavy export diesel (estimate)"),
    loco("ckd8j", "CKD8J (Export)", "diesel", "diesel", "single", "6", "0", "2014",
         120, 2800, "kW", 138, 0.26, 84, 66, track_type="BACN",
         purchase_running_cost_factor="198", purchase_cost_display="84",
         ac_supply="1", comment="Broad gauge heavy export diesel (estimate)"),
    loco("ckd9a", "CKD9A (Export)", "diesel", "diesel", "single", "6", "0", "2016",
         120, 3000, "kW", 150, 0.26, 90, 70, purchase_running_cost_factor="210",
         purchase_cost_display="90", ac_supply="1", reliability_decay="8",
         comment="Modern AC transmission export diesel (estimate)"),
    loco("ckd9b", "CKD9B (Export)", "diesel", "diesel", "single", "6", "0", "2018",
         120, 3000, "kW", 150, 0.26, 90, 70, track_type="BACN",
         purchase_running_cost_factor="210", purchase_cost_display="90",
         ac_supply="1", reliability_decay="8",
         comment="Modern AC transmission export diesel (estimate)"),
    loco("ckd9c", "CKD9C (Export)", "diesel", "diesel", "single", "6", "0", "2020",
         120, 3200, "kW", 150, 0.27, 96, 72, purchase_running_cost_factor="216",
         purchase_cost_display="96", ac_supply="1", reliability_decay="8",
         comment="Modern AC transmission export diesel (estimate)"),
    loco("df4bex", "DF4B (Export)", "diesel", "diesel", "single", "6", "0", "1985",
         100, 1985, "kW", 138, 0.24, 60, 55, model_life="50", retire_early="30",
         purchase_running_cost_factor="165", purchase_cost_display="60",
         reliability_decay="12", ac_supply="1",
         comment="DF4B sold to DPRK / Ukraine / abroad (estimate)"),
    loco("df4dex", "DF4D (Export)", "diesel", "diesel", "single", "6", "0", "2000",
         145, 2940, "kW", 138, 0.25, 78, 68, model_life="50", retire_early="25",
         purchase_running_cost_factor="204", purchase_cost_display="78",
         ac_supply="1", comment="DF4D export variant (estimate)"),
    loco("df5ex", "DF5 (Export)", "diesel", "diesel", "single", "4", "0", "1985",
         100, 930, "kW", 120, 0.31, 45, 42, model_life="50", retire_early="25",
         vehicle_life="25", purchase_running_cost_factor="126",
         purchase_cost_display="45", reliability_decay="14", ac_supply="1",
         comment="Shunting diesel, also sold to Kazakhstan as DF5KZ (estimate)"),
    loco("df7gex", "DF7G (Export)", "diesel", "diesel", "single", "4", "0", "2003",
         100, 1470, "kW", 138, 0.30, 52, 46, purchase_running_cost_factor="138",
         purchase_cost_display="52", reliability_decay="12", ac_supply="1",
         comment="Heavy shunting and branch line diesel (estimate)"),
    loco("df8bex", "DF8B (Export)", "diesel", "diesel", "single", "6", "0", "1997",
         120, 3100, "kW", 138, 0.25, 80, 70, model_life="45",
         purchase_running_cost_factor="210", purchase_cost_display="80",
         ac_supply="1", comment="Main line freight diesel export variant (estimate)"),
    loco("df11ex", "DF11 (Export)", "diesel", "diesel", "single", "6", "0", "1992",
         170, 3860, "kW", 138, 0.25, 92, 84, model_life="50", retire_early="25",
         purchase_running_cost_factor="252", purchase_cost_display="92",
         ac_supply="1", comment="Main line passenger diesel export variant (estimate)"),
    loco("df21ex", "DF21 (Export)", "diesel", "diesel", "single", "4", "0", "2003",
         100, 1000, "kW", 92, 0.28, 40, 38, model_life="40", vehicle_life="25",
         track_type="BACN", purchase_running_cost_factor="114",
         purchase_cost_display="40", reliability_decay="14", ac_supply="1",
         comment="Narrow body metre gauge export diesel (estimate)"),
    loco("sd40_2ex", "SD40-2 (Export)", "diesel", "diesel", "single", "6", "0", "1972",
         105, 2200, "kW", 168, 0.22, 72, 64, model_life="50", retire_early="25",
         cost_factor="72", purchase_running_cost_factor="192",
         purchase_cost_display="72", reliability_decay="14", ac_supply="1",
         comment="Licence built export locomotive for Africa and South America (estimate)"),
    loco("sd70acex", "SD70ACe (Export)", "diesel", "diesel", "single", "6", "0", "2004",
         120, 3200, "kW", 180, 0.24, 110, 92, model_life="45",
         purchase_running_cost_factor="276", purchase_cost_display="110",
         ac_supply="1", reliability_decay="8",
         comment="Modern heavy export diesel for overseas heavy haul (estimate)"),
    loco("c30_7ex", "C30-7 (Export)", "diesel", "diesel", "single", "6", "0", "1977",
         105, 2200, "kW", 168, 0.22, 70, 62, model_life="50", retire_early="25",
         purchase_running_cost_factor="186", purchase_cost_display="70",
         reliability_decay="14", ac_supply="1",
         comment="Licence built export locomotive (estimate)"),
    loco("gt42cuacex", "GT42CU-AC (Export)", "diesel", "diesel", "single", "6", "0", "2005",
         115, 3100, "kW", 180, 0.23, 105, 88, model_life="45",
         purchase_running_cost_factor="264", purchase_cost_display="105",
         ac_supply="1", comment="Narrow gauge heavy haul export diesel for Australia (estimate)"),
    loco("ckd6dex", "CKD6D (Export)", "diesel", "diesel", "single", "5", "0", "2008",
         120, 1600, "kW", 126, 0.24, 58, 52, track_type="BACN",
         purchase_running_cost_factor="156", purchase_cost_display="58",
         ac_supply="1", comment="Co-Co export diesel (estimate)"),
    loco("ckd8kex", "CKD8K (Export)", "diesel", "diesel", "single", "6", "0", "2012",
         120, 2500, "kW", 144, 0.25, 76, 64, track_type="BACN",
         purchase_running_cost_factor="192", purchase_cost_display="76",
         ac_supply="1", comment="Broad gauge export diesel (estimate)"),
]

ELECTRIC = [
    loco("hxd1ex", "HXD1 (Export)", "electric", "25-electric", "single", "6", "0",
         "2007", 120, 9600, "kW", 200, 0.32, 180, 150, track_type="BAAA",
         purchase_running_cost_factor="450", purchase_cost_display="180",
         reliability_decay="10", ac_supply="1",
         comment="25 kV AC heavy haul export electric (estimate)"),
    loco("hxd2ex", "HXD2 (Export)", "electric", "25-electric", "single", "6", "0",
         "2007", 120, 10000, "kW", 200, 0.32, 185, 155, track_type="BAAA",
         purchase_running_cost_factor="465", purchase_cost_display="185",
         reliability_decay="10", ac_supply="1",
         comment="25 kV AC heavy haul export electric (estimate)"),
    loco("hxd3ex", "HXD3 (Export)", "electric", "25-electric", "single", "6", "0",
         "2006", 120, 7200, "kW", 138, 0.28, 150, 130, track_type="SAAA",
         purchase_running_cost_factor="390", purchase_cost_display="150",
         reliability_decay="10", ac_supply="1",
         comment="25 kV AC export electric (estimate)"),
    loco("ss3ex", "SS3 (Export)", "electric", "25-electric", "single", "6", "0",
         "1979", 100, 4800, "kW", 138, 0.26, 110, 100, model_life="50",
         retire_early="25", track_type="SAAA", purchase_running_cost_factor="300",
         purchase_cost_display="110", reliability_decay="14", ac_supply="1",
         comment="Vacuum braked export electric (estimate)"),
    loco("ss4ex", "SS4 (Export)", "electric", "25-electric", "triple", "2|4|2", "1",
         "1985", 100, 6400, "kW", 184, 0.30, 140, 124, model_life="50",
         retire_early="25", track_type="SAAA", purchase_running_cost_factor="372",
         purchase_cost_display="140", reliability_decay="12", ac_supply="1",
         comment="Twin-section export electric (estimate)"),
    loco("ss7ex", "SS7 (Export)", "electric", "25-electric", "single", "6", "0",
         "1992", 100, 4800, "kW", 138, 0.27, 108, 98, model_life="50",
         retire_early="25", track_type="SAAD", purchase_running_cost_factor="294",
         purchase_cost_display="108", reliability_decay="14", ac_supply="1",
         comment="Export electric for mountainous 3 kV DC lines (estimate)"),
    loco("ss8ex", "SS8 (Export)", "electric", "25-electric", "single", "4", "0",
         "1994", 170, 3600, "kW", 88, 0.24, 127, 104, model_life="50",
         retire_early="30", track_type="SACA", purchase_running_cost_factor="312",
         purchase_cost_display="127", reliability_decay="10",
         purchase_speed="170", purchase_power="3600", ac_supply="1",
         comment="High speed export electric (estimate)"),
    loco("ss9ex", "SS9 (Export)", "electric", "25-electric", "single", "6", "0",
         "2002", 170, 4800, "kW", 126, 0.25, 150, 124, model_life="45",
         track_type="SACA", purchase_running_cost_factor="372",
         purchase_cost_display="150", reliability_decay="10",
         purchase_speed="170", purchase_power="4800", ac_supply="1",
         comment="High speed export electric (estimate)"),
]

STEAM = [
    loco("qjex", "QJ (Export)", "steam", "steam", "single", "6", "0", "1956",
         80, 2200, "kW", 240, 0.28, 70, 90, model_life="35", retire_early="20",
         vehicle_life="25", purchase_running_cost_factor="270",
         purchase_cost_display="70", reliability_decay="25", name_callback="0",
         comment="2-10-2 steam locomotive built for industrial and export service"),
]

DMU = [
    loco("ndj3ex", "NDJ3 (Export)", "dmu", "dmu", "triple", "2|4|2", "1", "2008",
         160, 2200, "kW", 138, 0.22, 90, 80, mu="1", ai_special_flag="AI_FLAG_PASSENGER",
         capacity="60", cargo_age_period="185", ac_supply="1", airconditioned="1",
         purchase_running_cost_factor="240", purchase_cost_display="90",
         purchase_speed="160", purchase_power="2200",
         comment="Diesel multiple unit for export (estimate)"),
    loco("nzj2ex", "NZJ2 (Export)", "dmu", "dmu", "triple", "2|4|2", "1", "2010",
         160, 2500, "kW", 150, 0.22, 95, 84, track_type="BACN", mu="1",
         capacity="64", ac_supply="1", airconditioned="1",
         purchase_running_cost_factor="252", purchase_cost_display="95",
         purchase_speed="160", purchase_power="2500",
         comment="Diesel multiple unit for export (estimate)"),
]

EMU = [
    loco("crh2ex", "CRH2 (Export)", "emu", "25-emu", "triple", "2|8|2", "1", "2007",
         250, 4800, "kW", 140, 0.20, 120, 105, track_type="SABA", mu="1",
         capacity="100", cargo_age_period="400", ac_supply="1", airconditioned="1",
         reliability_decay="8", purchase_running_cost_factor="315",
         purchase_cost_display="120", purchase_speed="250", purchase_power="4800",
         comment="High speed EMU head car for export (estimate)"),
    loco("crh5ex", "CRH5 (Export)", "emu", "25-emu", "triple", "2|8|2", "1", "2007",
         250, 5500, "kW", 150, 0.20, 125, 110, track_type="SABA", mu="1",
         capacity="100", cargo_age_period="400", ac_supply="1", airconditioned="1",
         reliability_decay="8", purchase_running_cost_factor="330",
         purchase_cost_display="125", purchase_speed="250", purchase_power="5500",
         comment="High speed EMU for cold climate export (estimate)"),
    loco("crh6ex", "CRH6 (Export)", "emu", "25-emu", "triple", "2|8|2", "1", "2012",
         200, 3000, "kW", 120, 0.20, 105, 92, track_type="SABA", mu="1",
         capacity="120", cargo_age_period="300", loading_speed="10",
         ac_supply="1", airconditioned="1", reliability_decay="8",
         purchase_running_cost_factor="276", purchase_cost_display="105",
         purchase_speed="200", purchase_power="3000",
         comment="Intercity EMU for export (estimate)"),
    loco("cr400aex", "CR400AF (Export)", "emu", "25-emu", "triple", "2|8|2", "1",
         "2017", 350, 9750, "kW", 180, 0.19, 190, 170, track_type="SABA", mu="1",
         capacity="110", cargo_age_period="400", ac_supply="1", airconditioned="1",
         reliability_decay="5", purchase_running_cost_factor="510",
         purchase_cost_display="190", purchase_speed="350", purchase_power="9750",
         comment="High speed EMU head car for export (estimate)"),
    loco("cr400bex", "CR400BF (Export)", "emu", "25-emu", "triple", "2|8|2", "1",
         "2017", 350, 9750, "kW", 180, 0.19, 190, 170, track_type="SABA", mu="1",
         capacity="110", cargo_age_period="400", ac_supply="1", airconditioned="1",
         reliability_decay="5", purchase_running_cost_factor="510",
         purchase_cost_display="190", purchase_speed="350", purchase_power="9750",
         comment="High speed EMU head car for export (estimate)"),
]

# --------------------------------------------------------------------------
# coaches
# --------------------------------------------------------------------------

COACHES = [
    row(id="yz25tex", name_string="YZ25T (Export) (Hard Seat)", category="coach",
        folder="coaches", model="triple", parts="2|8|2", power_section="1",
        intro_year="2004", speed="160", power="0", power_unit="hp", weight="47.3",
        cost_factor="9", running_cost_factor="6", purchase_running_cost_factor="24",
        purchase_cost_display="9", capacity="118", cargo_age_period="185",
        airconditioned="1", refittable_cargo_classes="bitmask(CC_PASSENGERS)",
        cargo_allow_refit="[PASS|TOUR]",
        additional_text="",
        comment="Export hard seat coach, 25T family (estimate)"),
    row(id="yw25tex", name_string="YW25T (Export) (Hard Sleeper)", category="coach",
        folder="coaches", model="triple", parts="2|8|2", power_section="1",
        intro_year="2004", speed="160", power="0", power_unit="hp", weight="47.6",
        cost_factor="10", running_cost_factor="6", purchase_running_cost_factor="27",
        purchase_cost_display="10", capacity="66", cargo_age_period="190",
        airconditioned="1", refittable_cargo_classes="bitmask(CC_PASSENGERS)",
        cargo_allow_refit="[PASS|TOUR]",
        additional_text="",
        comment="Export hard sleeper coach (estimate)"),
    row(id="rw25tex", name_string="RW25T (Export) (Soft Sleeper)", category="coach",
        folder="coaches", model="triple", parts="2|8|2", power_section="1",
        intro_year="2004", speed="160", power="0", power_unit="hp", weight="48.0",
        cost_factor="14", running_cost_factor="7", purchase_running_cost_factor="36",
        purchase_cost_display="14", capacity="36", cargo_age_period="200",
        airconditioned="1", refittable_cargo_classes="bitmask(CC_PASSENGERS)",
        cargo_allow_refit="[PASS|TOUR]",
        additional_text="",
        comment="Export soft sleeper coach (estimate)"),
    row(id="ca25tex", name_string="CA25T (Export) (Restaurant Car)", category="coach",
        folder="coaches", model="triple", parts="2|8|2", power_section="1",
        intro_year="2004", speed="160", power="0", power_unit="hp", weight="48.0",
        cost_factor="13", running_cost_factor="7", purchase_running_cost_factor="33",
        purchase_cost_display="13", capacity="48", cargo_age_period="200",
        airconditioned="1", restaurant="1",
        refittable_cargo_classes="bitmask(CC_PASSENGERS)", cargo_allow_refit="[PASS|TOUR]",
        additional_text="",
        comment="Export restaurant car (estimate)"),
    row(id="kd25tex", name_string="KD25T (Export) (Generator Car)", category="coach",
        folder="coaches", model="triple", parts="2|8|2", power_section="1",
        intro_year="2004", speed="160", power="0", power_unit="hp", weight="52.0",
        cost_factor="12", running_cost_factor="7", purchase_running_cost_factor="30",
        purchase_cost_display="12", capacity="0", cargo_age_period="185",
        ac_supply="1", refittable_cargo_classes="0",
        cargo_allow_refit="[]", default_cargo_type="PASS",
        additional_text="",
        comment="Export air conditioner generator car (estimate)"),
    row(id="yz22ex", name_string="YZ22 (Export) (Hard Seat)", category="coach",
        folder="coaches", model="triple", parts="2|8|2", power_section="1",
        intro_year="1980", speed="120", power="0", power_unit="hp", weight="45.0",
        cost_factor="7", running_cost_factor="5", purchase_running_cost_factor="20",
        purchase_cost_display="7", capacity="108", cargo_age_period="180",
        vehicle_life="28", refittable_cargo_classes="bitmask(CC_PASSENGERS)",
        cargo_allow_refit="[PASS|TOUR]",
        additional_text="",
        comment="Export hard seat coach, 22 family (estimate)"),
    row(id="yw22ex", name_string="YW22 (Export) (Hard Sleeper)", category="coach",
        folder="coaches", model="triple", parts="2|8|2", power_section="1",
        intro_year="1980", speed="120", power="0", power_unit="hp", weight="45.5",
        cost_factor="8", running_cost_factor="5", purchase_running_cost_factor="22",
        purchase_cost_display="8", capacity="60", cargo_age_period="185",
        vehicle_life="28", refittable_cargo_classes="bitmask(CC_PASSENGERS)",
        cargo_allow_refit="[PASS|TOUR]",
        additional_text="",
        comment="Export hard sleeper coach (estimate)"),
    row(id="xl25ex", name_string="XL25 (Export) (Luggage Van)", category="coach",
        folder="coaches", model="triple", parts="2|8|2", power_section="1",
        intro_year="1995", speed="140", power="0", power_unit="hp", weight="42.0",
        cost_factor="8", running_cost_factor="5", purchase_running_cost_factor="20",
        purchase_cost_display="8", capacity="90", cargo_age_period="185",
        refittable_cargo_classes="bitmask(CC_MAIL, CC_EXPRESS, CC_PIECE_GOODS)",
        cargo_allow_refit="[MAIL]", default_cargo_type="MAIL",
        ai_special_flag="AI_FLAG_CARGO",
        additional_text="",
        comment="Export luggage van (estimate)"),
    row(id="uz25ex", name_string="UZ25 (Export) (Postal Car)", category="coach",
        folder="coaches", model="triple", parts="2|8|2", power_section="1",
        intro_year="1995", speed="140", power="0", power_unit="hp", weight="42.0",
        cost_factor="8", running_cost_factor="5", purchase_running_cost_factor="20",
        purchase_cost_display="8", capacity="100", cargo_age_period="185",
        refittable_cargo_classes="bitmask(CC_MAIL)", cargo_allow_refit="[MAIL]",
        default_cargo_type="MAIL", ai_special_flag="AI_FLAG_CARGO",
        additional_text="",
        comment="Export postal car (estimate)"),
]

# --------------------------------------------------------------------------
# wagons
# --------------------------------------------------------------------------

WAGONS = [
    row(id="c70ex", name_string="C70 (Export) (Open Wagon)", category="wagon",
        folder="wagons", model="triple", parts="2|2|2", power_section="1",
        intro_year="2005", speed="120", weight="23.8", cost_factor="6",
        running_cost_factor="5", purchase_running_cost_factor="20",
        purchase_cost_display="6", capacity="70",
        refittable_cargo_classes="bitmask(CC_MAIL, CC_EXPRESS, CC_BULK, CC_PIECE_GOODS, CC_COVERED, CC_OVERSIZED)",
        non_refittable_cargo_classes="bitmask(CC_PASSENGERS, CC_LIQUID, CC_HAZARDOUS)",
        cargo_disallow_refit="[YETI|YETY]", default_cargo_type="DEFAULT_CARGO_FIRST_REFITTABLE",
        ai_special_flag="AI_FLAG_CARGO", wagon_decay="1",
        additional_text="",
        comment="Export open wagon (estimate)"),
    row(id="c64ex", name_string="C64 (Export) (Open Wagon)", category="wagon",
        folder="wagons", model="triple", parts="2|2|2", power_section="1",
        intro_year="1990", speed="100", weight="22.5", cost_factor="7",
        running_cost_factor="5", purchase_running_cost_factor="20",
        purchase_cost_display="7", capacity="64", track_type="BACN",
        refittable_cargo_classes="bitmask(CC_MAIL, CC_EXPRESS, CC_BULK, CC_PIECE_GOODS, CC_COVERED)",
        non_refittable_cargo_classes="bitmask(CC_PASSENGERS, CC_LIQUID, CC_HAZARDOUS)",
        cargo_disallow_refit="[YETI|YETY]", default_cargo_type="DEFAULT_CARGO_FIRST_REFITTABLE",
        ai_special_flag="AI_FLAG_CARGO", wagon_decay="1",
        additional_text="",
        comment="Export open wagon (estimate)"),
    row(id="p70ex", name_string="P70 (Export) (Flat Wagon)", category="wagon",
        folder="wagons", model="triple", parts="2|2|2", power_section="1",
        intro_year="2005", speed="120", weight="22.0", cost_factor="8",
        running_cost_factor="5", purchase_running_cost_factor="20",
        purchase_cost_display="8", capacity="70",
        refittable_cargo_classes="bitmask(CC_PIECE_GOODS, CC_OVERSIZED, CC_COVERED, CC_BULK)",
        non_refittable_cargo_classes="bitmask(CC_PASSENGERS, CC_LIQUID)",
        cargo_disallow_refit="[YETI|YETY]", default_cargo_type="DEFAULT_CARGO_FIRST_REFITTABLE",
        ai_special_flag="AI_FLAG_CARGO", wagon_decay="1",
        additional_text="",
        comment="Export flat wagon (estimate)"),
    row(id="n60ex", name_string="N60 (Export) (Flat Wagon)", category="wagon",
        folder="wagons", model="triple", parts="2|2|2", power_section="1",
        intro_year="1990", speed="100", weight="20.0", cost_factor="7",
        running_cost_factor="5", purchase_running_cost_factor="20",
        purchase_cost_display="7", capacity="60", track_type="BACN",
        refittable_cargo_classes="bitmask(CC_PIECE_GOODS, CC_OVERSIZED, CC_COVERED, CC_BULK)",
        non_refittable_cargo_classes="bitmask(CC_PASSENGERS, CC_LIQUID)",
        cargo_disallow_refit="[YETI|YETY]", default_cargo_type="DEFAULT_CARGO_FIRST_REFITTABLE",
        ai_special_flag="AI_FLAG_CARGO", wagon_decay="1",
        additional_text="",
        comment="Export flat wagon for containers and steel (estimate)"),
    row(id="g70ex", name_string="G70 (Export) (Tank Wagon)", category="wagon",
        folder="wagons", model="triple", parts="2|2|2", power_section="1",
        intro_year="2005", speed="120", weight="24.0", cost_factor="9",
        running_cost_factor="6", purchase_running_cost_factor="22",
        purchase_cost_display="9", capacity="70",
        refittable_cargo_classes="bitmask(CC_LIQUID, CC_HAZARDOUS)",
        non_refittable_cargo_classes="bitmask(CC_PASSENGERS, CC_BULK, CC_PIECE_GOODS)",
        cargo_disallow_refit="[YETI|YETY]", default_cargo_type="OIL_",
        ai_special_flag="AI_FLAG_CARGO", wagon_decay="1",
        additional_text="",
        comment="Export tank wagon (estimate)"),
    row(id="gn70ex", name_string="GN70 (Export) (Tank Wagon)", category="wagon",
        folder="wagons", model="triple", parts="2|2|2", power_section="1",
        intro_year="2008", speed="120", weight="26.0", cost_factor="10",
        running_cost_factor="6", purchase_running_cost_factor="24",
        purchase_cost_display="10", capacity="78",
        refittable_cargo_classes="bitmask(CC_LIQUID, CC_HAZARDOUS)",
        non_refittable_cargo_classes="bitmask(CC_PASSENGERS, CC_BULK, CC_PIECE_GOODS)",
        cargo_disallow_refit="[YETI|YETY]", default_cargo_type="OIL_",
        ai_special_flag="AI_FLAG_CARGO", wagon_decay="1",
        additional_text="",
        comment="Export high capacity tank wagon (estimate)"),
    row(id="jsq5ex", name_string="JSQ5 (Export) (Car Transporter)", category="wagon",
        folder="wagons", model="triple", parts="2|2|2", power_section="1",
        intro_year="2008", speed="120", weight="30.0", cost_factor="12",
        running_cost_factor="7", purchase_running_cost_factor="26",
        purchase_cost_display="12", capacity="18",
        refittable_cargo_classes="0", non_refittable_cargo_classes="0",
        cargo_allow_refit="[VEHI|ENSP|FMSP]", default_cargo_type="VEHI",
        ai_special_flag="AI_FLAG_CARGO", wagon_decay="1",
        additional_text="",
        comment="Export double deck car transporter (estimate)"),
    row(id="l70ex", name_string="L70 (Export) (Refrigerator Wagon)", category="wagon",
        folder="wagons", model="triple", parts="2|2|2", power_section="1",
        intro_year="2005", speed="120", weight="26.0", cost_factor="14",
        running_cost_factor="9", purchase_running_cost_factor="34",
        purchase_cost_display="14", capacity="64", cargo_age_period="300",
        loading_speed="6",
        refittable_cargo_classes="bitmask(CC_COVERED, CC_PIECE_GOODS)",
        non_refittable_cargo_classes="bitmask(CC_PASSENGERS, CC_BULK, CC_LIQUID)",
        cargo_disallow_refit="[YETI|YETY]", default_cargo_type="DEFAULT_CARGO_FIRST_REFITTABLE",
        ai_special_flag="AI_FLAG_CARGO", wagon_decay="1",
        additional_text="",
        comment="Export refrigerator wagon (estimate)"),
    row(id="b22ex", name_string="B22 (Export) (Boxcar)", category="wagon",
        folder="wagons", model="triple", parts="2|2|2", power_section="1",
        intro_year="1995", speed="120", weight="23.0", cost_factor="9",
        running_cost_factor="6", purchase_running_cost_factor="22",
        purchase_cost_display="9", capacity="70",
        refittable_cargo_classes="bitmask(CC_PIECE_GOODS, CC_COVERED, CC_EXPRESS, CC_MAIL)",
        non_refittable_cargo_classes="bitmask(CC_PASSENGERS, CC_LIQUID, CC_BULK)",
        cargo_disallow_refit="[YETI|YETY]", default_cargo_type="DEFAULT_CARGO_FIRST_REFITTABLE",
        ai_special_flag="AI_FLAG_CARGO", wagon_decay="1",
        additional_text="",
        comment="Export boxcar (estimate)"),
    row(id="sq8ex", name_string="SQ8 (Export) (Hopper Wagon)", category="wagon",
        folder="wagons", model="triple", parts="2|2|2", power_section="1",
        intro_year="2005", speed="120", weight="23.0", cost_factor="9",
        running_cost_factor="6", purchase_running_cost_factor="22",
        purchase_cost_display="9", capacity="75", loading_speed="10",
        refittable_cargo_classes="bitmask(CC_BULK)",
        non_refittable_cargo_classes="bitmask(CC_PASSENGERS, CC_LIQUID, CC_PIECE_GOODS)",
        cargo_disallow_refit="[YETI|YETY]", default_cargo_type="COAL",
        ai_special_flag="AI_FLAG_CARGO", wagon_decay="1",
        additional_text="",
        comment="Export hopper wagon (estimate)"),
    row(id="x2kex", name_string="X2K (Export) (Container Flat)", category="wagon",
        folder="wagons", model="triple", parts="2|2|2", power_section="1",
        intro_year="2005", speed="120", weight="20.0", cost_factor="8",
        running_cost_factor="5", purchase_running_cost_factor="20",
        purchase_cost_display="8", capacity="80",
        refittable_cargo_classes="bitmask(CC_PIECE_GOODS, CC_OVERSIZED, CC_COVERED)",
        non_refittable_cargo_classes="bitmask(CC_PASSENGERS, CC_LIQUID, CC_BULK)",
        cargo_disallow_refit="[YETI|YETY]", default_cargo_type="GOOD",
        ai_special_flag="AI_FLAG_CARGO", wagon_decay="1",
        additional_text="",
        comment="Export container flat wagon (estimate)"),
    row(id="dq35ex", name_string="DQ35 (Export) (Departmental)", category="wagon",
        folder="wagons", model="triple", parts="2|2|2", power_section="1",
        intro_year="2000", speed="100", weight="30.0", cost_factor="10",
        running_cost_factor="6", purchase_running_cost_factor="24",
        purchase_cost_display="10", capacity="50",
        refittable_cargo_classes="bitmask(CC_PIECE_GOODS, CC_OVERSIZED)",
        non_refittable_cargo_classes="bitmask(CC_PASSENGERS, CC_LIQUID, CC_BULK)",
        cargo_disallow_refit="[YETI|YETY]", default_cargo_type="DEFAULT_CARGO_FIRST_REFITTABLE",
        ai_special_flag="AI_FLAG_CARGO", wagon_decay="1",
        additional_text="",
        comment="Export crane and departmental wagon (estimate)"),
]

# --------------------------------------------------------------------------
# MU trailers
# --------------------------------------------------------------------------

UNIT_WAGONS = [
    row(id="zecex", name_string="ZE (Export) (MU Trailer, Hard Seat)",
        category="unit_wagon", folder="unit-wagons", model="triple",
        parts="2|8|2", power_section="1", intro_year="2007", speed="250",
        weight="52.0", cost_factor="10", running_cost_factor="6",
        purchase_running_cost_factor="24", purchase_cost_display="10",
        capacity="90", loading_speed="10", cargo_age_period="400",
        track_type="SABA", airconditioned="1",
        cargo_allow_refit="[PASS|TOUR]",
        additional_text="",
        comment="Export MU trailer, hard seat (estimate)"),
    row(id="zycex", name_string="ZY (Export) (MU Trailer, Hard Sleeper)",
        category="unit_wagon", folder="unit-wagons", model="triple",
        parts="2|8|2", power_section="1", intro_year="2007", speed="250",
        weight="54.0", cost_factor="11", running_cost_factor="6",
        purchase_running_cost_factor="26", purchase_cost_display="11",
        capacity="60", loading_speed="10", cargo_age_period="400",
        track_type="SABA", airconditioned="1", cargo_allow_refit="[PASS|TOUR]",
        additional_text="",
        comment="Export MU trailer, hard sleeper (estimate)"),
    row(id="zscex", name_string="ZS (Export) (MU Trailer, Double Deck)",
        category="unit_wagon", folder="unit-wagons", model="triple",
        parts="2|8|2", power_section="1", intro_year="2012", speed="200",
        weight="54.0", cost_factor="11", running_cost_factor="6",
        purchase_running_cost_factor="26", purchase_cost_display="11",
        capacity="120", loading_speed="10", cargo_age_period="400",
        track_type="SABA", airconditioned="1", cargo_allow_refit="[PASS|TOUR]",
        additional_text="",
        comment="Export MU trailer, double deck (estimate)"),
    row(id="zwcex", name_string="ZW (Export) (MU Trailer, Soft Sleeper)",
        category="unit_wagon", folder="unit-wagons", model="triple",
        parts="2|8|2", power_section="1", intro_year="2007", speed="250",
        weight="54.0", cost_factor="13", running_cost_factor="7",
        purchase_running_cost_factor="32", purchase_cost_display="13",
        capacity="40", loading_speed="10", cargo_age_period="400",
        track_type="SABA", airconditioned="1", cargo_allow_refit="[PASS|TOUR]",
        additional_text="",
        comment="Export MU trailer, soft sleeper (estimate)"),
]

TABLES = {
    "locomotives.csv": DIESEL + ELECTRIC + STEAM + DMU + EMU,
    "coaches.csv": COACHES,
    "wagons.csv": WAGONS,
    "unit_wagons.csv": UNIT_WAGONS,
}

# --------------------------------------------------------------------------
# livery table: a compact literal, expanded to CSV with an explicit "id" column
# --------------------------------------------------------------------------
# id, sprite suffix, livery label, first build year, last build year
LIVERIES = [
    ("ckd4a", "", "STR_BUILD_YEAR", 0, 9999),
    ("ckd8f", "", "STR_BUILD_YEAR", 0, 2009),
    ("ckd8f", "exblue", "STR_EXPORT_BLUE", 2010, 9999),
    ("hxd1ex", "", "STR_BUILD_YEAR", 0, 2011),
    ("hxd1ex", "exblue", "STR_EXPORT_BLUE", 2012, 9999),
    ("hxd2ex", "", "STR_BUILD_YEAR", 0, 2011),
    ("hxd2ex", "exblue", "STR_EXPORT_BLUE", 2012, 9999),
    ("hxd3ex", "", "STR_BUILD_YEAR", 0, 2010),
    ("hxd3ex", "exblue", "STR_EXPORT_BLUE", 2011, 9999),
    ("ss8ex", "", "STR_BUILD_YEAR", 0, 2002),
    ("ss8ex", "exblue", "STR_EXPORT_BLUE", 2003, 9999),
    ("df4bex", "", "STR_BUILD_YEAR", 0, 9999),
    ("df4bex", "dprk", "STR_DPRK_LIVERY", 0, 9999),
    ("df4bex", "ukraine", "STR_UKRAINE_LIVERY", 0, 9999),
    ("yz25tex", "", "STR_BUILD_YEAR", 0, 2014),
    ("yz25tex", "green", "STR_EXPORT_GREEN", 2015, 9999),
    ("yw25tex", "", "STR_BUILD_YEAR", 0, 2014),
    ("yw25tex", "green", "STR_EXPORT_GREEN", 2015, 9999),
    ("rw25tex", "", "STR_BUILD_YEAR", 0, 2014),
    ("rw25tex", "green", "STR_EXPORT_GREEN", 2015, 9999),
    ("c70ex", "", "STR_BUILD_YEAR", 0, 9999),
    ("c70ex", "gray", "STR_EXPORT_GRAY", 0, 9999),
]

# --------------------------------------------------------------------------
# freight appearance table
# --------------------------------------------------------------------------
# id, variant, sprite suffix, cargo class selector, cargo type list,
# first cargo_count of the partial load, last cargo_count of the partial load
VARIANTS = [
    ("c70ex", "coal", "c70ex-coal", "bitmask(CC_BULK)", "", 6, 45),
    ("c70ex", "cont", "c70ex-container", "bitmask(CC_MAIL)", "", 6, 40),
    ("c70ex", "cont", "c70ex-container", "bitmask(CC_EXPRESS)", "", 6, 40),
    ("c70ex", "cover", "c70ex-cover", "bitmask(CC_COVERED)", "", 0, 0),
    ("c70ex", "cover", "c70ex-cover", "bitmask(CC_PIECE_GOODS)", "", 0, 0),
    ("c70ex", "cover", "c70ex-cover", "bitmask(CC_OVERSIZED)", "", 0, 0),
    ("c64ex", "coal", "c64ex-coal", "bitmask(CC_BULK)", "", 6, 40),
    ("c64ex", "cover", "c64ex-cover", "bitmask(CC_COVERED)", "", 0, 0),
    ("c64ex", "cover", "c64ex-cover", "bitmask(CC_PIECE_GOODS)", "", 0, 0),
    ("p70ex", "metal", "p70ex-metal", "",
     "ALUM|COPR|CSTI|IRON|METL|PIPE|STEL|STAL|STST|STCB|STSE|STSH|STWR|ZINC", 6, 40),
    ("p70ex", "bucket", "p70ex-bucket", "",
     "EOIL|FZDR|WATR|OIL_|PETR|RFPR|BUBL|COAT|DYES|PLAS|PLST|RUBR|SOAP|ACID|CTAR|LYE_|FUEL|NH3_", 6, 30),
    ("p70ex", "goods", "p70ex-goods", "",
     "GOOD|GRAI|WOOD|WHEA|FOOD|FRUT|MAIZ|SAND|CMNT|FERT|CLAY|KAOL|SALT|SUGR", 6, 38),
    ("n60ex", "metal", "n60ex-metal", "",
     "ALUM|COPR|CSTI|IRON|METL|PIPE|STEL|STAL|STST|STCB|STSE|STSH|STWR|ZINC", 6, 30),
    ("n60ex", "bucket", "n60ex-bucket", "",
     "EOIL|FZDR|WATR|OIL_|PETR|RFPR|BUBL|COAT|DYES|PLAS|PLST|RUBR|SOAP|ACID|CTAR|LYE_|FUEL|NH3_", 6, 30),
    ("n60ex", "goods", "n60ex-goods", "",
     "GOOD|GRAI|WOOD|WHEA|FOOD|FRUT|MAIZ|SAND|CMNT|FERT|CLAY|KAOL|SALT|SUGR", 6, 38),
    ("n60ex", "vehi", "n60ex-vehi", "", "VEHI|FMSP|ENSP", 0, 0),
    ("g70ex", "oil", "g70ex-oil", "bitmask(CC_LIQUID)", "", 6, 40),
    ("g70ex", "haz", "g70ex-haz", "bitmask(CC_HAZARDOUS)", "", 6, 40),
    ("gn70ex", "oil", "gn70ex-oil", "bitmask(CC_LIQUID)", "", 6, 45),
    ("gn70ex", "haz", "gn70ex-haz", "bitmask(CC_HAZARDOUS)", "", 6, 45),
    ("jsq5ex", "vehi", "jsq5ex-vehi", "", "VEHI", 3, 10),
    ("jsq5ex", "ensp", "jsq5ex-ensp", "", "ENSP|FMSP", 3, 10),
    ("l70ex", "goods", "l70ex-goods", "bitmask(CC_COVERED)", "", 6, 40),
    ("l70ex", "goods", "l70ex-goods", "bitmask(CC_PIECE_GOODS)", "", 6, 40),
    ("b22ex", "goods", "b22ex-goods", "bitmask(CC_PIECE_GOODS)", "", 6, 45),
    ("b22ex", "goods", "b22ex-goods", "bitmask(CC_COVERED)", "", 6, 45),
    ("b22ex", "mail", "b22ex-mail", "bitmask(CC_MAIL)", "", 6, 45),
    ("b22ex", "mail", "b22ex-mail", "bitmask(CC_EXPRESS)", "", 6, 45),
    ("sq8ex", "coal", "sq8ex-coal", "bitmask(CC_BULK)", "", 6, 50),
    ("x2kex", "cont", "x2kex-cont", "bitmask(CC_PIECE_GOODS)", "", 6, 45),
    ("x2kex", "cont", "x2kex-cont", "bitmask(CC_COVERED)", "", 6, 45),
    ("x2kex", "cont", "x2kex-cont", "bitmask(CC_OVERSIZED)", "", 6, 45),
    ("dq35ex", "goods", "dq35ex-goods", "bitmask(CC_PIECE_GOODS)", "", 3, 30),
    ("dq35ex", "goods", "dq35ex-goods", "bitmask(CC_OVERSIZED)", "", 3, 30),
]

LIVERY_COLUMNS = ("id", "sprite_suffix", "string", "from_year", "to_year",
                  "purchase_suffix", "templates")
VARIANT_COLUMNS = ("id", "variant", "sprite_suffix", "cargo_classes", "cargo_types",
                   "from_index", "to_index", "template")


def main() -> None:
    for name, records in TABLES.items():
        path = os.path.join(ROOT, "data", name)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("# China Set: Export Rail Vehicles Add-on -- %s\n" % HEADER_NOTE[name])
            handle.write("#\n")
            handle.write("# Generated by tools/build_data_tables.py; hand editing is fine\n")
            handle.write("# afterwards.  List cells use \"|\" as the separator so that the\n")
            handle.write("# CSV stays readable, e.g. bitmask(CC_BULK|CC_COVERED), [PASS|TOUR].\n")
            handle.write("# See data/README.md for the column reference.\n#\n")
            writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
            writer.writeheader()
            for record in records:
                writer.writerow(record)
        print("%-20s %3d rows" % (name, len(records)))

    # livery table
    path = os.path.join(ROOT, "data", "liveries.csv")
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
        rows = 0
        previous = None
        for cid, suffix, label, from_year, to_year in LIVERIES:
            if previous is not None and cid != previous:
                writer.writerow([])
            previous = cid
            writer.writerow([cid, suffix, label, from_year if suffix else 0,
                             to_year if suffix else 9999, "", ""])
            rows += 1
    print("%-20s %3d rows" % ("liveries.csv", rows))

    # freight appearance table
    path = os.path.join(ROOT, "data", "cargo_variants.csv")
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
        rows = 0
        previous = None
        for cid, variant, suffix, classes, types, from_index, to_index in VARIANTS:
            if previous is not None and cid != previous:
                writer.writerow([])
            previous = cid
            writer.writerow([cid, variant, suffix, classes, types,
                             from_index, to_index, ""])
            rows += 1
    print("%-20s %3d rows" % ("cargo_variants.csv", rows))


if __name__ == "__main__":
    main()
