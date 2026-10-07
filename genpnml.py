#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
genpnml.py -- China Set: Export Rail Vehicles Add-on, PNML generator
====================================================================

Reads the declarative tables in ``data/`` and writes

  * ``src/usercode.pnml``      all generated switches / spritesets
  * ``src/vehicleid.pnml``     the ``item (FEAT_TRAINS, name, id) {}`` table
  * ``src/vehiclesort.pnml``   the ``sort (FEAT_TRAINS, [...])`` block
  * ``gfx/<folder>/<name>.vox`` placeholder voxel models (optional, ``--vox``)

for every locomotive, coach and wagon described in the tables.

The output is plain NML/PNML following exactly the layout used by
China Set: Trains and China Set: Narrow Gauge Add-on, so the generated files
can be compiled side by side with hand written ones.

Usage
-----
    python3 genpnml.py --data data --out src --vox
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
import os
import shutil
import struct
import sys
import zlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

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
    model: str
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
    vox_part: str = "body"
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
    def is_articulated(self) -> bool:
        return len(self.parts) > 1

    @property
    def body_part(self) -> int:
        """Index of the part that carries the real body sprite."""
        return self.power_section

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
    def length_switch(self) -> str:
        if not self.is_articulated:
            return ""
        if len(self.parts) == 3 and self.parts[0] == self.parts[2]:
            return "switch_length_2_%d_2" % self.parts[1]
        if len(self.parts) == 3:
            return "switch_length_2_%d_%d" % (self.parts[1], self.parts[2])
        return ""

    @property
    def part_count(self) -> int:
        return len(self.parts)


# --------------------------------------------------------------------------
# CSV loading
# --------------------------------------------------------------------------


