#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local web workbench for the export rail vehicle add-on.

The browser owns the editing experience; this server keeps the repository
consistent.  It deliberately uses only the Python standard library and delegates
every piece of real work to the project's existing command line tools:

    genpnml.py                     vehicle code and gfx folder preparation
    tools/vehicle_row.py           safe CSV row handling (same writer here)
    tools/verify_assets.py         sprite basename versus rendered file
    tools/clear_vehicle_data.py    empty the tables

Nothing about NML generation is reimplemented here.  The server reads the data
tables, validates a change against the same rules the generator enforces, writes
the row atomically, and runs the build commands.

Start it with::

    python3 web/workbench/server.py
    make workbench

and open http://127.0.0.1:4174/workbench/
"""

from __future__ import annotations

import csv
import importlib
import io
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
# The repository root has to be importable too: parse_graphics_cell() parses a
# rule cell with genpnml.py itself, and running this file as a script puts
# web/workbench on sys.path rather than the root.  Without this the import
# failed, every rule preview came back as "no rules", and a malformed cell was
# never reported -- a silent empty answer is exactly what hid it.
sys.path.insert(0, str(ROOT))

import schema as schema_module  # noqa: E402

WEB_ROOT = ROOT / "web"
DATA = ROOT / "data"
SRC = ROOT / "src"
GFX = ROOT / "gfx"
DOCS = ROOT / "docs"
LANG_CSV = DOCS / "str.csv"

VEHICLE_TABLES = ("locomotives.csv", "coaches.csv", "wagons.csv", "unit_wagons.csv")
AUX_TABLES = ("liveries.csv", "cargo_variants.csv")

# the generator module and the mtime it was loaded at; see generator_module()
_GENPNML = None
_GENPNML_STAMP = None
ALL_TABLES = VEHICLE_TABLES + AUX_TABLES

ID_RE = re.compile(r"^[a-z0-9_]+$")
# the folder column may be a multi level path ("diesel/df4c"), so a segment is
# checked rather than the whole cell; the depth matches what the Makefile
# collects with $(wildcard)
FOLDER_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
MAX_FOLDER_DEPTH = 4
BACKUP_SUFFIX = ".workbench.bak"
# a livery label is written LV_<NAME> and becomes STR_LV_<NAME> in the code;
# a raw STR_ constant is still accepted so older tables keep working
LIVERY_LABEL_RE = re.compile(r"^(?:LV_[A-Za-z0-9_]+|STR_[A-Za-z0-9_]+)$")
# A purchase menu group label is *not* a livery label: it goes into the NML
# verbatim as a string the player reads, so it has to be a real STR_ constant.
# LV_ values are deliberately not accepted here -- genpnml.py would refuse the
# cell, and a workbench that saves something the build rejects is worse than one
# that says no.
SERIES_STRING_RE = re.compile(r"^STR_[A-Z0-9_]+$")
# the six labels the generator shipped before the LV_ convention, which map onto
# their STR_LV_ names instead of being reported as undefined
LEGACY_LIVERY_LABELS = {
    "STR_BUILD_YEAR": "STR_LV_BUILD_YEAR",
    "STR_ORIGINAL": "STR_LV_ORIGINAL",
    "STR_EXPORT_BLUE": "STR_LV_EXPORT_BLUE",
    "STR_EXPORT_GREEN": "STR_LV_EXPORT_GREEN",
    "STR_EXPORT_GRAY": "STR_LV_EXPORT_GRAY",
    "STR_DPRK_LIVERY": "STR_LV_DPRK",
}

VEHICLE_ID_ITEM_RE = re.compile(
    r'item\s*\(\s*FEAT_TRAINS\s*,\s*([A-Za-z0-9_]+)\s*,\s*(\d+)\s*\)'
)

# the only commands the browser may start
COMMANDS = {
    "gen": {
        "label": "生成车辆代码",
        "steps": [[sys.executable, "genpnml.py", "--strings", "--strings-file", "docs/str.csv"],
                  [sys.executable, "genpnml.py", "--data", "data", "--out", "src",
                   "--sprite-manifest", "gfx/.workbench-sprites.json"]],
    },
    "build": {
        "label": "编译 GRF",
        "steps": [["make"]],
    },
    "check": {
        "label": "一致性检查",
        "steps": [
            # the front end's own wiring first: it is instant, needs no build,
            # and a data problem in the steps below would otherwise hide it
            [sys.executable, "tools/check_workbench_routes.py"],
            [sys.executable, "genpnml.py", "--data", "data", "--check",
             "--strings-file", "docs/str.csv"],
            [sys.executable, "tools/verify_assets.py"],
            [sys.executable, "tools/check_gfx_config.py"]],
    },
    "render": {
        "label": "渲染精灵图",
        "steps": [["make", "sprites"]],
    },
    "clean_gen": {
        "label": "清除生成的 PNML",
        "steps": [[sys.executable, "genpnml.py", "--data", "data", "--out", "src", "--clean"]],
    },
}


# ==========================================================================
# generic helpers
# ==========================================================================
def repo_path(value: str | Path) -> Path:
    """Resolve a repository relative path and refuse anything outside."""
    path = Path(value)
    candidate = path if path.is_absolute() else ROOT / path
    candidate = candidate.resolve()
    if candidate != ROOT and ROOT not in candidate.parents:
        raise ValueError("path escapes the repository")
    return candidate


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def safe_table(value: object) -> str:
    name = str(value or "").strip()
    if name not in ALL_TABLES:
        raise ValueError("unknown table: %r" % name)
    return name


def safe_id(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("id is required")
    if not ID_RE.match(text):
        raise ValueError("id may contain only lower case letters, digits and '_': %r" % text)
    return text


def table_path(table: str) -> Path:
    return DATA / safe_table(table)


# ==========================================================================
# CSV reading and writing -- the same conventions vehicle_row.py uses
# ==========================================================================
def read_table(table: str):
    """Return (comments, header, rows) for one data table."""
    path = table_path(table)
    if not path.is_file():
        raise FileNotFoundError("%s does not exist" % table)
    comments, lines = [], []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for line in handle:
            if line.lstrip().startswith("#"):
                comments.append(line.rstrip("\r\n"))
            elif line.strip():
                lines.append(line)
    records = list(csv.reader(lines))
    if not records:
        raise ValueError("%s: the table is empty" % table)
    header = [cell.strip() for cell in records[0]]
    rows = []
    for raw in records[1:]:
        if not raw or not raw[0].strip():
            continue
        rows.append(dict(zip(header, raw + [""] * (len(header) - len(raw)))))
    remember_table(table, path)
    return comments, header, rows


# Every table write is a read-modify-write of the whole file, so a write based
# on a stale read silently destroys whatever changed in between -- a row edited
# in a text editor, restored by git, or written by a script.  The modification
# time the rows were read at is therefore recorded, and a write whose file has
# moved on since is refused rather than allowed to lose data.
TABLE_STAMPS: dict = {}


def table_stamp(path: Path):
    try:
        info = path.stat()
    except OSError:
        return None
    return (info.st_mtime_ns, info.st_size)


def remember_table(table: str, path: Path) -> None:
    TABLE_STAMPS[table] = table_stamp(path)


class TableChangedError(RuntimeError):
    """The file changed after the rows were read."""


def check_table_unchanged(table: str) -> None:
    """Refuse to write a table that changed since the server last touched it.

    Separated from write_table so a request that writes several tables can check
    them all before writing any: a refusal half way through would leave the data
    in a state nobody asked for.
    """
    if table not in TABLE_STAMPS:
        return
    current = table_stamp(table_path(table))
    if current is not None and current != TABLE_STAMPS[table]:
        raise TableChangedError(
            "%s 在读取之后被改动过，为避免覆盖别人的修改，本次写入已取消。"
            "请点「重新读取」后再改一次。" % table)


def write_table(table: str, comments, header, rows, force: bool = False) -> None:
    path = table_path(table)
    if not force:
        check_table_unchanged(table)
    if path.is_file():
        shutil.copyfile(path, path.with_name(path.name + BACKUP_SUFFIX))
    temporary = path.with_name(path.name + ".workbench.tmp")
    buffer = io.StringIO()
    for line in comments:
        buffer.write(line + "\n")
    writer = csv.DictWriter(buffer, fieldnames=header, lineterminator="\n",
                            extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in header})
    temporary.write_text(buffer.getvalue(), encoding="utf-8", newline="")
    os.replace(temporary, path)
    remember_table(table, path)


def blank_row(header) -> dict:
    return {key: "" for key in header}


# ==========================================================================
# docs/str.csv -- the language table, edited through the workbench
# ==========================================================================
STR_CONSTANT_RE = re.compile(r"^STR_[A-Z0-9_]+$")
LANG_HEADER = ["STRING", "ENGLISH", "SIMPLIFIED CHINESE"]


def is_lang_header(cells) -> bool:
    """Is this CSV record the language table's header line?

    It must be recognised in one place: a header that one reader skips and
    another keeps becomes a phantom row the browser renders as a string, which
    then cannot be saved or deleted ("字符串表里没有 STRING").
    """
    if not cells or len(cells) < 2:
        return False
    return cells[0].strip().lstrip("\ufeff") == LANG_HEADER[0] \
        and cells[1].strip() == LANG_HEADER[1]


def read_lang_table():
    """Return (comments, rows) of docs/str.csv as 3 cell lists.

    This file has no room for the ``#`` handling ``read_table`` does, because
    its comments are single lines rather than a leading block, so it is read
    and written here instead of through the generic CSV helpers.
    """
    if not LANG_CSV.is_file():
        raise FileNotFoundError("docs/str.csv does not exist")
    comments, rows = [], []
    with LANG_CSV.open(encoding="utf-8-sig", newline="") as handle:
        for raw in csv.reader(handle):
            if not raw:
                continue
            first = raw[0].strip().lstrip("\ufeff")
            if not first:
                continue
            if first.startswith("#"):
                comments.append(",".join(raw))
                continue
            if is_lang_header(raw):
                continue          # the header is written back by write_lang_table
            cells = [cell.strip() for cell in raw] + ["", "", ""]
            rows.append([first, cells[1], cells[2]])
    return comments, rows


def write_lang_table(comments, rows) -> None:
    if LANG_CSV.is_file():
        shutil.copyfile(LANG_CSV, LANG_CSV.with_name(LANG_CSV.name + BACKUP_SUFFIX))
    temporary = LANG_CSV.with_name(LANG_CSV.name + ".workbench.tmp")
    buffer = io.StringIO()
    for line in comments:
        buffer.write(line + "\n")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(LANG_HEADER)
    for row in rows:
        writer.writerow(row)
    temporary.write_text(buffer.getvalue(), encoding="utf-8", newline="")
    os.replace(temporary, LANG_CSV)


def find_lang_row(rows, constant: str):
    wanted = (constant or "").strip()
    for index, row in enumerate(rows):
        if row[0] == wanted:
            return index
    return None


def save_lang_row(payload: dict) -> dict:
    """Add or update one string, keyed by its constant."""
    constant = str(payload.get("constant") or "").strip().upper()
    english = str(payload.get("english") or "").strip()
    chinese = str(payload.get("chinese") or "").strip()
    original = str(payload.get("original") or "").strip().upper()
    if not STR_CONSTANT_RE.match(constant):
        raise ValueError("常量只能是大写字母、数字和下划线，并以 STR_ 开头：%r" % constant)
    if not english and not chinese:
        raise ValueError("英文与中文至少要填一个，否则这个字符串是空的")

    comments, rows = read_lang_table()
    index = find_lang_row(rows, original or constant)
    if original and original != constant and find_lang_row(rows, constant) is not None:
        raise ValueError("%s 已经存在" % constant)
    if original and index is None:
        raise FileNotFoundError("字符串表里没有 %s" % original)
    if index is None:
        rows.append([constant, english, chinese])
    else:
        rows[index] = [constant, english, chinese]
    write_lang_table(comments, rows)
    return {"ok": True, "constant": constant, "created": index is None,
            "state": build_state()}


def delete_lang_row(payload: dict) -> dict:
    constant = str(payload.get("constant") or "").strip()
    comments, rows = read_lang_table()
    index = find_lang_row(rows, constant)
    if index is None:
        raise FileNotFoundError("字符串表里没有 %s" % constant)
    rows.pop(index)
    write_lang_table(comments, rows)
    return {"ok": True, "constant": constant, "state": build_state()}


# ==========================================================================
# validation -- mirrors what genpnml.py rejects
# ==========================================================================
def band_of(category: str) -> str:
    bands = {
        "unit_wagon": "1024:2047", "coach": "2048:3071", "wagon": "3072:4095",
        "steam": "4096:5119", "diesel": "5120:6143", "electric": "6144:7167",
        "multipower": "7168:7679", "1500v_dc": "7680:8191", "dmu": "8192:9215",
        "emu": "9216:10239", "1500_emu": "10240:11263", "750_emu": "11264:12287",
        "third_emu": "12288:13311", "multi_mu": "13312:14335",
        "mono_mu": "14336:14847", "mglv_mu": "14848:15359",
        "cargo_dmu": "15360:15615", "cargo_emu": "15616:16127",
        "multi_cargo_mu": "16128:16383",
    }
    return bands.get(category, "")


def category_for(table: str, row: dict) -> str:
    if table == "coaches.csv":
        return "coach"
    if table == "wagons.csv":
        return "wagon"
    if table == "unit_wagons.csv":
        return "unit_wagon"
    return (row.get("category") or "").strip()


def is_locomotive_table(table: str) -> bool:
    return table == "locomotives.csv"


def normalize_folder(value: str) -> str:
    """Normalise a ``folder`` cell and refuse anything that escapes ``gfx/``.

    The cell may be a multi level path such as ``diesel/df4c`` or
    ``export/dprk/df4c``; forward slashes are the separator because the value is
    also the first argument of the NML sprite templates, and NML paths always
    use forward slashes.  Backslashes are folded to slashes so a cell typed on
    Windows still works, and ``.`` / ``..`` segments are resolved and then
    rejected rather than silently kept.
    """
    text = (value or "").strip().replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    return text


def folder_error(value: str) -> str:
    """Return why a folder cell is unusable, or an empty string."""
    text = normalize_folder(value)
    if not text:
        return "folder 不能为空（它是 gfx/ 子目录，也是精灵图模板的第一个参数）"
    if text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        return "folder 必须是 gfx/ 下的相对路径，不能是绝对路径：%r" % value
    segments = text.split("/")
    if any(segment in ("", ".", "..") for segment in segments):
        return "folder 不能包含空段、. 或 ..：%r" % value
    if len(segments) > MAX_FOLDER_DEPTH:
        return "folder 最多 %d 层目录，当前 %d 层：%r" % (MAX_FOLDER_DEPTH,
                                                        len(segments), value)
    for segment in segments:
        if not FOLDER_SEGMENT_RE.match(segment):
            return "folder 的每一层只能是字母、数字、下划线、点和横线，且不能以点或横线开头：%r" % segment
    return ""


def validate_vehicle_row(table: str, row: dict, others, is_new: bool):
    """Return a list of error strings; empty means the row may be written."""
    errors = []
    vehicle_id = (row.get("id") or "").strip()
    if not ID_RE.match(vehicle_id):
        errors.append("id 只能用小写字母、数字和下划线：%r" % vehicle_id)

    category = category_for(table, row)
    if is_locomotive_table(table) and not category:
        errors.append("category 不能为空（机车表用它决定 ID 段和 ENGINE_CLASS）")
    if category and not band_of(category):
        errors.append("未知的 category：%r" % category)

    problem = folder_error(row.get("folder"))
    if problem:
        errors.append(problem)

    if not (row.get("name_string") or "").strip():
        errors.append("name_string 不能为空")

    parts = [piece for piece in re.split(r"[|,]", row.get("parts") or "") if piece.strip()]
    for piece in parts:
        if not piece.strip().isdigit() or int(piece) <= 0:
            errors.append("parts 只能是正整数，用 | 分隔：%r" % piece.strip())
    # every vehicle is three sections: 2 + body + 2
    if len(parts) != 3:
        errors.append("每台车固定为三段（2 + 车身 + 2），当前 %d 段：%r"
                      % (len(parts), row.get("parts", "")))
    power_section = (row.get("power_section") or "").strip()
    if power_section:
        if not power_section.isdigit():
            errors.append("power_section 必须是数字")
        elif parts and int(power_section) >= len(parts):
            errors.append("power_section=%s 超出分段数 %d" % (power_section, len(parts)))

    numeric = {
        "intro_year": (1800, 2200), "intro_month": (1, 12), "intro_day": (1, 31),
        "speed": (0, 2000), "power": (0, 500000), "weight": (0, 10000),
        "cost_factor": (0, 100000), "running_cost_factor": (0, 100000),
        "capacity": (0, 100000), "loading_speed": (0, 10000),
        "cargo_age_period": (0, 100000), "vehicle_life": (0, 1000),
        "min_cars": (0, 200),
    }
    for column, (low, high) in numeric.items():
        value = (row.get(column) or "").strip()
        if not value:
            continue
        try:
            number = float(value)
        except ValueError:
            errors.append("%s 必须是数字：%r" % (column, value))
            continue
        if number < low or number > high:
            errors.append("%s 应在 %s … %s 之间，当前 %s" % (column, low, high, value))

    life = (row.get("model_life") or "").strip()
    if life and life != "VEHICLE_NEVER_EXPIRES" and not life.isdigit():
        errors.append("model_life 只能是年数或 VEHICLE_NEVER_EXPIRES：%r" % life)

    # min_cars only produces a start_stop switch on a multiple unit
    min_cars = (row.get("min_cars") or "").strip()
    if min_cars and min_cars.isdigit() and int(min_cars) > 0:
        mu = (row.get("mu") or "").strip().lower()
        if mu not in ("1", "y", "yes", "true", "t", "on"):
            errors.append("min_cars=%s 只在 mu=1（动车组）时生效，当前 mu=%r"
                          % (min_cars, row.get("mu", "")))

    track = (row.get("track_type") or "").strip()
    if track:
        known = schema_module.railtype_labels()
        if known and track not in known:
            errors.append("track_type %r 不在 src/railtypetable.pnml 中" % track)

    if is_new:
        for other in others:
            if (other.get("id") or "").strip() == vehicle_id:
                errors.append("%s 中已存在 id=%s" % (table, vehicle_id))
                break

    for column in ("refittable_cargo_classes", "non_refittable_cargo_classes"):
        value = (row.get(column) or "").strip()
        if value and not (value.startswith("bitmask(") or value == "0"):
            errors.append("%s 应形如 bitmask(CC_BULK|CC_COVERED) 或 0：%r" % (column, value))
    for column in ("cargo_allow_refit", "cargo_disallow_refit"):
        value = (row.get(column) or "").strip()
        if value and not (value.startswith("[") and value.endswith("]")):
            errors.append("%s 应形如 [VEHI|ENSP]：%r" % (column, value))

    additional = (row.get("additional_text") or "").strip()
    if "STR_BAD" in additional.upper():
        errors.append("additional_text 里出现了像 NML 字符串但不是合法名字的片段")
    return errors


def livery_basename(vehicle_id: str, suffix: str) -> str:
    """The sprite basename a livery row resolves to: ``<id>`` or ``<id>-<suffix>``.

    This mirrors ``genpnml._livery_basename``; the workbench shows it next to
    the row because the suffix alone does not say which ``.vox`` a livery needs.
    """
    vehicle_id = (vehicle_id or "").strip()
    suffix = (suffix or "").strip()
    return "%s-%s" % (vehicle_id, suffix) if suffix else vehicle_id


def purchase_basename(vehicle_id: str, row: dict) -> str:
    """The sheet the depot preview of that scheme uses (mirrors genpnml).

    ``purchase_suffix`` names a sheet of its own -- the column the parent set's
    hand written purchase spritesets correspond to -- so the depot sprite can be
    drawn from a sheet that exists while the scheme's own artwork does not.
    """
    suffix = (row.get("purchase_suffix") or row.get("sprite_suffix") or "").strip()
    return livery_basename(vehicle_id, suffix)


def livery_constant(label: str) -> str:
    """The NML constant a livery label cell refers to (mirrors genpnml).

    ``LV_<NAME>`` becomes ``STR_LV_<NAME>``, and the six labels the generator
    used to ship as plain ``STR_`` constants are mapped onto their new names so
    a table written before the convention still resolves to real text.
    """
    text = (label or "").strip()
    if text.startswith("LV_"):
        return "STR_" + text
    return LEGACY_LIVERY_LABELS.get(text, text)


def generator_module():
    """The generator module, reloaded when genpnml.py changed on disk.

    The workbench validates a cell with the generator's own parser, so it has to
    be the parser that is currently on disk.  A plain ``import`` caches the
    module for the life of the process, which means editing genpnml.py while the
    server runs would leave the editor validating against code that no longer
    exists -- and an out-of-date parser answers "no rules" rather than failing.

    Returns ``(module, "")`` or ``(None, reason)``.
    """
    global _GENPNML, _GENPNML_STAMP
    source = ROOT / "genpnml.py"
    try:
        stamp = source.stat().st_mtime_ns
    except OSError as error:
        return None, "找不到 genpnml.py（%s），规则无法解析" % error
    if _GENPNML is not None and _GENPNML_STAMP == stamp:
        return _GENPNML, ""
    try:
        import genpnml
        if _GENPNML is not None:
            genpnml = importlib.reload(genpnml)
    except Exception as error:  # noqa: BLE001 -- reported to the editor
        return None, "无法导入 genpnml.py（%s: %s），规则无法解析" % (
            type(error).__name__, error)
    _GENPNML = genpnml
    _GENPNML_STAMP = stamp
    return genpnml, ""


def parse_graphics_cell(cell: str, part_count: int) -> dict:
    """Parse one ``graphics_parts`` cell into a displayable report.

    The cell decides which sprite each section shows depending on where the car
    sits in the whole train, which is the least obvious column in the tables.
    The editor shows the same parse the generator will compile, so a rule nmlc
    would reject is reported as text rather than as a build failure.

    A section is a *tree* of switches, not a list, so the report keeps the
    nesting: the editor draws it as an indented tree, which is the shape the
    generated NML has.
    """
    cell = (cell or "").strip()
    if not cell:
        return {"set": False, "text": "", "sections": [], "error": ""}
    genpnml, failure = generator_module()
    if genpnml is None:
        # the parser lives in the generator, so without it nothing here can be
        # checked; say so instead of reporting an empty, valid-looking cell
        return {"set": True, "text": cell, "sections": [], "error": failure}
    try:
        parsed = genpnml.parse_graphics_parts(cell, part_count)
    except ValueError as error:
        # GraphicsPartsError subclasses ValueError, and so does a mismatch in
        # the section count, so one clause covers every refusal the parser makes
        return {"set": True, "text": cell, "sections": [], "error": str(error)}
    except Exception as error:  # noqa: BLE001 -- surface it in the editor
        # An unexpected failure must still reach the editor: a request that
        # silently answered "no rules" is what hid a stale parser once already.
        return {"set": True, "text": cell, "sections": [],
                "error": "%s: %s" % (type(error).__name__, error)}
    sections = []
    for position, roots in enumerate(parsed):
        sections.append({
            "position": position,
            "roots": [genpnml.tree_to_json(node) for node in roots],
            "basenames": [name for name in _graphics_basenames(roots)],
        })
    return {"set": True, "text": cell, "sections": sections, "error": ""}


def render_graphics_cell(sections, part_count: int) -> dict:
    """Turn the editor's switch tree back into a cell, then parse it again.

    The editor never writes a cell itself: it posts the tree, this renders it and
    returns the parse of what was rendered, so the author is shown exactly what
    the table will hold.  A tree the cell language cannot express comes back as
    an error instead of as a cell that would mean something else.
    """
    genpnml, failure = generator_module()
    if genpnml is None:
        return {"error": failure}
    try:
        cell = genpnml.render_graphics_json(sections, part_count)
    except ValueError as error:
        return {"error": str(error)}
    report = parse_graphics_cell(cell, part_count)
    if report.get("error"):
        return {"error": report["error"]}
    report["cell"] = cell
    return report


def _graphics_basenames(roots) -> list:
    """Every sprite sheet a section's tree names, in order, without repeats."""
    seen = []
    for root in roots:
        for node in root.walk():
            if node.basename and node.basename not in seen:
                seen.append(node.basename)
    return seen


