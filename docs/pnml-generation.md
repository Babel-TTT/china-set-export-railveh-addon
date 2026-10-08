# PNML 自动生成说明

本文说明 `genpnml.py` 如何按照 China-Set-Trains 的 PNML（NML）结构，
**从数据表与模型文件自动生成机车与车厢代码**。

---

## 1. 总体数据流

```
data/*.csv          ──┐
                       ├─► genpnml.py ─┬─► src/vehiclefiles.pnml   （include 清单）
gfx/**/*.vox        ──┘                ├─► src/<目录>/<id>.pnml   （一辆车一个文件）
                                       ├─► src/vehicleid.pnml     （车辆 ID）
                                       ├─► src/vehiclesort.pnml   （采购菜单排序）
                                       ├─► docs/str.csv           （语言字符串）
                                       └─► gfx/<目录>/*.vox       （你的体素模型 + manifest）

gfx/**/*.vox   ──renderobject──► gfx/**/*_32bpp.png
docs/str.csv   ──str-csv.py────► lang/*.lng
chinasettrainsexport.pnml ──gcc -E──► .nml ──nmlc──► .grf
```

一条命令即可完成全部生成：`make gen`；完整构建：`make`。

### 1.1 一辆车一个文件

与《中国包：火车》一致，每辆车输出到独立的 `src/<目录>/<id>.pnml`：

```
src/diesel/ckd4a.pnml
src/diesel/df4bex.pnml
src/25-electric/ss8ex.pnml
src/coaches/yz25tex.pnml
src/wagons/c70ex.pnml
```

`src/vehiclefiles.pnml` 是这些文件的 include 清单，**顺序即采购菜单顺序**；
主索引只 include 这一个文件：

```c
// chinasettrainsexport.pnml
#include "src/vehiclefiles.pnml"   // 内含每辆车的 #include
#include "src/vehiclesort.pnml"
```

由此得到的好处：

* 改一辆车只动一个文件，git diff 干净，多人协作不易冲突；
* 删除数据表里的一行后，`make gen` 依据 `src/.genpnml-manifest` 把对应的
  `.pnml` 一并删除，不会留下孤儿文件；
* 新增车辆时主索引**完全不变**。

> 注意 include 路径是相对**索引文件**解析的，所以 `vehiclefiles.pnml` 里写的是
> `#include "diesel/ckd4a.pnml"`，**不能**再带 `src/` 前缀（否则 gcc 会去找
> `src/src/...`）。

---

## 2. 生成的 PNML 结构

每个 `src/<目录>/<id>.pnml` 严格遵循母包的书写顺序，分为三段：

```text
/* SWITCHES   (callbacks, per section graphics, livery and cargo selection) */
switch (FEAT_TRAINS, SELF, switch_<id>_articulated_part, extra_callback_info1) {...}
switch (FEAT_TRAINS, SELF, switch_<id>_section_<涂装序号>, position_in_articulated_veh % 3) {...}
switch (FEAT_TRAINS, SELF, switch_<id>_graphics, cargo_subtype) {...}
switch (FEAT_TRAINS, SELF, switch_<id>_capacity, position_in_articulated_veh % 3) {...}
switch (FEAT_TRAINS, SELF, switch_<id>_visual, position_in_articulated_veh % 3) {...}
/* 有分节规则时还会多出 switch_<id>_<涂装序号>_<段序号>（以及嵌套的 _<n>、串联的 _next）这样的规则开关 */
/* 设了 series_string 时还会多出 switch_<id>_name（购买菜单折叠项的名字回调，见 2.5） */

/* SPRITESETS */
spriteset (spriteset_<id>, ZOOM_LEVEL_IN_4X, BIT_DEPTH_32BPP) {
    template_standard ("<folder>", "<basename>")
}
spriteset (spriteset_<id>_purchase, ...) { template_purchase ("<folder>", "<basename>") }
spriteset (spriteset_<id>_<涂装>, ...) {...}
spriteset (spriteset_<id>_<货物>_<涂装>, ...) {...}

/* VEHICLE */
item (FEAT_TRAINS, <id>) {
    property { ... }
    graphics { ... }
}
```

注意：`property` 块里的 `power`、`weight`、`speed` 都是**整车属性**，
没有对应的每段开关；只有 `cargo_capacity` 会写成按段分派的开关。

