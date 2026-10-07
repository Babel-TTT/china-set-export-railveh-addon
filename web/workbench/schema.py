#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Column metadata for the export rail vehicle workbench.

The workbench renders its data-entry forms from this module, so a column is
never hard-coded in the JavaScript.  Everything here mirrors what
``genpnml.py`` actually reads and how ``tools/vehicle_row.py`` writes it.

A field is a tuple:

    (name, group, kind, label, hints)

where ``hints`` is an optional dict with any of:

    default     value a new row starts with
    choices     fixed set of allowed values (``kind == "enum"``)
    placeholder grey text in the input
    help        longer explanation shown under the field
    min / max   numeric bounds
    applies     "all" (default), "locomotive", "coach", "wagon", "unit_wagon"
    columns     for ``kind == "toggle"``: the four tables and their default

Groups are emitted in ``GROUPS`` order.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]

GROUPS: List[Dict[str, str]] = [
    {"id": "identity", "label": "身份与外观", "note": "决定 NML 标识符、ID 段和精灵图文件名。"},
    {"id": "dates", "label": "日期与寿命", "note": "决定购入菜单里车辆出现的年代。"},
    {"id": "physics", "label": "物理性能", "note": "速度、功率、重量与牵引特性。"},
    {"id": "cost", "label": "成本与可靠性", "note": "相对价格系数，最终价格由 GRF 参数缩放。"},
    {"id": "cargo", "label": "货运与容量", "note": "可改装货物、默认货物与载量。"},
    {"id": "systems", "label": "装置", "note": "供电、空调、餐车、动车组等属性。"},
    {"id": "text", "label": "文案", "note": "车厢描述与备注。"},
    {"id": "meta", "label": "元数据", "note": "人类可读的备注，生成器不读取。"},
]

CATEGORIES: List[str] = [
    "steam", "diesel", "electric", "multipower", "1500v_dc",
    "dmu", "emu", "1500_emu", "750_emu", "third_emu",
    "multi_mu", "mono_mu", "mglv_mu",
    "cargo_dmu", "cargo_emu", "multi_cargo_mu",
]

CATEGORY_NOTES: Dict[str, str] = {
    "steam": "蒸汽机车 · ID 段 4096-5119 · ENGINE_CLASS_STEAM",
    "diesel": "内燃机车 · ID 段 5120-6143 · ENGINE_CLASS_DIESEL",
    "electric": "25kV 交流电力机车 · ID 段 6144-7167",
    "multipower": "多电源机车（内燃 + 电力）· ID 段 7168-7679",
    "1500v_dc": "1500V 直流电力机车 · ID 段 7680-8191",
    "dmu": "内燃动车组 · ID 段 8192-9215",
    "emu": "25kV 交流动车组 · ID 段 9216-10239",
    "1500_emu": "1.5kV 直流动车组 · ID 段 10240-11263",
    "750_emu": "750V 直流动车组 · ID 段 11264-12287",
    "third_emu": "第三轨动车组 · ID 段 12288-13311",
    "multi_mu": "多电源动车组 · ID 段 13312-14335",
    "mono_mu": "单轨动车组 · ID 段 14336-14847",
    "mglv_mu": "磁悬浮动车组 · ID 段 14848-15359",
    "cargo_dmu": "内燃货运动车组 · ID 段 15360-15615",
    "cargo_emu": "25kV 交流货运动车组 · ID 段 15616-16127",
    "multi_cargo_mu": "多电源货运动车组 · ID 段 16128-16383",
}

CITIES: List[Dict[str, str]] = [
    {"id": "locomotives.csv", "table": "locomotives", "label": "机车 / 动车组头车",
     "category": "explicit",
     "note": "category 列在这里生效，决定 ID 段与 ENGINE_CLASS。"},
    {"id": "coaches.csv", "table": "coaches", "label": "客车",
     "category": "coach", "note": "category 被忽略，固定按 coach 处理。"},
    {"id": "wagons.csv", "table": "wagons", "label": "货车",
     "category": "wagon", "note": "category 被忽略，固定按 wagon 处理。"},
    {"id": "unit_wagons.csv", "table": "unit_wagons", "label": "动车组拖车",
     "category": "unit_wagon", "note": "category 被忽略，固定按 unit_wagon 处理。"},
]

MODEL_KINDS: List[str] = ["triple"]   # kept for reference; the model column is gone
POWER_UNITS: List[str] = ["kW", "hp"]

