#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
genpnml.py -- China Set: Export Rail Vehicles Add-on, PNML generator
====================================================================

Reads the declarative tables in ``data/`` and writes

  * ``src/<folder>/<id>.pnml`` one file per vehicle, exactly like China Set:
                               Trains keeps one file per vehicle
  * ``src/vehiclefiles.pnml``  the include list of those files
  * ``src/vehicleid.pnml``     the ``item (FEAT_TRAINS, name, id) {}`` table
  * ``src/vehiclesort.pnml``   the ``sort (FEAT_TRAINS, [...])`` block

and prepares each ``gfx/<folder>/`` by writing the ``manifest.json`` and
``ttd_palette.json`` that gorender/renderobject reads next to the models.  It
does **not** write ``.vox`` models: those are the author's artwork, so a missing
one is reported instead of filled in with a placeholder.

for every locomotive, coach and wagon described in the tables.

The output is plain NML/PNML following exactly the layout used by
China Set: Trains and China Set: Narrow Gauge Add-on, so the generated files
can be compiled side by side with hand written ones.

Usage
-----
    python3 genpnml.py --data data --out src
    python3 genpnml.py --clean

Tables (all CSV, UTF-8, ``#`` starts a comment line)
----------------------------------------------------
``data/locomotives.csv``  one row per locomotive / multiple unit head
``data/coaches.csv``      one row per passenger coach
``data/wagons.csv``       one row per freight wagon
``data/liveries.csv``     livery / paint scheme per vehicle   (optional)
``data/cargo_variants.csv``  freight appearance per cargo class (optional)

See ``data/README.md`` for the full column reference.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import struct
import sys
import zlib
from dataclasses import dataclass, field
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# constants
# --------------------------------------------------------------------------

GENERATED_HEADER = (
    "/* ==========================================================================\n"
    " *  China Set: Export Rail Vehicles Add-on\n"
    " *  {title}\n"
    " *\n"
    " *  *** GENERATED FILE -- DO NOT EDIT BY HAND ***\n"
    " *  Produced by genpnml.py from the tables in data/.\n"
    " *  Edit data/*.csv and run `make gen` (or `python3 genpnml.py`) instead.\n"
    " * ========================================================================== */\n"
)

# NML identifier of the category the vehicle belongs to, and the ID band it
# uses.  A band is a CSV "start:end" string, exactly as used by vehicleid.pnml.
BANDS: Dict[str, str] = {
    "unit_wagon": "1024:2047",
    "coach": "2048:3071",
    "wagon": "3072:4095",
    "steam": "4096:5119",
    "diesel": "5120:6143",
    "electric": "6144:7167",
    "multipower": "7168:7679",
    "1500v_dc": "7680:8191",
    "dmu": "8192:9215",
    "emu": "9216:10239",
    "1500_emu": "10240:11263",
    "750_emu": "11264:12287",
    "third_emu": "12288:13311",
    "multi_mu": "13312:14335",
    "mono_mu": "14336:14847",
    "mglv_mu": "14848:15359",
    "cargo_dmu": "15360:15615",
    "cargo_emu": "15616:16127",
    "multi_cargo_mu": "16128:16383",
}

BAND_COMMENT: Dict[str, Tuple[str, str]] = {
    "unit_wagon": ("Unit Wagons", "0x0400..0x07FF"),
    "coach": ("Coaches", "0x0800..0x0BFF"),
    "wagon": ("Wagons", "0x0C00..0x0FFF"),
    "steam": ("Steam", "0x1000..0x13FF"),
    "diesel": ("Diesel", "0x1400..0x17FF"),
    "electric": ("25kV AC Electric", "0x1800..0x1BFF"),
    "multipower": ("Multi Power Locomotive", "0x1C00..0x1DFF"),
    "1500v_dc": ("1500V DC Power Locomotive", "0x1E00..0x1FFF"),
    "dmu": ("DMU", "0x2000..0x23FF"),
    "emu": ("25kV AC EMU", "0x2400..0x27FF"),
    "1500_emu": ("1.5kV DC EMU", "0x2800..0x2BFF"),
    "750_emu": ("750V DC EMU", "0x2C00..0x2FFF"),
    "third_emu": ("Third Rail EMU", "0x3000..0x33FF"),
    "multi_mu": ("Multi Power MU", "0x3400..0x37FF"),
    "mono_mu": ("Monorail MU", "0x3800..0x39FF"),
    "mglv_mu": ("Maglev MU", "0x3A00..0x3BFF"),
    "cargo_dmu": ("Cargo DMU", "0x3C00..0x3CFF"),
    "cargo_emu": ("25kV AC Cargo EMU", "0x3D00..0x3EFF"),
    "multi_cargo_mu": ("Multi Power Cargo MU", "0x3F00..0x3FFF"),
}

# order in which the bands are emitted into vehicleid.pnml
BAND_ORDER: List[str] = list(BANDS.keys())

ENGINE_CLASS = {
    "steam": "ENGINE_CLASS_STEAM",
    "diesel": "ENGINE_CLASS_DIESEL",
    "electric": "ENGINE_CLASS_ELECTRIC",
    "multipower": "ENGINE_CLASS_ELECTRIC",
    "1500v_dc": "ENGINE_CLASS_ELECTRIC",
    "dmu": "ENGINE_CLASS_DIESEL",
    "cargo_dmu": "ENGINE_CLASS_DIESEL",
    "emu": "ENGINE_CLASS_ELECTRIC",
    "1500_emu": "ENGINE_CLASS_ELECTRIC",
    "750_emu": "ENGINE_CLASS_ELECTRIC",
    "third_emu": "ENGINE_CLASS_ELECTRIC",
    "multi_mu": "ENGINE_CLASS_ELECTRIC",
    "mono_mu": "ENGINE_CLASS_ELECTRIC",
    "mglv_mu": "ENGINE_CLASS_ELECTRIC",
    "cargo_emu": "ENGINE_CLASS_ELECTRIC",
    "multi_cargo_mu": "ENGINE_CLASS_ELECTRIC",
}

# categories whose vehicles are multiple units: their head cars and trailers
# may only be coupled to other multiple unit stock
MU_CATEGORIES = {
    "dmu", "emu", "1500_emu", "750_emu", "third_emu", "multi_mu",
    "mono_mu", "mglv_mu", "cargo_dmu", "cargo_emu", "multi_cargo_mu",
    "unit_wagon",
}

# category -> directory under src/, used for the "section" bookkeeping only;
# the real gfx folder comes from the folder column.
CATEGORY_LABEL = {    "steam": "Locomotives/Steam",
    "diesel": "Locomotives/Diesel",
    "electric": "Locomotives/Electric",
    "multipower": "Locomotives/Multi Power",
    "1500v_dc": "Locomotives/1500V DC",
    "dmu": "DMU",
    "emu": "EMU",
    "1500_emu": "EMU/1500V DC",
    "750_emu": "EMU/750V DC",
    "third_emu": "EMU/Third Rail",
    "multi_mu": "MU/Multi Power",
    "mono_mu": "MU/Monorail",
    "mglv_mu": "MU/Maglev",
    "cargo_dmu": "MU/Cargo DMU",
    "cargo_emu": "MU/Cargo EMU",
    "multi_cargo_mu": "MU/Multi Power Cargo",
    "coach": "Coaches",
    "wagon": "Wagons",
    "unit_wagon": "Unit Wagons",
}

# carriage return / comment handling -------------------------------------------------

TRUE = {"1", "y", "yes", "true", "t", "on"}


def _bool(value: str, default: bool = False) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in TRUE


def _int(value: str, default: int = 0) -> int:
    value = (value or "").strip()
    if value == "":
        return default
    return int(float(value))


def _float(value: str, default: float = 0.0) -> float:
    value = (value or "").strip()
    if value == "":
        return default
    return float(value)


def _split_list(value: str) -> List[str]:
    """Split a CSV cell such as ``a|b|c`` or ``a,b,c`` into a list."""
    if not value:
        return []
    raw = value.replace(",", "|").replace(";", "|")
    return [part.strip() for part in raw.split("|") if part.strip()]


def _read_csv(path: str) -> List[Dict[str, str]]:
    """Read a CSV table.

    '#' marks a comment, and comments are allowed between data rows because
    they group the tables visually.  Only a *comment-only* line is dropped:
    a header line that merely begins with '#', such as
    ``# id,variant,sprite_suffix`` in the documentation header of a table
    without its own header row, would otherwise hide the real header from
    csv.DictReader and shift every column.
    """
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        text = handle.read()

    cleaned: List[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#") and "," not in stripped:
            continue  # a pure comment line
        cleaned.append(line)
    if not cleaned:
        return []

    # The real header is the first row starting with the "id" column; the
    # documentation headers above it are commented out and must not win.
    start = next((i for i, line in enumerate(cleaned)
                  if line.lstrip().startswith("id,")), None)
    if start is None:
        return []
    cleaned = cleaned[start:]

    rows: List[Dict[str, str]] = []
    reader = csv.DictReader(cleaned)
    fields = [(name or "").strip() for name in (reader.fieldnames or [])]
    for raw in reader:
        values = list(raw.values())
        record: Dict[str, str] = {}
        for index, name in enumerate(fields):
            if not name or name.startswith("#"):
                continue
            value = values[index] if index < len(values) else ""
            record[name] = (value or "").strip()
        if not record.get("id"):
            continue
        rows.append(record)
    return rows


# --------------------------------------------------------------------------
# data model
# --------------------------------------------------------------------------


@dataclass
class Livery:
    """One paint scheme / livery of a vehicle."""

    index: int
    suffix: str
    string: str
    from_year: int = 0
    to_year: int = 9999
    purchase_suffix: str = ""
    templates: List[str] = field(default_factory=list)
    # Per section graphics of *this* scheme: which sprite each section shows,
    # decided by the section's place in the whole train.  It belongs to the
    # paint scheme rather than to the vehicle, because the artwork that depends
    # on the train's shape is exactly the artwork that differs between schemes.
    graphics_parts: List[List[Tuple[str, str]]] = field(default_factory=list)

    @property
    def is_automatic(self) -> bool:
        return self.index == 0

    def template_for(self, part_index: int, part_count: int) -> str:
        """Return the template name used by ``part_index`` of ``part_count``."""
        if not self.templates:
            return "template_standard"
        if len(self.templates) == 1:
            return self.templates[0]
        if len(self.templates) >= part_count:
            return self.templates[part_index]
        return self.templates[-1]


@dataclass
class CargoVariant:
    """How a freight wagon looks when carrying a given class of cargo."""

    name: str          # short selector used in the cargo_type table (may be "")
    suffix: str        # sprite basename suffix
    classes: str       # e.g. "CC_BULK", or "" when only cargo types apply
    from_index: int = 0
    to_index: int = 0
    types: List[str] = field(default_factory=list)
    template: str = "template_standard"


@dataclass
class Vehicle:
    """A single vehicle described by one CSV row."""

    id: str
    name_string: str
    category: str
    folder: str
    intro_year: int
    intro_month: int = 1
    intro_day: int = 1
    model_life: str = "VEHICLE_NEVER_EXPIRES"
    retire_early: int = 0
    vehicle_life: int = 30
    track_type: str = "SACN"
    climates: str = "ALL_CLIMATES"
    # performance
    speed: int = 120
    power: float = 0.0
    power_unit: str = "kW"
    weight: float = 40.0
    te_coeff: float = 0.0
    cost_factor: int = 10
    running_cost_factor: int = 10
    purchase_running_cost_factor: int = 0
    purchase_cost_display: int = 0
    reliability_decay: int = 10
    purchase_speed: int = 0
    purchase_power: float = 0.0
    # cargo
    refit_classes: str = "bitmask(CC_PASSENGERS)"
    non_refit_classes: str = "0"
    cargo_allow: str = "[]"
    cargo_disallow: str = "[]"
    default_cargo: str = "PASS"
    ai_flag: str = "AI_FLAG_PASSENGER"
    capacity: int = 0
    capacity_by_cargo: str = ""
    loading_speed: int = 8
    cargo_age_period: int = 185
    wagon_decay: bool = False
    # mechanical / graphical
    parts: List[int] = field(default_factory=lambda: [2, 4, 2])
    power_section: int = 0
    # one rule list per section; see parse_graphics_parts()
    # shortest train an MU may be started as, in three car units; 0 disables
    min_cars: int = 0
    ac_supply: bool = False
    airconditioned: bool = False
    restaurant: bool = False
    mu: bool = False
    visual_effect: str = ""
    train_flags: str = ""
    name_callback: bool = False
    additional_text: str = ""
    liveries: List[Livery] = field(default_factory=list)
    cargo_variants: List[CargoVariant] = field(default_factory=list)
    source: str = ""

    # -- helpers -----------------------------------------------------------

    @property
    def is_locomotive(self) -> bool:
        return self.category not in ("coach", "wagon", "unit_wagon")

    @property
    def name_constant(self) -> str:
        """The STR_ constant used for ``name:``.

        A table cell that is empty or holds a plain name such as
        "SS8 (Export)" is mapped onto STR_NAME_<ID>, which is the convention
        used by docs/str.csv.  A cell that already looks like an NML string
        (``STR_...`` or a quoted literal) is passed through unchanged.
        """
        text = (self.name_string or "").strip()
        if text.startswith("STR_") or text.startswith('"'):
            return text
        return "STR_NAME_" + self.id.upper()

    @property
    def display_name(self) -> str:
        """Human readable name, for the language table."""
        text = (self.name_string or "").strip()
        if not text or text.startswith("STR_") or text.startswith('"'):
            return self.id.upper()
        return text

    @property
    def full_name_constant(self) -> str:
        return "STR_FULL_NAME_" + self.id.upper()

    @property
    def can_supply_head_end_power(self) -> bool:
        """True only for vehicles that feed the train (locomotives, gen cars).

        A passenger coach is *air conditioned*, it does not supply power, so
        only these vehicles get a visual_effect_and_powered callback.
        """
        return self.ac_supply and (self.is_locomotive or self.category == "coach")

    @property
    def default_livery(self) -> Livery:
        return self.liveries[0]

    @property
    def year_dependent(self) -> bool:
        """True when livery 0 means "pick by build year"."""
        return len(self.liveries) > 1

    @property
    def running_cost_base(self) -> str:
        return "RUNNING_COST_DIESEL" if self.category == "diesel" else "RUNNING_COST_ELECTRIC"

    @property
    def known_length_switch(self) -> str:
        """A ``switch_length_*`` name that ``src/functions.pnml`` declares.

        The parent set only predefines ``switch_length_2_<body>_2`` for body
        lengths 1..8 and a few asymmetric shapes; those are the cases that can
        name a shared block.  Anything else needs a switch of its own, because
        a property cannot hold an inline ``switch`` -- NML answers
        ``Syntax error, unexpected token "switch"``.
        """
        parts = self.parts
        if len(parts) != 3:
            return ""
        if parts[0] == parts[2] and 1 <= parts[1] <= 8:
            return "switch_length_2_%d_2" % parts[1]
        if (parts[0], parts[1], parts[2]) in ((2, 1, 1), (2, 6, 4), (2, 8, 6)):
            return "switch_length_2_%d_%d" % (parts[1], parts[2])
        return ""

    @property
    def length_switch(self) -> str:
        """The value of the ``length`` property.

        A name when ``functions.pnml`` has one, otherwise the name of the block
        ``emit_length_switch()`` writes for this vehicle.
        """
        if len(self.parts) == 1:
            return str(self.parts[0])
        return self.known_length_switch or "switch_%s_length" % self.id

    @property
    def part_count(self) -> int:
        return len(self.parts)


# --------------------------------------------------------------------------
# CSV loading
# --------------------------------------------------------------------------


# A livery label is written ``LV_<NAME>`` and becomes ``STR_LV_<NAME>``.  The
# six labels the generator ships used to be plain ``STR_`` constants, so a table
# written before the convention existed still names them that way; they are
# mapped across rather than reported as missing, because the text they refer to
# is the same and only the constant moved.
LEGACY_LIVERY_LABELS = {
    "STR_BUILD_YEAR": "STR_LV_BUILD_YEAR",
    "STR_ORIGINAL": "STR_LV_ORIGINAL",
    "STR_EXPORT_BLUE": "STR_LV_EXPORT_BLUE",
    "STR_EXPORT_GREEN": "STR_LV_EXPORT_GREEN",
    "STR_EXPORT_GRAY": "STR_LV_EXPORT_GRAY",
    "STR_DPRK_LIVERY": "STR_LV_DPRK",
}


def _livery_label(cell: str) -> str:
    """The NML string constant a livery's ``string`` cell refers to.

    A livery label is written as ``LV_<NAME>`` in the table and becomes
    ``STR_LV_<NAME>`` in the code, so the labels of one kind are grouped in
    ``docs/str.csv`` instead of being buried among the interface strings.  A
    label that is still one of the six old constants is mapped across, and any
    other ``STR_`` constant is passed through unchanged, which keeps a project
    that deliberately points two schemes at one shared label working.
    """
    text = (cell or "").strip()
    if not text:
        return ""
    if text.startswith("LV_"):
        return "STR_" + text
    return LEGACY_LIVERY_LABELS.get(text, text)


def _load_liveries(rows: List[Dict[str, str]], sections: Dict[str, int]) -> Dict[str, List[Livery]]:
    table: Dict[str, List[Livery]] = {}
    counters: Dict[str, int] = {}
    for row in rows:
        vehicle = row["id"]
        index = counters.get(vehicle, 0)
        counters[vehicle] = index + 1
        cell = (row.get("graphics_parts", "") or "").strip()
        # the section count is the vehicle's, so parsing has to wait until the
        # vehicle tables are known; a scheme for a vehicle that does not exist
        # is left empty and reported by validate_vehicles()
        graphics_parts = parse_graphics_parts(cell, sections[vehicle]) \
            if cell and vehicle in sections else []
        livery = Livery(
            index=index,
            suffix=row.get("sprite_suffix", ""),
            string=_livery_label(row.get("string", "")),
            from_year=_int(row.get("from_year", ""), 0),
            to_year=_int(row.get("to_year", ""), 9999),
            purchase_suffix=row.get("purchase_suffix", ""),
            templates=_split_list(row.get("templates", "")),
            graphics_parts=graphics_parts,
        )
        table.setdefault(vehicle, []).append(livery)
    return table


def _load_cargo_variants(rows: List[Dict[str, str]]) -> Dict[str, List[CargoVariant]]:
    table: Dict[str, List[CargoVariant]] = {}
    for row in rows:
        vehicle = row["id"]
        variant = CargoVariant(
            name=row.get("variant", ""),
            suffix=row.get("sprite_suffix", ""),
            classes=row.get("cargo_classes", ""),
            from_index=_int(row.get("from_index", ""), 0),
            to_index=_int(row.get("to_index", ""), 0),
            types=_split_list(row.get("cargo_types", "")),
            template=row.get("template", "") or "template_standard",
        )
        table.setdefault(vehicle, []).append(variant)
    return table


def _build_vehicle(
    row: Dict[str, str],
    category: str,
    source: str,
    liveries: Dict[str, List[Livery]],
    cargo_variants: Dict[str, List[CargoVariant]],
) -> Vehicle:
    vehicle_id = row["id"]

    parts = [_int(part) for part in _split_list(row.get("parts", "")) if part.strip()]
    if not parts:
        parts = [2, 4, 2] if category not in ("coach", "wagon", "unit_wagon") else [2, 8, 2]

    power_section = _int(row.get("power_section", ""), 1 if len(parts) == 3 else 0)
    if power_section >= len(parts):
        power_section = len(parts) - 1

    min_cars = _int(row.get("min_cars", ""), 0)
    if min_cars < 0:
        raise ValueError("%s: min_cars 不能为负" % vehicle_id)

    vehicle = Vehicle(
        id=vehicle_id,
        name_string=row.get("name_string", "") or ("STR_NAME_" + vehicle_id.upper()),
        category=category,
        folder=row.get("folder", "") or category,
        intro_year=_int(row.get("intro_year", ""), 1980),
        intro_month=_int(row.get("intro_month", ""), 1),
        intro_day=_int(row.get("intro_day", ""), 1),
        model_life=(row.get("model_life", "") or "VEHICLE_NEVER_EXPIRES").strip(),
        retire_early=_int(row.get("retire_early", ""), 0),
        vehicle_life=_int(row.get("vehicle_life", ""), 30),
        track_type=(row.get("track_type", "") or "SACN").strip(),
        climates=(row.get("climates_available", "") or "ALL_CLIMATES").strip(),
        speed=_int(row.get("speed", ""), 120),
        power=_float(row.get("power", ""), 0.0),
        power_unit=(row.get("power_unit", "") or "kW").strip(),
        weight=_float(row.get("weight", ""), 40.0),
        te_coeff=_float(row.get("tractive_effort_coefficient", ""), 0.0),
        cost_factor=_int(row.get("cost_factor", ""), 10),
        running_cost_factor=_int(row.get("running_cost_factor", ""), 10),
        purchase_running_cost_factor=_int(row.get("purchase_running_cost_factor", ""), 0),
        purchase_cost_display=_int(row.get("purchase_cost_display", ""), 0),
        reliability_decay=_int(row.get("reliability_decay", ""), 10),
        purchase_speed=_int(row.get("purchase_speed", ""), 0),
        purchase_power=_float(row.get("purchase_power", ""), 0.0),
        refit_classes=(row.get("refittable_cargo_classes", "") or "bitmask(CC_PASSENGERS)").strip(),
        non_refit_classes=(row.get("non_refittable_cargo_classes", "") or "0").strip(),
        cargo_allow=(row.get("cargo_allow_refit", "") or "[]").strip(),
        cargo_disallow=(row.get("cargo_disallow_refit", "") or "[]").strip(),
        default_cargo=(row.get("default_cargo_type", "") or "PASS").strip(),
        ai_flag=(row.get("ai_special_flag", "") or "AI_FLAG_PASSENGER").strip(),
        capacity=_int(row.get("capacity", ""), 0),
        capacity_by_cargo=(row.get("capacity_by_cargo", "") or "").strip(),
        loading_speed=_int(row.get("loading_speed", ""), 8),
        cargo_age_period=_int(row.get("cargo_age_period", ""), 185),
        wagon_decay=_bool(row.get("wagon_decay", ""), category in ("wagon",)),
        parts=parts,
        power_section=power_section,
        min_cars=min_cars,
        ac_supply=_bool(row.get("ac_supply", ""), False),
        airconditioned=_bool(row.get("airconditioned", ""), False),
        restaurant=_bool(row.get("restaurant", ""), False),
        mu=_bool(row.get("mu", ""), False),
        visual_effect=(row.get("visual_effect", "") or "").strip(),
        train_flags=(row.get("train_flags", "") or "").strip(),
        name_callback=_bool(row.get("name_callback", ""), category not in ("coach", "wagon", "unit_wagon")),
        additional_text=(row.get("additional_text", "") or "").strip(),
        source=source,
    )

    # The purchase window text is assembled from the data: the cell in the
    # table, when present, is used as-is (minus the outer string() wrapper,
    # which render_item adds); otherwise the standard export description is
    # built from the vehicle's own figures.
    vehicle.liveries = liveries.get(vehicle_id) or [Livery(0, "", "")]
    vehicle.cargo_variants = cargo_variants.get(vehicle_id, [])

    text = (vehicle.additional_text or "").replace("\\n", " ").strip()
    if text:
        if text.startswith("string(") and text.endswith(")"):
            text = text[len("string("):-1]
        vehicle.additional_text = text.replace(
            "{FULL_NAME}", "STR_FULL_NAME_" + vehicle_id.upper())
    else:
        vehicle.additional_text = build_additional_text(vehicle)

    # list cells are normalised to the "|" separator so that both
    # "bitmask(CC_BULK|CC_COVERED)" and "bitmask(CC_BULK, CC_COVERED)" work
    vehicle.refit_classes = _join_list_cell(vehicle.refit_classes)
    vehicle.non_refit_classes = _join_list_cell(vehicle.non_refit_classes)
    vehicle.cargo_allow = _join_list_cell(vehicle.cargo_allow)
    vehicle.cargo_disallow = _join_list_cell(vehicle.cargo_disallow)
    return vehicle


def _join_list_cell(value: str) -> str:
    """Rewrite a bitmask(...) or [...] cell so its items are "|" separated."""
    text = (value or "").strip()
    if not text:
        return text
    for opener, closer in (("bitmask(", ")"), ("[", "]")):
        if text.startswith(opener) and text.endswith(closer):
            inner = text[len(opener):-len(closer)]
            items = [item.strip() for item in inner.replace("|", ",").split(",")
                     if item.strip()]
            return opener + "|".join(items) + closer
    return text


def load_vehicles(data_dir: str) -> List[Vehicle]:
    """Load every vehicle table and return the vehicles in menu order."""
    livery_rows = _read_csv(os.path.join(data_dir, "liveries.csv"))
    cargo_variants = _load_cargo_variants(_read_csv(os.path.join(data_dir, "cargo_variants.csv")))

    tables = [
        ("locomotives.csv", None),
        ("coaches.csv", "coach"),
        ("wagons.csv", "wagon"),
        ("unit_wagons.csv", "unit_wagon"),
    ]
    # read every vehicle table once: the livery table needs each vehicle's
    # section count, which only the vehicle rows carry
    loaded = [(filename, forced, _read_csv(os.path.join(data_dir, filename)))
              for filename, forced in tables]
    rows_by_id = {row["id"]: row for _f, _c, rows in loaded for row in rows}

    liveries = _load_liveries(livery_rows,
                              {vehicle: _section_count(row)
                               for vehicle, row in rows_by_id.items()})

    vehicles: List[Vehicle] = []
    seen: Dict[str, str] = {}
    for filename, forced_category, rows in loaded:
        for row in rows:
            category = forced_category or (row.get("category", "") or "diesel").strip().lower()
            if category not in BANDS:
                raise SystemExit(
                    "ERROR: %s: vehicle '%s' has unknown category '%s'"
                    % (filename, row["id"], category)
                )
            vehicle = _build_vehicle(row, category, filename, liveries, cargo_variants)
            if vehicle.id in seen:
                raise SystemExit(
                    "ERROR: vehicle id '%s' is declared twice (%s and %s)"
                    % (vehicle.id, seen[vehicle.id], filename)
                )
            seen[vehicle.id] = filename
            vehicles.append(vehicle)

    problems, warnings = validate_vehicles(vehicles)
    for warning in warnings:
        print("WARNING: %s" % warning, file=sys.stderr)
    if problems:
        for problem in problems:
            print("ERROR: %s" % problem, file=sys.stderr)
        raise SystemExit(1)
    return vehicles


def _section_count(row: Dict[str, str]) -> int:
    """How many sections a vehicle row declares, for the livery table."""
    parts = [_int(part) for part in _split_list(row.get("parts", "")) if part.strip()]
    return len(parts) if parts else 3


def assign_ids(vehicles: Sequence[Vehicle]) -> Dict[str, int]:
    """Assign a free ID inside the band of each category."""
    used: Dict[str, int] = {}
    result: Dict[str, int] = {}
    for vehicle in vehicles:
        band = BANDS[vehicle.category]
        start, end = (int(part) for part in band.split(":"))
        candidate = used.get(vehicle.category, start)
        while candidate in result.values() and candidate <= end:
            candidate += 1
        if candidate > end:
            raise SystemExit(
                "ERROR: ID band for category '%s' (%s) is exhausted" % (vehicle.category, band)
            )
        result[vehicle.id] = candidate
        used[vehicle.category] = candidate + 1
    return result


# --------------------------------------------------------------------------
# PNML emitter
# --------------------------------------------------------------------------


class Emitter:
    """Collects generated PNML blocks."""

    def __init__(self) -> None:
        self.blocks: List[str] = []

    def add(self, text: str) -> None:
        self.blocks.append(text.rstrip("\n"))

    # -- spritesets --------------------------------------------------------

    def spriteset(self, name: str, folder: str, basename: str, template: str) -> None:
        # The template's first parameter is the folder *path* as a quoted string,
        # not an identifier, which is what lets the folder column name a nested
        # directory such as "diesel/df4c".  nmlc 0.9.0 has no string rewriting
        # (subst() is undefined), so the path has to be passed through whole.
        self.add(
            "spriteset (%s, ZOOM_LEVEL_IN_4X, BIT_DEPTH_32BPP) {\n"
            '    %s ("%s", "%s")\n'
            "}" % (name, template, folder, basename)
        )

    # -- switches ----------------------------------------------------------

    def switch(self, name: str, expression: str, cases: Sequence[Tuple[str, str]],
               fallback: Optional[str] = None) -> None:
        lines = ["switch (FEAT_TRAINS, SELF, %s, %s) {" % (name, expression)]
        for selector, target in cases:
            lines.append("    %s: %s;" % (selector, target))
        if fallback is not None:
            text = fallback.rstrip()
            # a switch body is a list of statements, so the fallback needs its
            # terminating semicolon just like the cases
            if not text.endswith(";"):
                text += ";"
            lines.append("    %s" % text)
        lines.append("}")
        self.add("\n".join(lines))


def _identifier_part(text: str) -> str:
    """Make one piece of an NML identifier out of a sprite suffix.

    A suffix is a *file name* fragment, so it legitimately contains dashes
    (``korea-1`` makes the sheet ``df4c-korea-1``), but NML identifiers may not.
    Such a suffix may also start with a dash, which the livery table uses to mean
    "the whole basename is a suffix" (``df4c,-korean-1`` gives
    ``df4c--korean-1``); those runs of dashes are folded so the identifier stays
    readable.
    """
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", text or "").strip("_")
    return cleaned


def _livery_basename(vehicle: Vehicle, livery: Livery) -> str:
    """Sprite sheet basename of a livery: <id> or <id>-<livery suffix>."""
    if livery.suffix:
        return "%s-%s" % (vehicle.id, livery.suffix)
    return vehicle.id


def _livery_spriteset_name(vehicle: Vehicle, livery: Livery) -> str:
    if livery.suffix:
        return "spriteset_%s_%s" % (vehicle.id, _identifier_part(livery.suffix))
    return "spriteset_%s" % vehicle.id


def _livery_purchase_name(vehicle: Vehicle, livery: Livery) -> str:
    suffix = livery.purchase_suffix or livery.suffix
    if suffix:
        return "spriteset_%s_purchase_%s" % (vehicle.id, _identifier_part(suffix))
    return "spriteset_%s_purchase" % vehicle.id


def _cargo_spriteset_name(vehicle: Vehicle, variant: CargoVariant, livery: Livery) -> str:
    """Unique NML identifier for one cargo appearance of one livery.

    The livery suffix is included so that e.g. c70ex in black and c70ex in grey
    can both carry coal without the names colliding.  NML identifiers may not
    contain dashes, so the sprite basename (which legitimately has them) is
    turned into an underscore separated identifier.
    """
    parts = ["spriteset", vehicle.id]
    if variant.suffix:
        parts.append(_identifier_part(variant.suffix))
    if livery.suffix:
        parts.append(_identifier_part(livery.suffix))
    return "_".join(parts)


def _cargo_switch_prefix(vehicle: Vehicle, livery: Livery) -> str:
    """Prefix for the cargo switches of one livery (unique per livery)."""
    if livery.suffix:
        return "switch_%s_%s" % (vehicle.id, _identifier_part(livery.suffix))
    return "switch_%s" % vehicle.id


def _cargo_basename(variant: CargoVariant, livery: Livery) -> str:
    name = variant.suffix
    if livery.suffix:
        name = "%s-%s" % (name, livery.suffix) if name else livery.suffix
    return name


def emit_vehicle(sprites: Emitter, switches: Emitter, items: Emitter,
                 vehicle: Vehicle) -> None:
    """Emit every spriteset, switch and item needed by one vehicle.

    The three kinds of block go into three different emitters so that the
    generated file keeps the layout the hand written sets use: all spritesets
    and switches first, then the item blocks.
    """
    vid = vehicle.id
    folder = vehicle.folder

    # ---- spritesets ---------------------------------------------------
    # Several cargo rows may share one appearance (e.g. mail and express both
    # ride in a container), and several schemes may share one section graphic,
    # so the same spriteset must only be defined once.  A basename is a file, so
    # a second definition with a different template would be a contradiction.
    seen_spritesets: set = set()
    seen_templates: Dict[str, str] = {}

    def define_spriteset(name: str, basename: str, template: str) -> None:
        if name in seen_spritesets:
            if seen_templates[name] != template:
                raise SystemExit(
                    "ERROR: %s: 贴图基名 %s 被两个涂装用不同的模板定义"
                    "（%s 与 %s）；同一个基名只能有一个模板"
                    % (vehicle.id, basename, seen_templates[name], template))
            return
        seen_spritesets.add(name)
        seen_templates[name] = template
        sprites.spriteset(name, folder, basename, template)

    for livery in vehicle.liveries:
        define_spriteset(
            _livery_spriteset_name(vehicle, livery),
            _livery_basename(vehicle, livery),
            livery.template_for(0, vehicle.part_count),
        )
        define_spriteset(
            _livery_purchase_name(vehicle, livery),
            _livery_basename(vehicle, livery),
            "template_purchase",
        )
        for variant in vehicle.cargo_variants:
            if not variant.suffix:
                continue
            define_spriteset(
                _cargo_spriteset_name(vehicle, variant, livery),
                _cargo_basename(variant, livery),
                variant.template,
            )

    # graphics_parts: one spriteset per basename the *schemes* name, so a
    # section can show artwork of its own.  Two schemes that share a basename
    # share the spriteset, which is why a differing template is an error.
    for livery in vehicle.liveries:
        for basename in graphics_rule_basenames(livery.graphics_parts):
            define_spriteset(_graphics_part_spriteset(vehicle, basename), basename,
                             _graphics_part_template(vehicle, livery, basename))

    # ---- cargo appearance chain (freight wagons) ----------------------
    cargo_root: Optional[str] = None
    if vehicle.cargo_variants:
        per_livery_roots: List[Tuple[str, str]] = []
        for livery in vehicle.liveries:
            root = _emit_cargo_chain(switches, vehicle, livery)
            per_livery_roots.append((str(livery.index), root))
        if len(per_livery_roots) == 1:
            cargo_root = per_livery_roots[0][1]
        else:
            cargo_root = "switch_%s_cargo_livery" % vid
            switches.switch(cargo_root, "cargo_subtype", per_livery_roots,
                            per_livery_roots[0][1])

    # ---- capacity per part --------------------------------------------
    # Capacity is the one value that must be distributed across the sections:
    # OpenTTD reads ``cargo_capacity`` per vehicle part.  Weight and power are
    # deliberately *not* distributed -- they are plain properties, see
    # render_item().
    capacity_switch = _emit_capacity_switch(switches, vehicle)
    start_stop_switch = _emit_start_stop(switches, vehicle)

    # ---- livery graphics chain ---------------------------------------
    if vehicle.cargo_variants and cargo_root:
        livery_cases = [(str(livery.index), cargo_root) for livery in vehicle.liveries]
    else:
        livery_cases = [(str(livery.index), _livery_spriteset_name(vehicle, livery))
                        for livery in vehicle.liveries]
    # The plain per-livery graphics, one entry per livery index.  These are what
    # a section falls back to when its scheme names no rule of its own.
    livery_roots: Dict[int, str] = {}
    for index, root in livery_cases:
        livery_roots[int(index)] = root

    # ---- graphics dispatch ---------------------------------------------
    # Every scheme owns its own graphics_parts, so the dispatch is built from
    # the livery table: each scheme gets a section switch, and the outer switch
    # selects it by cargo_subtype.  A scheme that names no rules keeps the plain
    # behaviour -- the body section draws, the invisible ends stay invisible.
    # That dispatch replaces the older livery switch entirely, so the switch is
    # only emitted for the one case that still needs it; emitting it anyway
    # would leave an orphan block and an nmlc "not referenced" warning.
    parts_root = _emit_graphics_parts(switches, vehicle, livery_roots)
    if parts_root:
        default_graphics = parts_root
    else:
        # no scheme of this vehicle has any section switch, so the plain livery
        # graphics are the default
        default_graphics = _emit_livery_switch(switches, vehicle, livery_cases, cargo_root)

    # ---- item ---------------------------------------------------------
    items.add(render_item(vehicle, default_graphics, capacity_switch, start_stop_switch))


def _emit_livery_switch(emitter: Emitter, vehicle: Vehicle,
                        cases: List[Tuple[str, str]],
                        cargo_root: Optional[str]) -> str:
    """Build switch_<id>_livery returning the graphics for the current livery.

    Index 0 is the automatic choice: if any livery carries a real date range
    the graphics are picked from build_year, and the livery that applied before
    the first change becomes the default.  A range of 0..9999 means "always
    valid", so such a livery never becomes a case of its own.
    """
    vid = vehicle.id
    if len(cases) == 1 and not vehicle.year_dependent:
        return cases[0][1]

    def sprite_for(livery: Livery) -> str:
        if vehicle.cargo_variants and cargo_root:
            return cargo_root
        return _livery_spriteset_name(vehicle, livery)

    if vehicle.year_dependent:
        others = vehicle.liveries[1:]
        # A date range of 0..9999 means "this scheme was always available", so
        # it never needs a case of its own: it is folded into the default.
        timed = [livery for livery in others
                 if not (livery.from_year <= 0 and livery.to_year >= 9999)]
        always = [livery for livery in others
                  if livery.from_year <= 0 and livery.to_year >= 9999]

        if timed:
            # the oldest dated scheme was the one in use before the first
            # change; NML rejects a default that duplicates a case, so the
            # default drops into the body and the other ranges become cases
            first = min(timed, key=lambda livery: livery.from_year)
            year_cases = [("%d..%d" % (livery.from_year, livery.to_year),
                           sprite_for(livery))
                          for livery in sorted(timed, key=lambda l: l.from_year)
                          if livery is not first]
            default = sprite_for(first)
            emitter.switch("switch_%s_livery_auto" % vid, "build_year",
                           year_cases, default)
            cases = [("0", "switch_%s_livery_auto" % vid)] + cases[1:]
        elif always:
            # every alternative applies throughout, so "automatic" is simply
            # the first of them and no switch on build_year is needed
            cases = [("0", sprite_for(always[0]))] + cases[1:]

    root = "switch_%s_livery" % vid
    emitter.switch(root, "cargo_subtype", cases, cases[0][1])
    return root


def _emit_cargo_chain(emitter: Emitter, vehicle: Vehicle, livery: Livery) -> str:
    """Emit the cargo_count / cargo_classes / cargo_type_in_veh switches.

    Every switch name carries the livery suffix, so a wagon with several paint
    schemes gets one independent chain per scheme.
    """
    variants = vehicle.cargo_variants

    class_cases: List[Tuple[str, str]] = []
    type_cases: List[Tuple[str, str]] = []
    prefix = _cargo_switch_prefix(vehicle, livery)
    emitted_stages: set = set()

    for variant in variants:
        # A row without sprite suffix is the "unloaded" state; it needs no
        # sprite of its own, the livery sprite is used directly.
        if not variant.suffix:
            continue
        sprite = _cargo_spriteset_name(vehicle, variant, livery)
        stage = "%s_%s_stage" % (prefix, variant.name or variant.suffix)

        if stage not in emitted_stages:
            stage_cases: List[Tuple[str, str]] = []
            if variant.from_index:
                stage_cases.append(("0..%d" % (variant.from_index - 1),
                                    _empty_sprite(vehicle, livery)))
            if variant.to_index:
                stage_cases.append(("%d..%d" % (variant.from_index, variant.to_index),
                                    sprite))
            if stage_cases:
                emitter.switch(stage, "cargo_count", stage_cases, sprite)
                emitted_stages.add(stage)
                target = stage
            else:
                target = sprite
        else:
            target = stage

        if variant.types:
            for cargo in variant.types:
                type_cases.append((cargo, target))
        elif variant.classes:
            class_cases.append((variant.classes, target))

    if not class_cases and not type_cases:
        return _livery_spriteset_name(vehicle, livery)

    inner_default = _livery_spriteset_name(vehicle, livery)
    if type_cases:
        inner = "%s_cargo_type" % prefix
        emitter.switch(inner, "cargo_type_in_veh", _dedupe(type_cases), inner_default)
    else:
        inner = inner_default

    if class_cases:
        class_switch = "%s_cargo_class" % prefix
        emitter.switch(class_switch, "cargo_classes", _dedupe(class_cases), inner)
    else:
        class_switch = inner

    # loading stages: the wagon looks empty while (almost) nothing is loaded
    empty_switch = "%s_empty" % prefix
    emitter.switch(empty_switch, "cargo_count < 5",
                   [("0", class_switch)], _empty_sprite(vehicle, livery))
    return empty_switch


def _dedupe(cases: Sequence[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """Drop repeated selectors, keeping the first occurrence."""
    seen = set()
    result: List[Tuple[str, str]] = []
    for selector, target in cases:
        if selector in seen:
            continue
        seen.add(selector)
        result.append((selector, target))
    return result


def _empty_sprite(vehicle: Vehicle, livery: Livery) -> str:
    """The "wagon is empty" sprite: the livery sprite without load suffix."""
    return _livery_spriteset_name(vehicle, livery)


def _emit_capacity_switch(emitter: Emitter, vehicle: Vehicle) -> Optional[str]:
    """Emit the ``cargo_capacity`` graphics callback for an articulated vehicle.

    Capacity is the one value OpenTTD reads per vehicle part, so on stock that
    OpenTTD treats as 2-<body>-2 the load must be placed on one section only:
    a plain number would give every section the same capacity and multiply the
    train's total.  Weight and power need no such treatment, because both are
    shared by the whole vehicle.  This is the pattern China Set: Trains uses,
    for example::

        switch (FEAT_TRAINS, SELF, switch_<id>_capacity,
                position_in_articulated_veh % 3) {
            1: return 62;
            return 0;
        }

    Returns ``None`` for a single section vehicle, which uses the plain
    property instead.
    """
    if vehicle.part_count < 2:
        return None
    switch = "switch_%s_capacity" % vehicle.id
    if vehicle.capacity_by_cargo:
        # the capacity depends on the cargo, so the section switch falls back
        # to a cargo switch instead of a plain number
        inner = "switch_%s_capacity_cargo" % vehicle.id
        cases = []
        for item in _split_list(vehicle.capacity_by_cargo):
            cargo, _, value = item.partition("=")
            cases.append((cargo.strip(), "return %s" % value.strip()))
        emitter.switch(inner, "cargo_type_in_veh", cases,
                       "return %d" % vehicle.capacity)
        target = inner
    else:
        target = "return %d" % vehicle.capacity
    emitter.switch(
        switch,
        f"position_in_articulated_veh % {vehicle.part_count}",
        [(str(vehicle.power_section), target)],
        "return 0",
    )
    return switch


def _num(value: float) -> str:
    """Format a number for NML.

    Integers stay integers.  Decimal values are written with a fixed notation,
    because NML rejects floating point literals such as 1e-05 and also refuses
    long fractions inside switch blocks.
    """
    if float(value).is_integer():
        return str(int(value))
    text = "%.4f" % value
    return text.rstrip("0").rstrip(".")


def render_item(vehicle: Vehicle, default_graphics: str,
                capacity_switch: Optional[str], start_stop_switch: str) -> str:
    vid = vehicle.id
    is_loco = vehicle.is_locomotive
    lines: List[str] = []
    add = lines.append

    add("// Begin %s" % vid.upper())

    # name callback
    if vehicle.name_callback:
        add("/* name callback: series name in the depot window */")

    if vehicle.visual_effect:
        add(vehicle.visual_effect)

    add("item (FEAT_TRAINS, %s) {" % vid)
    add("    property {")
    add("        // Menu")
    add("        name:                           string(%s);" % vehicle.name_constant)
    add("        sprite_id:                      SPRITE_ID_NEW_TRAIN;")
    flags = ["TRAIN_FLAG_AUTOREFIT"]
    if vehicle.mu:
        flags.append("TRAIN_FLAG_MU")
    if vehicle.train_flags:
        flags.extend(_split_list(vehicle.train_flags))
    add("        misc_flags:                     bitmask(%s);" % ", ".join(flags))
    if is_loco:
        add("        engine_class:                   %s;" % ENGINE_CLASS[vehicle.category])
    add("")
    add("        // Availability")
    add("        climates_available:             %s;" % vehicle.climates)
    add("        introduction_date:              date(%d,%02d,%02d);"
        % (vehicle.intro_year, vehicle.intro_month, vehicle.intro_day))
    add("        model_life:                     %s;"
        % (_life(vehicle.model_life)))
    if vehicle.retire_early:
        add("        retire_early:                   %d;" % vehicle.retire_early)
    add("        vehicle_life:                   %d;" % vehicle.vehicle_life)
    add("        track_type:                     %s;" % vehicle.track_type)
    add("")
    add("        // Cargo")
    add("        refittable_cargo_classes:       %s;" % vehicle.refit_classes)
    add("        non_refittable_cargo_classes:   %s;" % vehicle.non_refit_classes)
    add("        cargo_allow_refit:              %s;" % vehicle.cargo_allow)
    add("        cargo_disallow_refit:           %s;" % vehicle.cargo_disallow)
    add("        refit_cost:                     0;")
    add("        default_cargo_type:             %s;" % vehicle.default_cargo)
    add("        ai_special_flag:                %s;" % vehicle.ai_flag)
    # Capacity is the one value OpenTTD reads per section, so a vehicle split
    # into sections overrides it from the graphics block below.  The property
    # keeps the plain value, which is what a single section vehicle uses.
    add("        cargo_capacity:                 %d;" % vehicle.capacity)
    add("        loading_speed:                  %d << param_loading_speed;" % vehicle.loading_speed)
    add("        cargo_age_period:               %d << param_cargo_decay;" % vehicle.cargo_age_period)
    add("")
    add("        // Stats")
    add("        speed:                          %d km/h;" % vehicle.speed)
    if is_loco:
        add("        power:                          %s;"
            % _power(vehicle.power, vehicle.power_unit))
    else:
        add("        power:                          0 hp;")
    # ``weight`` is the mass of the whole vehicle, articulated parts included,
    # and ``power`` is likewise the output of the whole vehicle.  Both are plain
    # properties: the table value is exactly what the game receives.
    add("        weight:                         %s ton;" % _num(vehicle.weight))
    if is_loco and vehicle.te_coeff:
        add("        tractive_effort_coefficient:    %s;" % _num(vehicle.te_coeff))
    add("        cost_factor:                    %d;" % vehicle.cost_factor)
    add("        running_cost_base:              %s;" % vehicle.running_cost_base)
    add("        running_cost_factor:            %d;" % vehicle.running_cost_factor)
    if is_loco:
        add("        reliability_decay:              %d;" % vehicle.reliability_decay)
    bitmask = _info_bitmask(vehicle)
    if bitmask:
        add("        bitmask_vehicle_info:           %s;" % bitmask)
    add("    }")
    add("    graphics {")

    # menu
    add("        // Menu")
    if vehicle.additional_text:
        add("        additional_text:                string(%s);" % vehicle.additional_text)
    if vehicle.name_callback:
        add("        name:                           switch_name_series;")
    if len(vehicle.liveries) > 1:
        add("        cargo_subtype_text:             switch_%s_cargo_subtype;" % vid)
    add("        can_attach_wagon:               %s;" % _attach_switch(vehicle))
    if start_stop_switch:
        add("        start_stop:                     %s;" % start_stop_switch)

    # graphics
    add("")
    add("        // Graphics")
    add("        default:                        %s;" % default_graphics)
    add("        purchase:                       %s;" % _livery_purchase_name(vehicle, vehicle.default_livery))
    if vehicle.part_count > 1:
        add("        articulated_part:               switch_%s_articulated_part;" % vid)
    if vehicle.can_supply_head_end_power:
        add("        visual_effect_and_powered:      switch_%s_visual;" % vid)

    # stats overrides
    add("")
    add("        // Stats")
    if vehicle.length_switch:
        add("        length:                         %s;" % vehicle.length_switch)
    if capacity_switch:
        # Only a vehicle split into sections needs the callback: the load
        # belongs to the section named by power_section, and a plain number
        # would force the same capacity onto every section.
        add("        cargo_capacity:                 %s;" % capacity_switch)
    # Weight and power are plain properties.  Both are shared by the whole
    # vehicle, articulated parts included, which is why the parent set writes a
    # single ``weight: 138 ton`` for a three section locomotive.  No callback is
    # needed or wanted here.
    if vehicle.capacity > 1:
        # the depot window shows one third of the articulated capacity
        share = vehicle.capacity // 3 if vehicle.capacity % 3 == 0 else vehicle.capacity
        add("        purchase_cargo_capacity:        %d;" % share)
    add("        cost_factor:                    %d;"
        % (vehicle.purchase_cost_display or vehicle.cost_factor))
    add("        running_cost_factor:            %d * runningcostfactor()%s;"
        % (vehicle.running_cost_factor,
           _extra_cost(vehicle)))
    add("        purchase_running_cost_factor:   %d;"
        % (vehicle.purchase_running_cost_factor or vehicle.running_cost_factor * 3))
    if vehicle.purchase_speed:
        add("        purchase_speed:                 %d;" % vehicle.purchase_speed)
    if vehicle.purchase_power:
        add("        purchase_power:                 %s;" % _num(vehicle.purchase_power))
    add("    }")
    add("}")
    add("")
    add("// End %s" % vid.upper())

    # the cargo_subtype_text callback, emitted separately
    if len(vehicle.liveries) > 1:
        pass

    return "\n".join(lines)


def _life(value: str) -> str:
    value = (value or "").strip()
    if value.upper() in ("NEVER", "VEHICLE_NEVER_EXPIRES", ""):
        return "VEHICLE_NEVER_EXPIRES"
    return value


def _power(value: float, unit: str) -> str:
    return "%s %s" % (_num(value), unit)


def _extra_cost(vehicle: Vehicle) -> str:
    if vehicle.airconditioned:
        return " * cafecostfactor() + accostfactor()"
    return ""


def _info_bitmask(vehicle: Vehicle) -> str:
    """Build bitmask_vehicle_info.

    bit 1  restaurant car
    bit 2  the consist has an air conditioner / generator car available
    """
    bits: List[str] = []
    if vehicle.restaurant:
        bits.append("1")
    if vehicle.can_supply_head_end_power or vehicle.airconditioned:
        bits.append("2")
    if not bits:
        return ""
    return "bitmask(%s)" % ", ".join(bits)


def _attach_switch(vehicle: Vehicle) -> str:
    """Which attach callback restricts what may be coupled to this vehicle.

    * ``locowagon``  -- locomotives and coaches: coaches and freight wagons may
      be attached, multiple unit trailers may not.
    * ``muhead``     -- multiple unit head cars and multiple unit trailers:
      only multiple unit stock of this set, of China Set: Trains or of the
      narrow gauge add-on may be attached.
    """
    if vehicle.category in MU_CATEGORIES or vehicle.category == "unit_wagon":
        return "muhead"
    return "locowagon"


def _emit_start_stop(emitter: Emitter, vehicle: Vehicle) -> str:
    """Build the ``start_stop`` switch that gates a multiple unit.

    A multiple unit is bought as one three car unit and coupled until the train
    is as long as the player wants, so the only length rules that make sense are
    "at least N units" and "whole units only".  The parent set instead allows
    only 4 to 24 cars, which blocks a two unit train; this replaces that with
    the two rules an EMU actually needs, written as nested switches because a
    switch has a single selector and a single comparison.

    Returns the switch name, or ``""`` when the vehicle is not a multiple unit.
    """
    if not vehicle.mu:
        return ""
    vid = vehicle.id
    units = 3                        # one unit is three sections
    nothing = "CB_RESULT_NO_TEXT"

    # "whole units only": the part count has to divide by three
    units_switch = "switch_%s_whole_units" % vid
    emitter.switch(units_switch, "(num_vehs_in_consist % 3) != 0",
                   [("1", "return string(STR_MUST_BE_MULTIPLE_OF_3)")],
                   "return %s" % nothing)

    if vehicle.min_cars <= 0:
        # no minimum asked for: multiples of three may be one unit long
        return units_switch

    length_switch = "switch_%s_start_stop" % vid
    emitter.switch(
        length_switch,
        "num_vehs_in_consist < %d" % (vehicle.min_cars * units),
        [("1", "return string(STR_MUST_BE_4_TO_24_CARS)")],
        "return %s" % units_switch,
    )
    return length_switch


def emit_livery_callbacks(emitter: Emitter, vehicles: Sequence[Vehicle]) -> None:
    """Emit the cargo_subtype_text switches for vehicles with several liveries."""
    for vehicle in vehicles:
        if len(vehicle.liveries) < 2:
            continue
        cases: List[Tuple[str, str]] = []
        for livery in vehicle.liveries:
            label = livery.string or "STR_LV_ORIGINAL"
            if livery.is_automatic:
                label = livery.string or "STR_LV_BUILD_YEAR"
            cases.append((str(livery.index), "return string(%s)" % label))
        emitter.switch("switch_%s_cargo_subtype" % vehicle.id, "cargo_subtype", cases,
                       "return CB_RESULT_NO_TEXT")


def emit_length_switch(emitter: Emitter, vehicle: Vehicle) -> None:
    """Emit this vehicle's ``length`` switch when no shared one fits.

    A ``.length`` property takes either a number or the name of a switch, so a
    shape ``src/functions.pnml`` does not predefine has to become a block of its
    own instead of an inline switch.
    """
    if len(vehicle.parts) == 1 or vehicle.known_length_switch:
        return
    cases = [(str(position), "return %d" % length)
             for position, length in enumerate(vehicle.parts)]
    # the last section is the default, which also covers any position past the
    # end (position_in_articulated_veh wraps, so this is belt and braces)
    emitter.switch("switch_%s_length" % vehicle.id,
                   f"position_in_articulated_veh % {len(vehicle.parts)}",
                   cases[:-1], "return %d" % vehicle.parts[-1])


def emit_articulated_callbacks(emitter: Emitter, vehicles: Sequence[Vehicle]) -> None:
    """Emit articulated_part and, for locomotives, visual_effect_and_powered."""
    for vehicle in vehicles:
        vid = vehicle.id
        if vehicle.part_count > 1:
            extra = vehicle.part_count - 1
            switch = "switch_%s_articulated_part" % vid
            emitter.add(
                "switch (FEAT_TRAINS, SELF, %s, extra_callback_info1) {\n"
                "    1..%d: return %s;\n"
                "    return CB_RESULT_NO_MORE_ARTICULATED_PARTS;\n"
                "}" % (switch, extra, vid)
            )
        if vehicle.can_supply_head_end_power:
            switch = "switch_%s_visual" % vid
            cases = [(str(vehicle.power_section),
                      "return visual_effect_and_powered(%s, 0, ENABLE_WAGON_POWER)"
                      % _visual_effect(vehicle))]
            emitter.switch(switch, f"position_in_articulated_veh % {vehicle.part_count}",
                           cases,
                           "return visual_effect_and_powered(VISUAL_EFFECT_DISABLE, 0, DISABLE_WAGON_POWER)")


def _visual_effect(vehicle: Vehicle) -> str:
    if vehicle.visual_effect:
        return vehicle.visual_effect
    if vehicle.category in ("diesel", "dmu", "cargo_dmu"):
        return "VISUAL_EFFECT_DIESEL"
    return "VISUAL_EFFECT_ELECTRIC"


def collect_sprite_basenames(vehicle: Vehicle) -> List[str]:
    """Every sprite sheet basename this vehicle needs.

    This is the only authority on which ``gfx/<folder>/<basename>.vox`` files a
    set of rows requires: ``tools/verify_assets.py`` and the workbench both ask
    for it rather than reimplementing the suffix rules.

    Only basenames something actually names are returned.  The bare ``<id>`` is
    deliberately *not* included: it is the spriteset a livery with no suffix
    uses, so it appears here as soon as such a livery exists, and listing it
    unconditionally would report a model as missing that the generated code
    never references.
    """
    wanted: List[str] = []

    def add(basename: str) -> None:
        if basename and basename not in wanted:
            wanted.append(basename)

    for livery in vehicle.liveries:
        if livery.suffix:
            add(_livery_basename(vehicle, livery))
    for variant in vehicle.cargo_variants:
        if not variant.suffix:
            continue
        add(variant.suffix)
        for livery in vehicle.liveries:
            if livery.suffix:
                add(_cargo_basename(variant, livery))
    for livery in vehicle.liveries:
        for basename in graphics_rule_basenames(livery.graphics_parts):
            add(basename)
    return wanted


# --------------------------------------------------------------------------
# graphics_parts: which sprite a section shows, decided by its place in the
# whole train rather than by its place inside the vehicle
# --------------------------------------------------------------------------

# The table writes conditions in a small, lowercase language, and this is the
# translation into NML, so nobody has to remember the exact NewGRF variable
# names.  A condition is deliberately limited to ``variable 比较 数字``: the
# consist variables may only ever be the *selector* of a switch, so anything
# richer cannot be compiled into one, and predicate_selector() refuses it with
# an explanation instead of letting nmlc fail later.
GRAPHICS_VARIABLES = {
    "pos": "position_in_consist",
    "tailpos": "position_in_consist_from_end",
    "consist": "num_vehs_in_consist",
    "unitpos": "position_in_articulated_veh",
}


CONSIST_VARIABLES = ("position_in_consist", "position_in_consist_from_end",
                     "num_vehs_in_consist", "position_in_articulated_veh")


class GraphicsPartsError(ValueError):
    """A graphics_parts cell that cannot be turned into NML."""


def graphics_condition(text: str) -> str:
    """Translate one condition from the table language into NML.

    ``pos <= 2`` becomes ``position_in_consist <= 2``.  ``pos``/``tailpos`` count
    vehicle *parts*, exactly like ``position_in_consist`` does, so a three
    section vehicle occupies ``pos`` 0..2 and "the first car" is ``pos <= 2``.

    Only the variables above are recognised; anything else in a condition is
    refused here rather than pasted into NML, and predicate_selector() then
    narrows the expression down to the simple comparison a switch can select on.
    """
    translated = re.sub(
        r"\b(" + "|".join(GRAPHICS_VARIABLES) + r")\b",
        lambda match: GRAPHICS_VARIABLES[match.group(1)],
        text,
    )
    remainder = re.sub(r"\b(position_in_\w+|num_vehs_in_\w+)\b", "", translated)
    if not re.fullmatch(r"[0-9\s()%+\-*/<>=!&|.]*", remainder):
        raise GraphicsPartsError(
            "无法识别的条件片段 %r；可用变量：%s"
            % (text.strip(), ", ".join(sorted(GRAPHICS_VARIABLES))))
    return translated.strip()


def predicate_selector(text: str):
    """Turn one condition into a (selector, case) pair, or fail with advice.

    NewGRF only exposes consist variables as the *selector* of a switch: writing
    ``switch (..., 1) { num_vehs_in_consist < 3: ... }`` is rejected by nmlc
    with "Unrecognized identifier".  A condition therefore has to be a simple
    test on one variable, which becomes the selector, plus the comparison that
    becomes the case.  Anything more elaborate is refused here rather than
    compiled into something nmlc will not accept.
    """
    expression = graphics_condition(text)
    if "|" in expression or "&" in expression:
        raise GraphicsPartsError(
            "条件 %r 含 & 或 |；编组变量只能作为开关的选择器，"
            "请拆成多条规则（用 | 分隔）让生成器嵌套开关" % text.strip())
    if "!" in expression:
        raise GraphicsPartsError("条件 %r 不支持取反，请改用相反的比较" % text.strip())

    parts = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|\d+", expression)
    used = [name for name in parts if name in CONSIST_VARIABLES]
    if len(set(used)) > 1:
        raise GraphicsPartsError(
            "条件 %r 同时用了 %s；一个条件只能比较一个变量，"
            "请拆成多条规则" % (text.strip(), " 和 ".join(sorted(set(used)))))
    if not used:
        raise GraphicsPartsError(
            "条件 %r 没有用到任何编组变量（pos/tailpos/consist/unitpos）" % text.strip())
    selector = used[0]

    # normalise "consist<=9", "consist <= 9" and "consist  <=  9" to one shape
    normalised = re.sub(r"\s*(==|!=|<=|>=|<|>)\s*", r" \1 ", expression).strip()
    for operator in ("==", "!=", "<=", ">=", "<", ">"):
        match = re.fullmatch(
            r"%s\s+([0-9]+)" % re.escape(selector + " " + operator), normalised)
        if not match:
            continue
        number = int(match.group(1))
        if operator == "==":
            return selector, str(number)
        if operator == "!=":
            raise GraphicsPartsError("条件 %r 不支持 !=，请改用两个区间规则" % text.strip())
        if operator == "<":
            low, high = 0, number - 1
        elif operator == "<=":
            low, high = 0, number
        elif operator == ">":
            low, high = number + 1, 255
        else:
            low, high = number, 255
        if high < low:
            raise GraphicsPartsError("条件 %r 永远不成立" % text.strip())
        return selector, "%d..%d" % (low, high)

    raise GraphicsPartsError(
        "条件 %r 不受支持。一个条件只能是“变量 比较 数字”的简单形式，例如 "
        "consist <= 9、pos == 0、tailpos >= 3、unitpos == 1；"
        "不支持算式（如 pos / 3）。同一段里需要多个条件时请写多条规则，"
        "生成器会把它们编成嵌套开关" % text.strip())


class TreeNode:
    """One switch of a section's rule tree.

    ``selector`` is the NML variable this switch branches on.  Every child is one
    branch: its ``case`` is the value or range that selects it, and it either
    shows a sprite sheet (``basename``) or continues into the switch named by
    ``selector_below``.  A branch with an empty ``case`` is that switch's
    ``default``, and a node with no ``selector`` is a plain holder.

    The selection lives on the *branch* rather than on the node, which is what
    keeps the two shapes apart::

        pos<=2=a | pos>2=b           one switch, two cases
        pos<=2=a | tailpos<=2=b | c  two switches in a chain, plus a catch-all

    The second is not a switch with three cases -- its rules test two different
    variables, and a switch can only select on one -- it is the first switch
    sending everything it did not match to the second.  A flat list of
    ``(selector, case, basename)`` triples cannot tell those apart, so the parser
    builds the tree directly.
    """

    selector: str
    case: str
    basename: str
    selector_below: str
    children: List["TreeNode"]

    def __init__(self, selector: str = "", case: str = "",
                 basename: str = "", selector_below: str = "",
                 children: Optional[List["TreeNode"]] = None) -> None:
        self.selector = selector
        self.case = case
        self.basename = basename
        self.selector_below = selector_below
        self.children = list(children) if children else []

    @property
    def is_leaf(self) -> bool:
        """True when this branch shows a sheet instead of switching again."""
        return not self.selector_below

    def walk(self) -> Iterator["TreeNode"]:
        """This node and every node below it, parents before children."""
        yield self
        for child in self.children:
            for node in child.walk():
                yield node

    def __repr__(self) -> str:  # keeps test failures readable
        if self.selector:
            return "TreeNode(switch on %r, %d branches)" % (
                self.selector, len(self.children))
        return "TreeNode(%r -> %r)" % (self.case, self.basename)


BASENAME_RE = re.compile(r"[a-z0-9_]+")


def parse_graphics_parts(text: str, part_count: int) -> List[List[TreeNode]]:
    """Parse a ``graphics_parts`` cell into one rule tree per section.

    The cell is split on ``;`` -- one piece per section -- and each piece on
    ``|``.  A rule is a *path* through the tree: every condition on the way down,
    then the sprite sheet, all joined with ``=``::

        consist<=6=pos<=2=head_s | consist<=6=head_l | body_l

    reads as "on a train of at most six parts: the first two parts show
    ``head_s`` and the rest ``head_l``; on a longer train, ``body_l``".

    A condition itself contains ``=`` (``<=``, ``==``), so the split is not
    simply "the last ``=``": each leading piece is tried as a condition until
    what is left is a bare basename.  Two rules that share the start of their
    path describe two branches of *one* switch, which is why the pieces are
    merged back into a tree here rather than left as a list of paths.

    The number of pieces is checked against ``parts``, so a trailing ``;`` counts
    as a real section instead of punctuation: ``a;b;`` is three sections, which
    is what a 3 section vehicle needs, and ``a;b;c;`` is four and an error.  An
    empty piece stays invisible, which is how the two end pieces of the usual
    ``2|8|2`` vehicle are written.
    """
    text = (text or "").strip()
    if not text:
        return []
    sections = [piece.strip() for piece in text.split(";")]
    if len(sections) != part_count:
        raise GraphicsPartsError(
            "graphics_parts 需要 %d 段（与 parts 相同），当前 %d 段"
            "（空段表示该段隐形；末尾的 ; 也算一段）"
            % (part_count, len(sections)))

    parsed: List[List[TreeNode]] = []
    for index, piece in enumerate(sections):
        paths: List[Tuple[List[Tuple[str, str]], str]] = []
        for raw in piece.split("|"):
            rule = raw.strip()
            if not rule:
                continue
            # a condition contains '=', so walk the pieces left to right and
            # let predicate_selector decide where a condition ends
            rest = rule
            chain: List[Tuple[str, str]] = []
            while True:
                candidate, found = _longest_condition(rest)
                if not found:
                    break
                chain.append((candidate[0], candidate[1]))
                rest = rest[len(candidate[2]):].lstrip("=").strip()
                if not rest:
                    break
            if not BASENAME_RE.fullmatch(rest):
                raise GraphicsPartsError(
                    "第 %d 段的 %r 无法解析：每一条规则是"
                    "「条件=条件=…=贴图基名」，基名只能用小写字母、数字和下划线"
                    % (index + 1, rule))
            paths.append((chain, rest))
        # an empty section is valid and means "this section stays invisible"
        parsed.append(_graphics_rule_tree(paths, index + 1))
    return parsed


def _graphics_rule_tree(paths: List[Tuple[List[Tuple[str, str]], str]],
                        section: int) -> List[TreeNode]:
    """Build one section's switch tree out of the rules written for it.

    Rules form a **chain**: they are tried in the order they are written, the
    first one whose condition holds picks the sheet, and a rule with no condition
    is the catch-all at the end.  That is what a chain of hand written switches
    does -- each one tests a variable and sends the values it does not match on
    to the next -- and it is why two rules may name *different* variables at the
    same level::

        pos<=2=set_head | tailpos<=2=set_tail | set_mid

    is "the first three parts show set_head, the last three show set_tail,
    everything else shows set_mid", which is two switches in a row plus a
    catch-all, not one switch with three cases.

    Rules that share a condition start with, though, are *not* a chain: they are
    two branches of one switch, so ``pos<=2=a | pos>2=b`` is one switch with two
    cases, and a rule that stops part way down becomes the default of the switch
    at the level where it stopped.
    """
    if not paths:
        return []
    roots: List[TreeNode] = []
    for chain, basename in paths:
        _graphics_insert(roots, chain, basename, section)
    for root in roots:
        _graphics_merge_cases(root, section)
        _graphics_check_cases(root, section)
    return roots


def _graphics_insert(roots: List[TreeNode],
                     chain: List[Tuple[str, str]],
                     basename: str, section: int) -> None:
    """Add one rule path to the section's chain of switches.

    A rule whose first condition names the variable the deepest switch already
    uses joins that switch as another branch; a rule naming a different variable
    becomes that switch's *default*, so the chain continues from there.  A rule
    with no condition at all is the catch-all at the end of the chain.
    """
    if not chain:
        # a rule with no condition at all: this section shows one sheet whatever
        # the consist looks like, so it is the default of the deepest switch
        _graphics_set_default(_graphics_deepest_switch(roots), basename, section)
        return

    parent = _graphics_chain_parent(roots, chain[0][0], section)
    _graphics_leaf(parent, chain, basename, section)


def _graphics_switch_selector(node: TreeNode) -> str:
    """The variable a switch container selects on.

    A container is either a root node (``selector``) or a switch's default branch
    (``selector_below``), and both hold the case branches in ``children``.  The
    chain needs one name for "which variable does this switch test".
    """
    return node.selector or node.selector_below


def _graphics_chain_parent(roots: List[TreeNode], selector: str,
                           section: int) -> TreeNode:
    """The switch of the chain that a condition on ``selector`` continues.

    A selector the deepest switch already uses joins that switch, so
    ``pos<=2=a | pos>2=b`` describes one switch rather than two.  Any other
    selector carries the chain on: that switch's default becomes a switch on the
    new variable, which is exactly how the same thing is written by hand.
    """
    if not roots:
        node = TreeNode(selector=selector)
        roots.append(node)
        return node
    node = _graphics_deepest_switch(roots)
    if _graphics_switch_selector(node) == selector:
        return node
    tail = None
    for child in node.children:
        if not child.case:
            tail = child
            break
    if tail is None:
        tail = TreeNode()
        node.children.append(tail)
    _graphics_open_below(tail, selector, section)
    return tail


def _graphics_deepest_switch(roots: List[TreeNode]) -> TreeNode:
    """The last switch of the chain, which is where a catch-all belongs."""
    if not roots:
        node = TreeNode()
        roots.append(node)
        return node
    node = roots[-1]
    for child in node.children:
        if not child.case and child.selector_below:
            return _graphics_deepest_switch([child])
    return node


def _graphics_leaf(parent: TreeNode, chain: List[Tuple[str, str]], basename: str,
                   section: int) -> Optional[TreeNode]:
    """Walk ``chain`` under ``parent``, creating and merging branches, and put
    ``basename`` at the end of it.  Returns the branch, or None for a chain with
    no conditions."""
    if not chain:
        return None
    node = parent
    for depth, (selector, case) in enumerate(chain):
        last = depth == len(chain) - 1
        branch = None
        for existing in node.children:
            if existing.case == case:
                branch = existing
                break
        if branch is None:
            branch = TreeNode(case=case)
            node.children.append(branch)
        if last:
            _graphics_set_leaf(branch, basename, case, section)
        else:
            _graphics_open_below(branch, chain[depth + 1][0], section)
        node = branch
    return node


def _graphics_set_leaf(branch: TreeNode, basename: str, case: str,
                       section: int) -> None:
    """Give ``branch`` its sprite sheet, or record it as that level's default."""
    if branch.is_leaf:
        if branch.basename and branch.basename != basename:
            raise GraphicsPartsError(
                "第 %d 段的 %r 同时指定了模型 %r 和 %r；一个截面上只有一个"
                "模型，请把其中一个改成范围更小的下一层条件"
                % (section, case, branch.basename, basename))
        branch.basename = basename
        return
    # the branch already switches further down, so this sheet is what an
    # unmatched value of that switch shows
    _graphics_set_default(branch, basename, section)


def _graphics_set_default(branch: TreeNode, basename: str, section: int) -> None:
    """Record ``basename`` as the default of the switch inside ``branch``."""
    for child in branch.children:
        # a child with no case is a default unless it is the chain continuing
        # into the next switch, which is a default *and* a switch
        if not child.case and not child.selector_below:
            if child.basename and child.basename != basename:
                raise GraphicsPartsError(
                    "第 %d 段的 %r 一层有两个默认模型（%r 和 %r）"
                    % (section, branch.case, child.basename, basename))
            child.basename = basename
            return
    branch.children.append(TreeNode(basename=basename))


def _graphics_open_below(branch: TreeNode, selector: str, section: int) -> None:
    """Make ``branch`` switch again on ``selector`` instead of drawing a sheet."""
    if branch.is_leaf:
        if branch.basename:
            # the sheet this branch showed becomes the default of the switch it
            # is turning into, which is where a hand written switch puts it
            basename, branch.basename = branch.basename, ""
            branch.children.append(TreeNode(basename=basename))
    elif branch.selector_below != selector:
        raise GraphicsPartsError(
            "第 %d 段的 %r 下面同时按 %s 和 %s 判断；同一层只能筛选一个变量"
            % (section, branch.case, branch.selector_below, selector))
    branch.selector_below = selector


def _graphics_merge_cases(node: TreeNode, section: int) -> None:
    """Collapse branches that select on the same value into one.

    Two rules can name the same condition and still be written as separate
    branches -- ``pos<=2=a | pos<=2=b`` -- which a hand written switch could only
    express by nesting.  Merging them keeps one case per value, because nmlc
    rejects a switch that names a case twice.

    A branch with no case is not a case at all: it is either the switch's default
    or the chain continuing into the next switch, and the two are allowed to sit
    side by side.  Two *defaults* are not, so that is reported.
    """
    merged: List[TreeNode] = []
    default_seen: Optional[TreeNode] = None
    for branch in node.children:
        if branch.selector_below or not branch.case:
            if not branch.selector_below:
                if default_seen is not None:
                    raise GraphicsPartsError(
                        "第 %d 段写了两个没有条件的默认贴图（%r 和 %r）；"
                        "一段只能有一个默认"
                        % (section, default_seen.basename, branch.basename))
                default_seen = branch
            merged.append(branch)
            continue
        double = None
        for existing in merged:
            if existing.case == branch.case:
                double = existing
                break
        if double is None:
            merged.append(branch)
        else:
            _graphics_merge_branches(double, branch, section)
    node.children = merged
    for branch in node.children:
        if branch.selector_below:
            _graphics_merge_cases(branch, section)


def _graphics_merge_branches(into: TreeNode, other: TreeNode, section: int) -> None:
    """Fold one branch with the same case as another into it."""
    if into.is_leaf and other.is_leaf:
        if into.basename != other.basename:
            raise GraphicsPartsError(
                "第 %d 段的 %r 同时指定了 %r 和 %r；一个截面上只有一个模型，"
                "请改用更细的条件（例如把其中一个改成范围更小的一层）"
                % (section, into.case, into.basename, other.basename))
        return
    if into.is_leaf != other.is_leaf:
        raise GraphicsPartsError(
            "第 %d 段的 %r 既直接指定了模型又写了下一层条件，无法同时成立"
            % (section, into.case))
    into.children.extend(other.children)


def _graphics_case_range(case: str) -> Tuple[int, int]:
    """The inclusive bounds a parsed case covers."""
    if ".." in case:
        low, _, high = case.partition("..")
        return int(low), int(high)
    value = int(case)
    return value, value


def _graphics_check_cases(root: TreeNode, section: int,
                          ancestors: Tuple[str, ...] = ()) -> None:
    """Refuse sibling cases that swallow each other, and repeated selectors.

    A switch is tried top to bottom and stops at the first match, so
    ``consist<=6=a | consist<=10=b`` would never reach ``b``: ``<=6`` catches
    every value ``<=10`` as well.  Catching it here is worth the trouble because
    the mistake looks perfectly reasonable and would otherwise show up as a
    sprite that simply never appears in game.  A gap between two cases is fine --
    that is what the fallback is for.

    ``ancestors`` holds the variables of the switches above this one.  Selecting
    on one of them again would need two switches on the same variable nested in
    each other, which is both confusing and rejected by the emitter, so it is
    refused here instead -- at parse time, which is what lets the workbench show
    the same complaint the build would.
    """
    selector = _graphics_switch_selector(root)
    if selector:
        if selector in ancestors:
            raise GraphicsPartsError(
                "第 %d 段里重复使用了 %s；同一条路径上的每个条件要换一个变量"
                % (section, selector))
        ancestors = ancestors + (selector,)

    ranges = [(_graphics_case_range(branch.case), branch.case)
              for branch in root.children if branch.case]
    for index, ((low, high), case) in enumerate(ranges):
        for other_low, other_high in (r[0] for r in ranges[:index]):
            if other_low <= low and high <= other_high:
                raise GraphicsPartsError(
                    "第 %d 段的 %r 被前面的条件完全覆盖，永远不会生效；"
                    "请把范围小的写在前面，或改成互不重叠的区间"
                    % (section, case))
    for branch in root.children:
        if branch.selector_below:
            _graphics_check_cases(branch, section, ancestors)


def tree_to_json(node: TreeNode) -> Dict[str, object]:
    """One switch-tree node as a plain dict, for the workbench editor.

    This is the shape the editor loads, edits and posts back, so it is defined
    here next to the parser rather than in the web layer: one definition means
    the editor cannot drift from what the generator reads.
    """
    return {
        "selector": node.selector,
        "case": node.case,
        "basename": node.basename,
        "selector_below": node.selector_below,
        "children": [tree_to_json(child) for child in node.children],
    }


def tree_from_json(data: object) -> TreeNode:
    """Rebuild one switch-tree node from the dict ``tree_to_json`` wrote."""
    if not isinstance(data, dict):
        raise GraphicsPartsError("规则树的一个节点不是对象：%r" % (data,))
    node = TreeNode(
        selector=str(data.get("selector") or ""),
        case=str(data.get("case") or ""),
        basename=str(data.get("basename") or ""),
        selector_below=str(data.get("selector_below") or ""),
    )
    children = data.get("children") or []
    if not isinstance(children, list):
        raise GraphicsPartsError("规则树的 children 不是列表：%r" % (children,))
    node.children = [tree_from_json(child) for child in children]
    return node


def render_graphics_json(sections: object, part_count: int) -> str:
    """Render the editor's tree back into a ``graphics_parts`` cell.

    The result is parsed again before it is returned, so the editor can show the
    author exactly what the table will contain -- including a normalised form
    that differs from what was typed.
    """
    if not isinstance(sections, list):
        raise GraphicsPartsError("sections 不是列表：%r" % (sections,))
    if not sections:
        # the editor's "这一行的涂装完全没有规则" state, which is not the same as
        # N empty sections: the generator then uses its plain per-section default
        return ""
    if len(sections) != part_count:
        raise GraphicsPartsError(
            "graphics_parts 需要 %d 段（与 parts 相同），当前 %d 段"
            % (part_count, len(sections)))
    trees = [[tree_from_json(root) for root in (section or [])]
             for section in sections]
    return render_graphics_parts(trees)


def render_graphics_parts(rules: Sequence[Sequence[TreeNode]]) -> str:
    """Turn parsed section trees back into a ``graphics_parts`` cell.

    The workbench editor needs this round trip to be exact: it shows the tree the
    parser produced, the author edits it with the same building blocks NML has
    (a switch, its cases, each case a sheet or another switch), and the cell
    written back into the table has to parse to the same tree again.  The order
    below is what makes that true -- cases first, then defaults, and a switch
    that is another switch's default written as its own rules after them, which
    is exactly how the chain is written by hand.
    """
    return ";".join(_render_section(roots) for roots in rules)


def _render_section(roots: Sequence[TreeNode]) -> str:
    """One ``;`` piece: the rules of a single section."""
    if not roots:
        return ""
    root = roots[0]
    if not root.selector:
        # No condition anywhere, so the section is one sheet (or invisible).  A
        # branch under such a root cannot be written at all: the cell would say
        # "this section always shows X" and the branch would disappear, so it is
        # refused rather than silently dropped.
        sheets = [node for node in root.walk() if node.basename]
        branches = [node for node in root.walk()
                    if node is not root and (node.case or node.selector_below)]
        if branches or len(sheets) > 1:
            raise GraphicsPartsError(
                "这一段没有筛选条件，写回表格只会剩下「整段一张图」；"
                "请先选一个变量再分区间")
        return sheets[0].basename if sheets else ""
    return " | ".join(_render_container(root, ()))


def _render_container(node: TreeNode, prefix: Sequence[str]) -> List[str]:
    """The rule paths of one switch and of everything below it.

    ``prefix`` holds the conditions already walked through, so a nested switch
    writes ``consist<=6=pos<=2=h_s`` while the outermost one writes ``pos<=2=a``.
    """
    selector = _graphics_switch_selector(node)
    if not selector:
        raise GraphicsPartsError("这一段有一层开关没有选择变量，无法写回表格")

    paths: List[str] = []
    for branch in node.children:
        if not branch.case:
            continue
        path = list(prefix) + [_render_condition(selector, branch.case)]
        if branch.selector_below:
            paths.extend(_render_container(_graphics_sub_switch(branch), path))
        else:
            paths.append("=".join(path + [branch.basename]))

    for branch in node.children:
        if branch.case:
            continue
        if branch.selector_below:
            # A switch that is another switch's default is the chain continuing,
            # which the cell language can only write at the top level: further
            # down, the same variable would have to be selected twice on one path
            # and the parser refuses that.
            if prefix:
                raise GraphicsPartsError(
                    "「%s」这一层里还有一层开关，表格语言写不出来；"
                    "请把它改成模型，或移到最外层" % "=".join(prefix))
            paths.extend(_render_container(_graphics_sub_switch(branch), prefix))
        elif branch.basename:
            paths.append("=".join(list(prefix) + [branch.basename]))
    return paths


def _graphics_sub_switch(branch: TreeNode) -> TreeNode:
    """The switch a branch continues into, as a node of its own."""
    node = TreeNode(selector=branch.selector_below)
    node.children = branch.children
    return node


def _render_condition(selector: str, case: str) -> str:
    """Write one case back as the condition text the cell language uses."""
    low, high = _graphics_case_range(case)
    if low == high:
        return "%s==%d" % (selector, low)
    if low == 0:
        return "%s<=%d" % (selector, high)
    if high == 255:
        return "%s>=%d" % (selector, low)
    raise GraphicsPartsError(
        "区间 %s 写不回表格（表格只能写「小于等于」「大于等于」和「等于」）"
        % case)


def _longest_condition(text: str) -> Tuple[Tuple[str, str, str], bool]:
    """Split the longest valid condition off the front of a rule path.

    Returns ``((selector, case, raw), True)`` or ``(("", "", ""), False)``.  The
    longest match is what makes ``consist<=6=pos<=2`` two conditions rather than
    one comparison against the text ``6=pos<=2``.  A comparison operator is
    required, so a bare sprite sheet name is never mistaken for a condition,
    which is what used to swallow the fallback in ``… | body_l``.
    """
    best = ("", "", "")
    for end in range(len(text), 0, -1):
        candidate = text[:end]
        if not re.search(r"[=<>]", candidate):
            continue
        try:
            selector, case = predicate_selector(candidate)
        except GraphicsPartsError:
            continue
        best = (selector, case, candidate)
        break
    return best, bool(best[0])


def graphics_rule_basenames(rules: List[List[TreeNode]]) -> List[str]:
    """Every basename a parsed graphics_parts list refers to, in order."""
    seen: List[str] = []
    for section in rules:
        for root in section:
            for node in root.walk():
                if node.basename and node.basename not in seen:
                    seen.append(node.basename)
    return seen


def emit_graphics_rules(switches: "Emitter", vehicle: Vehicle, prefix: str,
                        rules: List[TreeNode], fallback: str,
                        selectors: Tuple[str, ...] = (),
                        index: int = 0) -> str:
    """Compile one section's rules into switches, and name the result.

    NewGRF only exposes these variables as a switch *selector*, never inside a
    condition: ``switch (..., 1) { num_vehs_in_consist <= 9: ... }`` is rejected
    by nmlc.  A rule therefore becomes a switch on its own variable, and a rule
    on a different variable becomes that switch's default, because a chain of
    switches is the only way to test two variables in one section.

    ``rules`` is the section's whole chain; the first switch is the entry point.
    The result is not always a switch, because a section that names no condition
    at all is just a sprite sheet.

    ``selectors`` holds the variables of the switches *above* this call, so a
    branch that selects on a variable an ancestor already selected is refused
    with a useful message instead of compiling into NML nmlc rejects.
    """
    if not rules:
        return fallback

    chain = [node for node in rules if node.selector]
    if not chain:
        # no condition anywhere: the section shows one sheet, or stays invisible
        for root in rules:
            for node in root.walk():
                if node.basename:
                    return _graphics_part_spriteset(vehicle, node.basename)
        return fallback

    root = chain[0]
    selector = root.selector
    branches: List[TreeNode] = []
    default_target: Optional[str] = None
    for branch in root.children:
        if branch.case:
            branches.append(branch)
        elif branch.selector_below:
            # the chain carries on: this switch's default is the next switch
            default_target = _graphics_branch_target(
                switches, vehicle, "%s_next" % prefix, branch, fallback,
                selectors + (selector,), index + len(branches))
        else:
            default_target = _graphics_part_spriteset(vehicle, branch.basename)
    return _graphics_switch(switches, vehicle, prefix, selector, branches,
                            fallback, default_target, selectors, index)


def _graphics_switch(switches: "Emitter", vehicle: Vehicle, prefix: str,
                     selector: str, branches: List[TreeNode], fallback: str,
                     default_target: Optional[str], selectors: Tuple[str, ...],
                     index: int) -> str:
    """Emit one switch and return its name.

    ``branches`` are the cases that select a value; ``default_target`` is what an
    unmatched value resolves to, or ``None`` to use the caller's ``fallback``.
    The switch is emitted even with a single branch, because it is the default
    that makes the branch conditional -- folding the level away would apply the
    sprite to every value the condition rejected.
    """
    if selector in selectors:
        raise GraphicsPartsError(
            "同一段里重复使用了 %s 作为同一层的选择器；请把同层的分支合成"
            "一个区间，或换一个变量" % selector)

    cases: List[Tuple[str, str]] = []
    for position, branch in enumerate(branches):
        cases.append((branch.case, "return %s"
                      % _graphics_branch_target(switches, vehicle,
                                                "%s_%d" % (prefix, position),
                                                branch, fallback,
                                                selectors + (selector,),
                                                index + 1 + position)))

    if not branches and default_target is None:
        # a switch with no cases and no default selects nothing at all
        return fallback
    default = "return %s" % (default_target if default_target is not None
                             else fallback)
    name = "switch_%s" % prefix
    switches.switch(name, selector, cases, default)
    return name


def _graphics_branch_node(selector: str, branch: TreeNode) -> TreeNode:
    """The sub tree of one branch, as a node that can be compiled on its own."""
    node = TreeNode(selector=selector)
    node.children = branch.children
    return node


def _graphics_branch_target(switches: "Emitter", vehicle: Vehicle, label: str,
                            branch: TreeNode, fallback: str,
                            selectors: Tuple[str, ...], index: int) -> str:
    """The switch or spriteset one branch of a rule tree resolves to."""
    if branch.is_leaf:
        return _graphics_part_spriteset(vehicle, branch.basename)
    root = _graphics_branch_node(branch.selector_below, branch)
    return emit_graphics_rules(switches, vehicle, label, [root], fallback,
                               selectors, index)


def _graphics_part_spriteset(vehicle: Vehicle, basename: str) -> str:
    """Spriteset name for one basename named by the ``graphics_parts`` column."""
    return "spriteset_%s_gfx_%s" % (vehicle.id, _identifier_part(basename))


def _graphics_part_template(vehicle: Vehicle, livery: "Livery", basename: str) -> str:
    """The template a graphics_parts basename is drawn with.

    A scheme may name a template per section; when the basename being drawn is
    one of that scheme's own basenames, the scheme's first template is used so
    that ``template_speciel_0`` style artwork keeps working.  Anything else
    falls back to the vehicle's first scheme and finally to the standard one.
    """
    if livery.templates:
        if _livery_basename(vehicle, livery) == basename:
            return livery.template_for(0, vehicle.part_count)
    if vehicle.liveries and vehicle.liveries[0].templates:
        return vehicle.liveries[0].template_for(0, vehicle.part_count)
    return "template_standard"


def _emit_graphics_parts(switches: "Emitter", vehicle: Vehicle,
                         livery_roots: Dict[int, str]) -> Optional[str]:
    """Build the per scheme graphics dispatch from the livery table.

    Every paint scheme owns its own ``graphics_parts``: which sprite each
    section shows depends on the scheme, because different artwork is exactly
    what distinguishes the schemes.  Each scheme therefore gets its own
    ``switch_<id>_section_<index>`` chain, and the outer switch selects it by
    ``cargo_subtype`` so that refitting changes the shape as well as the paint.

    A scheme that names no rules keeps the plain per-section behaviour: only the
    body section draws the scheme's own sheet, the invisible end sections stay
    invisible.

    Once a scheme *does* name rules, nothing is assumed on its behalf: a section
    whose piece is empty stays invisible, and a section whose rules match nothing
    also stays invisible.  The alternative -- quietly showing the scheme's
    whole-car sheet on those sections -- would paint the entire model once per
    section, so ``;emu_body;`` would draw the car three times instead of hiding
    its ends.
    """
    vid = vehicle.id
    liveries = [livery for livery in vehicle.liveries if livery.index in livery_roots]
    if not liveries:
        return None

    def section_switch(livery: Livery, fallback: str) -> str:
        if not livery.graphics_parts:
            # the shape dispatch every vehicle had before the column moved
            switch = "switch_%s_section_%d" % (vid, livery.index)
            switches.switch(
                switch,
                f"position_in_articulated_veh % {vehicle.part_count}",
                [(str(vehicle.power_section), fallback)],
                "empty_sprites;",
            )
            return switch
        targets: List[str] = []
        for position, rules in enumerate(livery.graphics_parts):
            prefix = "%s_%d_%d" % (vid, livery.index, position)
            targets.append(emit_graphics_rules(switches, vehicle, prefix, rules,
                                               "empty_sprites"))
        switch = "switch_%s_section_%d" % (vid, livery.index)
        switches.switch(switch,
                        f"position_in_articulated_veh % {vehicle.part_count}",
                        [(str(position), target)
                         for position, target in enumerate(targets)],
                        "empty_sprites;")
        return switch

    per_livery: List[Tuple[str, str]] = [
        (str(livery.index), section_switch(livery, livery_roots[livery.index]))
        for livery in liveries
    ]

    if len(per_livery) == 1 and not vehicle.year_dependent:
        return per_livery[0][1]
    switch = "switch_%s_graphics" % vid
    switches.switch(switch, "cargo_subtype", per_livery, per_livery[0][1])
    return switch


# --------------------------------------------------------------------------
# file writing
# --------------------------------------------------------------------------


def write_png(path: str, width: int, height: int, rgba: Tuple[int, int, int, int]) -> None:
    """Write a tiny RGBA PNG without external dependencies."""
    raw = bytearray()
    for _ in range(height):
        raw.append(0)  # filter type 0
        for _ in range(width):
            raw.extend(rgba)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    data = (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))
    with open(path, "wb") as handle:
        handle.write(data)


def write_manifest(path: str) -> None:
    """Write the gorender/renderobject manifest used for every sprite sheet.

    The eight entries describe the eight isometric views and their pixel sizes;
    template.pnml crops the sheets with exactly these rectangles, so the two
    files must agree.
    """
    views = [
        (0, 36, 166, True, 33),
        (45, 120, 116, True, None),
        (90, 192, 80, True, None),
        (135, 120, 116, True, None),
        (180, 36, 166, True, 33),
        (225, 120, 116, True, None),
        (270, 192, 80, True, None),
        (315, 120, 116, True, None),
    ]
    lines = [
        "{",
        '  "lighting_angle": 50,',
        '  "lighting_elevation": 45,',
        '  "depth_influence": 0,',
        '  "tiled_normals": false,',
        '  "soften_edges": 1.5,',
        '  "alpha_edge_threshold": 0.75,',
        '  "sampler": "square",',
        '  "accuracy": 8,',
        '  "overlap": 0.05,',
        '  "brightness": -0.025,',
        '  "contrast": 0.025,',
        '  "pad_to_full_length": false,',
        '  "detail_boost": 10.0,',
        '  "falloff_adjustment": 0.5,',
        '  "size": {',
        '    "x": 192,',
        '    "y": 48,',
        '    "z": 80',
        "  },",
        '  "render_elevation": 30,',
        '  "sprites": [',
    ]
    blocks = []
    for angle, width, height, flip, elevation in views:
        entry = ['    {',
                 '      "angle": %d,' % angle,
                 '      "width": %d,' % width,
                 '      "height": %d,' % height,
                 '      "flip": %s' % ("true" if flip else "false")]
        if elevation is not None:
            entry[-1] += ","
            entry.append('      "render_elevation": %d' % elevation)
        entry.append("    }")
        blocks.append("\n".join(entry))
    lines.append(",\n".join(blocks))
    lines.append("  ]")
    lines.append("}")
    write_file(path, "\n".join(lines) + "\n")


def ensure_dir(path: str) -> None:
    if path and not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)


def write_file(path: str, text: str) -> None:
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


# --------------------------------------------------------------------------
# output assembly
# --------------------------------------------------------------------------


def vehicle_file_path(vehicle: Vehicle, out_dir: str) -> str:
    """Path of the generated file of one vehicle.

    One vehicle, one file, grouped by kind exactly like China Set: Trains:

        src/<folder>/<id>.pnml
    """
    return os.path.join(out_dir, vehicle.folder, "%s.pnml" % vehicle.id)


def render_vehicle_file(vehicle: Vehicle) -> str:
    """Assemble the PNML of a single vehicle.

    The file holds that vehicle's switches, its spritesets and its item block,
    in the order the hand written sets use.  Keeping one vehicle per file means
    adding or changing a vehicle touches exactly one file, so diffs stay small
    and merge conflicts are rare.
    """
    switches = Emitter()
    sprites = Emitter()
    items = Emitter()

    # callbacks that belong to this vehicle only
    emit_livery_callbacks(switches, [vehicle])
    emit_articulated_callbacks(switches, [vehicle])
    emit_length_switch(switches, vehicle)

    emit_vehicle(sprites, switches, items, vehicle)

    def section(title: str, emitter: Emitter) -> str:
        body = "\n\n".join(block for block in emitter.blocks if block.strip())
        if not body:
            return ""
        bar = "=" * 74
        return "/* %s\n *  %s\n * %s */\n\n%s" % (bar, title, bar, body)

    parts = [GENERATED_HEADER.format(
        title="src/%s/%s.pnml -- generated vehicle code"
              % (vehicle.folder, vehicle.id)).rstrip("\n")]
    for title, emitter in (("SWITCHES  (callbacks, livery and cargo selection)", switches),
                           ("SPRITESETS", sprites),
                           ("VEHICLE", items)):
        text = section(title, emitter)
        if text:
            parts.append(text)
    return "\n\n".join(parts) + "\n"


def render_vehiclefiles(vehicles: Sequence[Vehicle], out_dir: str) -> str:
    """The include list that pulls every generated vehicle file into the GRF.

    This is the file the hand written index includes, so the index itself never
    has to change when a vehicle is added or removed.
    """
    lines = [GENERATED_HEADER.format(
        title="src/vehiclefiles.pnml -- include list of the generated vehicle files").rstrip("\n"),
        "",
        "// One file per vehicle, grouped by kind.  The order of the includes is",
        "// the order the vehicles appear in the purchase menu.",
        ""]
    current = None
    for vehicle in vehicles:
        label = CATEGORY_LABEL.get(vehicle.category, vehicle.category)
        if label != current:
            if current is not None:
                lines.append("")
            current = label
            lines.append("// %s" % label)
        # the path is relative to the index file, which includes this file as
        # "src/vehiclefiles.pnml"; a nested include therefore must NOT repeat
        # the "src/" prefix or gcc would look for src/src/...
        relative = os.path.join(vehicle.folder, "%s.pnml" % vehicle.id)
        lines.append('#include "%s"' % relative.replace(os.sep, "/"))
    lines.append("")
    return "\n".join(lines)


def render_vehicleid(vehicles: Sequence[Vehicle], ids: Dict[str, int]) -> str:
    by_category: Dict[str, List[Vehicle]] = {}
    for vehicle in vehicles:
        by_category.setdefault(vehicle.category, []).append(vehicle)

    lines = [GENERATED_HEADER.format(
        title="src/vehicleid.pnml -- generated vehicle ID table").rstrip("\n"), ""]
    lines.append("//Vehicle IDs are assigned automatically inside the band of each")
    lines.append("//category.  Add new vehicles to data/*.csv, not to this file.")
    lines.append("")

    for category in BAND_ORDER:
        band = BANDS[category]
        start, end = band.split(":")
        label, hex_range = BAND_COMMENT[category]
        lines.append("//%s, available ID range: %s-%s (hex %s)"
                     % (label, start, end, hex_range))
        lines.append("#define id_range_%s 0x%04X..0x%04X"
                     % (category, int(start), int(end)))
        for vehicle in by_category.get(category, []):
            lines.append("item (FEAT_TRAINS, %s, %d) {}" % (vehicle.id, ids[vehicle.id]))
        lines.append("")
    return "\n".join(lines)


def render_vehiclesort(vehicles: Sequence[Vehicle], ids: Dict[str, int]) -> str:
    lines = [GENERATED_HEADER.format(
        title="src/vehiclesort.pnml -- generated purchase menu order").rstrip("\n"), ""]
    lines.append("//Order of the tables in data/: locomotives, coaches, wagons, unit wagons.")
    lines.append("//Within a table the order is the row order of the CSV file.")
    lines.append("")
    lines.append("sort (FEAT_TRAINS, [")
    last_category = None
    for vehicle in vehicles:
        if vehicle.category != last_category:
            last_category = vehicle.category
            if vehicle is not vehicles[0]:
                lines.append("")
            lines.append("    // %s" % CATEGORY_LABEL.get(vehicle.category, vehicle.category))
        lines.append("    %s," % vehicle.id)
    lines.append("]);")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# language string table
# --------------------------------------------------------------------------

# Strings used by src/header.pnml and by the generated vehicle code for which
# the value cannot be derived from the data tables.
STATIC_STRINGS: List[Tuple[str, str, str]] = [
    ("STR_GRF_NAME", "China Set: Export Rail Vehicles Add-on",
     "中国包：出口铁路载具附加包"),
    ("STR_GRF_DESC", "The export rail vehicles sector of the China Set of OpenTTD.",
     "OpenTTD中国包的出口铁路载具附加包。"),
    ("STR_GRF_URL", "https://www.tt-forums.net/viewtopic.php?t=91092", ""),
    ("STR_GRF_DESC_EXTRA",
     "Locomotives, multiple units, coaches and wagons built for export. "
     "Includes broad gauge, metre gauge and gauge changing stock. "
     "More contents in the future.",
     "为出口而建造的机车、动车组、客车和货车，包含宽轨、米轨和可变轨距车辆。"
     "未来会有更多内容。"),
    ("STR_GRF_DESC_README", "See readme for details.", "更多信息请查看Readme。"),
    ("STR_GRF_DESC_4", "{RED}The people's railway for the people", "{RED}人民铁路为人民"),
    ("STR_PARAM_LOADING_SPEED", "Loading speed", "装载速度"),
    ("STR_PARAM_LOADING_SPEED_DESC",
     "Adjust vehicle loading speed. Default is 100%.", "调整车辆装载速度。默认为100%。"),
    ("STR_PARAM_PURCHASE_COST", "Purchase costs", "购买费用"),
    ("STR_PARAM_PURCHASE_COST_DESC",
     "Adjust vehicle purchase costs. Default is 25%.", "调整车辆购买费用。默认为25%。"),
    ("STR_PARAM_RUNNING_COST", "Running costs", "运营费用"),
    ("STR_PARAM_RUNNING_COST_DESC",
     "Adjust vehicle running costs. Default is 25%.", "调整车辆运营费用。默认为25%。"),
    ("STR_PARAM_DIVIDE_16", "6.25%", ""),
    ("STR_PARAM_DIVIDE_8", "12.50%", ""),
    ("STR_PARAM_DIVIDE_4", "25%", ""),
    ("STR_PARAM_DIVIDE_2", "50%", ""),
    ("STR_PARAM_NORMAL", "100%", ""),
    ("STR_PARAM_TIMES_2", "200%", ""),
    ("STR_PARAM_TIMES_4", "400%", ""),
    ("STR_PARAM_TIMES_8", "800%", ""),
    ("STR_PARAM_TIMES_16", "1600%", ""),
    ("STR_PARAM_CARGO_DECAY", "Cargo age period", "货物贬值周期"),
    ("STR_PARAM_CARGO_DECAY_DESC",
     "Adjust cargo age period (the ability of keeping freshness of cargo and "
     "comfort for passengers) of coaches and wagons. Default is 100%.",
     "调整车厢的货物贬值周期（旅客舒适度/货物保鲜度）。默认为100%。"),
    ("STR_PARAM_WAGON_CARGO_DECAY", "Cargo age period of mail and freight wagons",
     "单独设置货车的货物贬值周期"),
    ("STR_PARAM_WAGON_CARGO_DECAY_DESC",
     "Set cargo age period of mail and freight wagons individually, multiplied "
     "by \"Cargo age period\" again. It makes very-long-distance transport of "
     "freight possible.",
     "单独设置邮件车和货车的货物贬值周期，在选项\"货物贬值周期\"上叠加计算。"),
    ("STR_PARAM_EXPORT_LIVERY",
     "Export stock built after a paint scheme change uses the new scheme",
     "涂装换代后建造的出口车辆默认使用新涂装"),
    ("STR_PARAM_EXPORT_LIVERY_DESC",
     "Choose whether a vehicle whose livery was changed mid-life is delivered "
     "in the new paint scheme automatically. Turning this off always uses the "
     "original factory scheme.",
     "决定涂装换代期间建造的车辆是否自动使用新涂装。关闭后一律使用原始出厂涂装。"),
    ("STR_USED_WITH_DYNAMIC_ENGINES",
     "This GRF needs dynamic_engines to be turned on. Open console, and type "
     "\"set dynamic_engines 1\".",
     "请切换至控制台模式，键入 \"set dynamic_engines 1\"， 否则您无法游玩本附加包。"),
    # livery labels.  The table writes them as LV_<NAME>, this list holds the
    # NML constants they map to, so every paint scheme label sits together in
    # docs/str.csv instead of being mixed into the interface strings.
    ("STR_LV_BUILD_YEAR", "Livery of the build year", "建造年份对应涂装"),
    ("STR_LV_ORIGINAL", "Original", "原始涂装"),
    ("STR_LV_EXPORT_BLUE", "Export blue", "出口蓝"),
    ("STR_LV_EXPORT_GREEN", "Export olive green", "出口橄榄绿"),
    ("STR_LV_EXPORT_GRAY", "Light grey", "浅灰"),
    ("STR_LV_DPRK", "DPRK scheme", "朝鲜涂装"),
    ("STR_UKRAINE_LIVERY", "Ukraine scheme", "乌克兰涂装"),
    ("STR_LIVERY_EXPORT", "Export livery: {STRING}", "出口涂装：{STRING}"),
    ("STR_EXPORT_SERIES", "Export series", "出口系列"),
    ("STR_RESTAURANT_CAR", "Restaurant car", "餐车"),
    ("STR_AC_GENERATOR_CAR", "Air conditioner generator car", "空调发电车"),
    ("STR_LUGGAGE_VAN", "Luggage van", "行李车"),
    ("STR_POSTAL_CAR", "Postal car", "邮政车"),
    ("STR_MU_WAGON", "Multiple unit trailer", "动车组拖车"),
    ("STR_ELECTRICITY_SUPPLY_YES", "Head end power: yes", "可供电：是"),
    ("STR_ELECTRICITY_SUPPLY_NO", "Head end power: no", "可供电：否"),
    ("STR_COMFORT_LOW", "Comfort: low ({STRING} days)", "舒适度：低（{STRING} 天）"),
    ("STR_COMFORT_MEDIUM", "Comfort: medium ({STRING} days)", "舒适度：中（{STRING} 天）"),
    ("STR_COMFORT_HIGH", "Comfort: high ({STRING} days)", "舒适度：高（{STRING} 天）"),
    ("STR_FRESHNESS_MEDIUM", "Freshness: medium ({STRING} days)", "保鲜度：中（{STRING} 天）"),
    ("STR_FRESHNESS_HIGH", "Freshness: high ({STRING} days)", "保鲜度：高（{STRING} 天）"),
    ("STR_RELDEC_LOW", "Reliability decay: low ({STRING})", "可靠性衰减：低（{STRING}）"),
    ("STR_RELDEC_HIGH", "Reliability decay: high ({STRING})", "可靠性衰减：高（{STRING}）"),
    ("STR_TOO_SHORT", "This train is too short", "列车过短"),
    ("STR_MUST_BE_4_TO_24_CARS", "This train must have 4 to 24 cars", "列车必须为4至24节"),
    ("STR_MUST_BE_MULTIPLE_OF_3",
     "This train must be a whole number of three car units",
     "列车必须由整数个三节单元组成"),
    # the GRF description is assembled from four nested strings
    ("STR_DESC_4", "{STRING}{}{STRING}{}{STRING}{}{STRING}", ""),
    # purchase window description.  NML strings only accept *string* arguments
    # (integer parameters are not supported in this position), so the three
    # slots hold the full name, the export livery and a category label.
    # Numeric data such as capacity, speed and costs is shown by the depot
    # window itself.
    ("STR_DESC_EXPORT", "{STRING}{}{STRING}{}{STRING}", ""),
    ("STR_CAT_LOCO", "Locomotive", "机车"),
    ("STR_CAT_COACH", "Passenger coach", "客车"),
    ("STR_CAT_WAGON", "Freight wagon", "货车"),
    ("STR_CAT_MU", "Multiple unit", "动车组"),
    ("STR_CAT_MU_TRAILER", "Multiple unit trailer", "动车组拖车"),
]

# category -> the descriptive label appended to the purchase window text
CATEGORY_DESCRIPTION = {
    "coach": "STR_CAT_COACH",
    "wagon": "STR_CAT_WAGON",
    "unit_wagon": "STR_CAT_MU_TRAILER",
    "dmu": "STR_CAT_MU",
    "emu": "STR_CAT_MU",
    "1500_emu": "STR_CAT_MU",
    "750_emu": "STR_CAT_MU",
    "third_emu": "STR_CAT_MU",
    "multi_mu": "STR_CAT_MU",
    "mono_mu": "STR_CAT_MU",
    "mglv_mu": "STR_CAT_MU",
    "cargo_dmu": "STR_CAT_MU",
    "cargo_emu": "STR_CAT_MU",
    "multi_cargo_mu": "STR_CAT_MU",
}


def build_additional_text(vehicle: "Vehicle") -> str:
    """Assemble the *arguments* of the purchase window string() call.

    Returns e.g.
        STR_DESC_EXPORT, string(STR_FULL_NAME_SS8EX),
        string(STR_LIVERY_EXPORT, string(STR_LV_EXPORT_BLUE)), string(STR_CAT_LOCO)

    render_item() adds the surrounding string(...), so every producer of this
    field -- the tables and this function alike -- yields bare arguments.
    Only string valued arguments are used: NML rejects integer parameters and
    empty quoted literals in this position.
    """
    parts = ["STR_DESC_EXPORT", "string(%s)" % vehicle.full_name_constant]

    schemes = [livery.string for livery in vehicle.liveries if livery.string]
    if len(schemes) > 1:
        schemes = schemes[1:]          # index 0 is the automatic choice
    if not schemes:
        schemes = ["STR_LV_ORIGINAL"]
    parts.append("string(STR_LIVERY_EXPORT, %s)"
                 % ", ".join("string(%s)" % s for s in schemes))
    parts.append("string(%s)" % CATEGORY_DESCRIPTION.get(vehicle.category, "STR_CAT_LOCO"))
    return ", ".join(parts)


def collect_strings(vehicles: Sequence[Vehicle]) -> List[Tuple[str, str, str]]:
    """Return (constant, english, chinese) for every string the GRF needs."""
    result: List[Tuple[str, str, str]] = list(STATIC_STRINGS)
    known = {row[0] for row in result}

    def add(constant: str, english: str, chinese: str = "") -> None:
        if constant in known:
            return
        known.add(constant)
        result.append((constant, english, chinese))

    for vehicle in vehicles:
        plain_name = vehicle.display_name
        add(vehicle.name_constant, plain_name, "")
        if vehicle.additional_text and "STR_FULL_NAME_" + vehicle.id.upper() in vehicle.additional_text:
            add(vehicle.full_name_constant, plain_name, "")
        for livery in vehicle.liveries:
            if livery.string and livery.string.startswith("STR_"):
                # a livery label is written by hand in docs/str.csv: the ones
                # this generator knows are already in STATIC_STRINGS, and a new
                # LV_<NAME> is added to the table by the workbench, where its
                # text is editable
                known.add(livery.string)
    return result


# docs/str.csv is a three column CSV whose second column is headed ENGLISHand
# whose first data column holds STR_ constants.  The header line has to be
# recognised wherever the file is read: ``STRING`` happens to match
# ``STR_[A-Z0-9_]+``, so a header treated as data becomes a phantom string that
# ``--check`` reports as unused and ``--strings`` then keeps for ever.
LANG_HEADER = ("STRING", "ENGLISH")


def is_lang_header(row: Sequence[str]) -> bool:
    """Is this CSV record the language table's header line?"""
    if len(row) < 2:
        return False
    return (row[0].strip().lstrip("\ufeff") == LANG_HEADER[0]
            and row[1].strip() == LANG_HEADER[1])


def render_strings(vehicles: Sequence[Vehicle], path: str) -> None:
    """Write docs/str.csv, preserving translations from an existing file.

    Two kinds of row survive a re-run: the third column of a row this function
    generates, and any whole row the generator does not know about.  The second
    kind is what makes hand written labels usable -- a livery points at a
    string constant, so a constant that is not in ``STATIC_STRINGS`` and not
    derived from a vehicle must be addable by hand without the next
    ``make gen`` deleting it again.
    """
    translations: Dict[str, str] = {}
    extra: List[Tuple[str, str, str]] = []
    seen = set()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8-sig") as handle:
            for row in csv.reader(handle):
                if not row or not row[0].strip() or row[0].strip().startswith("#"):
                    continue
                if is_lang_header(row):
                    continue
                constant = row[0].strip().lstrip("\ufeff")
                english = row[1].strip() if len(row) > 1 else ""
                chinese = row[2].strip() if len(row) > 2 else ""
                if chinese:
                    translations[constant] = chinese
                if constant not in seen:
                    seen.add(constant)
                    extra.append((constant, english, chinese))

    rows = collect_strings(vehicles)
    generated = {constant for constant, _, _ in rows}
    # a hand written row keeps the text it was written with; anything that is
    # not an STR_ constant (including the header line this file writes itself)
    # is not a string and must never be carried over
    extra = [(constant, english, chinese) for constant, english, chinese in extra
             if constant not in generated and (english or chinese)
             and re.fullmatch(r"STR_[A-Z0-9_]+", constant)]

    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("# STRING,ENGLISH,SIMPLIFIED CHINESE\n")
        handle.write("# Generated by genpnml.py --strings; the third column of a\n")
        handle.write("# generated row and every hand written row are preserved.\n")
        writer = csv.writer(handle, lineterminator="\n")
        for constant, english, chinese in rows:
            writer.writerow([constant, english, translations.get(constant, chinese)])
        for constant, english, chinese in extra:
            writer.writerow([constant, english, chinese])
    print("genpnml: wrote %d strings to %s (%d generated, %d hand written)"
          % (len(rows) + len(extra), path, len(rows), len(extra)))


def load_string_table(path: str) -> Dict[str, str]:
    """Return {constant: english} of an existing language table."""
    table: Dict[str, str] = {}
    if not os.path.exists(path):
        return table
    with open(path, "r", encoding="utf-8-sig") as handle:
        for row in csv.reader(handle):
            if not row or not row[0].strip() or row[0].lstrip().startswith("#"):
                continue
            if is_lang_header(row):
                continue
            constant = row[0].strip().lstrip("\ufeff")
            if re.fullmatch(r"STR_[A-Z0-9_]+", constant):
                table[constant] = row[1].strip() if len(row) > 1 else ""
    return table


def collect_referenced_strings(vehicles: Sequence[Vehicle]) -> set:
    """Every STR_ constant the generated code and the hand written files use."""
    referenced = set()

    # src/header.pnml and the shared library files
    src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
    if os.path.isdir(src_dir):
        for name in sorted(os.listdir(src_dir)):
            if not name.endswith(".pnml"):
                continue
            with open(os.path.join(src_dir, name), "r", encoding="utf-8") as handle:
                text = handle.read()
            referenced.update(re.findall(r"\b(STR_[A-Z0-9_]+)\b", text))

    # everything the generator emits
    for vehicle in vehicles:
        referenced.add(vehicle.name_constant)
        if "STR_FULL_NAME_" + vehicle.id.upper() in (vehicle.additional_text or ""):
            referenced.add(vehicle.full_name_constant)
        for livery in vehicle.liveries:
            if livery.string:
                referenced.add(livery.string)
        for constant in re.findall(r"\b(STR_[A-Z0-9_]+)\b",
                                   vehicle.additional_text or ""):
            referenced.add(constant)
    for constant, _, _ in STATIC_STRINGS:
        referenced.add(constant)
    return referenced


def check_strings(vehicles: Sequence[Vehicle], path: str) -> int:
    """Report strings the code needs but the table lacks, and vice versa."""
    defined = load_string_table(path)
    referenced = collect_referenced_strings(vehicles)

    missing = sorted(referenced - set(defined))
    unused = sorted(set(defined) - referenced)

    for constant in missing:
        print("genpnml: MISSING  %s is used but not defined in %s"
              % (constant, path), file=sys.stderr)
    for constant in unused:
        print("genpnml: unused   %s is defined but never used" % constant)

    print("genpnml --check: %d referenced, %d defined, %d missing, %d unused"
          % (len(referenced), len(defined), len(missing), len(unused)))
    return 1 if missing else 0


NML_STRING_RE = re.compile(r'^(?:STR_[A-Z0-9_]+|"[^"]*"|\{[^}]*\})$')


def validate_vehicles(vehicles: Sequence[Vehicle]):
    """Cheap sanity checks that keep malformed tables out of the compiler.

    A name that is neither an STR_ constant nor a quoted literal would be
    pasted into string(...) verbatim, which produces a confusing NML syntax
    error much later; catching it here names the offending row instead.

    Returns ``(problems, warnings)``.  A problem stops the build; a warning is
    printed and the build continues, because it describes something legal that
    is probably not what was meant.
    """
    problems: List[str] = []
    warnings: List[str] = []
    for vehicle in vehicles:
        raw = (vehicle.name_string or "").strip()
        if raw.startswith("STR_") or raw.startswith('"'):
            if not NML_STRING_RE.match(raw):
                problems.append(
                    "%s: name_string %r looks like an NML string but is not "
                    "a valid STR_ constant or quoted literal" % (vehicle.id, raw))
        elif not raw:
            problems.append("%s: name_string is empty" % vehicle.id)
        # a plain display name is fine, it becomes STR_NAME_<ID>
        if not re.fullmatch(r"[a-z][a-z0-9_]*", vehicle.id):
            problems.append(
                "%s: id must be lower case letters, digits and underscores only"
                % vehicle.id)
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_./-]*", vehicle.folder) \
                or "/../" in "/%s/" % vehicle.folder or vehicle.folder.count("/") > 3:
            problems.append(
                "%s: folder %r must be a relative path of at most four segments, "
                "each made of letters, digits, '_', '.' and '-', separated by '/'"
                % (vehicle.id, vehicle.folder))
        # Multiples of three sections are the convention this set follows: a car
        # is an invisible end, a body that carries the cargo, and another
        # invisible end, so a longer unit is always short+body+short repeated.
        # It is a rule about the artwork, not about NewGRF -- position_in_
        # articulated_veh % N works for any N -- so it is stated as a warning and
        # does not block a build.
        sections = vehicle.part_count
        if sections % 3:
            warnings.append(
                "%s: parts 有 %d 段，不是 3 的倍数；本包的习惯是"
                "「隐形头 + 载货车身 + 隐形尾」，一组三节，"
                "例如 2|8|2 或 2|8|2|2|8|2" % (vehicle.id, sections))
        # graphics_parts lives in the livery table now, so a malformed cell has
        # to name the scheme it came from: the vehicle alone is not enough.  The
        # parsing itself has already happened by the time this runs, so what is
        # checked here is the shape of the tree rather than its text.
        for livery in vehicle.liveries:
            for position, roots in enumerate(livery.graphics_parts):
                for root in roots:
                    for node in root.walk():
                        if node.basename and not BASENAME_RE.fullmatch(node.basename):
                            problems.append(
                                "%s 涂装 #%d（%s）第 %d 段：贴图基名 %r 只能用小写"
                                "字母、数字和下划线"
                                % (vehicle.id, livery.index,
                                   livery.suffix or _livery_basename(vehicle, livery),
                                   position + 1, node.basename))
    return problems, warnings


def remove_generated(out_dir: str) -> int:
    """Delete everything the previous run wrote, using its manifest."""
    manifest_path = os.path.join(out_dir, MANIFEST_NAME)
    previous = _read_manifest(manifest_path)
    removed = 0
    for relative in previous:
        path = os.path.join(out_dir, relative)
        if os.path.isfile(path):
            os.remove(path)
            removed += 1
        directory = os.path.dirname(path)
        while directory and os.path.abspath(directory) != os.path.abspath(out_dir):
            if os.path.isdir(directory) and not os.listdir(directory):
                os.rmdir(directory)
                directory = os.path.dirname(directory)
            else:
                break
    if os.path.exists(manifest_path):
        os.remove(manifest_path)
    return removed


def render_include(index_file: str, vehicles: Sequence[Vehicle]) -> None:
    """Refresh the generated include block inside the hand written index file.

    Only the region between the two marker comments is replaced, so the hand
    written #include lines above and below it survive a regeneration.  The
    vehicle files themselves are pulled in through src/vehiclefiles.pnml, which
    is why the index does not change when a vehicle is added or removed.
    """
    begin = "// >>> GENERATED VEHICLES (do not edit, run `make gen`) >>>"
    end = "// <<< GENERATED VEHICLES <<<"
    lines = [begin,
             "// One generated file per vehicle; src/vehiclefiles.pnml lists them all",
             "// in purchase menu order.",
             '#include "src/vehiclefiles.pnml"',
             "",
             "// Purchase menu order.",
             '#include "src/vehiclesort.pnml"',
             end]
    block = "\n".join(lines)

    if not os.path.exists(index_file):
        return
    with open(index_file, "r", encoding="utf-8") as handle:
        text = handle.read()
    if begin in text and end in text:
        head = text.split(begin, 1)[0]
        tail = text.split(end, 1)[1]
        text = head + block + "\n" + tail.lstrip("\n")
    else:
        text = text.rstrip("\n") + "\n\n" + block + "\n"
    write_file(index_file, text)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


MANIFEST_NAME = ".genpnml-manifest"


def _read_manifest(path: str) -> List[str]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip()]