def validate_livery_row(row: dict, vehicle_ids, is_new: bool, rows, index=None,
                        part_counts=None) -> dict:
    """Return {"errors": [...], "warnings": [...]} for one livery row.

    An error blocks the write; a warning is shown but saved, because the two
    things it reports are legal NML that is merely probably not what was meant.
    """
    errors = []
    warnings = []
    vehicle_id = (row.get("id") or "").strip()
    if not ID_RE.match(vehicle_id):
        errors.append("id 只能用小写字母、数字和下划线：%r" % vehicle_id)
    elif vehicle_id not in vehicle_ids:
        errors.append("id=%s 不在任何车辆表中" % vehicle_id)
    string = (row.get("string") or "").strip()
    if string and not LIVERY_LABEL_RE.match(string):
        errors.append("涂装名称应形如 LV_EXPORT_BLUE（或旧的 STR_EXPORT_BLUE）：%r" % string)
    for column in ("from_year", "to_year"):
        value = (row.get(column) or "").strip()
        if value and not value.isdigit():
            errors.append("%s 必须是非负整数（0 与 9999 表示不限）：%r" % (column, value))
    from_year = (row.get("from_year") or "0").strip() or "0"
    to_year = (row.get("to_year") or "9999").strip() or "9999"
    if from_year.isdigit() and to_year.isdigit() and int(to_year) < int(from_year):
        errors.append("to_year (%s) 小于 from_year (%s)" % (to_year, from_year))

    # the section count of this scheme's rules is the vehicle's section count.
    # Parsing the cell already validates every condition, so a report with no
    # error needs nothing more: the tree it returns is what the generator emits.
    cell = (row.get("graphics_parts") or "").strip()
    if cell:
        count = (part_counts or {}).get(vehicle_id)
        if count is None:
            warnings.append("找不到 %s 的 parts 列，分节图像规则暂时无法校验" % vehicle_id)
        else:
            report = parse_graphics_cell(cell, count)
            if report["error"]:
                errors.append("分节图像规则：%s" % report["error"])

    basename = livery_basename(vehicle_id, row.get("sprite_suffix"))

    def siblings():
        for position, other in enumerate(rows):
            if index is not None and position == index:
                continue
            if (other.get("id") or "").strip() != vehicle_id:
                continue
            yield position, other

    # two rows of one vehicle that resolve to the same basename would make the
    # generator declare the same sprite sheet twice
    for position, other in siblings():
        if livery_basename(vehicle_id, other.get("sprite_suffix")) == basename:
            errors.append("同一台车的第 %d 行已经是同一个模型 %s；"
                          "要新增涂装请换一个模型后缀（每行一个 .vox）。"
                          "如果只是想让车库购买列表里那张小图借用另一张图，"
                          "请改「购买菜单小图后缀」，它与模型无关"
                          % (position + 1, basename))
            break

    # A livery is identified in the refit menu by its string, so two schemes of
    # one vehicle sharing a label are listed as two identical entries and the
    # player cannot tell them apart.  Reusing a label is deliberate sometimes
    # (one scheme delivered with several models), so this only warns -- but it
    # has to warn, or the only thing distinguishing the rows is a file name.
    constant = livery_constant(row.get("string"))
    if constant:
        sharing = [position for position, other in siblings()
                   if livery_constant(other.get("string")) == constant]
        if sharing:
            warnings.append(
                "同一台车还有 %d 行（第 %s 行）用的是同一个字符串 %s；"
                "改装菜单里它们会显示成同一条，玩家分不出来。"
                "要让菜单能区分，请给这一行单独的 LV_<名字>"
                % (len(sharing), "、".join(str(position + 1) for position in sharing),
                   constant))

    if not (from_year.isdigit() and to_year.isdigit()):
        return {"errors": errors, "warnings": warnings}

    # Overlapping ranges are compiled (the generator sorts them and nmlc picks
    # the first case that matches), so this is a warning: the player sees the
    # earlier row inside the overlap, which is rarely the intent.
    bounds = (int(from_year), int(to_year))
    for position, other in siblings():
        other_from = (other.get("from_year") or "0").strip() or "0"
        other_to = (other.get("to_year") or "9999").strip() or "9999"
        if not (other_from.isdigit() and other_to.isdigit()):
            continue
        low, high = int(other_from), int(other_to)
        if low <= bounds[1] and bounds[0] <= high:
            warnings.append("年份区间 %s-%s 与第 %d 行的 %s-%s 重叠；"
                            "编译后重叠部分会取行序靠前的那一行"
                            % (from_year, to_year, position + 1, low, high))
            break
    return {"errors": errors, "warnings": warnings}