### 2.1 三节铰接（articulated）机制

本包约定：一辆车在游戏中是 **前 2 + 车身 N + 后 2** 共三段。生成器据此产出：

| 生成物 | 作用 |
| ------ | ---- |
| `switch_<id>_articulated_part` | `extra_callback_info1` 为 `1..N` 时 `return <id>`，即重复挂接自身 |
| `switch_<id>_section_<涂装序号>` | `position_in_articulated_veh % <段数>`；涂装没填 `graphics_parts` 时只在 `power_section`（车身段）返回该涂装的图，其余段返回 `empty_sprites`；填了规则则每一段各有一个 case（见 2.2） |
| `switch_<id>_graphics` | 多涂装时用 `cargo_subtype` 把上面的分段开关分派给对应涂装 |
| `switch_<id>_capacity` | `position_in_articulated_veh % <段数>`，只在 `power_section` 段返回载量，其余段返回 `0` |

`power_section` 只决定**哪一段是车身段**。功率与重量是整车属性，
直接写成 `power: 2165 kW;` / `weight: 92 ton;`，**不经过任何开关**，
也不按段下发——OpenTTD 唯一按段读取的是 `cargo_capacity`。

如果某个涂装填了 `graphics_parts`，那一段的分段开关就换成规则链，
而不是「只有车身段出图」；规则链怎么编出来见下一节。

### 2.2 分节图像规则（`graphics_parts`）如何变成开关

涂装的 `graphics_parts` 一格按 `;` 分成**与 `parts` 段数相同**的份数，每份是若干条
`条件=条件=…=贴图基名` 的规则（末尾的 `;` 也算一份，空份表示该段隐形）。条件里的变量
短名（`pos`）与完整 NML 名（`position_in_consist`）都能写，运算符两侧空格可有可无；
一个条件要么是「变量 比较 数字」（`pos<=2`、`pos==0`、`tailpos>=3`），要么是
「变量 区间」（`pos=3..8`，也可以写成 `pos 3..8`，两头都算）。`<` 和 `>` 是
`<=` / `>=` 的糖（`pos>2` 就是 `pos>=3`），写回单元格时会被规范化成后者。
生成器先把规则**按书写顺序**合并成一棵**开关树**，再展开成 **NML 的嵌套开关**：
一个条件一层开关，一个 case 一张图。

| 规则写法 | 编成什么 |
| -------- | -------- |
| 同一变量的多个区间 | **一个开关的多个 case**，自上而下试：`pos<=2=a \| pos>2=b` → `0..2` 与 `3..255` |
| 同一变量上一个两头都有界的区间 | 就是**一个 case**：`pos=3..8` → `3..8`。`pos>=3` 与 `pos<=8` 是两个条件，而同一条路径上同一个变量只能选一次，所以这是比较运算符写不出来的形状 |
| 换成另一个变量 | 上一个开关的 **default** 指向新开关，两个开关**串联**（链到下一层） |
| 停在半路上的规则 | 它就是「停在哪一层」那个开关的 default |
| 裸基名（完全没有条件） | 整段的兜底，即最深那个开关的 default |
| 整段一个条件都没有 | **不生成开关**，这一段直接是一张精灵集 |

**没有「单分支折叠」这回事。** 只要写了条件，哪怕只有一个区间也会生成开关——
default 正是「条件不满足时怎么办」的出口。单条件开关长这样：

```c
/* graphics_parts = ;consist<=6=h_s | h_l; 的第 2 段 */
switch (FEAT_TRAINS, SELF, switch_<id>_<涂装序号>_1, num_vehs_in_consist) {
    0..6: return spriteset_<id>_gfx_h_s;
    return spriteset_<id>_gfx_h_l;      /* 裸基名 h_l 是整段的兜底 */
}
```

**嵌套**（先看编组长短，再看位置）与**串联**（换变量继续判断）各看一例：