# variables allowed in a graphics_parts condition
GRAPHICS_VARIABLES: Dict[str, str] = {
    "pos": "position_in_consist（整列第几节，从 0 开始）",
    "tailpos": "position_in_consist_from_end（从尾部数第几节）",
    "consist": "num_vehs_in_consist（整列总节数）",
    "unitpos": "position_in_articulated_veh（本车第几段）",
}

CLIMATES: List[str] = [
    "ALL_CLIMATES", "TEMPERATE", "ARCTIC", "TROPIC", "TOYLAND",
]

SPECIAL_VEHICLE_LIFE: List[str] = ["VEHICLE_NEVER_EXPIRES"]
DEFAULT_CARGO: List[str] = [
    "DEFAULT_CARGO_FIRST_REFITTABLE", "PASS", "COAL", "MAIL", "GOODS",
]

AI_FLAGS: List[str] = ["AI_FLAG_PASSENGER", "AI_FLAG_CARGO", "AI_FLAG_MAIL", "AI_FLAG_NONE"]

CARGO_CLASSES: List[str] = [
    "CC_PASSENGERS", "CC_MAIL", "CC_EXPRESS", "CC_ARMOURED", "CC_BULK",
    "CC_PIECE_GOODS", "CC_LIQUID", "CC_REFRIGERATED", "CC_HAZARDOUS",
    "CC_COVERED", "CC_OVERSIZED", "CC_POWDERIZED", "CC_NON_POURABLE",
]

CUSTOM_TAGS: List[str] = ["ALL_CLIMATES", "VEHICLE_NEVER_EXPIRES"]

