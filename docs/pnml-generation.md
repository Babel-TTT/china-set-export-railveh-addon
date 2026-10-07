# PNML 自动生成说明

本文说明 `genpnml.py` 如何按照 China-Set-Trains 的 PNML（NML）结构，
**从数据表与模型文件自动生成机车与车厢代码**。

---

## 1. 总体数据流

```
data/*.csv          ──┐
                       ├─► genpnml.py ─► src/usercode.pnml      （开关 / 精灵集 / item）
gfx/**/*.vox        ──┘                ├─► src/vehicleid.pnml   （车辆 ID）
                                       ├─► src/vehiclesort.pnml （采购菜单排序）
                                       ├─► docs/str.csv         （语言字符串）
                                       └─► gfx/<目录>/*.vox     （占位模型，含 manifest.json）

gfx/**/*.vox   ──renderobject──► gfx/**/*_32bpp.png
docs/str.csv   ──str-csv.py────► lang/*.lng
chinasettrainsexport.pnml ──gcc -E──► .nml ──nmlc──► .grf
```

一条命令即可完成全部生成：`make gen`；完整构建：`make`。

---

## 2. 生成的 PNML 结构

`src/usercode.pnml` 严格遵循母包的书写顺序，分为三段：

```text
/* SWITCHES   (callbacks, livery and cargo selection) */
switch (FEAT_TRAINS, SELF, switch_<id>_articulated_part, extra_callback_info1) {...}
switch (FEAT_TRAINS, SELF, switch_<id>_livery_auto, build_year) {...}
switch (FEAT_TRAINS, SELF, switch_<id>_livery, cargo_subtype) {...}
switch (FEAT_TRAINS, SELF, switch_<id>_graphics, position_in_articulated_veh % 3) {...}
switch (FEAT_TRAINS, SELF, switch_<id>_capacity, ...) {...}
switch (FEAT_TRAINS, SELF, switch_<id>_weight, ...) {...}

/* SPRITESETS */
spriteset (spriteset_<id>, ZOOM_LEVEL_IN_4X, BIT_DEPTH_32BPP) {
    template_standard ("<folder>", "<basename>")
}
spriteset (spriteset_<id>_purchase, ...) { template_purchase ("<folder>", "<basename>") }
spriteset (spriteset_<id>_<涂装>, ...) {...}
spriteset (spriteset_<id>_<货物>_<涂装>, ...) {...}

/* VEHICLES */
item (FEAT_TRAINS, <id>) {
    property { ... }
    graphics { ... }
}
```

### 2.1 三节铰接（articulated）机制

母包约定：一辆车在游戏中是 **前 2 + 本体 N + 后 2** 三段。
生成器据此产出标准三件套：

| 生成物 | 作用 |
| ------ | ---- |
| `switch_<id>_articulated_part` | `extra_callback_info1` 为 `1..N` 时 `return <id>`，即重复挂接自身 |
| `switch_<id>_graphics` | `position_in_articulated_veh % <段数>`，只在 `power_section` 段返回车体，其余段返回 `empty_sprites` |
| `switch_<id>_capacity` | 同上，只在 `power_section` 段返回载量，其余段返回 `0` |

`model=single` 的车辆不生成这三者。

### 2.2 涂装（livery）机制

涂装表 `data/liveries.csv` 的行序即涂装索引：

* 索引 0 = 自动涂装。若存在**真实年份区间**的涂装，则生成
  `switch_<id>_livery_auto`，以 `build_year` 选择；最早的那一款作为默认。
* 区间 `0..9999` 视为"始终可用"，不单独占一个 case，避免
  `Range overlaps with existing ranges` 警告（这是母包中存在的问题，本包已避免）。
* 索引 1..n = 玩家可在改装菜单中显式选择的涂装，由
  `switch_<id>_livery`（`cargo_subtype`）分派，文字由
  `switch_<id>_cargo_subtype` 返回。

每款涂装需要独立精灵，基名为 `<id>-<涂装后缀>`；`genpnml.py --vox`
会为它们生成颜色不同的占位模型。

### 2.3 货物外观（freight appearance）机制

`data/cargo_variants.csv` 会被编译为母包同款的链条：

```text
switch_<id>_empty            cargo_count < 5     →  空车 / 车体精灵
switch_<id>_cargo_class      cargo_classes       →  按货物类别
switch_<id>_cargo_type       cargo_type_in_veh   →  按具体货种（有 cargo_types 的行）
switch_<id>_<变体>_stage     cargo_count         →  半载 / 满载
```

多涂装货车会为**每套涂装**生成独立链条，开关名带涂装后缀：
`switch_c70ex_gray_cargo_class` 等。

### 2.4 其他自动生成的开关

| 生成物 | 说明 |
| ------ | ---- |
| `switch_<id>_weight` | 整备重量按段均分（NML 不接受 switch 默认位的表达式，故此处预算为整数） |
| `switch_<id>_power` | 功率只放在 `power_section` 段 |
| `switch_<id>_visual` | `visual_effect_and_powered()`，仅对有供电能力的机车/发电车生成 |
| `switch_<id>_cargo_subtype` | 涂装文字回调，仅多涂装车辆生成 |