```c
/* consist<=6=pos<=2=h_s | consist<=6=h_l | b_l */
switch (FEAT_TRAINS, SELF, switch_<id>_<涂装序号>_0_0, position_in_consist) {
    0..2: return spriteset_<id>_gfx_h_s;
    return spriteset_<id>_gfx_h_l;      /* 停在半路 = 这一层的 default */
}
switch (FEAT_TRAINS, SELF, switch_<id>_<涂装序号>_0, num_vehs_in_consist) {
    0..6: return switch_<id>_<涂装序号>_0_0;
    return spriteset_<id>_gfx_b_l;      /* 裸基名 = 整段的兜底 */
}

/* pos<=2=set_head | tailpos<=2=set_tail | set_mid */
switch (FEAT_TRAINS, SELF, switch_<id>_<涂装序号>_0_next,
        position_in_consist_from_end) {
    0..2: return spriteset_<id>_gfx_set_tail;
    return spriteset_<id>_gfx_set_mid;
}
switch (FEAT_TRAINS, SELF, switch_<id>_<涂装序号>_0, position_in_consist) {
    0..2: return spriteset_<id>_gfx_set_head;
    return switch_<id>_<涂装序号>_0_next;   /* 换变量 → 链到下一层 */
}
```

开关命名：

```text
switch_<id>_section_<涂装序号>        position_in_articulated_veh % <段数>，一段一个 case
switch_<id>_<涂装序号>_<段序号>       该段的第一个条件
switch_<id>_<涂装序号>_<段序号>_<n>   该段里嵌套的第 n 个分支
switch_<id>_<涂装序号>_<段序号>_next  链到下一个变量的开关
```

**哪一段画什么**：只要这一格非空，分段开关就给每一段一个 case；某一段没有规则、
或规则一个区间都没命中，该段返回 `empty_sprites`（隐形）。整格留空是另一条路：
只有 `power_section` 段返回涂装自己的整图，其余段 `empty_sprites`。