def validate_variant_row(row: dict, rows, wagon_ids, others):
    errors = []
    vehicle_id = (row.get("id") or "").strip()
    variant = (row.get("variant") or "").strip()
    if not ID_RE.match(vehicle_id):
        errors.append("id 只能用小写字母、数字和下划线：%r" % vehicle_id)
    elif vehicle_id not in wagon_ids:
        errors.append("id=%s 不在 wagons.csv 中（货运外观只能挂在货车上）" % vehicle_id)
    if not ID_RE.match(variant):
        errors.append("variant 只能用小写字母、数字和下划线：%r" % variant)
    classes = (row.get("cargo_classes") or "").strip()
    types = (row.get("cargo_types") or "").strip()
    if not classes and not types:
        errors.append("cargo_classes 与 cargo_types 至少要填一个，否则这一行永远不会被选中")
    if classes and not classes.startswith("bitmask("):
        errors.append("cargo_classes 应形如 bitmask(CC_BULK)：%r" % classes)
    for column in ("from_index", "to_index"):
        value = (row.get(column) or "").strip()
        if value and not value.isdigit():
            errors.append("%s 必须是非负整数：%r" % (column, value))
    from_index = (row.get("from_index") or "0").strip() or "0"
    to_index = (row.get("to_index") or "0").strip() or "0"
    if from_index.isdigit() and to_index.isdigit() and int(to_index) and int(to_index) < int(from_index):
        errors.append("to_index (%s) 小于 from_index (%s)" % (to_index, from_index))
    if variant:
        for other in others:
            if (other.get("id") or "").strip() == vehicle_id \
                    and (other.get("variant") or "").strip() == variant:
                errors.append("id=%s 已经有 variant=%s" % (vehicle_id, variant))
                break
    return errors