def write_generated(out_dir: str, files: Dict[str, str]) -> Tuple[int, int]:
    """Write the generated files and remove ones that are no longer produced.

    A manifest records what the previous run wrote, so deleting a row from a
    table also deletes its .pnml instead of leaving an orphan behind that the
    include list no longer mentions.
    """
    manifest_path = os.path.join(out_dir, MANIFEST_NAME)
    previous = set(_read_manifest(manifest_path))
    current = set(files)

    for relative, text in sorted(files.items()):
        write_file(os.path.join(out_dir, relative), text)

    removed = 0
    for relative in sorted(previous - current):
        path = os.path.join(out_dir, relative)
        if os.path.isfile(path):
            os.remove(path)
            removed += 1
    # drop directories that just became empty
    for relative in sorted(previous - current):
        directory = os.path.dirname(os.path.join(out_dir, relative))
        while directory and os.path.abspath(directory) != os.path.abspath(out_dir):
            if os.path.isdir(directory) and not os.listdir(directory):
                os.rmdir(directory)
                directory = os.path.dirname(directory)
            else:
                break

    with open(manifest_path, "w", encoding="utf-8", newline="\n") as handle:
        for relative in sorted(current):
            handle.write(relative + "\n")
    return len(files), removed


def generate(data_dir: str, out_dir: str, index_file: str,
             vox_root: str, gfx_root: str, sprite_manifest: str = "") -> int:
    vehicles = load_vehicles(data_dir)

    if not vehicles:
        # An empty project is a valid state: the tables are just headers and
        # the generator writes the index files with nothing in them.  This is
        # the starting point for a fresh module, and it still compiles.
        print("genpnml: the tables in %s contain no vehicles" % data_dir)
        print("genpnml: writing the empty index files and leaving the gfx "
              "collection untouched")

    if sprite_manifest:
        # The local web workbench needs to know which sprite basenames every
        # row requires; collect_sprite_basenames() is the only authority on
        # that, so publish its answer instead of duplicating the rules.
        wanted = {vehicle.id: sorted(collect_sprite_basenames(vehicle))
                  for vehicle in vehicles}
        ensure_dir(os.path.dirname(sprite_manifest) or ".")
        with open(sprite_manifest, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(wanted, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        print("genpnml: recorded the sprite basenames of %d vehicles in %s"
              % (len(wanted), sprite_manifest))

    ids = assign_ids(vehicles)

    # one file per vehicle, plus the three index files
    files: Dict[str, str] = {}
    for vehicle in vehicles:
        relative = os.path.join(vehicle.folder, "%s.pnml" % vehicle.id)
        files[relative] = render_vehicle_file(vehicle)
    files["vehiclefiles.pnml"] = render_vehiclefiles(vehicles, out_dir)
    files["vehicleid.pnml"] = render_vehicleid(vehicles, ids)
    files["vehiclesort.pnml"] = render_vehiclesort(vehicles, ids)

    written, removed = write_generated(out_dir, files)

    # gfx/empty.png must be an 8bpp indexed image carrying the OpenTTD
    # palette, otherwise nmlc refuses to load it; it is part of the repository,
    # so only create a fallback when it is missing.
    ensure_dir(gfx_root)
    fallback = os.path.join(gfx_root, "empty.png")
    if not os.path.exists(fallback):
        write_png(fallback, 2, 2, (0, 0, 0, 0))
    fallback32 = os.path.join(gfx_root, "empty_32bpp.png")
    if not os.path.exists(fallback32):
        write_png(fallback32, 2, 2, (0, 0, 0, 0))

    # A multi level folder may not exist yet, and gorender/renderobject reads the
    # manifest and the palette from the folder each .vox lives in, so prepare
    # them.  The .vox files themselves are the author's artwork: the generator
    # does not create models, because a placeholder would be a file you have to
    # notice and delete before your own model could be trusted.
    prepared = 0
    if vehicles:
        source_palette = os.path.join(gfx_root, "ttd_palette.json")
        for folder in sorted({vehicle.folder for vehicle in vehicles}):
            directory = os.path.join(vox_root, folder)
            ensure_dir(directory)
            write_manifest(os.path.join(directory, "manifest.json"))
            if os.path.exists(source_palette):
                # copied as text with LF endings, so that a Windows checkout's
                # CRLF does not show the file as modified for ever
                with open(source_palette, "r", encoding="utf-8") as handle:
                    palette_text = handle.read()
                with open(os.path.join(directory, "ttd_palette.json"), "w",
                          encoding="utf-8", newline="\n") as handle:
                    handle.write(palette_text)
            prepared += 1

    render_include(index_file, vehicles)

    print("genpnml: %d vehicles -> %d files (%d removed), %d gfx folder(s) prepared"
          % (len(vehicles), written, removed, prepared))
    missing = []
    for vehicle in vehicles:
        directory = os.path.join(vox_root, vehicle.folder)
        for basename in collect_sprite_basenames(vehicle):
            if not os.path.exists(os.path.join(directory, "%s.vox" % basename)):
                missing.append("gfx/%s/%s.vox" % (vehicle.folder, basename))
    if missing:
        print("genpnml: %d model(s) still to be drawn:" % len(missing))
        for path in missing:
            print("  %s" % path)
    for category in BAND_ORDER:
        group = [v for v in vehicles if v.category == category]
        if group:
            print("  %-16s %3d  ids %d..%d"
                  % (category, len(group), ids[group[0].id], ids[group[-1].id]))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate PNML vehicle code for China Set: Export Rail Vehicles Add-on")
    parser.add_argument("--data", default="data", help="directory with the CSV tables")
    parser.add_argument("--out", default="src", help="directory for generated PNML")
    parser.add_argument("--index", default="chinasettrainsexport.pnml",
                        help="index PNML file whose generated include block is refreshed")
    parser.add_argument("--vox-root", default="gfx", help="root for the .vox models")
    parser.add_argument("--gfx", default="gfx", help="root for shared gfx files")
    parser.add_argument("--clean", action="store_true",
                        help="only remove the generated files")
    parser.add_argument("--strings", action="store_true",
                        help="refresh docs/str.csv from the data tables and exit")
    parser.add_argument("--strings-file", default="docs/str.csv",
                        help="path of the language table")
    parser.add_argument("--check", action="store_true",
                        help="verify that every string the code uses is defined in "
                             "the language table, and exit")
    parser.add_argument("--sprite-manifest", default="",
                        help="also record which sprite basename each vehicle needs "
                             "into this JSON file (used by the web workbench)")
    args = parser.parse_args(argv)

    if args.strings:
        render_strings(load_vehicles(args.data), args.strings_file)
        return 0

    if args.check:
        return check_strings(load_vehicles(args.data), args.strings_file)

    if args.clean:
        removed = remove_generated(args.out)
        print("genpnml: removed %d generated files" % removed)
        return 0

    return generate(args.data, args.out, args.index, args.vox_root,
                    args.gfx, args.sprite_manifest)


if __name__ == "__main__":
    sys.exit(main())