会被当场拒绝的写法：份数与 `parts` 不符；同一个变量在同一条判定路径上出现两次；
一个条件写了两个不同基名；后写的区间被前面的完全覆盖；条件不是「变量 比较 数字」
或「变量 区间」（含 `!=`、`!`、条件内的 `&`、算式），以及区间写反了（`pos=8..3`）。
**条件本身写错时报的是具体原因**（`条件 'pos<0' 永远不成立`、
`区间 'pos=8..3' 的低值 8 比高值 3 大，永远不会匹配；请把小的写在前面`）；只有
**基名**写错时才报那句通用的「基名只能用小写字母、数字、下划线和连字符」。
基名就是贴图基名，涂装表里的 `df4c-korea-1`、`tm2-a` 可以直接写；但 `-` 与 `_` 会折成
同一个 NML 标识符，两个只差这一点的基名（`a-b` 与 `a_b`）会撞在同一个精灵集上，
生成器会直接报错而不是让其中一张图悄悄失效。语法与原文见
[操作指南第 7 章](guide-zh.md#7-分节图像规则怎么填)，
`tools/check_graphics_parts.py` 会把每种写法生成出来用 nmlc 编译一遍。

### 2.3 涂装（livery）机制

涂装表 `data/liveries.csv` 的行序即涂装索引：

* 索引 0 = 自动涂装。若存在**真实年份区间**的涂装，则生成
  `switch_<id>_livery_auto`，以 `build_year` 选择；最早的那一款作为默认。
* 区间 `0..9999` 视为"始终可用"，不单独占一个 case，避免
  `Range overlaps with existing ranges` 警告（这是母包中存在的问题，本包已避免）。
* 索引 1..n = 玩家可在改装菜单中显式选择的涂装，由
  `switch_<id>_livery`（`cargo_subtype`）分派，文字由
  `switch_<id>_cargo_subtype` 返回。

每款涂装需要独立精灵，基名为 `<id>-<涂装后缀>`，模型由你自己画好放进该目录；
`make gen` 会列出还缺哪些。

涂装标签写成 `LV_<名字>`，映射为 `docs/str.csv` 里的 `STR_LV_<名字>`。

`graphics_parts` 属于涂装：每个涂装各自决定每一段在整列的什么位置显示哪张图
（怎么变成开关见 2.2）。
它支持把某个涂装的分段链换掉，因此同一个 `id` 的不同涂装可以有不同的头脸。

### 2.4 货物外观（freight appearance）机制

`data/cargo_variants.csv` 会被编译为母包同款的链条：

```text
switch_<id>_empty            cargo_count < 5     →  空车 / 车体精灵
switch_<id>_cargo_class      cargo_classes       →  按货物类别
switch_<id>_cargo_type       cargo_type_in_veh   →  按具体货种（有 cargo_types 的行）
switch_<id>_<变体>_stage     cargo_count         →  半载 / 满载
```

多涂装货车会为**每套涂装**生成独立链条，开关名带涂装后缀：
`switch_c70ex_gray_cargo_class` 等。

### 2.5 购买菜单：分组、排序与两级名字

数据表最后三列直接决定购买菜单的呈现：

| 列 | 生成物 |
| -- | ------ |
| `variant_group` | `item { property { variant_group: <父项 id>; } }`，即 OpenTTD 13 的分组属性（自动替换菜单也按它分组） |
| `menu_order` | `src/vehiclesort.pnml` 的 `sort (FEAT_TRAINS, [...])` 里的位置 |
| `series_string` | 这台车自己的名字回调 `switch_<id>_name` |

`variant_group` 填的是**另一台车的 id**（不是引擎编号），NML 会把它解析成引擎 ID，
所以 ID 怎样重排都不影响分组：

```nml
item (FEAT_TRAINS, <id>) {
    property {
        // Purchase menu group: shown under <parent>
        variant_group:                  <parent>;
    }
    ...
}
```

排序规则在 `render_vehiclesort()`：按 `(menu_order, 载入序号)` 排，留空（或 `0`）
的车当作无穷大、排在所有设了顺序的车之后并按表序，结果写进 `src/vehiclesort.pnml`
的 `sort` 块（每个类别前带一行注释）。
**它故意不是分配 ID 的顺序**：`assign_ids()` 按行序依次发号，把菜单顺序单独做成一列，
正是为了不去动 `src/vehicleid.pnml` 里的引擎 ID——存档记的是引擎 ID，重排行序会让
存档里的车对不上号。

设了 `series_string` 的车多一个 `switch_<id>_name`（`emit_name_switch()`）：

```nml
switch (FEAT_TRAINS, SELF, switch_<id>_name, getbits(extra_callback_info1, 0, 8) == 0x20? getbits(extra_callback_info1, 8, 8) : 0xFFFF) {
    0: return string(STR_...);
    return CB_RESULT_NO_TEXT;
}
```

0 号槽是购买菜单问「折叠项叫什么」时用的槽，其余槽回 `CB_RESULT_NO_TEXT`，于是
`property` 里的 `name: string(STR_NAME_<ID>)` 仍然管组内那一行：同一台车在折叠行
显示系列名、在组里显示自己的车名。没设 `series_string` 但开了 `name_callback` 的车
共用 `src/functions.pnml` 的 `switch_name_series`。

`series_string` 必须是 `docs/str.csv` 里已有的 `STR_` 常量。`collect_referenced_strings()`
把它算作引用，`--check` 因此会报 `MISSING`，而不是留到 nmlc 报 `Unknown string`。
这个函数**递归遍历 `src/`**：生成的车辆文件在 `src/<folder>/<id>.pnml`，
子目录里的文件同样会被扫到。

分组本身由 `check_variant_groups()` 把关：父项必须存在**于同一张表**、不能是自己、
不能成环；父项自己也分组只是**警告**（上游把嵌套标为实验性）。工作台保存时调用的
就是同一个函数，所以两边不会各说各话。

### 2.6 其他自动生成的开关

| 生成物 | 说明 |
| ------ | ---- |
| `switch_<id>_visual` | `visual_effect_and_powered()`，仅对有供电能力的机车/发电车生成；特效只出现在 `power_section` 段 |
| `switch_<id>_cargo_subtype` | 涂装文字回调，仅多涂装车辆生成 |
| `switch_<id>_capacity_cargo` | 填了 `capacity_by_cargo` 时，按 `cargo_type_in_veh` 分派载量 |
| `switch_<id>_start_stop` | 填了 `min_cars` 且 `mu=1` 时，检查编组长度 |

**没有** `switch_<id>_power` 和 `switch_<id>_weight`：功率与重量都是整车普通属性。

---

## 3. 数据表

完整列说明见 [data/README.md](../data/README.md)。最小可用的一行只需要：

```csv
id,name_string,category,folder,parts,power_section,intro_year,...,speed,...
newloco,New Loco (Export),diesel,diesel,2|8|2,1,2020,...,120,...
```

生成器会自动完成：

1. 在 `src/vehicleid.pnml` 的对应类别区段内分配一个**空闲 ID**（不会与既有车辆冲突）；
2. 在 `src/vehiclesort.pnml` 中按 `menu_order` 把它排进购买菜单顺序（没设的车按表序排在最后，见 2.5）；
3. 生成全部 `switch` / `spriteset` / `item`；
4. 在 `docs/str.csv` 中补齐 `STR_NAME_<ID>`、`STR_FULL_NAME_<ID>`；
5. 准备好 `gfx/<folder>/`：写出该目录的 `manifest.json` 与 `ttd_palette.json`
   （目录不存在就建），并列出**还缺哪些 `.vox`**。

注意第 5 步：**生成器不造占位模型**。模型是作者的美术资源，由你自己画好放进
`gfx/<folder>/`；缺失的会被打印出来，`tools/verify_assets.py` 也会再列一遍，
nmlc 在找不到 `_32bpp.png` 时报错。

**`make gen` 只刷新字符串表并生成代码，从不写 `.vox`。** 所以工作顺序是
「先有模型，再往表里加车」：`make gen` 告诉你还缺哪些模型，把它们画好放进
`gfx/<folder>/`，再 `make sprites` / `make` 渲染与编译。

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
`make gen` 后即出现在改装菜单；新后缀需要的 `.vox` 会被列出来，画好即可。

### 5.4 生成器改写点

| 需求 | 修改位置 |
| ---- | -------- |
| 增加数据列 | `Vehicle` dataclass + `_build_vehicle()` + `render_item()` |
| 改变 PNML 版式 | `Emitter` / `render_vehicle_file()` / `render_item()` |
| 改变文件组织方式 | `vehicle_file_path()` 与 `render_vehiclefiles()` |
| 改变 ID 区段 | `BANDS` 与 `BAND_COMMENT` |
| 改变购买界面文字 | `build_additional_text()` 与 `STATIC_STRINGS` |
| 改变购买菜单的分组与排序 | `render_item()`（`variant_group` 属性）/ `render_vehiclesort()` / `check_variant_groups()` |
| 改变精灵图基名的推导规则 | `collect_sprite_basenames()` |
| 增加输入校验 | `validate_vehicles()` |

---

## 6. 命令速查

```bash
make                     # 生成 + 渲染 + 语言 + 编译
make -j 8                # 并行构建
make gen                 # 刷新语言表 + 从 data/ 生成 PNML + 补齐 gfx 目录
make check               # 校验字符串表
make sprites             # 仅渲染 .vox → .png
make lang                # 仅从 docs/str.csv 生成 lang/*.lng
make clean               # 清理构建产物
make clean_gen           # 删除生成的所有 PNML（按清单）

python3 genpnml.py --data data --out src          # 生成
python3 genpnml.py --strings                     # 刷新 docs/str.csv（保留已有译文）
python3 genpnml.py --check                       # 校验字符串表
python3 genpnml.py --clean                       # 删除生成的 PNML
python3 tools/vehicle_row.py …                   # 安全地增删/复制数据行
python3 tools/build_data_tables.py               # 重新生成 data/*.csv
python3 tools/verify_assets.py                   # 校验：PNML 引用的精灵是否都存在
python3 tools/check_graphics_parts.py            # 每种 graphics_parts 写法都生成并用 nmlc 编译一遍
python3 tools/check_section_lengths.py           # 每种 parts 形状都生成并用 nmlc 编译一遍
python3 tools/check_gfx_config.py                # manifest.json / ttd_palette.json 是否与生成器一致
python3 tools/check_string_table.py              # 字符串表的读写与引用是否自洽
python3 tools/check_variant_menu.py              # 临时造一台折叠车、完整编译一遍，检查购买菜单三列
python3 tools/check_workbench_routes.py          # 工作台前端调的每个 API 路径，服务端都真的有这条路由
python3 tools/check_markdown_tables.py           # 文档：表格列数是否对齐、文件是否是 UTF-8
python3 tools/check_purchase_sprite.py           # 购买菜单小图能否单独指定一张图（完整编译一遍验证）
python3 tools/migrate_menu_columns.py            # 给四张车辆表补上购买菜单的三列（只补缺的列）
```

这几个检查脚本都会自己恢复它们改动过的数据表，并在收尾时按恢复后的表重新生成代码
（`check_gfx_config.py` 只读，不改任何东西），所以在有改动的工程里直接跑也安全。