# ==========================================================================
# repository inspection
# ==========================================================================
def read_vehicle_tables() -> dict:
    """{table: (comments, header, rows)} for the four vehicle tables."""
    result = {}
    for table in VEHICLE_TABLES:
        try:
            result[table] = read_table(table)
        except (OSError, ValueError):
            result[table] = ([], list(schema_module.payload()["vehicle_columns"]), [])
    return result


def regenerate_ids(rows_by_table: dict) -> dict:
    """Reproduce the generator's ID assignment without running it.

    The bands are taken from the same table the generator uses, and rows are
    numbered in CSV order inside their band, so this matches vehicleid.pnml.
    """
    assigned = {}
    for table in VEHICLE_TABLES:
        for row in rows_by_table.get(table, ([], [], []))[2]:
            vehicle_id = (row.get("id") or "").strip()
            if not vehicle_id:
                continue
            category = category_for(table, row)
            band = band_of(category)
            assigned.setdefault(band, []).append((vehicle_id, table, category))
    ids = {}
    for band, entries in assigned.items():
        if not band:
            continue
        low = int(band.split(":")[0])
        for offset, (vehicle_id, _table, _category) in enumerate(entries):
            ids.setdefault(vehicle_id, low + offset)
    return ids


def read_vehicleid_file() -> dict:
    """Read the ID assignment the generator actually wrote."""
    path = SRC / "vehicleid.pnml"
    ids = {}
    if not path.is_file():
        return ids
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ids
    for match in VEHICLE_ID_ITEM_RE.finditer(text):
        ids.setdefault(match.group(1), int(match.group(2)))
    return ids


def sprite_manifest_path() -> Path:
    """Where the last ``genpnml.py`` run recorded the sprite basenames."""
    return ROOT / "gfx" / ".workbench-sprites.json"