---

## 3. 数据表

完整列说明见 [data/README.md](../data/README.md)。最小可用的一行只需要：

```csv
id,name_string,category,folder,model,parts,power_section,intro_year,...,speed,...
newloco,New Loco (Export),diesel,diesel,single,6,0,2020,...,120,...
```

生成器会自动完成：

1. 在 `src/vehicleid.pnml` 的对应类别区段内分配一个**空闲 ID**（不会与既有车辆冲突）；
2. 在 `src/vehiclesort.pnml` 中把它排到所属类别的顺序位置；
3. 生成全部 `switch` / `spriteset` / `item`；
4. 在 `docs/str.csv` 中补齐 `STR_NAME_<ID>`、`STR_FULL_NAME_<ID>`；
5. 在 `gfx/<folder>/` 生成占位 `.vox`（含该目录的 `manifest.json` 与 `ttd_palette.json`）。

### 为什么 ID 不写进 CSV

ID 由生成器在类别区段内顺序分配，因此：

* 两辆车不可能撞号；
* 新增一行不会重排其他车辆；
* 区段划分与《中国包：火车》保持一致（客车 2048 起、货车 3072 起、内燃 5120 起、
  电力 6144 起、动车组 9216 起……），所以本包与母包的 ID 语义可以互相对应。

---

## 4. NML 语法约束（踩过的坑）

这些是实际编译验证中确定的约束，生成器已全部规避：

| 约束 | 处理方式 |
| ---- | -------- |
| `string()` 的参数**只能是字符串**，不能是整数 | 购买界面文字 `STR_DESC_EXPORT` 只用 3 个 `{STRING}` 槽（全名、涂装、类别），数值信息交给游戏自带的车辆属性栏显示 |
| `string()` 不接受空字符串字面量 `""` | 生成器始终传入真实的 `STR_` 常量 |
| switch 的 case 与 default **不能相同** | 有年份区间的涂装用"默认 = 最早一款"，其余年份才生成 case |
| switch 的**默认位不接受表达式** | 重量在生成器内预先算成整数 |
| switch 默认位若相当于常量会被优化 | 无害，但已尽量减少 |
| `spriteset` 名必须是合法标识符 | 货物变体后缀中的 `-` 会转成 `_` |
| 一个 switch 的 fallback 后面**必须有分号** | emitter 统一补分号 |
| `empty.png` 必须是带调色板的 8bpp 索引图 | 直接使用仓库内的文件，生成器不再覆盖 |
| `renderobject` 从 `.vox` 所在目录读取 `manifest.json` 与 `ttd_palette.json` | 生成器为每个 `gfx/` 子目录都写一份 |

---

## 5. 扩展指南

### 5.1 增加一辆车

1. 在 `data/locomotives.csv`（或 `coaches.csv` / `wagons.csv` / `unit_wagons.csv`）
   增加一行；
2. 如需涂装，在 `data/liveries.csv` 增加若干行；
3. 如需按货物改变外观，在 `data/cargo_variants.csv` 增加若干行；
4. `make gen`；
5. 用真实美术替换 `gfx/<目录>/<基名>.vox`，`make` 即可。

### 5.2 增加一种货物外观

只要在 `cargo_variants.csv` 里增加一行（`sprite_suffix` 指向新的精灵基名），
生成器便会自动补齐对应的 `_stage` 开关与 `spriteset`。

### 5.3 增加一辆车的新涂装

在 `liveries.csv` 里为同一个 `id` 追加一行，`sprite_suffix` 用新的后缀，
`make gen` 后即出现在改装菜单；`--vox` 会为新后缀生成颜色不同的占位模型。

### 5.4 生成器改写点

| 需求 | 修改位置 |
| ---- | -------- |
| 增加数据列 | `Vehicle` dataclass + `_build_vehicle()` + `render_item()` |
| 改变 PNML 版式 | `Emitter` / `render_usercode()` / `render_item()` |
| 改变 ID 区段 | `BANDS` 与 `BAND_COMMENT` |
| 改变购买界面文字 | `build_additional_text()` 与 `STATIC_STRINGS` |
| 改变占位模型形状 | `build_placeholder_vox()` 与 `SUFFIX_COLOUR` |

---

## 6. 命令速查

```bash
make                     # 生成 + 渲染 + 语言 + 编译
make -j 8                # 并行构建
make gen                 # 仅从 data/ 生成 PNML 与占位 .vox
make sprites             # 仅渲染 .vox → .png
make lang                # 仅从 docs/str.csv 生成 lang/*.lng
make clean               # 清理构建产物
make clean_gen           # 删除生成的 PNML

python3 genpnml.py --data data --out src --vox   # 等价于 make gen
python3 genpnml.py --strings                     # 刷新 docs/str.csv（保留已有译文）
python3 genpnml.py --clean                       # 删除生成的 PNML
python3 tools/build_data_tables.py               # 重新生成 data/*.csv（保证 CSV 引号正确）
python3 tools/verify_assets.py                   # 校验：PNML 引用的精灵是否都存在
```