# --------------------------------------------------------------------------
# the 46 vehicle columns, in the order of the CSV header
# --------------------------------------------------------------------------
VEHICLE_FIELDS: List[tuple] = [
    ("id", "identity", "text", "车辆 ID", {
        "required": True, "placeholder": "ckd4a",
        "help": "NML 标识符，同时是精灵图文件名。只能用小写字母、数字和下划线。"}),
    ("name_string", "identity", "text", "显示名称", {
        "required": True, "placeholder": "CKD4A (Export)",
        "help": "车厢窗口里显示的名字，生成器会映射到 STR_NAME_<ID> 并写进 docs/str.csv。"}),
    ("category", "identity", "enum", "类别", {
        "choices": CATEGORIES, "default": "diesel", "applies": "locomotive",
        "help": "决定 ID 段与 ENGINE_CLASS。客车、货车、拖车表里这一列被忽略。"}),
    ("folder", "identity", "text", "gfx 子目录", {
        "default": "diesel", "placeholder": "diesel",
        "help": "模型所在目录，也是精灵图模板的第一个参数。只能是 gfx/ 下的单层目录名。"}),
    ("parts", "identity", "list", "分段长度", {
        "default": "2|8|2", "placeholder": "2|8|2",
        "help": "三段长度，| , ; 都可作分隔符，例如 2|8|2。中间那个是车身长度，"
                "两端固定为 2（隐形车厢）。"}),
    ("power_section", "identity", "int", "动力段索引", {
        "default": "1", "min": 0,
        "help": "承载车体图形、功率与载量的段序号（从 0 开始），三段结构就是 1。"}),
    ("graphics_parts", "identity", "list", "分节图像规则", {
        "default": "",
        "placeholder": "consist<=6=emu_short | emu_mid | consist<=6=emu_short;"
                       "emu_midbody;"
                       "consist<=6=emu_short | emu_mid | consist<=6=emu_short",
        "help": "按段用 ; 分隔（需与 parts 段数一致），段内用 | 分隔规则，"
                "规则写成 条件=基名 或 只写基名（兜底）。"
                "可用变量：pos（整列第几节，从 0 起）、tailpos（从尾部数）、"
                "consist（整列节数）、unitpos（本车第几段）。"
                "留空则只有车身段出图、两端隐形。"}),

    ("intro_year", "dates", "int", "启用年份", {
        "default": "1950", "min": 1800, "max": 2200}),
    ("intro_month", "dates", "int", "启用月份", {"default": "1", "min": 1, "max": 12}),
    ("intro_day", "dates", "int", "启用日期", {"default": "1", "min": 1, "max": 31}),
    ("model_life", "dates", "text", "车型寿命", {
        "default": "30", "placeholder": "30 或 VEHICLE_NEVER_EXPIRES",
        "help": "可用年数，或 VEHICLE_NEVER_EXPIRES 表示永不过时。"}),
    ("retire_early", "dates", "int", "提前退场年数", {"default": "", "min": 0}),
    ("vehicle_life", "dates", "int", "单车寿命", {"default": "30", "min": 0}),

    ("track_type", "physics", "enum", "轨道类型", {
        "choices": [], "dynamic": "railtypes", "default": "SACN",
        "help": "src/railtypetable.pnml 中的标签：首字母轨距，第 2 位速度等级，第 3 位轴重，末位电气化。"}),
    ("climates_available", "physics", "enum", "适用气候", {
        "choices": CLIMATES, "default": "ALL_CLIMATES"}),
    ("speed", "physics", "int", "最高速度", {"unit": "km/h", "default": "100", "min": 1, "max": 1000}),
    ("power", "physics", "int", "功率", {
        "unit": "见 power_unit", "default": "1000", "applies": "locomotive", "min": 0}),
    ("power_unit", "physics", "enum", "功率单位", {
        "choices": POWER_UNITS, "default": "kW", "applies": "locomotive"}),
    ("weight", "physics", "float", "重量", {"unit": "t", "default": "92", "min": 0}),
    ("tractive_effort_coefficient", "physics", "float", "牵引力系数", {
        "default": "0.25", "applies": "locomotive", "min": 0, "max": 0.4,
        "help": "0.0 … 0.4，仅机车使用。"}),

    ("cost_factor", "cost", "int", "购置成本系数", {"default": "45", "min": 0,
        "help": "相对系数，最终价格由 GRF 参数 cost 缩放。"}),
    ("running_cost_factor", "cost", "int", "运行成本系数", {"default": "40", "min": 0,
        "help": "会被 GRF 参数 runningcostfactor() 缩放。"}),
    ("purchase_running_cost_factor", "cost", "int", "采购成本中的运行成本", {
        "default": "", "min": 0, "help": "留空则取运行成本系数的三倍。"}),
    ("purchase_cost_display", "cost", "int", "采购价格显示系数", {
        "default": "", "min": 0, "help": "留空则取 cost_factor。"}),
    ("reliability_decay", "cost", "int", "可靠性衰减", {
        "default": "", "applies": "locomotive", "min": 0}),
    ("purchase_speed", "cost", "int", "菜单显示速度", {"default": "", "unit": "km/h", "min": 0}),
    ("purchase_power", "cost", "int", "菜单显示功率", {"default": "", "min": 0}),

    ("refittable_cargo_classes", "cargo", "list", "可改装货物类别", {
        "default": "bitmask(CC_PASSENGERS)", "placeholder": "bitmask(CC_BULK|CC_COVERED)",
        "help": "bitmask(...) 表达式，多个类别用 | 分隔。"}),
    ("non_refittable_cargo_classes", "cargo", "list", "不可改装货物类别", {"default": "0"}),
    ("cargo_allow_refit", "cargo", "list", "允许改装白名单", {
        "default": "[]", "placeholder": "[VEHI|ENSP]"}),
    ("cargo_disallow_refit", "cargo", "list", "禁止改装黑名单", {
        "default": "[]", "placeholder": "[YETI|YETY]"}),
    ("default_cargo_type", "cargo", "enum", "默认货物", {
        "choices": DEFAULT_CARGO, "default": "PASS"}),
    ("ai_special_flag", "cargo", "enum", "AI 特殊标志", {
        "choices": AI_FLAGS, "default": "AI_FLAG_PASSENGER"}),
    ("capacity", "cargo", "int", "载量", {
        "default": "1", "min": 0,
        "help": "可载单位数。机车填 0（不载货）或 1；NML 不允许 property 里写 0，"
                "生成器会自动改用 graphics 的 cargo_capacity 回调按分节下发，"
                "所以 0 是安全的。"}),
    ("capacity_by_cargo", "cargo", "list", "按货物分别载量", {
        "default": "", "placeholder": "COAL=45|IRON=40",
        "help": "LABEL=数值，多个用 | 分隔。填写后回调会先按 cargo_type_in_veh 分支，"
                "未列出的货物取 capacity 的值。"}),
    ("loading_speed", "cargo", "int", "装载速度", {"default": "20", "min": 0}),
    ("cargo_age_period", "cargo", "int", "货物老化周期", {"default": "185", "min": 0}),

    ("train_flags", "systems", "list", "附加列车标志", {
        "default": "", "placeholder": "TRAIN_FLAG_2CC",
        "help": "额外的 TRAIN_FLAG_* 值，多个用 | 分隔。"}),
    ("ac_supply", "systems", "toggle", "供电（本务）", {
        "default": "0", "help": "1 表示该车向整列车供电。"}),
    ("airconditioned", "systems", "toggle", "需供电（空调）", {
        "default": "0", "help": "1 表示该车需要本务供电，舒适度与运行成本随之变化。"}),
    ("restaurant", "systems", "toggle", "餐车", {"default": "0"}),
    ("mu", "systems", "toggle", "动车组车辆", {
        "default": "0", "help": "1 会加上 TRAIN_FLAG_MU 并检查起停长度。"}),
    ("name_callback", "systems", "toggle", "显示系列名", {
        "default": "1", "applies": "locomotive",
        "help": "1 时车厢窗口显示系列名。机车默认开，客货车默认关。"}),
    ("wagon_decay", "systems", "toggle", "套用货车衰减参数", {"default": "0"}),

    ("additional_text", "text", "text-long", "车厢描述", {
        "default": "",
        "placeholder": "留空自动生成标准出口文案",
        "help": "留空则由生成器生成 STR_DESC_EXPORT 引用的标准文案；填写则视为 string(...) 的内部参数，{FULL_NAME} 会展开为 STR_FULL_NAME_<ID>。"}),
    ("comment", "meta", "text-long", "备注", {
        "default": "", "help": "仅供人阅读，生成器完全忽略。"}),
]