def collect_sprite_basenames() -> dict:
    """{vehicle id: [basename, ...]} straight from the generator.

    ``collect_sprite_basenames()`` in ``genpnml.py`` is the only authority on
    which ``gfx/<folder>/<basename>.vox`` files a set of rows needs, so the
    workbench asks it instead of reimplementing the suffix rules.  Reading the
    tables writes nothing, so this is read-only.
    """
    script = (
        "import json, genpnml\n"
        "vehicles = genpnml.load_vehicles(%r)\n"
        "out = {v.id: genpnml.collect_sprite_basenames(v) for v in vehicles}\n"
        "print('__SPRITES__' + json.dumps(out))\n"
    ) % str(DATA)
    try:
        done = subprocess.run([sys.executable, "-c", script], cwd=str(ROOT), text=True,
                              capture_output=True, check=False, timeout=120,
                              env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    except (OSError, subprocess.SubprocessError) as error:
        report("asking the generator for the sprite names failed: %s" % error)
        return {}
    for line in (done.stdout or "").splitlines():
        if line.startswith("__SPRITES__"):
            try:
                return json.loads(line[len("__SPRITES__"):])
            except json.JSONDecodeError:
                break
    # Say so rather than returning an empty mapping that reads like "nothing is
    # missing": this fallback is what covers a table edited since the last
    # `--sprite-manifest` run, and silence here was hiding a broken call.
    report("asking the generator for the sprite names produced nothing: %s"
             % (done.stderr or done.stdout or "").strip()[-300:])
    return {}


def report(message: str) -> None:
    """Say something on the server's stderr, where the terminal running it sees it."""
    sys.stderr.write("[workbench] %s\n" % message)


def tables_newer_than(path: Path) -> bool:
    """True when a data table was saved after ``path`` was written.

    The sprite manifest is written by a ``genpnml.py`` run that asks for one
    (``--sprite-manifest``), and neither ``make gen`` nor a plain generator run
    does, so it goes stale as soon as a row is edited.  Comparing the times is
    what keeps the list of missing models -- and the model dropdown, which is
    built from the same records -- about the tables as they are now.
    """
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return True
    for name in ALL_TABLES:
        try:
            if (DATA / name).stat().st_mtime > stamp:
                return True
        except OSError:
            continue
    return False


def sprite_basenames() -> dict:
    """{vehicle id: [record, ...]} with the model and sheet state of each basename."""
    cache = sprite_manifest_path()
    by_id = {}
    if cache.is_file() and not tables_newer_than(cache):
        try:
            by_id = json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            by_id = {}
    if not isinstance(by_id, dict):
        by_id = {}
    if not by_id:
        by_id = collect_sprite_basenames()

    vehicles = {}
    for table in VEHICLE_TABLES:
        try:
            rows = read_table(table)[2]
        except (OSError, ValueError):
            continue
        for row in rows:
            vehicle_id = (row.get("id") or "").strip()
            folder = normalize_folder(row.get("folder"))
            if not vehicle_id or not folder:
                continue
            records = []
            for basename in by_id.get(vehicle_id, []):
                directory = GFX.joinpath(*folder.split("/"))
                records.append({
                    "folder": folder,
                    "basename": basename,
                    "vox": (directory / (basename + ".vox")).is_file(),
                    "png": (directory / (basename + "_32bpp.png")).is_file(),
                    "vox_path": "gfx/%s/%s.vox" % (folder, basename),
                    "png_path": "gfx/%s/%s_32bpp.png" % (folder, basename),
                })
            vehicles[vehicle_id] = records
    return vehicles


def string_kind(constant: str) -> str:
    """Which family a string constant belongs to.

    The language table mixes three kinds of text, and a livery label is the one
    a maker edits most often, so they are classified rather than flat listed.
    """
    name = (constant or "").strip()
    if name.startswith("STR_LV_"):
        return "livery"
    if name.startswith(("STR_NAME_", "STR_FULL_NAME_")):
        return "vehicle"
    return "interface"


def string_table_rows() -> list:
    """Every row of docs/str.csv as {constant, english, chinese, kind}.

    The livery and cargo tables refer to a string by its constant, which says
    nothing about the text the player will read.  Publishing the table lets the
    workbench show the resolved text next to the field and filter by family.

    The header line and anything that is not a real ``STR_`` constant are left
    out: a row the editor can display but not save is worse than no row.
    """
    rows = []
    if not LANG_CSV.is_file():
        return rows
    with LANG_CSV.open(encoding="utf-8-sig", newline="") as handle:
        for cells in csv.reader(handle):
            if not cells or not cells[0].strip():
                continue
            if is_lang_header(cells):
                continue
            constant = cells[0].strip().lstrip("\ufeff")
            if constant.startswith("#") or not STR_CONSTANT_RE.match(constant):
                continue
            padded = list(cells) + ["", ""]
            rows.append({"constant": constant,
                         "english": padded[1].strip(),
                         "chinese": padded[2].strip(),
                         "kind": string_kind(constant)})
    usage = livery_label_usage()
    for row in rows:
        counts = usage.get(row["constant"], [])
        row["livery_uses"] = sum(counts)
        row["livery_vehicles"] = len(counts)
        # more than one scheme of a single vehicle under one label
        row["livery_duplicate"] = bool(counts) and counts[0] > 1
    return rows


def livery_label_usage() -> dict:
    """{constant: [how many schemes of each vehicle point at it]}.

    A livery label is the only thing that names a scheme in the refit menu, and
    that menu is per vehicle: two schemes of *one* vehicle sharing a label are
    listed as two identical entries, while two vehicles using the same label is
    perfectly normal.  The per vehicle counts are what the string table needs to
    tell the two cases apart.
    """
    per_constant: dict = {}
    for row in read_aux("liveries.csv"):
        constant = livery_constant(row.get("string"))
        vehicle_id = (row.get("id") or "").strip()
        if not constant or not vehicle_id:
            continue
        counted = per_constant.setdefault(constant, {})
        counted[vehicle_id] = counted.get(vehicle_id, 0) + 1
    return {constant: sorted(counts.values(), reverse=True)
            for constant, counts in per_constant.items()}


def lang_comments() -> list:
    """The comment lines of docs/str.csv, for round tripping the file."""
    try:
        return read_lang_table()[0]
    except (OSError, ValueError):
        return []


def language_strings() -> set:
    """Every STR_ key defined in docs/str.csv."""
    keys = set()
    if not LANG_CSV.is_file():
        return keys
    with LANG_CSV.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if row and row[0].strip() and not row[0].lstrip().startswith("#"):
                keys.add(row[0].strip())
    return keys


def git_status() -> dict:
    def run(args):
        try:
            done = subprocess.run(args, cwd=str(ROOT), text=True,
                                  capture_output=True, check=False, timeout=20)
            return done.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""
    return {
        "describe": run(["git", "describe", "--tags", "--always", "--dirty"]),
        "dirty": bool(run(["git", "status", "--porcelain"])),
    }


# ==========================================================================
# API state
# ==========================================================================
def build_state() -> dict:
    tables = read_vehicle_tables()
    vehicles = []
    for table in VEHICLE_TABLES:
        _comments, _header, rows = tables[table]
        for row in rows:
            vehicle_id = (row.get("id") or "").strip()
            if not vehicle_id:
                continue
            category = category_for(table, row)
            vehicles.append({
                "id": vehicle_id,
                "table": table,
                "name_string": row.get("name_string", ""),
                "category": category,
                "folder": row.get("folder", ""),
                "intro_year": row.get("intro_year", ""),
                "track_type": row.get("track_type", ""),
                "speed": row.get("speed", ""),
                "power": row.get("power", ""),
                "weight": row.get("weight", ""),
                "capacity": row.get("capacity", ""),
                "ac_supply": row.get("ac_supply", ""),
                "airconditioned": row.get("airconditioned", ""),
                "mu": row.get("mu", ""),
                "comment": row.get("comment", ""),
                # the purchase menu columns the fleet overview edits in place
                "variant_group": row.get("variant_group", ""),
                "menu_order": row.get("menu_order", ""),
                "series_string": row.get("series_string", ""),
            })

    aux = {}
    for table in AUX_TABLES:
        try:
            aux[table] = read_table(table)[2]
        except (OSError, ValueError):
            aux[table] = []

    # a livery row is only useful if the .vox it names exists, so publish the
    # resolved basename and the state of both files next to every row
    folders, parts_by_id = {}, {}
    for table in VEHICLE_TABLES:
        for row in tables[table][2]:
            vehicle_id = (row.get("id") or "").strip()
            if vehicle_id:
                folders[vehicle_id] = normalize_folder(row.get("folder"))
                pieces = [piece.strip() for piece in re.split(r"[|,;]", row.get("parts") or "")
                          if piece.strip()]
                parts_by_id[vehicle_id] = len(pieces) or 3

    def sprite_file(folder: str, name: str) -> bool:
        if not folder or not name:
            return False
        return GFX.joinpath(*folder.split("/"), name).is_file()

    labels_by_vehicle: dict = {}
    # the first scheme of a vehicle is its default one, and the depot preview is
    # taken from it -- so the editor can say which row that is
    first_livery: dict = {}
    for position, row in enumerate(aux["liveries.csv"]):
        vehicle_id = (row.get("id") or "").strip()
        constant = livery_constant(row.get("string"))
        if vehicle_id and constant:
            labels_by_vehicle.setdefault(vehicle_id, []).append(constant)
        if vehicle_id and vehicle_id not in first_livery:
            first_livery[vehicle_id] = position

    for position, row in enumerate(aux["liveries.csv"]):
        vehicle_id = (row.get("id") or "").strip()
        basename = livery_basename(vehicle_id, row.get("sprite_suffix"))
        folder = folders.get(vehicle_id, "")
        row["_index"] = position
        row["_basename"] = basename
        row["_folder"] = folder
        row["_label"] = (row.get("string") or "").strip()
        row["_constant"] = livery_constant(row.get("string"))
        row["_sections"] = parts_by_id.get(vehicle_id, 3)
        row["_graphics"] = parse_graphics_cell(row.get("graphics_parts"),
                                              row["_sections"])
        row["_vox"] = sprite_file(folder, basename + ".vox")
        row["_png"] = sprite_file(folder, basename + "_32bpp.png")
        # the depot preview: the vehicle's first scheme is what the item block
        # returns, and purchase_suffix may point it at another sheet
        row["_purchase"] = position == first_livery.get(vehicle_id)
        purchase = purchase_basename(vehicle_id, row)
        row["_purchase_basename"] = purchase
        row["_purchase_png"] = sprite_file(folder, purchase + "_32bpp.png")
        # a livery is identified in the refit menu by its string, so the editor
        # has to say when several schemes of one vehicle would be listed under
        # the same label and the player could not tell them apart
        row["_label_used"] = (labels_by_vehicle.get(vehicle_id, [])
                              .count(row["_constant"]) if row["_constant"] else 0)
    for position, row in enumerate(aux["cargo_variants.csv"]):
        vehicle_id = (row.get("id") or "").strip()
        suffix = (row.get("sprite_suffix") or "").strip()
        folder = folders.get(vehicle_id, "")
        row["_index"] = position
        row["_basename"] = suffix
        row["_folder"] = folder
        # an empty suffix means "unloaded, draw the livery sprite itself"
        row["_own_sprite"] = bool(suffix)
        row["_vox"] = sprite_file(folder, suffix + ".vox") if suffix else False
        row["_png"] = sprite_file(folder, suffix + "_32bpp.png") if suffix else False

    ids = read_vehicleid_file()
    computed = regenerate_ids(tables)
    for vehicle in vehicles:
        vehicle["vehicle_id"] = ids.get(vehicle["id"], computed.get(vehicle["id"]))
        vehicle["band"] = band_of(vehicle["category"]) or ""

    sprites = sprite_basenames()
    for vehicle in vehicles:
        records = sprites.get(vehicle["id"], [])
        vehicle["sprites"] = records
        vehicle["sprites_ready"] = bool(records) and all(r["png"] for r in records)
        vehicle["sprites_missing"] = [r["basename"] for r in records if not r["png"]]
        vehicle["livery_count"] = sum(
            1 for row in aux["liveries.csv"]
            if (row.get("id") or "").strip() == vehicle["id"])
        vehicle["sections"] = parts_by_id.get(vehicle["id"], 3)

    counts = {table: len(tables[table][2]) for table in VEHICLE_TABLES}

    # Purchase menu order and grouping, so the fleet overview can show the list
    # the way the depot will and edit it in place.  The order is the generator's
    # own rule: menu_order first, empty last, then the table and row order.
    def menu_key(item):
        row = item[1]
        try:
            order = int((row.get("menu_order") or "").strip() or 0)
        except ValueError:
            order = 0
        return (order if order > 0 else 10 ** 6, item[0])

    ordered = [vehicle for _index, vehicle in sorted(enumerate(vehicles), key=menu_key)]
    children: dict = {}
    for vehicle in vehicles:
        parent = (vehicle.get("variant_group") or "").strip()
        if parent:
            children[(vehicle.get("table"), parent)] = \
                children.get((vehicle.get("table"), parent), 0) + 1
    for position, vehicle in enumerate(ordered):
        vehicle["menu_index"] = position
        vehicle["children_count"] = children.get((vehicle.get("table"),
                                                  vehicle.get("id")), 0)
    return {
        "vehicles": vehicles,
        "liveries": aux["liveries.csv"],
        "variants": aux["cargo_variants.csv"],
        "counts": counts,
        "total": len(vehicles),
        "git": git_status(),
        "grf": {
            "exists": (ROOT / "chinasettrainsexport.grf").is_file(),
            "size": (ROOT / "chinasettrainsexport.grf").stat().st_size
            if (ROOT / "chinasettrainsexport.grf").is_file() else 0,
        },
        "strings": len(language_strings()),
        "string_rows": string_table_rows(),
    }


# ==========================================================================
# background jobs
# ==========================================================================
JOBS: dict = {}
JOBS_LOCK = threading.Lock()


def start_job(action: str) -> dict:
    if action not in COMMANDS:
        raise ValueError("unknown action: %r" % action)
    steps = COMMANDS[action]["steps"]
    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "action": action,
        "label": COMMANDS[action]["label"],
        "status": "running",
        "started": time.time(),
        "finished": None,
        "lines": [],
        "returncode": None,
        "cursor": 0,
    }
    with JOBS_LOCK:
        JOBS[job_id] = job
    thread = threading.Thread(target=_run_job, args=(job, steps), daemon=True)
    thread.start()
    return {"job": job_id, "label": job["label"], "action": action}


