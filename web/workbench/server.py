#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local web workbench for the export rail vehicle add-on.

The browser owns the editing experience; this server keeps the repository
consistent.  It deliberately uses only the Python standard library and delegates
every piece of real work to the project's existing command line tools:

    genpnml.py                     vehicle code and placeholder models
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

import schema as schema_module  # noqa: E402

WEB_ROOT = ROOT / "web"
DATA = ROOT / "data"
SRC = ROOT / "src"
GFX = ROOT / "gfx"
DOCS = ROOT / "docs"
LANG_CSV = DOCS / "str.csv"

VEHICLE_TABLES = ("locomotives.csv", "coaches.csv", "wagons.csv", "unit_wagons.csv")
AUX_TABLES = ("liveries.csv", "cargo_variants.csv")
ALL_TABLES = VEHICLE_TABLES + AUX_TABLES

ID_RE = re.compile(r"^[a-z0-9_]+$")
FOLDER_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
BACKUP_SUFFIX = ".workbench.bak"

VEHICLE_ID_ITEM_RE = re.compile(
    r'item\s*\(\s*FEAT_TRAINS\s*,\s*([A-Za-z0-9_]+)\s*,\s*(\d+)\s*\)'
)

# the only commands the browser may start
COMMANDS = {
    "gen": {
        "label": "生成车辆代码",
        "steps": [[sys.executable, "genpnml.py", "--strings", "--strings-file", "docs/str.csv"],
                  [sys.executable, "genpnml.py", "--data", "data", "--out", "src", "--vox",
                   "--sprite-manifest", "gfx/.workbench-sprites.json"]],
    },
    "build": {
        "label": "编译 GRF",
        "steps": [["make"]],
    },
    "check": {
        "label": "一致性检查",
        "steps": [[sys.executable, "genpnml.py", "--data", "data", "--check",
                   "--strings-file", "docs/str.csv"],
                  [sys.executable, "tools/verify_assets.py"]],
    },
    "vox": {
        "label": "生成占位模型",
        "steps": [[sys.executable, "genpnml.py", "--data", "data", "--out", "src", "--vox",
                   "--sprite-manifest", "gfx/.workbench-sprites.json"]],
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
    return comments, header, rows


def write_table(table: str, comments, header, rows) -> None:
    path = table_path(table)
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


def blank_row(header) -> dict:
    return {key: "" for key in header}


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

    folder = (row.get("folder") or "").strip()
    if not folder:
        errors.append("folder 不能为空（它是 gfx/ 子目录，也是精灵图模板的第一个参数）")
    elif not FOLDER_RE.match(folder) or "/" in folder or "\\" in folder or ".." in folder:
        errors.append("folder 只能是一层目录名，且不能包含路径分隔符：%r" % folder)

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

    # graphics_parts is compiled into NML switches, so a broken cell would only
    # surface as an nmlc syntax error much later; parse it the same way the
    # generator does and report the reason now.
    graphics_parts = (row.get("graphics_parts") or "").strip()
    if graphics_parts:
        try:
            import genpnml
            genpnml.parse_graphics_parts(graphics_parts, len(parts) or 3)
        except ImportError:
            pass
        except ValueError as error:
            errors.append("graphics_parts：%s" % error)

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


def validate_livery_row(row: dict, vehicle_ids, is_new: bool, rows):
    errors = []
    vehicle_id = (row.get("id") or "").strip()
    if not ID_RE.match(vehicle_id):
        errors.append("id 只能用小写字母、数字和下划线：%r" % vehicle_id)
    elif vehicle_id not in vehicle_ids:
        errors.append("id=%s 不在任何车辆表中" % vehicle_id)
    string = (row.get("string") or "").strip()
    if string and not string.startswith("STR_"):
        errors.append("string 应形如 STR_EXPORT_BLUE：%r" % string)
    for column in ("from_year", "to_year"):
        value = (row.get(column) or "").strip()
        if value and not value.isdigit():
            errors.append("%s 必须是非负整数（0 与 9999 表示不限）：%r" % (column, value))
    from_year = (row.get("from_year") or "0").strip() or "0"
    to_year = (row.get("to_year") or "9999").strip() or "9999"
    if from_year.isdigit() and to_year.isdigit() and int(to_year) < int(from_year):
        errors.append("to_year (%s) 小于 from_year (%s)" % (to_year, from_year))
    return errors


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
    """Where the last ``genpnml.py --vox`` run recorded the sprite basenames."""
    return ROOT / "gfx" / ".workbench-sprites.json"


def collect_sprite_basenames() -> dict:
    """{vehicle id: [basename, ...]} straight from the generator.

    ``collect_sprite_basenames()`` in ``genpnml.py`` is the only authority on
    which ``gfx/<folder>/<basename>.vox`` files a set of rows needs, so the
    workbench asks it instead of reimplementing the suffix rules.  Running the
    generator without ``--vox`` writes no files, so this is read-only.
    """
    script = (
        "import json, genpnml\n"
        "vehicles = genpnml.load_vehicles()\n"
        "out = {v.id: [b for b, _c in genpnml.collect_sprite_basenames(v)] for v in vehicles}\n"
        "print('__SPRITES__' + json.dumps(out))\n"
    )
    try:
        done = subprocess.run([sys.executable, "-c", script], cwd=str(ROOT), text=True,
                              capture_output=True, check=False, timeout=120,
                              env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    except (OSError, subprocess.SubprocessError):
        return {}
    for line in (done.stdout or "").splitlines():
        if line.startswith("__SPRITES__"):
            try:
                return json.loads(line[len("__SPRITES__"):])
            except json.JSONDecodeError:
                return {}
    return {}


def sprite_basenames() -> dict:
    """{vehicle id: [record, ...]} with the model and sheet state of each basename."""
    cache = sprite_manifest_path()
    by_id = {}
    if cache.is_file():
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
            folder = (row.get("folder") or "").strip()
            if not vehicle_id or not folder:
                continue
            records = []
            for basename in by_id.get(vehicle_id, []):
                directory = GFX / folder
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


def string_table_rows() -> list:
    """Every row of docs/str.csv as {constant, english, chinese}.

    The livery and cargo tables refer to a string by its constant, which says
    nothing about the text the player will read.  Publishing the table lets the
    workbench show the resolved text next to the field.
    """
    rows = []
    if not LANG_CSV.is_file():
        return rows
    with LANG_CSV.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if not row or not row[0].strip() or row[0].lstrip().startswith("#"):
                continue
            cells = list(row) + ["", ""]
            rows.append({"constant": cells[0].strip(),
                         "english": cells[1].strip(),
                         "chinese": cells[2].strip()})
    return rows


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
                "model": row.get("model", ""),
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
            })

    aux = {}
    for table in AUX_TABLES:
        try:
            aux[table] = read_table(table)[2]
        except (OSError, ValueError):
            aux[table] = []

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

    counts = {table: len(tables[table][2]) for table in VEHICLE_TABLES}
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

    A vehicle is identified by ``id``; a cargo variant by ``id`` plus
    ``variant``; a livery scheme by ``id``, its sprite suffix and its year
    range, because the row order of one vehicle defines the livery index and
    several schemes of the same vehicle may share an empty sprite suffix.
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


def save_row(payload: dict) -> dict:
    table = safe_table(payload.get("table"))
    row = dict(payload.get("row") or {})
    original = dict(payload.get("original") or {})
    _comments, header, rows = read_table(table)

    is_new = bool(payload.get("create"))

    unknown = set(row) - set(header)
    if unknown:
        raise ValueError("未知的列：%s" % ", ".join(sorted(unknown)))

    index = None
    if is_new:
        # never lose a column the browser does not know about
        merged = blank_row(header)
        merged.update({key: value for key, value in row.items() if key in header})
    else:
        index = find_row(table, rows, original or row)
        if index is None:
            raise FileNotFoundError("找不到要修改的行（%s id=%s）"
                                    % (table, (original or row).get("id", "?")))
        merged = dict(rows[index])
        merged.update({key: value for key, value in row.items() if key in header})

    if table in VEHICLE_TABLES:
        # every row except the one being edited, so a rename cannot collide with
        # itself and an add is checked against the whole table
        others = [r for position, r in enumerate(rows) if position != index]
        renamed = is_new or (merged.get("id") or "").strip() != (original.get("id") or "").strip()
        errors = validate_vehicle_row(table, merged, others, renamed)
    elif table == "liveries.csv":
        errors = validate_livery_row(merged, all_vehicle_ids(), is_new, rows)
    else:
        others = [r for position, r in enumerate(rows) if position != index]
        errors = validate_variant_row(merged, rows, wagon_ids(), others)
    if errors:
        return {"ok": False, "errors": errors}

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
        "needs_gen": True,
        "state": build_state(),
    }


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

    # auxiliary tables: one row is identified by its key cells, not by id
    if not isinstance(key, list):
        raise ValueError("删除涂装 / 货运外观行需要提供 key")
    key = [str(part) for part in key]
    remaining = [row for row in rows if row_key(table, row) != tuple(key)]
    if len(remaining) == len(rows):
        raise FileNotFoundError("%s 中找不到该行" % table)
    write_table(table, _comments, header, remaining)
    return {"ok": True, "table": table, "id": key[0] if key else "", "removed": [],
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
                self.send_json({"ok": True, "strings": string_table_rows()})
                return
            if parsed.path == "/api/state":
                self.send_json(build_state())
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
            elif self.path == "/api/copy":
                self.send_json(copy_row(payload))
            elif self.path == "/api/run":
                self.send_json(start_job(str(payload.get("action") or "")))
            else:
                self.send_error(HTTPStatus.NOT_FOUND, "unknown API endpoint")
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            return
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