def _load_liveries(rows: List[Dict[str, str]]) -> Dict[str, List[Livery]]:
    table: Dict[str, List[Livery]] = {}
    counters: Dict[str, int] = {}
    for row in rows:
        vehicle = row["id"]
        index = counters.get(vehicle, 0)
        counters[vehicle] = index + 1
        livery = Livery(
            index=index,
            suffix=row.get("sprite_suffix", ""),
            string=row.get("string", ""),
            from_year=_int(row.get("from_year", ""), 0),
            to_year=_int(row.get("to_year", ""), 9999),
            purchase_suffix=row.get("purchase_suffix", ""),
            templates=_split_list(row.get("templates", "")),
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

    model = (row.get("model", "") or "").strip().lower()
    if not model:
        model = "triple" if len(parts) > 1 else "single"
    if model == "single":
        # a single section vehicle is one sprite, the length switch is omitted
        parts = [parts[0]] if parts else [4]

    vehicle = Vehicle(
        id=vehicle_id,
        name_string=row.get("name_string", "") or ("STR_NAME_" + vehicle_id.upper()),
        category=category,
        folder=row.get("folder", "") or category,
        model=model,
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
        ac_supply=_bool(row.get("ac_supply", ""), False),
        airconditioned=_bool(row.get("airconditioned", ""), False),
        restaurant=_bool(row.get("restaurant", ""), False),
        mu=_bool(row.get("mu", ""), False),
        visual_effect=(row.get("visual_effect", "") or "").strip(),
        train_flags=(row.get("train_flags", "") or "").strip(),
        name_callback=_bool(row.get("name_callback", ""), category not in ("coach", "wagon", "unit_wagon")),
        additional_text=(row.get("additional_text", "") or "").strip(),
        source=source,
        vox_part=(row.get("vox_part", "") or "body").strip(),
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
    liveries = _load_liveries(_read_csv(os.path.join(data_dir, "liveries.csv")))
    cargo_variants = _load_cargo_variants(_read_csv(os.path.join(data_dir, "cargo_variants.csv")))

    tables = [
        ("locomotives.csv", None),
        ("coaches.csv", "coach"),
        ("wagons.csv", "wagon"),
        ("unit_wagons.csv", "unit_wagon"),
    ]

    vehicles: List[Vehicle] = []
    seen: Dict[str, str] = {}
    for filename, forced_category in tables:
        path = os.path.join(data_dir, filename)
        for row in _read_csv(path):
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
    return vehicles


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


def _livery_basename(vehicle: Vehicle, livery: Livery) -> str:
    """Sprite sheet basename of a livery: <id> or <id>-<livery suffix>."""
    if livery.suffix:
        return "%s-%s" % (vehicle.id, livery.suffix)
    return vehicle.id


def _livery_spriteset_name(vehicle: Vehicle, livery: Livery) -> str:
    if livery.suffix:
        return "spriteset_%s_%s" % (vehicle.id, livery.suffix)
    return "spriteset_%s" % vehicle.id


def _livery_purchase_name(vehicle: Vehicle, livery: Livery) -> str:
    suffix = livery.purchase_suffix or livery.suffix
    if suffix:
        return "spriteset_%s_purchase_%s" % (vehicle.id, suffix)
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
        parts.append(variant.suffix.replace("-", "_"))
    if livery.suffix:
        parts.append(livery.suffix)
    return "_".join(parts)


def _cargo_switch_prefix(vehicle: Vehicle, livery: Livery) -> str:
    """Prefix for the cargo switches of one livery (unique per livery)."""
    if livery.suffix:
        return "switch_%s_%s" % (vehicle.id, livery.suffix)
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
    # ride in a container), so the same spriteset must only be defined once.
    seen_spritesets: set = set()

    def define_spriteset(name: str, basename: str, template: str) -> None:
        if name in seen_spritesets:
            return
        seen_spritesets.add(name)
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

    # ---- capacity / power / weight per part ---------------------------
    capacity_switch = _emit_capacity_switch(switches, vehicle)
    power_switch = _emit_part_switch(switches, vehicle, "power", vehicle.power)
    weight_switch = _emit_part_switch(switches, vehicle, "weight", vehicle.weight)

    # ---- livery graphics chain ---------------------------------------
    if vehicle.cargo_variants and cargo_root:
        livery_cases = [(str(livery.index), cargo_root) for livery in vehicle.liveries]
    else:
        livery_cases = [(str(livery.index), _livery_spriteset_name(vehicle, livery))
                        for livery in vehicle.liveries]
    livery_root = _emit_livery_switch(switches, vehicle, livery_cases, cargo_root)

    # ---- graphics dispatch by articulated part ------------------------
    if vehicle.is_articulated:
        graphics_switch = "switch_%s_graphics" % vid
        switches.switch(
            graphics_switch,
            f"position_in_articulated_veh % {vehicle.part_count}",
            [(str(vehicle.power_section), livery_root)],
            "empty_sprites;",
        )
        default_graphics = graphics_switch
    else:
        default_graphics = livery_root

    # ---- item ---------------------------------------------------------
    items.add(render_item(vehicle, default_graphics, capacity_switch, power_switch,
                          weight_switch, livery_root))


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
    if not vehicle.is_articulated:
        return None
    switch = "switch_%s_capacity" % vehicle.id
    if vehicle.capacity_by_cargo:
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


def _emit_part_switch(emitter: Emitter, vehicle: Vehicle, kind: str,
                      value: float) -> Optional[str]:
    """Emit a switch that puts the whole value on the powered part only."""
    if not vehicle.is_articulated:
        return None
    if kind == "power" and not value:
        return None
    if kind == "weight":
        # The weight is shared by all sections.  NML wants a constant in the
        # default position of a switch, so the per-section weight is computed
        # here and rounded to a whole tonne.
        total = int(round(value))
        parts = max(1, vehicle.part_count)
        per_part = max(1, total // parts)
        switch = "switch_%s_weight" % vehicle.id
        emitter.switch(switch, "position_in_articulated_veh", [],
                       "return %d" % per_part)
        return switch
    switch = "switch_%s_%s" % (vehicle.id, kind)
    emitter.switch(
        switch,
        f"position_in_articulated_veh % {vehicle.part_count}",
        [(str(vehicle.power_section), "return %s" % _num(value))],
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
                capacity_switch: Optional[str], power_switch: Optional[str],
                weight_switch: Optional[str], livery_root: str) -> str:
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
    if vehicle.mu:
        add("        start_stop:                     mu4to24car;")

    # graphics
    add("")
    add("        // Graphics")
    add("        default:                        %s;" % default_graphics)
    add("        purchase:                       %s;" % _livery_purchase_name(vehicle, vehicle.default_livery))
    if vehicle.is_articulated:
        add("        articulated_part:               switch_%s_articulated_part;" % vid)
    if vehicle.can_supply_head_end_power:
        add("        visual_effect_and_powered:      switch_%s_visual;" % vid)

    # stats overrides
    add("")
    add("        // Stats")
    if vehicle.is_articulated and vehicle.length_switch:
        add("        length:                         %s;" % vehicle.length_switch)
    if capacity_switch:
        add("        cargo_capacity:                 %s;" % capacity_switch)
    if power_switch:
        add("        power:                          %s;" % power_switch)
    if weight_switch:
        add("        weight:                         %s;" % weight_switch)
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


def emit_livery_callbacks(emitter: Emitter, vehicles: Sequence[Vehicle]) -> None:
    """Emit the cargo_subtype_text switches for vehicles with several liveries."""
    for vehicle in vehicles:
        if len(vehicle.liveries) < 2:
            continue
        cases: List[Tuple[str, str]] = []
        for livery in vehicle.liveries:
            label = livery.string or "STR_ORIGINAL"
            if livery.is_automatic:
                label = livery.string or "STR_BUILD_YEAR"
            cases.append((str(livery.index), "return string(%s)" % label))
        emitter.switch("switch_%s_cargo_subtype" % vehicle.id, "cargo_subtype", cases,
                       "return CB_RESULT_NO_TEXT")


def emit_articulated_callbacks(emitter: Emitter, vehicles: Sequence[Vehicle]) -> None:
    """Emit articulated_part and, for locomotives, visual_effect_and_powered."""
    for vehicle in vehicles:
        vid = vehicle.id
        if vehicle.is_articulated:
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


# --------------------------------------------------------------------------
# placeholder voxel models
# --------------------------------------------------------------------------

VOX_PALETTE: Dict[str, int] = {
    "body": 1,     # dark blue   - export livery body
    "coach": 2,    # green       - passenger stock
    "wagon": 3,    # brown       - freight stock
    "loco": 4,     # blue        - locomotive
    "gray": 5,
}


def _vox_palette_cell(index: int) -> Tuple[int, int, int, int]:
    """Return a MagicaVoxel palette entry.  index is 0..255."""
    presets = {
        0: (0x00, 0x00, 0x00, 0xFF),   # unused / empty
        1: (0x22, 0x44, 0x88, 0xFF),   # export blue
        2: (0x1F, 0x6B, 0x3A, 0xFF),   # coach green
        3: (0x7A, 0x52, 0x2C, 0xFF),   # wagon brown
        4: (0x1B, 0x4F, 0x9C, 0xFF),   # locomotive blue
        5: (0x9A, 0x9A, 0x9A, 0xFF),   # light grey
        6: (0x2B, 0x2B, 0x2B, 0xFF),   # underframe, bogies
        7: (0xE0, 0xE0, 0xE0, 0xFF),   # roof
        8: (0xC0, 0x30, 0x30, 0xFF),   # DPRK scheme
        9: (0x2E, 0x6F, 0xB8, 0xFF),   # Ukraine scheme
        10: (0x1A, 0x1A, 0x1A, 0xFF),  # coal loaded
        11: (0xB0, 0x60, 0x30, 0xFF),  # container
        12: (0x55, 0x6B, 0x4A, 0xFF),  # tarpaulin
        13: (0x6E, 0x7B, 0x8A, 0xFF),  # steel
        14: (0x4A, 0x5A, 0x6A, 0xFF),  # liquid, barrel
        15: (0x8A, 0x7A, 0x5A, 0xFF),  # general goods
        16: (0xD8, 0x40, 0x40, 0xFF),  # vehicles
        17: (0x40, 0x90, 0xD0, 0xFF),  # engineering supplies
        18: (0x2A, 0x6A, 0x50, 0xFF),  # oil
        19: (0xC8, 0xA0, 0x20, 0xFF),  # hazardous
        20: (0xE8, 0xE8, 0xC8, 0xFF),  # mail
    }
    if index in presets:
        return presets[index]
    return (0x60, 0x60, 0x60, 0xFF)


def write_vox(path: str, size: Tuple[int, int, int],
              voxels: Sequence[Tuple[int, int, int, int]]) -> None:
    """Write a minimal MagicaVoxel .vox file."""
    sx, sy, sz = size
    body = bytearray()

    def chunk(cid: bytes, content: bytes, children: bytes = b"") -> bytes:
        return (cid + struct.pack("<ii", len(content), len(children))
                + content + children)

    body += chunk(b"SIZE", struct.pack("<iii", sx, sy, sz))

    xyzi = struct.pack("<i", len(voxels))
    for x, y, z, colour in voxels:
        xyzi += struct.pack("<BBBB", x, y, z, colour)
    body += chunk(b"XYZI", xyzi)

    rgba = bytearray()
    for index in range(256):
        rgba += bytes(_vox_palette_cell(index))
    body += chunk(b"RGBA", bytes(rgba))

    data = b"VOX " + struct.pack("<i", 150) + bytes(body)
    with open(path, "wb") as handle:
        handle.write(data)


def build_placeholder_vox(vehicle: Vehicle,
                          colour: Optional[int] = None
                          ) -> Tuple[Tuple[int, int, int], List[Tuple[int, int, int, int]]]:
    """A crude but correctly shaped block model for a vehicle.

    ``colour`` overrides the body colour, which is how a livery or a loaded
    wagon gets its own model until a real one is drawn.
    """
    length = max(8, int(round(vehicle.parts[vehicle.power_section] * 4)))
    width = 8
    height = 12 if vehicle.is_locomotive else 11
    body_z0 = 3                        # above the bogies
    body_z1 = height - 1
    roof_z1 = height

    if colour is None:
        colour = {
            "coach": 2,
            "wagon": 3,
        }.get(vehicle.category, 4)

    voxels: List[Tuple[int, int, int, int]] = []

    def box(x0: int, x1: int, y0: int, y1: int, z0: int, z1: int, tone: int) -> None:
        for x in range(x0, x1):
            for y in range(y0, y1):
                for z in range(z0, z1):
                    voxels.append((x, y, z, tone))

    # main body
    box(0, length, 0, width, body_z0, body_z1, colour)
    # roof
    box(0, length, 1, width - 1, body_z1, roof_z1, 7)
    # underframe
    box(2, length - 2, 1, width - 1, 2, body_z0, 6)
    # bogies
    box(2, 6, 1, width - 1, 0, 2, 6)
    box(length - 6, length - 2, 1, width - 1, 0, 2, 6)

    if vehicle.is_locomotive:
        # a slightly narrower cab block at both ends
        box(0, 3, 1, width - 1, body_z1, height + 1, colour)
        box(length - 3, length, 1, width - 1, body_z1, height + 1, colour)

    return (length, width, height + 1), voxels


# suffix -> palette index used for the placeholder model, so that a livery or
# a loaded wagon is visually distinguishable straight away
SUFFIX_COLOUR: Dict[str, int] = {
    "exblue": 4,
    "green": 2,
    "gray": 5,
    "dprk": 8,
    "ukraine": 9,
    "coal": 10,
    "container": 11,
    "cover": 12,
    "metal": 13,
    "bucket": 14,
    "goods": 15,
    "vehi": 16,
    "ensp": 17,
    "oil": 18,
    "haz": 19,
    "mail": 20,
}


def _colour_for_suffix(suffix: str, default: int) -> int:
    for key, value in SUFFIX_COLOUR.items():
        if key in suffix:
            return value
    return default


def collect_sprite_basenames(vehicle: Vehicle) -> List[Tuple[str, int]]:
    """Every sprite sheet basename + body colour this vehicle needs.

    The generator writes one placeholder voxel model per entry so that the
    whole pipeline (render -> nmlc) succeeds out of the box.  Replacing a .vox
    with real artwork is all that is needed later.
    """
    base_colour = {"coach": 2, "wagon": 3}.get(vehicle.category, 4)
    wanted: List[Tuple[str, int]] = []

    def add(basename: str, colour: int) -> None:
        if basename and all(basename != existing for existing, _ in wanted):
            wanted.append((basename, colour))

    add(vehicle.id, base_colour)
    for livery in vehicle.liveries:
        if livery.suffix:
            add(_livery_basename(vehicle, livery),
                _colour_for_suffix(livery.suffix, base_colour))
    for variant in vehicle.cargo_variants:
        if not variant.suffix:
            continue
        add(variant.suffix, _colour_for_suffix(variant.suffix, base_colour))
        for livery in vehicle.liveries:
            if livery.suffix:
                add(_cargo_basename(variant, livery),
                    _colour_for_suffix(variant.suffix, base_colour))
    return wanted


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


def render_usercode(vehicles: Sequence[Vehicle]) -> str:
    """Assemble src/usercode.pnml.

    The file has three sections in the order the hand written sets use:
    switches, spritesets, then the item blocks.  Keeping them apart makes the
    generated code far easier to read and diff.
    """
    switches = Emitter()
    sprites = Emitter()
    items = Emitter()

    emit_livery_callbacks(switches, vehicles)
    emit_articulated_callbacks(switches, vehicles)

    current = None
    for vehicle in vehicles:
        label = CATEGORY_LABEL.get(vehicle.category, vehicle.category)
        if label != current:
            current = label
            banner = ("/* ---------------------------------------------------------------\n"
                      " *  %s\n"
                      " * --------------------------------------------------------------- */"
                      % label)
            switches.add(banner)
            sprites.add(banner)
            items.add(banner)
        emit_vehicle(sprites, switches, items, vehicle)

    def section(title: str, emitter: Emitter) -> str:
        body = "\n\n".join(block for block in emitter.blocks if block.strip())
        bar = "=" * 74
        return "/* %s\n *  %s\n * %s */\n\n%s" % (bar, title, bar, body)

    parts = [
        GENERATED_HEADER.format(title="src/usercode.pnml -- generated vehicle code"),
        section("SWITCHES  (callbacks, livery and cargo selection)", switches),
        section("SPRITESETS", sprites),
        section("VEHICLES", items),
    ]
    return "\n".join(parts) + "\n"


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
    # menu / livery helper strings
    ("STR_BUILD_YEAR", "Livery of the build year", "建造年份对应涂装"),
    ("STR_ORIGINAL", "Original", "原始涂装"),
    ("STR_EXPORT_BLUE", "Export blue", "出口蓝"),
    ("STR_EXPORT_GREEN", "Export olive green", "出口橄榄绿"),
    ("STR_EXPORT_GRAY", "Light grey", "浅灰"),
    ("STR_DPRK_LIVERY", "DPRK scheme", "朝鲜涂装"),
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
        string(STR_LIVERY_EXPORT, string(STR_EXPORT_BLUE)), string(STR_CAT_LOCO)

    render_item() adds the surrounding string(...), so every producer of this
    field -- the tables and this function alike -- yields bare arguments.
    Only string valued arguments are used: NML rejects integer parameters and
    empty quoted literals in this position.
    """
    parts = ["STR_DESC_EXPORT", "string(%s)" % vehicle.full_name_constant]

    schemes = [livery.string for livery in vehicle.liveries
               if livery.string and livery.string.startswith("STR_")]
    if len(schemes) > 1:
        schemes = schemes[1:]          # index 0 is the automatic choice
    if not schemes:
        schemes = ["STR_ORIGINAL"]
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
        plain_name = (vehicle.name_string or "").strip()
        if plain_name.startswith("STR_") or plain_name.startswith('"'):
            plain_name = vehicle.id.upper()
        add(vehicle.name_constant, plain_name, "")
        if vehicle.additional_text and "STR_FULL_NAME_" + vehicle.id.upper() in vehicle.additional_text:
            add(vehicle.full_name_constant, plain_name, "")
        for livery in vehicle.liveries:
            if livery.string and livery.string.startswith("STR_"):
                # labels such as STR_EXPORT_BLUE are already in STATIC_STRINGS
                known.add(livery.string)
    return result


def render_strings(vehicles: Sequence[Vehicle], path: str) -> None:
    """Write docs/str.csv, preserving translations from an existing file."""
    translations: Dict[str, str] = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as handle:
            for row in csv.reader(handle):
                if len(row) >= 3 and row[0].strip() and not row[0].strip().startswith("#"):
                    if row[2].strip():
                        translations[row[0].strip()] = row[2].strip()

    rows = collect_strings(vehicles)
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("# STRING,ENGLISH,SIMPLIFIED CHINESE\n")
        handle.write("# Generated by genpnml.py --strings; translations in the third\n")
        handle.write("# column are preserved when it is re-run.\n")
        writer = csv.writer(handle, lineterminator="\n")
        for constant, english, chinese in rows:
            writer.writerow([constant, english, translations.get(constant, chinese)])
    print("genpnml: wrote %d strings to %s" % (len(rows), path))


def render_include(index_file: str, vehicles: Sequence[Vehicle]) -> None:
    """Refresh the generated include block inside the hand written index file.

    Only the region between the two marker comments is replaced, so the hand
    written #include lines above and below it survive a regeneration.
    """
    begin = "// >>> GENERATED VEHICLES (do not edit, run `make gen`) >>>"
    end = "// <<< GENERATED VEHICLES <<<"
    lines = [begin,
             "// Every vehicle is emitted into a single generated file; the order",
             "// inside it follows the row order of the tables in data/.",
             '#include "src/usercode.pnml"',
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


def generate(data_dir: str, out_dir: str, index_file: str, with_vox: bool,
             vox_root: str, gfx_root: str) -> int:
    vehicles = load_vehicles(data_dir)
    if not vehicles:
        print("genpnml: no vehicles found in %s" % data_dir, file=sys.stderr)
        return 1

    ids = assign_ids(vehicles)

    write_file(os.path.join(out_dir, "usercode.pnml"), render_usercode(vehicles))
    write_file(os.path.join(out_dir, "vehicleid.pnml"), render_vehicleid(vehicles, ids))
    write_file(os.path.join(out_dir, "vehiclesort.pnml"), render_vehiclesort(vehicles, ids))

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

    # gorender/renderobject reads the manifest and the palette from the folder
    # the .vox file lives in, so every folder needs its own copy
    source_palette = os.path.join(gfx_root, "ttd_palette.json")
    vox_written = 0
    if with_vox:
        folders = sorted({vehicle.folder for vehicle in vehicles})
        for folder in folders:
            directory = os.path.join(vox_root, folder)
            ensure_dir(directory)
            write_manifest(os.path.join(directory, "manifest.json"))
            if os.path.exists(source_palette):
                shutil.copyfile(source_palette,
                                os.path.join(directory, "ttd_palette.json"))
        for vehicle in vehicles:
            directory = os.path.join(vox_root, vehicle.folder)
            for basename, colour in collect_sprite_basenames(vehicle):
                size, voxels = build_placeholder_vox(vehicle, colour)
                write_vox(os.path.join(directory, "%s.vox" % basename), size, voxels)
                vox_written += 1

    render_include(index_file, vehicles)

    print("genpnml: %d vehicles, %d voxel models" % (len(vehicles), vox_written))
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
    parser.add_argument("--vox", action="store_true",
                        help="also write placeholder voxel models")
    parser.add_argument("--vox-root", default="gfx", help="root for generated .vox models")
    parser.add_argument("--gfx", default="gfx", help="root for shared gfx files")
    parser.add_argument("--clean", action="store_true",
                        help="only remove the generated files")
    parser.add_argument("--strings", action="store_true",
                        help="refresh docs/str.csv from the data tables and exit")
    parser.add_argument("--strings-file", default="docs/str.csv",
                        help="path of the language table")
    args = parser.parse_args(argv)

    if args.strings:
        render_strings(load_vehicles(args.data), args.strings_file)
        return 0

    if args.clean:
        removed = 0
        for name in ("usercode.pnml", "vehicleid.pnml", "vehiclesort.pnml"):
            path = os.path.join(args.out, name)
            if os.path.exists(path):
                os.remove(path)
                removed += 1
        print("genpnml: removed %d generated files" % removed)
        return 0

    return generate(args.data, args.out, args.index, args.vox, args.vox_root, args.gfx)


if __name__ == "__main__":
    sys.exit(main())