def _append(job: dict, stream: str, text: str) -> None:
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        with JOBS_LOCK:
            job["lines"].append({"stream": stream, "text": line})


def _run_job(job: dict, steps) -> None:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    for command in steps:
        _append(job, "meta", "$ " + " ".join(str(part) for part in command))
        try:
            process = subprocess.Popen(
                [str(part) for part in command],
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
            )
        except OSError as error:
            _append(job, "stderr", str(error))
            with JOBS_LOCK:
                job["status"] = "failed"
                job["returncode"] = -1
                job["finished"] = time.time()
            return
        assert process.stdout is not None
        for line in process.stdout:
            _append(job, "out", line.rstrip("\n"))
        process.wait()
        with JOBS_LOCK:
            job["returncode"] = process.returncode
        if process.returncode != 0:
            _append(job, "meta", "命令退出码 %d，中止后续步骤" % process.returncode)
            with JOBS_LOCK:
                job["status"] = "failed"
                job["finished"] = time.time()
            return
    _append(job, "meta", "全部步骤完成")
    with JOBS_LOCK:
        job["status"] = "ok"
        job["finished"] = time.time()


def job_state(job_id: str, cursor: int) -> dict:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            raise FileNotFoundError("unknown job: %s" % job_id)
        lines = job["lines"][cursor:]
        return {
            "job": job_id,
            "action": job["action"],
            "label": job["label"],
            "status": job["status"],
            "returncode": job["returncode"],
            "elapsed": round((job["finished"] or time.time()) - job["started"], 2),
            "cursor": len(job["lines"]),
            "lines": lines,
        }


def job_list() -> list:
    with JOBS_LOCK:
        jobs = sorted(JOBS.values(), key=lambda item: item["started"], reverse=True)
        return [{"job": item["id"], "action": item["action"], "label": item["label"],
                 "status": item["status"], "started": item["started"]} for item in jobs[:20]]


# ==========================================================================
# write operations
# ==========================================================================
def row_key(table: str, row: dict):
    """The cell tuple that identifies a row inside its table.

    A vehicle is identified by ``id`` and a cargo variant by ``id`` plus
    ``variant``.  A livery has no such key -- its sprite suffix and year range
    are all editable -- so it is identified by its position, and this key only
    serves as a fallback when no position is known.
    """
    if table in VEHICLE_TABLES:
        return ((row.get("id") or "").strip(),)
    if table == "cargo_variants.csv":
        return ((row.get("id") or "").strip(), (row.get("variant") or "").strip())
    return ((row.get("id") or "").strip(), (row.get("sprite_suffix") or "").strip(),
            (row.get("from_year") or "").strip(), (row.get("to_year") or "").strip())


def find_row(table: str, rows, original: dict):
    """Locate the row the editor started from, by key and then by best match."""
    wanted = row_key(table, original)
    for index, row in enumerate(rows):
        if row_key(table, row) == wanted:
            return index
    # an edited identity (for example a renamed sprite suffix) no longer matches
    candidates = [index for index, row in enumerate(rows)
                  if (row.get("id") or "").strip() == (original.get("id") or "").strip()]
    if table == "cargo_variants.csv":
        variant = (original.get("variant") or "").strip()
        for index in candidates:
            if (rows[index].get("variant") or "").strip() == variant:
                return index
    if len(candidates) == 1:
        return candidates[0]
    return None


def find_aux_row(table: str, rows, original: dict, index=None):
    """Locate one auxiliary row.

    A livery row is identified by four volatile cells (id, sprite suffix and
    both years), so editing any of them used to make the row impossible to find
    again -- "liveries.csv 中找不到该行" when deleting a row that is plainly
    there.  The row's position is therefore the primary identity, exactly like
    a vehicle row: the browser sends the index of the row it rendered and, when
    no index is available, the key cells are matched on their own.
    """
    if isinstance(index, int) and 0 <= index < len(rows):
        return index
    return find_row(table, rows, original)


def vehicle_section_counts() -> dict:
    """{vehicle id: section count}, so livery rules can be validated."""
    counts = {}
    for table in VEHICLE_TABLES:
        try:
            rows = read_table(table)[2]
        except (OSError, ValueError):
            continue
        for row in rows:
            vehicle_id = (row.get("id") or "").strip()
            if not vehicle_id:
                continue
            pieces = [piece for piece in re.split(r"[|,;]", row.get("parts") or "")
                      if piece.strip()]
            counts[vehicle_id] = len(pieces) or 3
    return counts


def browser_row(payload: dict, key: str) -> dict:
    """One row as the browser sent it, without the fields this server added.

    ``build_state`` decorates every row with presentation-only keys -- ``_index``,
    ``_basename``, ``_graphics``, ``_label_used`` and friends -- so the browser
    holds them in the very object it posts back.  They are not columns, so they
    must never reach the "unknown column" check: a leading underscore is this
    project's own marker for "computed for display", which is why the filter is
    on the underscore rather than on a list that has to be kept in step with
    ``build_state``.
    """
    return {name: value for name, value in dict(payload.get(key) or {}).items()
            if not str(name).startswith("_")}


def save_row(payload: dict) -> dict:
    table = safe_table(payload.get("table"))
    row = browser_row(payload, "row")
    original = browser_row(payload, "original")
    _comments, header, rows = read_table(table)

    is_new = bool(payload.get("create"))
    index_hint = payload.get("index")
    if not isinstance(index_hint, int) or isinstance(index_hint, bool):
        index_hint = None

    unknown = set(row) - set(header)
    if unknown:
        raise ValueError("未知的列：%s" % ", ".join(sorted(unknown)))

    index = None
    if is_new:
        # never lose a column the browser does not know about
        merged = blank_row(header)
        merged.update({key: value for key, value in row.items() if key in header})
    elif table in AUX_TABLES:
        index = find_aux_row(table, rows, original or row, index_hint)
        if index is None:
            raise FileNotFoundError("找不到要修改的行（%s id=%s）"
                                    % (table, (original or row).get("id", "?")))
        merged = dict(rows[index])
        merged.update({key: value for key, value in row.items() if key in header})
    else:
        index = find_row(table, rows, original or row)
        if index is None:
            raise FileNotFoundError("找不到要修改的行（%s id=%s）"
                                    % (table, (original or row).get("id", "?")))
        merged = dict(rows[index])
        merged.update({key: value for key, value in row.items() if key in header})

    warnings = []
    if table in VEHICLE_TABLES:
        # every row except the one being edited, so a rename cannot collide with
        # itself and an add is checked against the whole table
        others = [r for position, r in enumerate(rows) if position != index]
        renamed = is_new or (merged.get("id") or "").strip() != (original.get("id") or "").strip()
        errors = validate_vehicle_row(table, merged, others, renamed)
    elif table == "liveries.csv":
        report = validate_livery_row(merged, all_vehicle_ids(), is_new, rows, index,
                                     vehicle_section_counts())
        errors, warnings = report["errors"], report["warnings"]
    else:
        others = [r for position, r in enumerate(rows) if position != index]
        errors = validate_variant_row(merged, rows, wagon_ids(), others)
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}

    if is_new:
        rows.append(merged)
    else:
        rows[index] = merged
    write_table(table, _comments, header, rows)
    return {
        "ok": True,
        "table": table,
        "id": (merged.get("id") or "").strip(),
        "created": is_new,
        "index": index if not is_new else len(rows) - 1,
        "needs_gen": True,
        "errors": [],
        "warnings": warnings,
        "state": build_state(),
    }


def _fleet_menu_edits(payload: dict) -> dict:
    """{table: {vehicle id: {column: value}}} from the fleet overview's request.

    A row may carry ``variant_group``, ``menu_order`` or both; a column that is
    absent is left alone, so moving one vehicle does not have to restate the
    grouping, and changing a grouping does not have to restate the order.
    """
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("没有要保存的车辆")
    allowed = {"table", "id", "variant_group", "menu_order", "series_string"}
    edits: Dict[str, Dict[str, Dict[str, str]]] = {}
    for item in rows:
        if not isinstance(item, dict):
            raise ValueError("rows 里有一项不是对象：%r" % (item,))
        # a misspelled key would otherwise be dropped in silence, and the author
        # would be left wondering why nothing changed
        unknown = set(item) - allowed
        if unknown:
            raise ValueError("rows 里有无法识别的键：%s（只接受 %s）"
                             % (", ".join(sorted(unknown)), ", ".join(sorted(allowed))))
        table = safe_table(item.get("table"))
        if table not in VEHICLE_TABLES:
            raise ValueError("购买菜单只能改车辆表，不能改 %s" % table)
        vehicle = safe_id(item.get("id"))
        entry = edits.setdefault(table, {}).setdefault(vehicle, {})
        if "variant_group" in item:
            parent = str(item.get("variant_group") or "").strip()
            if parent and not ID_RE.match(parent):
                raise ValueError(
                    "variant_group 必须是另一台车的 id（小写字母、数字、下划线）：%r"
                    % parent)
            entry["variant_group"] = parent
        if "menu_order" in item:
            order = str(item.get("menu_order") or "").strip()
            if order and not order.isdigit():
                raise ValueError("menu_order 必须是非负整数：%r" % order)
            entry["menu_order"] = order
        if "series_string" in item:
            series = str(item.get("series_string") or "").strip()
            # the same rule genpnml.py reads the cell with: a group label is used
            # verbatim as an NML string, so it has to be a real STR_ constant.
            # Accepting LV_ here would let the workbench save something the
            # generator refuses a moment later.
            if series and not SERIES_STRING_RE.match(series):
                raise ValueError(
                    "series_string 必须是 STR_ 常量（折叠项显示的名字）：%r" % series)
            entry["series_string"] = series
    return edits