# --------------------------------------------------------------------------
# livery / cargo variant tables
# --------------------------------------------------------------------------
LIVERY_FIELDS: List[tuple] = [
    ("id", "identity", "text", "车辆 ID", {
        "required": True, "help": "必须已存在于某张车辆表中。"}),
    ("sprite_suffix", "identity", "text", "精灵图后缀", {
        "default": "", "placeholder": "green",
        "help": "后缀 green 表示模型是 gfx/<folder>/<id>-green.vox；留空表示直接用 <id>。"}),
    ("string", "identity", "text", "涂装名称字符串", {
        "default": "STR_BUILD_YEAR", "placeholder": "STR_EXPORT_BLUE",
        "help": "改装菜单里显示的标签，需要存在于 docs/str.csv。"}),
    ("from_year", "dates", "int", "起始年份", {"default": "0", "min": 0, "help": "0 表示不限。"}),
    ("to_year", "dates", "int", "结束年份", {"default": "9999", "min": 0, "help": "9999 表示不限。"}),
    ("purchase_suffix", "identity", "text", "菜单精灵图后缀", {"default": ""}),
    ("templates", "identity", "list", "分段模板", {
        "default": "", "placeholder": "template_standard|template_standard|template_standard",
        "help": "可选，每段一个模板名，用 | 分隔。"}),
]

VARIANT_FIELDS: List[tuple] = [
    ("id", "identity", "text", "车辆 ID", {
        "required": True, "help": "必须存在于 wagons.csv。"}),
    ("variant", "identity", "text", "外观短名", {
        "required": True, "placeholder": "coal",
        "help": "用于拼接开关标识符，只用小写字母数字下划线。"}),
    ("sprite_suffix", "identity", "text", "精灵图后缀", {
        "default": "", "placeholder": "c70ex-coal",
        "help": "空值表示空车状态，直接使用涂装精灵图。"}),
    ("cargo_classes", "cargo", "list", "货物类别选择器", {
        "default": "bitmask(CC_BULK)", "placeholder": "bitmask(CC_BULK)"}),
    ("cargo_types", "cargo", "list", "货物类型列表", {
        "default": "", "placeholder": "ALUM|COPR|IRON",
        "help": "填写后该行改由 cargo_type_in_veh 选择，而不是货物类别。"}),
    ("from_index", "cargo", "int", "分段起始载量", {"default": "0", "min": 0}),
    ("to_index", "cargo", "int", "分段结束载量", {
        "default": "0", "min": 0, "help": "from_index 与 to_index 都为 0 表示没有分段贴图。"}),
    ("template", "identity", "text", "精灵图模板", {"default": "template_standard"}),
]

RAILTYPE_RE = re.compile(r'^\s*("?[A-Za-z0-9(_]+"?)\s*:\s*\[', re.MULTILINE)
RAILTYPE_ITEM_RE = re.compile(r'"([^"]+)"|([A-Za-z_][A-Za-z0-9_]*)')
RAILTYPE_HEADER_RE = re.compile(r'^railtypetable\s*\{(.*?)\n\}', re.DOTALL | re.MULTILINE)