def save_fleet_menu(payload: dict) -> dict:
    """Set the purchase menu grouping and order of several vehicles at once.

    The fleet overview edits more than one row per action -- moving a vehicle
    renumbers everything after it -- so every affected table is read and checked
    first and nothing is written unless all of them are acceptable.  The
    grouping rules themselves are the generator's own ``check_variant_groups``,
    so the workbench cannot accept a grouping that would fail the build.
    """
    edits = _fleet_menu_edits(payload)
    prepared = {}
    for table in sorted(edits):
        comments, header, rows = read_table(table)
        position = {(row.get("id") or "").strip(): index
                    for index, row in enumerate(rows)}
        for vehicle, entry in sorted(edits[table].items()):
            if vehicle not in position:
                raise FileNotFoundError("%s 中没有 id=%s" % (table, vehicle))
            for column, value in sorted(entry.items()):
                if column not in header:
                    raise ValueError(
                        "%s 里没有 %s 这一列，请先运行 tools/migrate_menu_columns.py"
                        % (table, column))
                rows[position[vehicle]][column] = value
        prepared[table] = (comments, header, rows)

    genpnml, failure = generator_module()
    if genpnml is None:
        return {"error": failure}
    problems = []
    for _table, (_comments, _header, rows) in sorted(prepared.items()):
        links = {(row.get("id") or "").strip(): (row.get("variant_group") or "").strip()
                 for row in rows}
        problems.extend(genpnml.check_variant_groups(links)[0])
    if problems:
        return {"ok": False, "errors": problems}

    for table in sorted(prepared):
        check_table_unchanged(table)
    for table in sorted(prepared):
        comments, header, rows = prepared[table]
        write_table(table, comments, header, rows)
    return {"ok": True, "tables": sorted(prepared), "needs_gen": True,
            "errors": [], "state": build_state()}


def delete_row(payload: dict) -> dict:
    table = safe_table(payload.get("table"))
    key = payload.get("key")
    _comments, header, rows = read_table(table)

    if table in VEHICLE_TABLES:
        vehicle_id = safe_id(payload.get("id"))
        remaining = [row for row in rows if (row.get("id") or "").strip() != vehicle_id]
        if len(remaining) == len(rows):
            raise FileNotFoundError("%s 中没有 id=%s" % (table, vehicle_id))
        removed = []
        if bool(payload.get("prune")):
            for folder in (SRC, GFX):
                if not folder.is_dir():
                    continue
                for path in folder.rglob(vehicle_id + "*"):
                    if path.is_file() and path.suffix in (".pnml", ".vox", ".png"):
                        path.unlink()
                        removed.append(relative(path))
            # the generated index files are refreshed by the next `make gen`
        write_table(table, _comments, header, remaining)
        return {"ok": True, "table": table, "id": vehicle_id, "removed": removed,
                "state": build_state()}

    # auxiliary tables: one row is identified by its position, then by key cells
    key = payload.get("key")
    index_hint = payload.get("index")
    if not isinstance(index_hint, int) or isinstance(index_hint, bool):
        index_hint = None
    original = {"id": key[0] if isinstance(key, list) and key else ""}
    if isinstance(key, list) and len(key) >= 4:
        original.update({"sprite_suffix": key[1], "from_year": key[2], "to_year": key[3]})
    if isinstance(key, list) and len(key) == 2 and table == "cargo_variants.csv":
        original["variant"] = key[1]
    index = find_aux_row(table, rows, original, index_hint)
    if index is None:
        raise FileNotFoundError("%s 中找不到该行" % table)
    removed_row = rows.pop(index)
    write_table(table, _comments, header, rows)
    return {"ok": True, "table": table, "id": (removed_row.get("id") or ""),
            "removed": [], "state": build_state()}


def move_row(payload: dict) -> dict:
    """Move one auxiliary row up or down.

    The row order of one vehicle in ``liveries.csv`` *is* the livery index the
    refit menu uses, so reordering is an edit, not a convenience.
    """
    table = safe_table(payload.get("table"))
    if table not in AUX_TABLES:
        raise ValueError("只有涂装与货运外观表可以调整行序")
    offset = -1 if str(payload.get("direction") or "") == "up" else 1
    _comments, header, rows = read_table(table)
    index_hint = payload.get("index")
    if not isinstance(index_hint, int) or isinstance(index_hint, bool):
        raise ValueError("调整行序需要提供 index")
    if not 0 <= index_hint < len(rows):
        raise ValueError("index %s 超出 %s 的范围" % (index_hint, table))
    target = index_hint + offset
    if not 0 <= target < len(rows):
        return {"ok": True, "table": table, "index": index_hint, "moved": False,
                "state": build_state()}
    # only reorder inside one vehicle's own block, otherwise the livery index of
    # two different vehicles would silently change
    if (rows[target].get("id") or "").strip() != (rows[index_hint].get("id") or "").strip():
        return {"ok": True, "table": table, "index": index_hint, "moved": False,
                "state": build_state()}
    rows[index_hint], rows[target] = rows[target], rows[index_hint]
    write_table(table, _comments, header, rows)
    return {"ok": True, "table": table, "index": target, "moved": True,
            "state": build_state()}


SHEET_PADDING = 8      # renderobject leaves this many transparent columns per view
SHEET_CACHE: dict = {}