BLOCK_COMMENT_RE = re.compile(r'/\*.*?\*/', re.DOTALL)
LINE_COMMENT_RE = re.compile(r'//[^\n]*')
WORD_RE = re.compile(r'"([^"]+)"|([A-Za-z_][A-Za-z0-9_]*)')


def railtype_labels() -> List[str]:
    """Every label the railtype table declares, in file order.

    Reads ``src/railtypetable.pnml`` rather than hard-coding the list, so the
    workbench stays correct when the table grows.  Comments are stripped first:
    the file's bilingual comments contain ordinary words that must never be
    mistaken for labels.
    """
    path = ROOT / "src" / "railtypetable.pnml"
    labels: List[str] = []
    seen = set()

    def add(value: str) -> None:
        if value and value not in seen and value != "railtypetable":
            seen.add(value)
            labels.append(value)

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return labels

    text = LINE_COMMENT_RE.sub("", BLOCK_COMMENT_RE.sub("", text))
    match = re.search(r'railtypetable\s*\{(.*)\}', text, re.DOTALL)
    if not match:
        return labels
    body = match.group(1)
    # the leading bare list is "RAIL, ELRL, ..." without any ": [...]" pair
    head, _, rest = body.partition(":")
    for word in WORD_RE.finditer(head):
        add(word.group(1) or word.group(2))
    for definition in RAILTYPE_RE.finditer(":" + rest):
        add(definition.group(1).strip('"'))
    return labels


def _field(name: str, group: str, kind: str, label: str, hints: Dict[str, Any]) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "name": name,
        "group": group,
        "kind": kind,
        "label": label,
        "default": hints.get("default", ""),
        "placeholder": hints.get("placeholder", ""),
        "help": hints.get("help", ""),
        "unit": hints.get("unit", ""),
        "required": bool(hints.get("required", False)),
        "applies": hints.get("applies", "all"),
    }
    for key in ("choices", "min", "max", "dynamic"):
        if key in hints:
            data[key] = hints[key]
    return data


def payload() -> Dict[str, Any]:
    """The complete schema document handed to the browser."""
    return {
        "root": str(ROOT),
        "groups": GROUPS,
        "tables": CITIES,
        "categories": CATEGORIES,
        "category_notes": CATEGORY_NOTES,
        "model_kinds": MODEL_KINDS,
        "power_units": POWER_UNITS,
        "vehicle_fields": [_field(*item) for item in VEHICLE_FIELDS],
        "livery_fields": [_field(*item) for item in LIVERY_FIELDS],
        "variant_fields": [_field(*item) for item in VARIANT_FIELDS],
        "vehicle_columns": [item[0] for item in VEHICLE_FIELDS],
        "livery_columns": [item[0] for item in LIVERY_FIELDS],
        "variant_columns": [item[0] for item in VARIANT_FIELDS],
        "railtypes": railtype_labels(),
        "cargo_classes": CARGO_CLASSES,
        "cargo_labels": cargotype_labels(),
        "graphics_variables": GRAPHICS_VARIABLES,
        "track_type_rule": (
            "首字母轨距：S=1435mm，B=1520mm，D=套轨，N=1067/1000mm，n=762/600mm；"
            "第 2 位速度等级 A…G；第 3 位轴重等级 A…E；末位电气化："
            "N=非电气化，A=25kV 交流，d=1.5kV 直流，(=交流/直流双制，3=第三轨，Z=第三轨/直流。"
        ),
    }


def cargotype_labels() -> List[str]:
    """Cargo labels from ``src/cargotable.pnml``, for the refit whitelists."""
    path = ROOT / "src" / "cargotable.pnml"
    try:
        text = BLOCK_COMMENT_RE.sub("", path.read_text(encoding="utf-8"))
    except OSError:
        return []
    match = re.search(r'cargotable\s*\{(.*)\}', text, re.DOTALL)
    if not match:
        return []
    labels: List[str] = []
    seen = set()
    for word in re.finditer(r'[A-Za-z_][A-Za-z0-9_]*', match.group(1)):
        value = word.group(0)
        if value not in seen:
            seen.add(value)
            labels.append(value)
    return labels


if __name__ == "__main__":
    import json
    print(json.dumps(payload(), ensure_ascii=False, indent=2))