def sprite_sheet_layout(path: Path) -> dict:
    """Split a rendered ``_32bpp.png`` into its eight view rectangles.

    ``renderobject`` writes one horizontal strip whose cells vary in width,
    because a 36 px front view and a 192 px side view are different pictures.
    The per view sizes come from the folder's ``manifest.json``; each cell is
    padded and every view is centred vertically, so a naive fixed grid slice
    would cut the model in half.
    """
    key = str(path)
    if key in SHEET_CACHE:
        return SHEET_CACHE[key]
    result = {"path": None, "width": 0, "height": 0, "views": [], "error": ""}
    try:
        manifest = json.loads((path.parent / "manifest.json").read_text(encoding="utf-8"))
        sprites = manifest.get("sprites") or []
        width, height = png_size(path)
        cell_widths = [int(sprite.get("width") or 0) for sprite in sprites]
        cell_heights = [int(sprite.get("height") or 0) for sprite in sprites]
        padding = padding_for(width, cell_widths)
        x = 0
        views = []
        for index, cell_width in enumerate(cell_widths):
            cell_height = cell_heights[index] if index < len(cell_heights) else height
            views.append({
                "index": index,
                "angle": sprites[index].get("angle"),
                "x": x,
                "y": max(0, (height - cell_height) // 2),
                "width": cell_width,
                "height": min(cell_height, height),
            })
            x += cell_width + padding
        result.update({"path": relative(path), "width": width, "height": height,
                       "views": views, "padding": padding,
                       "tile_count": len(views)})
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as error:
        result["error"] = str(error)
    SHEET_CACHE[key] = result
    return result


def padding_for(width: int, cell_widths: list) -> int:
    """The gap renderobject left between two views, worked out from the sheet."""
    if len(cell_widths) < 2:
        return 0
    leftover = width - sum(cell_widths)
    if leftover <= 0:
        return 0
    # the gap is uniform and appears after every cell, including the last
    if leftover % len(cell_widths) == 0:
        return leftover // len(cell_widths)
    if leftover % (len(cell_widths) - 1) == 0:
        return leftover // (len(cell_widths) - 1)
    return SHEET_PADDING


def png_size(path: Path):
    """Read the dimensions straight out of the PNG header."""
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file: %s" % path.name)
    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")
    return width, height


def read_aux(table: str) -> list:
    """Rows of an optional auxiliary table; empty when the file is missing."""
    try:
        return read_table(table)[2]
    except (OSError, ValueError):
        return []


def all_vehicle_ids() -> set:
    ids = set()
    for table in VEHICLE_TABLES:
        try:
            for row in read_table(table)[2]:
                value = (row.get("id") or "").strip()
                if value:
                    ids.add(value)
        except (OSError, ValueError):
            continue
    return ids


def wagon_ids() -> set:
    try:
        return {(row.get("id") or "").strip() for row in read_table("wagons.csv")[2]}
    except (OSError, ValueError):
        return set()


def copy_row(payload: dict) -> dict:
    table = safe_table(payload.get("table"))
    source = safe_id(payload.get("id"))
    target = safe_id(payload.get("new_id"))
    _comments, header, rows = read_table(table)
    record = None
    for row in rows:
        if (row.get("id") or "").strip() == source:
            record = dict(row)
            break
    if record is None:
        raise FileNotFoundError("%s 中没有 id=%s" % (table, source))
    if any((row.get("id") or "").strip() == target for row in rows):
        raise ValueError("%s 中已存在 id=%s" % (table, target))
    record["id"] = target
    record["name_string"] = str(payload.get("name_string") or record.get("name_string") or target)
    errors = validate_vehicle_row(table, record, rows, True) if table in VEHICLE_TABLES else []
    if errors:
        return {"ok": False, "errors": errors}
    rows.append(record)
    write_table(table, _comments, header, rows)
    return {"ok": True, "table": table, "id": target, "copied_from": source,
            "needs_gen": True, "state": build_state()}


# ==========================================================================
# HTTP
# ==========================================================================
class WorkbenchHandler(BaseHTTPRequestHandler):
    server_version = "ExportRailVehicleWorkbench/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[workbench] " + (fmt % args) + "\n")

    # ---- plumbing -------------------------------------------------------
    def send_json(self, data, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, body: bytes, content_type: str, status: int = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_payload(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > 32 * 1024 * 1024:
            raise ValueError("request is too large")
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    # ---- GET ------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/api/schema":
                self.send_json(schema_module.payload())
                return
            if parsed.path == "/api/strings":
                # one list, not two: the browser renders `rows` and needs the
                # `kind` classification with it.  Publishing a second, poorer
                # copy as `strings` is what let the string table empty itself
                # after a save -- that copy had no `kind`, so the kind filter
                # matched nothing.
                self.send_json({
                    "ok": True,
                    "path": relative(LANG_CSV),
                    "comments": lang_comments(),
                    "strings": string_table_rows(),
                })
                return
            if parsed.path == "/api/state":
                self.send_json(build_state())
                return
            if parsed.path == "/api/rules":
                # the tier 3 editor parses the cell as it is typed, through the
                # generator's own parser, so the preview cannot drift from the
                # NML the build will produce
                cell = query.get("cell", [""])[0]
                parts = query.get("parts", [""])[0]
                try:
                    count = len([piece for piece in re.split(r"[|,;]", parts)
                                 if piece.strip()]) or 3
                except re.error:
                    count = 3
                self.send_json(parse_graphics_cell(cell, count))
                return
            if parsed.path == "/api/vehicle":
                table = safe_table(query.get("table", [""])[0])
                vehicle_id = safe_id(query.get("id", [""])[0])
                _comments, header, rows = read_table(table)
                for row in rows:
                    if (row.get("id") or "").strip() == vehicle_id:
                        self.send_json({
                            "ok": True,
                            "table": table,
                            "header": header,
                            "row": row,
                            "liveries": [r for r in read_aux("liveries.csv")
                                         if (r.get("id") or "").strip() == vehicle_id],
                            "variants": [r for r in read_aux("cargo_variants.csv")
                                         if (r.get("id") or "").strip() == vehicle_id],
                        })
                        return
                self.send_json({"error": "%s 中没有 id=%s" % (table, vehicle_id)},
                               HTTPStatus.NOT_FOUND)
                return
            if parsed.path == "/api/row":
                table = safe_table(query.get("table", [""])[0])
                row = json.loads(unquote(query.get("row", ["{}"])[0]) or "{}")
                _comments, header, rows = read_table(table)
                index = find_row(table, rows, row)
                if index is None:
                    self.send_json({"error": "%s 中找不到该行" % table}, HTTPStatus.NOT_FOUND)
                    return
                self.send_json({"ok": True, "table": table, "header": header,
                                "row": rows[index], "index": index})
                return
            if parsed.path == "/api/pnml":
                table = safe_table(query.get("table", [""])[0])
                vehicle_id = safe_id(query.get("id", [""])[0])
                _comments, _header, rows = read_table(table)
                for row in rows:
                    if (row.get("id") or "").strip() == vehicle_id:
                        target = SRC / (row.get("folder") or "").strip() / (vehicle_id + ".pnml")
                        if target.is_file():
                            self.send_json({"ok": True, "path": relative(target),
                                            "text": target.read_text(encoding="utf-8",
                                                                     errors="replace")})
                        else:
                            self.send_json({"ok": False, "path": relative(target),
                                            "text": "",
                                            "note": "尚未生成，先运行「生成车辆代码」"})
                        return
                self.send_json({"error": "%s 中没有 id=%s" % (table, vehicle_id)},
                               HTTPStatus.NOT_FOUND)
                return
            if parsed.path == "/api/sheet":
                path = repo_path(unquote(query.get("path", [""])[0]))
                if not path.is_file():
                    self.send_error(HTTPStatus.NOT_FOUND, "sprite sheet not found")
                    return
                self.send_json(sprite_sheet_layout(path))
                return
            if parsed.path == "/api/file":
                path = repo_path(unquote(query.get("path", [""])[0]))
                if not path.is_file():
                    self.send_error(HTTPStatus.NOT_FOUND, "file not found")
                    return
                content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                self.send_bytes(path.read_bytes(), content_type)
                return
            if parsed.path == "/api/text":
                path = repo_path(unquote(query.get("path", [""])[0]))
                if not path.is_file():
                    self.send_error(HTTPStatus.NOT_FOUND, "file not found")
                    return
                self.send_json({"ok": True, "path": relative(path),
                                "text": path.read_text(encoding="utf-8", errors="replace")})
                return
            if parsed.path == "/api/job":
                job_id = str(query.get("job", [""])[0])
                cursor = int(query.get("cursor", ["0"])[0] or 0)
                self.send_json(job_state(job_id, cursor))
                return
            if parsed.path == "/api/jobs":
                self.send_json({"jobs": job_list(), "commands": {
                    key: {"label": value["label"]} for key, value in COMMANDS.items()}})
                return
            if parsed.path == "/api/commands":
                self.send_json({"commands": {key: {"label": value["label"]}
                                             for key, value in COMMANDS.items()}})
                return
            self.serve_static(parsed.path)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # the browser closed the socket while the response was being
            # written; that is normal on a refresh and is not an error
            return
        except FileNotFoundError as error:
            self.log_error("GET %s: %s", self.path, error)
            self.send_json({"error": str(error)}, HTTPStatus.NOT_FOUND)
        except (OSError, ValueError) as error:
            # a real failure: without the traceback a 400 here cannot be
            # diagnosed, because the message alone does not name the reader
            self.log_error("GET %s failed: %s: %s", self.path, type(error).__name__, error)
            traceback.print_exc()
            self.send_json({"error": "%s: %s" % (type(error).__name__, error)},
                           HTTPStatus.BAD_REQUEST)

    def serve_static(self, path: str) -> None:
        if path in ("", "/", "/workbench", "/workbench/"):
            target = HERE / "index.html"
        elif path.startswith("/workbench/"):
            target = (HERE / path[len("/workbench/"):]).resolve()
            if HERE not in target.parents and target != HERE:
                self.send_error(HTTPStatus.NOT_FOUND, "page not found")
                return
        else:
            target = (WEB_ROOT / path.lstrip("/")).resolve()
            if WEB_ROOT not in target.parents:
                self.send_error(HTTPStatus.NOT_FOUND, "page not found")
                return
        if not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "page not found")
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/javascript",):
            content_type += "; charset=utf-8"
        self.send_bytes(target.read_bytes(), content_type)

    def do_HEAD(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---- POST -----------------------------------------------------------
    def do_POST(self) -> None:  # noqa: N802
        try:
            payload = self.read_payload()
            if self.path == "/api/save":
                self.send_json(save_row(payload))
            elif self.path == "/api/delete":
                self.send_json(delete_row(payload))
            elif self.path == "/api/move":
                self.send_json(move_row(payload))
            elif self.path == "/api/string":
                self.send_json(save_lang_row(payload))
            elif self.path == "/api/string-delete":
                self.send_json(delete_lang_row(payload))
            elif self.path == "/api/copy":
                self.send_json(copy_row(payload))
            elif self.path == "/api/graphics-parts":
                # the tier 3 editor posts a switch tree and gets back the cell it
                # renders to, already parsed again -- so the preview is always
                # the table's content and never the browser's idea of it
                parts = str(payload.get("parts") or "")
                count = len([piece for piece in re.split(r"[|,;]", parts)
                             if piece.strip()]) or 3
                self.send_json(render_graphics_cell(payload.get("sections"), count))
            elif self.path == "/api/fleet-menu":
                # the fleet overview's grouping and ordering, several rows at once
                self.send_json(save_fleet_menu(payload))
            elif self.path == "/api/run":
                self.send_json(start_job(str(payload.get("action") or "")))
            else:
                self.send_error(HTTPStatus.NOT_FOUND, "unknown API endpoint")
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            return
        except TableChangedError as error:
            # a conflict, not a bad request: the browser should reload
            self.send_json({"error": str(error), "reload": True},
                           HTTPStatus.CONFLICT)
        except FileNotFoundError as error:
            self.send_json({"error": str(error)}, HTTPStatus.NOT_FOUND)
        except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as error:
            self.log_error("POST %s failed: %s: %s", self.path, type(error).__name__, error)
            self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4174)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), WorkbenchHandler)
    print("Export rail vehicle workbench: http://%s:%d/workbench/" % (args.host, args.port))
    print("repository: %s" % ROOT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
