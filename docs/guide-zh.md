# 操作指南

本文是《中国包：出口铁路载具附加包》的完整操作手册。
如果你只想**加一辆车**，直接看[第 4 章](#4-加一辆新车完整流程)；
想**画模型**看[第 5 章](#5-制作模型vox)；
**出错**看[第 10 章](#10-疑难排查)。

---

## 目录

1. [环境准备](#1-环境准备)
2. [五分钟上手](#2-五分钟上手)
3. [工程结构与生成物](#3-工程结构与生成物)
4. [加一辆新车（完整流程）](#4-加一辆新车完整流程)
5. [制作模型（.vox）](#5-制作模型vox)
6. [加涂装与货物外观](#6-加涂装与货物外观)
7. [分节图像规则怎么填](#7-分节图像规则怎么填)
8. [购买菜单：分组与排序](#8-购买菜单分组与排序)
9. [校核实车数据](#9-校核实车数据)
10. [疑难排查](#10-疑难排查)
11. [命令速查](#11-命令速查)

---

## 1. 环境准备

### 1.1 必需工具

| 工具 | 用途 | 本机实测版本 |
| ---- | ---- | ------------ |
| `python3` | 运行生成器、语言表脚本 | 3.12.14 |
| `make` | 构建驱动 | GNU Make 4.4.1 |
| `gcc` | 预处理 `.pnml` → `.nml` | 13.2.0 |
| `nmlc` | 编译 `.nml` → `.grf` | 0.9.0 |
| `renderobject`（或 `gorender`） | 渲染 `.vox` → `.png` | — |
| `git` | 版本管理、生成版本号 | 2.45.2 |

### 1.2 安装

**Windows（推荐 scoop）**

```powershell
scoop bucket add main
scoop bucket add openttd https://github.com/WenSimEHRP/OpenTTD-Bucket
scoop install python
scoop install make
scoop install openttd/nml
scoop install openttd/gorender
scoop install mingw
```

**Linux / WSL**

```bash
sudo apt install python3 make gcc
pip3 install nml
# gorender 需从 https://github.com/mattkimber/gorender 自行编译
```

### 1.3 如果工具不在 PATH 里

复制一份 `Makefile.config` 并取消注释相应行，例如：

```make
PYTHON   ?= C:/Python312/python.exe
NMLC     ?= G:/NMLC/nmlc.exe
GORENDER ?= renderobject --palette "ttd_palette.json" -overwrite
```

`Makefile.config` 会被 `Makefile` 以 `-include` 方式读入，**不会**被 git 跟踪以外的任何流程修改。

### 1.4 验证工具链

```bash
python3 --version
make --version
gcc --version
nmlc --version
renderobject --help
```

五个都正常输出即可。

---

## 2. 五分钟上手

> ### ⚠️ 当前工程是空的
>
> 车辆数据表**已经被清空**：`data/` 下 6 个 CSV 只剩表头与说明注释，`gfx/` 里
> 没有任何 `.vox` 模型。工程骨架、生成器、共享库、构建系统、轨道与货物表、
> 文档全部保留且可用。
>
> 现在 `make` 依然能成功，产出的是一个**不含任何车辆**的 GRF
> （参数、轨道类型、货物类型都在，只是没有车）。
> 想看到车，按[第 4 章](#4-加一辆新车完整流程)加第一行数据即可。
> 空工程正是为了让你从实车数据开始录入。

```bash
cd china-set-export-railveh-addon

make -j 8          # 生成代码 + 渲染模型 + 生成语言 + 编译
```

有车之后，首次构建会渲染所有模型，需要几分钟；之后是增量的，很快。

产物：

```
chinasettrainsexport.grf        ← 游戏用文件（空工程约 13 KB）
chinasettrainsexport.nml        ← 预处理后的 NML（中间产物，排查错误时看它）
custom_tags.txt                 ← 版本标记
lang/english.lng                ← 语言文件（生成物）
lang/simplified_chinese.lng
```

把 `chinasettrainsexport.grf` 放进 OpenTTD 的 `newgrf` 目录，在游戏 **NewGRF 设置**里启用。注意：

> **必须开启 `dynamic_engines`。** 否则 GRF 加载时会直接报致命错误。
> 控制台输入：`set dynamic_engines 1`
>
> **需要 OpenTTD 13.1 或更高版本**（用到了 variants 与 name callback）。
>
> 建议同时启用《中国包：火车》和《中国包：窄轨附加包》——三个包的车辆可以互相编组。

---

## 3. 工程结构与生成物

### 3.1 目录一览

```
china-set-export-railveh-addon/
├── Makefile                      构建驱动
├── Makefile.config               本地工具路径覆盖（可选）
├── genpnml.py                    ★ 核心：PNML 生成器
├── str-csv.py                    docs/str.csv → lang/*.lng
├── chinasettrainsexport.pnml     ★ 构建入口（gcc -E 的对象）
├── ttd_palette.json              TTD 调色板
├── min_compatible_version        最低兼容版本的 git 提交号
│
├── data/                         ★ 你主要编辑的地方
│   ├── README.md                 逐列数据字典
│   ├── locomotives.csv           机车 / 动车头车
│   ├── coaches.csv               客车
│   ├── wagons.csv                货车
│   ├── unit_wagons.csv           动车组拖车
│   ├── liveries.csv              涂装（可选）
│   └── cargo_variants.csv        货物外观（可选）
│
├── src/
│   ├── header.pnml               ★ 手写：GRF 头、参数、basecost
│   ├── template.pnml             ★ 手写：精灵模板
│   ├── railtypetable.pnml        ★ 手写：轨道类型表
│   ├── cargotable.pnml           ★ 手写：货物表
│   ├── functions.pnml            ★ 手写：共享开关库
│   ├── vehicleid.pnml            ⚙ 生成：车辆 ID
│   ├── vehiclefiles.pnml         ⚙ 生成：每辆车文件的 include 清单
│   ├── vehiclesort.pnml          ⚙ 生成：采购菜单排序
│   ├── diesel/ckd4a.pnml         ⚙ 生成：**一辆车一个文件**
│   ├── diesel/df4bex.pnml
│   ├── 25-electric/ss8ex.pnml
│   ├── coaches/yz25tex.pnml
│   ├── wagons/c70ex.pnml
│   └── …                         每个类别一个目录
│
├── gfx/                          ★ 模型与精灵
│   ├── manifest.json             gorender 渲染参数（每个子目录一份）
│   ├── ttd_palette.json
│   ├── empty.png / empty_32bpp.png
│   ├── diesel/                   内燃机车
│   ├── 25-electric/              25kV 电力机车
│   ├── steam/                    蒸汽机车
│   ├── dmu/ emu 目录…            动车组
│   ├── coaches/                  客车
│   ├── wagons/                   货车
│   └── unit-wagons/              动车组拖车
│
├── docs/
│   ├── str.csv                   ★ 语言字符串表
│   ├── guide-zh.md               本文
│   ├── pnml-generation.md        生成原理说明（进阶阅读）
│   ├── readme.txt changelog.txt license.txt contributor.csv
│
└── tools/
    ├── vehicle_row.py            ★ 安全地增删/复制数据行（自动处理 CSV 引号）
    ├── clear_vehicle_data.py     ★ 清空全部车辆数据与体素模型
    ├── build_data_tables.py      只重建 liveries.csv 与 cargo_variants.csv
    ├── verify_assets.py          校验：PNML 引用的精灵是否都存在
    ├── check_graphics_parts.py   把每种分节规则写法生成出来并用 nmlc 编译一遍
    ├── check_section_lengths.py  把每种 parts 形状生成出来并用 nmlc 编译一遍
    ├── check_gfx_config.py       校验 manifest.json / ttd_palette.json
    ├── check_string_table.py     校验字符串表读写与引用是否自洽
    ├── check_workbench_routes.py 校验工作台前端调的 API 路径都有对应路由
    ├── check_purchase_sprite.py  编译验证「购买菜单小图」能单独指定（purchase_suffix）
    └── check_markdown_tables.py  校验文档：表格列数对齐、文件确实是 UTF-8

web/
└── workbench/                    可视化工作台（make workbench）
    ├── server.py                 纯标准库 HTTP 服务，转发给上面的工具
    ├── schema.py                 ★ 列元数据，前端表单由它生成
    ├── index.html app.js style.css
    └── README.md                 工作台说明
```

★ = 可以手工编辑；⚙ = **每次 `make gen` 都会被覆盖，不要手改**。

> **一辆车一个文件。** 每辆车生成到 `src/<目录>/<id>.pnml`，
> 由 `src/vehiclefiles.pnml` 汇总 include，再由主索引 `chinasettrainsexport.pnml`
> 引入——与《中国包：火车》的组织方式一致。
> 好处：改一辆车只动一个文件，git diff 干净，多人协作不容易冲突；
> 删掉数据表里的行后，`make gen` 会自动把对应的 `.pnml` 一起删掉。
>
> 生成的文件**是纳入 git 跟踪的**，这样没有 python 的机器也能直接编译，
> 生成代码的改动也能在 review 中看到。

### 3.2 构建流水线

```
data/*.csv ──genpnml.py──┬─► src/vehiclefiles.pnml     （include 清单）
                         ├─► src/<目录>/<id>.pnml      （一辆车一个文件）
                         ├─► src/vehicleid.pnml
                         ├─► src/vehiclesort.pnml
                         ├─► docs/str.csv
                         └─► gfx/<目录>/*.vox（体素模型，你自己画）

gfx/**/*.vox ──renderobject──► gfx/**/*_32bpp.png
docs/str.csv ──str-csv.py────► lang/*.lng
chinasettrainsexport.pnml ──gcc -E──► .nml ──nmlc──► .grf
```

### 3.3 常用 make 目标

| 命令 | 作用 |
| ---- | ---- |
| `make` | 全套：生成 → 渲染 → 语言 → 编译 |
| `make -j 8` | 同上，8 个任务并行 |
| `make gen` | **只**从 `data/` 重新生成 PNML、刷新语言表、补齐 gfx 目录（**从不写 `.vox`**） |
| `make check` | **校验**：代码用到的字符串是否都已定义、有无死字符串 |
| `make sprites` | **只**渲染 `.vox` → `.png` |
| `make lang` | **只**从 `docs/str.csv` 生成 `lang/*.lng` |
| `make clean` | 删掉 `*.grf` `*.nml` `custom_tags.txt` 与所有渲染出的 PNG |
| `make clean_gen` | 删掉生成的所有 PNML（按清单逐个删除） |
| `make bundle` | 打包发布用 `.tar` |

> **日常改数据后最常用的是 `make`**。只改 CSV 时可以 `make gen` 再 `make code`，
> 但直接 `make` 也不会慢。改完不确定字符串是否齐，跑一次 `make check`。

---

## 4. 加一辆新车（完整流程）

下面以「加一台出口内燃机车 **CKD8W**」为例，走完整个流程。

### 步骤 1：在数据表里加一行

**推荐做法：复制一行现成的再改**，用 `tools/vehicle_row.py`——它用 Python 的 csv
模块写文件，**引号一定正确**，不会出现「少一个引号导致整行列错位」这种坑：

```bash
python3 tools/vehicle_row.py copy data/locomotives.csv ckd4a ckd8w \
    name_string="CKD8W (Export)" \
    intro_year=2022 \
    comment="Modern export diesel (estimate)"
```

看某一表有哪些列：

```bash
python3 tools/vehicle_row.py columns data/locomotives.csv
```

也可以从零写一行（每一列都要给）：

```bash
python3 tools/vehicle_row.py add data/wagons.csv \
    id=x70ex name_string="X70 (Export) (Flat Wagon)" \
    category=wagon folder=wagons "parts=2|2|2" power_section=1 \
    intro_year=2010 speed=120 weight=22 cost_factor=8 running_cost_factor=5 \
    capacity=70 refittable_cargo_classes="bitmask(CC_PIECE_GOODS|CC_OVERSIZED)"
```

> 如果你更习惯直接编辑 CSV：列的顺序必须与表头一致。
> **凡是含逗号的格子必须整格加双引号**。为省心，列表类字段一律用 `|` 分隔，
> 写成 `bitmask(CC_MAIL|CC_BULK)`、`[PASS|TOUR]`，这样就不需要引号。

关键列含义速查（完整版见 `data/README.md`）：

| 列 | 本例取值 | 说明 |
| -- | -------- | ---- |
| `id` | `ckd8w` | **只允许小写字母、数字、下划线**。它同时是 NML 标识符和精灵文件名 |
| `name_string` | `CKD8W (Export)` | 车库显示名。生成器会自动映射到 `STR_NAME_CKD8W` |
| `category` | `diesel` | 决定 ID 区段与 engine class |
| `folder` | `diesel` | `gfx/` 与 `src/` 下的子目录，可写多级如 `diesel/df4c` |
| `parts` | `2\|8\|2` | 每段的长度：隐形头 + 车身 + 隐形尾。**数值个数就是节数**，本包的习惯是 3 的倍数（一组三节），生成器对不是 3 的倍数的段数只**警告**而不阻止生成 |
| `power_section` | `1` | 哪一段是**车身段**：承载贴图与载量的那一段。三段结构就是 `1`（第 2 段）。列名沿用 `power_section`，但功率与重量都是整车属性，不再按段下发 |
| `intro_year` | `2022` | 引入年份 |
| `model_life` | `VEHICLE_NEVER_EXPIRES` | 或写年数 |
| `track_type` | `BACN` | 取自 `src/railtypetable.pnml` |
| `speed` / `power` / `weight` | `120` / `2800` / `138` | 性能参数，**整车共用**，不按段分配 |
| `tractive_effort_coefficient` | `0.26` | 机车用 |
| `cost_factor` / `running_cost_factor` | `84` / `66` | 成本因子 |
| `capacity` | `1` | 机车固定写 `1` |
| `ac_supply` | `1` | 能给车厢供电（机车/发电车） |
| `comment` | `... (estimate)` | 仅给人看，生成器忽略 |

> **不要写车辆 ID、不要写 sprite_id、不要写开关名。** 这些都由生成器算出来。
>
> **购买菜单里的分组与顺序**由最后三列（`variant_group`、`menu_order`、
> `series_string`）决定，见[第 8 章](#8-购买菜单分组与排序)。

### 步骤 2：生成

```bash
make gen
```

输出类似：

```
genpnml: wrote 206 strings to docs/str.csv
genpnml: 73 vehicles -> 76 files (0 removed), 111 voxel models
  unit_wagon         4  ids 1024..1027
  coach              9  ids 2048..2056
  wagon             12  ids 3072..3083
  steam              1  ids 4096..4096
  diesel            32  ids 5120..5151      ← 多了一辆
  electric           8  ids 6144..6151
  ...
```

生成器自动完成：

1. 在 `src/vehicleid.pnml` 的 `diesel` 区段分配一个空闲 ID（本例 `5151`）；
2. 新建 `src/diesel/ckd8w.pnml`，内含这辆车的全部 switch / spriteset / item；
3. 在 `src/vehiclefiles.pnml` 的对应位置插入它的 `#include`；
4. 在 `src/vehiclesort.pnml` 里按 `menu_order` 排好购买菜单顺序（没设的车按表序排在最后）；
5. 在 `docs/str.csv` 补上 `STR_NAME_CKD8W`、`STR_FULL_NAME_CKD8W`；
6. 生成器会告诉你 `gfx/diesel/ckd8w.vox` 还没有，把它画好放进去。

### 步骤 3：编译

```bash
make
```

画好 `ckd8w.vox` 后**就可以编译了**。先验证 NML 逻辑正确，
再去画真模型——这是推荐的工作顺序。

也可以顺手做一次一致性检查：

```bash
make check
# genpnml --check: 206 referenced, 206 defined, 0 missing, 0 unused
```

### 步骤 4：换成真模型

见[第 5 章](#5-制作模型vox)。放好 `gfx/diesel/ckd8w.vox` 后：

```bash
make
```

### 步骤 5：在游戏里看效果

把新的 `.grf` 覆盖到 OpenTTD 的 newgrf 目录，**重新加载 NewGRF**（或在 NewGRF 设置界面
点 Apply），新机车就会出现在车库的购买列表里。

### 步骤 6：提交

```bash
git add data/locomotives.csv docs/str.csv src/ gfx/diesel/ckd8w.vox
git commit -m "Add CKD8W export diesel"
```

生成的文件是跟踪的，所以 `git add src/` 会把新车的 `.pnml` 一起提交——
这样别人拉下来即使不跑 python 也能直接编译。

### 步骤 7（可选）：删除车辆

```bash
python3 tools/vehicle_row.py remove data/locomotives.csv ckd8w --prune
make gen
```

`--prune` 会删掉该车的 `.pnml` 与 `.vox`；即使不用 `--prune`，
`make gen` 也会根据清单把不再生成的 `.pnml` 清理掉。字符串表会在下一次
`make gen` 中同步移除该车的条目。


---

## 5. 制作模型（.vox）

### 5.1 精灵是怎么来的

```
gfx/<目录>/<基名>.vox  ──renderobject──►  gfx/<目录>/<基名>_32bpp.png
```

PNML 里 `template_standard ("<目录>", "<基名>")` 会从 `_32bpp.png` 里按固定坐标
裁出 8 个等距视角。**渲染参数由同目录的 `manifest.json` 决定，而 `template.pnml`
里的裁剪坐标必须与它一致**——两者已经配套好，不要只改其中一个。

### 5.2 需要哪些 `.vox`

**生成器不造占位模型。** 它只准备好每个 `gfx/<目录>/` 需要的 `manifest.json`
与 `ttd_palette.json`，然后列出还缺哪些模型：

```
genpnml: 1 vehicles -> 4 files (0 removed), 1 gfx folder(s) prepared
genpnml: 1 model(s) still to be drawn:
  gfx/dprk/df4c/df4c-korea-2.vox
```

需要哪些基名，取决于你的数据：

| 情况 | 需要的模型 |
|------|-----------|
| 涂装的后缀留空 | `<id>.vox` |
| 涂装后缀为 `green` | `<id>-green.vox` |
| 货物外观后缀 `coal` | `coal.vox` |
| 货物外观 + 涂装 | `coal-green.vox` |
| 分节规则里写到的基名 | `<基名>.vox` |

`tools/verify_assets.py` 会把缺失的再列一遍。**模型必须存在，工程才能编译**——
nmlc 找不到 `_32bpp.png` 就会报错。

### 5.3 用 MagicaVoxel 画

1. 打开 MagicaVoxel，新建模型。
2. **画布尺寸要够长**：长度方向建议 ≥ 32 体素（对应约 192 px 的侧视图），
   宽 8 体素左右，高 12~16 体素。
   参考 `gfx/manifest.json` 的 `size`：`{"x": 192, "y": 48, "z": 80}`。
3. 让**车体纵轴沿着长度方向**，导出为 `.vox`，
   存成 `gfx/<目录>/<基名>.vox`。
4. 渲染并检查：

```bash
make sprites
```

   然后打开 `gfx/<目录>/<基名>_32bpp.png` 目视检查——它是一张长条图，8 个视角
   从左到右排列，**每个视角宽度不同**（正面 36 px、斜面 120 px、侧面 192 px），
   每格右侧带 8 px 透明内边距，所以整张图的宽度不是固定的 992 px 而是它们的
   总和。**如果车头朝向不对、或车体偏上偏下**，在同一张图里就能看出来。

   要看裁剪后的单个视角，用工作台的「车辆工作台 → 第 3 层 分节图像」，
   或右上角的「精灵图预览」：它按 `manifest.json` 里的真实坐标切图，
   而不是等分网格，还能按方向（SW / SE / NW / NE / W / S / N / E）逐一看。

6. 位置微调：如果车体相对轨道偏高/偏低，把 `src/<目录>/<id>.pnml` 里该车用的
   模板换掉即可——但该文件是生成物，正确做法是在 `data/liveries.csv` 的
   `templates` 列指定，例如 `template_speciel_1`。
   可用模板见 `src/template.pnml`：

   | 模板 | 用途 |
   | ---- | ---- |
   | `template_standard` | 默认 |
   | `template_speciel_0` / `template_speciel_1` | 车体偏高 / 偏低的特殊车型 |
   | `template_reversed` | 反向 |
   | `template_purchase` | 采购菜单用 |

### 5.4 只需要侧视图？不需要

`renderobject` 从 3D 模型自动生成 8 个方向，你不用手画 8 张图。
**只需一个 `.vox`。**

### 5.5 检查精灵是否齐全

```bash
python3 tools/verify_assets.py
```

输出示例：

```
sprite sheets referenced: 110
missing _32bpp.png: none
```

如果列出缺失文件，说明某个涂装/货物外观的 `.vox` 还没画或没渲染——
把它画好放进该目录，再跑 `make sprites` 即可。

### 5.6 改车辆的节数

节数由**车辆表 `parts` 列的数值个数**决定，不是单独一个字段。用 `|` 分隔：

```csv
id,...,parts,power_section,...
df4c,...,2|8|2,1,...        ← 3 段（前端 2 + 车身 8 + 后端 2）
df4c,...,2|12|2,1,...       ← 车身加长到 12
df4c,...,2|8|2|2,1,...      ← 4 段（数一下：四个数）
df4c,...,6,0,...            ← 1 段，不再铰接
```

| 想要 | 怎么做 |
|------|--------|
| 车身更长/更短 | 只改**中间那个数**，例如 `2\|8\|2` → `2\|12\|2` |
| 增加/减少节数 | 增加或删除 `\|` 分隔的数值个数 |
| 哪一节是车身 | `power_section` 的**下标**（从 0 起），必须小于节数 |

单位是 4 像素：`8` ≈ 32 px。所以 `2|8|2` 全长约 `(2+8+2) × 4 = 48 px`。

> **段数的习惯是「一组三节」= 3 的倍数**：隐形头 + 载货车身 + 隐形尾，
> 例如 `2|8|2`，加长一组就是 `2|8|2|2|8|2`。段数不是 3 的倍数（`2|8`、`6` 等）
> 生成器会**警告**，但**照常生成、照常编译**——`position_in_articulated_veh % N`
> 对任何 N 都成立，这是本包共同遵守的美术约定，**不是 NewGRF 的硬性要求**。
> 之所以建议遵守：`min_cars` 按「一辆车 = 三节」计长，共享的长车开关
> `switch_length_2_<车身>_2` 也只定义了头 2 + 车身 + 尾 2 这种形状。

改完 `make gen` 即可，生成器会自动跟着变：

- `articulated_part` 挂接的节数（N 段 → 递归 N−1 次）
- 载量按 `power_section` 分配给对应节，其余节为 0
- 每段的贴图开关 `position_in_articulated_veh % <节数>`

**两个必须同步改的地方：**

1. **涂装的 `graphics_parts`**：用 `;` 分隔的份数**必须等于节数**，
   否则报「graphics_parts 需要 N 段（与 parts 相同），当前 M 段」。
   节数一变，每个涂装的规则都要跟着改。
2. **`length` 的长度值**：`src/functions.pnml` 只为父包用到的形状预定义了
   `switch_length_2_<车身>_2`（车身 1–8）等少数几个。其它形状生成器会为该车单独
   输出一个 `switch_<id>_length`，**不需要你手工加开关**。

   想确认你打算用的形状能编译，跑：

   ```bash
   python3 tools/check_section_lengths.py
   ```

   它会用一组形状（`2|8|2`、`2|10|2`、`2|8|2|2`、`2|8`、`6` 等）各生成并编译一遍，
   然后恢复数据表。

**分节图像规则里的 `pos` 数的是"节"不是"车"**：三段车 1 台占 3 节，
所以改了节数之后，规则里的 `pos <= 2` 这类边界值也要重新算。

---

## 6. 加涂装与货物外观

### 6.1 加一套涂装

涂装分散在两个地方：**这台车有哪几种涂装**写在 `data/liveries.csv`，
**每种涂装的车模**是 `gfx/<目录>/<id>[-<后缀>].vox`。工作台把它们放在同一页：

> **工作台 → 车辆工作台 → 第 2 层「涂装管理」**

每一行涂装都会显示它解析出来的模型文件名和该文件的状态（缺 `.vox` / 未渲染 / 已渲染），
所以不用自己拼后缀。三层的分工是：

| 层 | 管什么 |
| -- | ------ |
| 1 车辆属性 | 这台车是什么（id、类别、`parts` 分段、性能……） |
| 2 涂装管理 | 这台车有哪几种涂装，每种用哪个 `.vox` |
| 3 分节图像 | 当前涂装的每一段在什么条件下显示哪张图 |

也可以直接编辑 `data/liveries.csv`，为同一个 `id` 追加行。**行序即涂装序号**：

```csv
id,sprite_suffix,string,from_year,to_year,purchase_suffix,templates,graphics_parts
ckd8w,,LV_BUILD_YEAR,0,2019,,,
ckd8w,exblue,LV_EXPORT_BLUE,2020,9999,,,
ckd8w,gray,LV_EXPORT_GRAY,0,9999,,,
```

规则：

* **第 1 行 = 索引 0 = 自动涂装**。若存在真实年份区间的涂装，会自动按
  `build_year` 选择。
* `0` 与 `9999` 表示「始终可用」，**不会**生成多余的 case（避免母包里的
  `Range overlaps` 警告）。
* 索引 1、2… 是玩家在**改装菜单**里能显式选的涂装。
* `sprite_suffix` = **这一行涂装自己的模型**的文件名后缀 → 需要
  `gfx/<目录>/<id>-<后缀>.vox`；留空表示直接用 `<id>.vox`。
* `purchase_suffix` = **车库购买列表里那张小图**用哪张图：填 `a` 就用
  `gfx/<目录>/<id>-a.vox`；留空 = 用本行自己的模型。购买小图是**这台车第一行涂装**
  提供的（`graphics { purchase: … }` 只取第一行），所以本行自己的模型还没画时，
  可以让第一行借用一张已经画好的图顶上去——这就是母包 China Set: Trains 里每台车
  单独写一个 `template_purchase ("目录", "基名")` 的对应写法。它**不改变本行的模型**，
  所以不会和别的行撞同一个 `.vox`；填在**第一行之外**不起作用，生成器会警告。
* 同一台车的两行**不能解析出同一个模型基名**——那会让生成器重复声明同一个精灵集，
  工作台会直接拦下来。**拦下来的提示里说的模型是 `sprite_suffix`**：如果本意是
  「让购买菜单借一张图」，要改的是上面的 `purchase_suffix`，不是这一列。
* 年份区间重叠只是**警告**（nmlc 取行序靠前的那条 case），不阻止保存。
* `string` 是菜单里的显示文字。涂装标签统一写成 `LV_<名字>`，生成器把它映射成
  `docs/str.csv` 里的 `STR_LV_<名字>`；写裸的 `STR_<名字>` 也仍然可用。
  表里已有 6 个现成的（`LV_ORIGINAL`、`LV_BUILD_YEAR`、`LV_EXPORT_BLUE`、
  `LV_EXPORT_GREEN`、`LV_EXPORT_GRAY`、`LV_DPRK`）。要新增标签，在
  **工作台 → 字符串表**里点「新增字符串」，它会被 `make gen` 保留；
  也可以手工往 `docs/str.csv` 追加。旧工程用
  `python3 tools/migrate_lv_labels.py` 一次性换名。
* `graphics_parts` 是**这一行涂装自己的**分节换图规则：按 `;` 一段一份、
  份内用 `|` 分出「条件=…=贴图基名」的规则路径，生成器把它们编成嵌套开关；
  决定每一段在整列不同位置上显示哪张贴图。规则写在第 2 层涂装行里，
  完整语法见[第 7 章](#7-分节图像规则怎么填)，
  列说明见 [data/README.md 的 per section graphics](../data/README.md#per-section-graphics)。
  可用变量是 `pos`、`tailpos`、`consist`、`unitpos`，短名和完整 NML 变量名都能写
  （见 [7.3](#73-四个可用变量)）。
  留空则该涂装只有车身段出图、两端隐形、整列同图。

然后：

```bash
make gen          # 生成新涂装的 spriteset，并列出还缺的 .vox
make              # 渲染并编译
```

`make gen` 会列出 `df4c-exblue.vox`、`df4c-gray.vox` 这些还缺的模型，逐个画好即可。
把 `gfx/<目录>/<id>-<后缀>.vox` 换成你自己的模型，再 `make sprites` 即可。

### 6.2 加一种货物外观

编辑 `data/cargo_variants.csv`：

```csv
id,variant,sprite_suffix,cargo_classes,cargo_types,from_index,to_index,template
c70ex,coal,c70ex-coal,bitmask(CC_BULK),,6,45,
c70ex,ore,c70ex-ore,bitmask(CC_BULK),,"IRON|STEL|ALUM",6,45,
```

* `cargo_classes` 非空 → 按**货物类别**选择；
* `cargo_types` 非空 → 按**具体货种**选择（`|` 分隔多个标签）；
* `from_index`/`to_index` → 在多少个货物单位之间显示「半载」图，
  范围之外显示满载图；写 `0,0` 表示不分段，始终用这一张。
* `sprite_suffix` = 精灵基名 → 需要 `gfx/<目录>/<后缀>.vox`。

生成器会产出母包同款链条：

```
switch_c70ex_empty          cargo_count < 5   →  空车精灵
switch_c70ex_cargo_class    cargo_classes     →  按类别
switch_c70ex_cargo_type     cargo_type_in_veh →  按货种
switch_c70ex_<变体>_stage   cargo_count       →  半载 / 满载
```

多涂装货车会为**每套涂装**生成独立链条，开关名带涂装后缀，互不冲突。

---

## 7. 分节图像规则怎么填

### 7.1 分段、份数与「一节」的关系

`parts` 列的 `2|8|2` 是**一台车自己的三段**，不是整列的三节：

| 段 | 长度 | 作用 | 一般出图吗 |
| -- | ---- | ---- | ---------- |
| 第 1 段 | 2 | 前端隐形车厢，只为让车吻合轨道 | 默认隐形 |
| 第 2 段 | 8 | **车身**，承载贴图、功率、载量 | 出图 |
| 第 3 段 | 2 | 后端隐形车厢 | 默认隐形 |

规则同样用 `;` 分成**与段数相同的份数**，第 1 份管第 1 段、第 2 份管第 2 段、
第 3 份管第 3 段：

```
第1段的规则 ; 第2段的规则 ; 第3段的规则
```

三条硬性规则：

1. **份数必须等于 `parts` 的段数。** `parts=3|8|3` 写 3 份，`parts=2|8|2|2|8|2` 写
   6 份。份数不对生成器直接报「graphics_parts 需要 3 段（与 parts 相同），当前 2 段
   （空段表示该段隐形；末尾的 ; 也算一段）」，工作台在输入框下面实时提示。
2. **末尾的 `;` 也算一份，不是标点。** `a;b;c;` 是 **4** 份，对 3 段车报「当前 4 段」；
   `;a;b` 是 3 份（第 1 份是空的）。
3. **空的一份 = 这一段隐形**（生成器给它 `empty_sprites`）；**整格留空 = 完全没有规则**，
   这时按默认行为走：只有车身段画涂装自己的整图，两端隐形。两者的差别见
   [7.4](#74-规则怎么变成开关)最后一条。

> **段数的习惯是「一组三节」= 3 的倍数**：隐形头 + 载货车身 + 隐形尾，加长一组就是
> `2|8|2|2|8|2`。段数不是 3 的倍数（`2|8`、`6` 等）生成器只**警告**，照常生成、
> 照常编译——这是本包共同遵守的美术约定，**不是 NewGRF 的硬性要求**。

### 7.2 一份里面怎么写：条件路径

每一份内部用 `|` 分隔规则，每条规则是一条**路径**：

```
条件=条件=…=贴图基名      整条路径都满足时用这张图
贴图基名                  兜底，前面都没命中时用这张
```

条件本身也含 `=`（`<=`、`==`），所以不能按「最后一个 `=` 左边是条件」来切：生成器
从左边开始**按最长匹配**切出一个又一个条件——比较（`pos<=2`）和有上下界的区间
（`pos=3..8`）都算一个条件——切不动时剩下的必须是一个贴图基名
（**小写字母、数字、下划线、连字符**：基名就是精灵图文件名，所以涂装表里的
`df4c-korea-1`、`tm2-a` 可以直接写在这里；大写、空格、点会被拒绝）。

```
consist<=6=pos<=2=h_s | consist<=6=h_l | b_l
```

读作：**整列不超过 6 节**时，`pos<=2` 的那些节用 `h_s`、其余用 `h_l`；**整列超过
6 节**时一律用 `b_l`。第二条 `consist<=6=h_l` 是「停在半路上」的规则，它的意思是
「这一层剩下的情况」，也就是那个开关的兜底，**不是**又一个并列分支。

规则**按书写顺序组成一条链**：先写的先判断，没命中的交给下一条；没有条件的裸基名
是整段的兜底，必须写在最后。

### 7.3 四个可用变量

| 变量 | 实际含义 | 单位 |
| ---- | -------- | ---- |
| `pos` | `position_in_consist`，这一节在整列里排第几（从 0 起） | **节**（不是车！三段车 1 台占 3 节） |
| `tailpos` | `position_in_consist_from_end`，从尾部数第几节 | 节 |
| `consist` | `num_vehs_in_consist`，整列一共多少节 | 节 |
| `unitpos` | `position_in_articulated_veh`，这是本车的第几段 | 段 |

条件里的变量**短名和完整 NML 名都可以写**，两者等价；运算符两侧的空格可有可无：

```
pos<=2        与  position_in_consist <= 2             等价
tailpos<=2    与  position_in_consist_from_end <= 2    等价
consist<=6    与  num_vehs_in_consist <= 6             等价
unitpos==1    与  position_in_articulated_veh == 1     等价
pos=3..8      与  position_in_consist 3..8             等价
```

短名只是方便书写的别名。一个条件只能是「变量 比较 数字」或「变量 区间」，数字必须是
无符号整数，一共四种写法：

| 写法 | 意思 | 回写成单元格里的样子 |
| ---- | ---- | -------------------- |
| `pos==3` | 正好第 3 节 | `position_in_consist==3` |
| `pos<=8` | 第 0 到第 8 节 | `position_in_consist<=8` |
| `pos>=3` | 第 3 节到最后一节 | `position_in_consist>=3` |
| `pos=3..8`（空格可有可无：`pos 3..8`） | 第 3 到第 8 节，**两头都算** | `position_in_consist=3..8` |

`<` 和 `>` 也还能写，但只是糖：`pos>2` 和 `pos>=3` 是同一批值，`pos<2` 和 `pos<=1`
是同一批值——数字挪一位而已——所以生成器写回时统一成 `<=` / `>=`；工作台的运算符
下拉框里干脆只列 `<=`、`==`、`>=` 和「区间」四种，列出来的都是能原样存回去的。

上下都有界的 `pos=3..8` 是**只有区间才写得出来**的形状：`pos>=3` 和 `pos<=8` 是两个
条件，而同一个变量在一条路径上只能选一次（见下面第 2 个坑），所以没有任何比较运算符
能说出「第 3 到第 8 节」。它编出来就是**一个 case**：`3..8: return spriteset…;`。

回写是生成器顺手做的规范化，所以手写和回写看起来可以不同，说的却是同一件事：
只有一个值时写 `==`，从 0 起写 `<=`，到 255 止写 `>=`，其余写 `low..high`——
`pos=0..6` 回写后是 `pos<=6`（两者本来就是一回事），而 `pos=3..8` 原样保留。
回写用的是**完整 NML 名**，所以 `pos=3..8` 落进表里写作 `position_in_consist=3..8`。
上界超过 255（`pos=248..300`）和 `pos<=300` 一样被接受：比较变量只装 0..255，
多出来的部分无害。

**下面这些一律被拒绝，而且会说是哪一段的哪条规则、错在哪**
（完整的报错对照表见 [7.6](#76-会被拒绝的写法)）：

* `!=` 与 `!`：「条件 'pos!=2' 不支持取反，请改用相反的比较」；
* 一个条件里的 `&`（`|` 会被当成规则分隔符）：「条件 '&consist<=6' 含 & 或 |；
  编组变量只能作为开关的选择器，请拆成多条规则（用 | 分隔）让生成器嵌套开关」；
* 算式（`pos/3==1`）：「条件 'pos/3==1' 不受支持」——一个条件只能是「变量 比较 数字」
  的简单形式，不支持算式（如 `pos / 3`）；改用 `pos==3`，或把区间重新划分；
* 不认识的变量（`speed<=6`）、**大写的变量名**（`POS<=2`）：
  「无法识别的条件片段 'speed<=6'；可用变量：consist, pos, tailpos, unitpos」；
* 永远不成立的条件，例如 `pos<0`：「条件 'pos<0' 永远不成立」；
* 区间写反了，例如 `pos=8..3`：「区间 'pos=8..3' 的低值 8 比高值 3 大，永远不会匹配；
  请把小的写在前面」；
* 乱写的基名（含大写、点）：**只有这一种**才报那句通用的「每一条规则是
  「条件=条件=…=贴图基名」，基名只能用小写字母、数字、下划线和连字符」——
  因为错的是基名。`.vox` 文件叫什么，这里就写什么（去掉 `_32bpp.png` 那一段）。

每条报错都带上是第几段的哪条规则，例如
`第 2 段的 'speed<=6=a' 无法解析：无法识别的条件片段 'speed<=6'；可用变量：consist, pos, tailpos, unitpos`。

⚠️ 两个最容易踩的坑：

1. **`pos` 数的是节，不是车。** 三段车的第 1 台车是节 0、1、2，第 2 台车是节 3、4、5。
   想判断「是不是第 1 台车」要写 `pos <= 2`，不能写 `pos == 0`（那只有第 1 段的 1 节
   满足）。
2. **同一条判定路径上，同一个变量只能出现一次。** `pos<=2=tailpos<=2=pos<=2=a` 和
   `pos<=2=a | tailpos<=2=b | pos<=3=c` 都会被拒绝：「第 2 段里重复使用了
   position_in_consist；同一条路径上的每个条件要换一个变量」。同一个开关的**多个区间**
   当然可以继续用这个变量：`pos<=2=a | pos>2=b` 是正常写法。

> `unitpos` 是合法变量，但多数情况下多余：生成器已经用
> `position_in_articulated_veh % 段数` 把每一段分开，**规则所在的第几份**就说明了
> 这是本车第几段；在规则里再写一次 `unitpos`，只会在这一段内部多套一层同类开关。

### 7.4 规则怎么变成开关

写下的规则先合并成一棵**开关树**，再展开成 NML 的嵌套开关。四条规矩决定它的形状：

* **同一个变量的多个区间 = 一个开关的多个 case**，按书写顺序自上而下试：
  `pos<=2=a | pos>2=b` 编成一个开关（`0..2 → a`、`3..255 → b`）；区间也算**一个**
  case，`pos<=2=a | pos=3..8=b | pos>=9=c` 编成 `0..2`、`3..8`、`9..255` 三个 case。
  同一层可以继续用这个变量写别的区间；但**同一条路径上同一个变量只能出现一次**。
* **换一个变量 = 变成上一个开关的 default**，也就是链到下一层：
  `pos<=2=set_head | tailpos<=2=set_tail | set_mid` 编成两个串联的开关。
* **停在半路上的规则 = 停在哪一层就是哪一层的 default**：
  `consist<=6=pos<=2=h_s | consist<=6=h_l | b_l` 读作「≤6 节时再按 `pos` 分，
  否则 `b_l`」。
* **没有条件的裸基名 = 整段的兜底**，它是最深那个开关的 default。

一个 case 只能对应一张图：同一个条件写两次、基名不同，会报「同时指定了模型 …；
一个截面上只有一个模型」。后写的 case 如果被前面的**完全覆盖**，会报「被前面的条件
完全覆盖，永远不会生效」——所以**范围小的写在前面**。

**只有一个 case 也照样生成开关**，因为正是 default 表达了「条件不满足时怎么办」；
只有整段一个条件都没有时，这一段才直接是一张精灵集，不生成开关。

⚠️ **条件都没命中时画什么：**

* **整格留空**（完全没写规则）：只有车身段（`power_section`）画涂装自己的整图，
  两端 `empty_sprites` 隐形——这是每辆车默认的样子。
* **写了规则**：分段开关 `switch_<id>_section_<涂装序号>` 会给每一段都生成 case，
  **哪一段没有规则、或规则一个都没命中，那一段就是 `empty_sprites`（隐形）**。
  想让某一段永远不画东西，留空那一份即可。

### 7.5 五个现成的例子

**例 1：每段一张固定图**（最简单，不生成开关）

```
emu_head;emu_body;emu_tail
```

第 1、2、3 段各一张图；没有任何条件，生成器直接把三段接到对应的精灵集上。

**例 2：按整列节数换大脸小脸**（最常见）

```
consist<=6=emu_face_s | emu_face_l;emu_body;consist<=6=emu_face_s | emu_face_l
```

头尾两份完全相同，所以整列两端看起来一样。带条件的那一份编成一个开关：

```c
switch (FEAT_TRAINS, SELF, switch_<id>_<涂装序号>_0, num_vehs_in_consist) {
    0..6: return spriteset_<id>_gfx_emu_face_s;
    return spriteset_<id>_gfx_emu_face_l;     // 裸基名 = 兜底
}
```

**例 3：先看编组长短，再看位置**（嵌套 + 兜底）

```
consist<=6=pos<=2=h_s | consist<=6=h_l | b_l;body;body
```

读作：整列不超过 6 节时，前 2 节用 `h_s`、其余用 `h_l`；更长的编组一律 `b_l`。
生成器先按编组长度分叉，再在「≤6 节」这一支里按位置分叉：

```c
switch (FEAT_TRAINS, SELF, switch_<id>_<涂装序号>_0_0, position_in_consist) {
    0..2: return spriteset_<id>_gfx_h_s;
    return spriteset_<id>_gfx_h_l;            // consist<=6=h_l 停在这一层，成为兜底
}
switch (FEAT_TRAINS, SELF, switch_<id>_<涂装序号>_0, num_vehs_in_consist) {
    0..6: return switch_<id>_<涂装序号>_0_0;
    return spriteset_<id>_gfx_b_l;            // 裸基名 b_l 是整段的兜底
}
```

**例 4：整列分成头 / 中 / 尾**（换变量 = 链到下一层）

```
pos<=2=set_head | tailpos<=2=set_tail | set_mid;set_mid;set_mid
```

整列最前面 3 节（1 台车）用 `set_head`，最后 3 节用 `set_tail`，其余用 `set_mid`。
前两条规则用了**不同变量**，所以编成两个串联的开关：

```c
switch (FEAT_TRAINS, SELF, switch_<id>_<涂装序号>_0_next,
        position_in_consist_from_end) {
    0..2: return spriteset_<id>_gfx_set_tail;
    return spriteset_<id>_gfx_set_mid;
}
switch (FEAT_TRAINS, SELF, switch_<id>_<涂装序号>_0, position_in_consist) {
    0..2: return spriteset_<id>_gfx_set_head;
    return switch_<id>_<涂装序号>_0_next;     // 没命中前 3 节，继续按 tailpos 判断
}
```

**例 5：用区间挑出整列中间的一段**（只有区间写得出来）

```
pos=3..8=emu_mid | emu_end;emu_body;pos=3..8=emu_mid | emu_end
```

第 1、3 段在整列第 4 到第 9 节（`pos` 0..2 是第 1 台车的三段，所以节 3 起是第 2 台车）
用 `emu_mid`、其余节用 `emu_end`，第 2 段（车身）一直是 `emu_body`。`pos>=3` 加
`pos<=8` 写不出来——那是两个条件，同一个变量在同一条路径上只能用一次——所以这里
必须写区间，它也就编成**一个 case**：

```c
switch (FEAT_TRAINS, SELF, switch_<id>_<涂装序号>_0, position_in_consist) {
    3..8: return spriteset_<id>_gfx_emu_mid;  // 一个 case，两头都算
    return spriteset_<id>_gfx_emu_end;        // 裸基名 emu_end = 兜底
}
```

`pos=3..8` 写回表格还是 `position_in_consist=3..8`；如果写成从 0 起的 `pos=0..6`，
回写时会变成等价的 `pos<=6`（见 [7.3](#73-四个可用变量)）。

### 7.6 会被拒绝的写法

生成器宁可当场报错，也不生成「永远看不到的图」，常见几种：

| 整格写法（3 段车） | 生成器说什么 |
| ------------------ | ------------ |
| `a;b;c;`（多一份） | graphics_parts 需要 3 段（与 parts 相同），当前 4 段（空段表示该段隐形；末尾的 ; 也算一段） |
| `;consist<=10=a \| consist<=6=b \| c;` | 第 2 段的 '0..6' 被前面的条件完全覆盖，永远不会生效；请把范围小的写在前面，或改成互不重叠的区间 |
| `;consist<=6=a \| consist<=6=b;` | 第 2 段的 '0..6' 同时指定了模型 'a' 和 'b'；一个截面上只有一个模型，请把其中一个改成范围更小的下一层条件 |
| `;pos<=2=tailpos<=2=pos<=2=a;`<br>`;pos<=2=a \| tailpos<=2=b \| pos<=3=c;` | 第 2 段里重复使用了 position_in_consist；同一条路径上的每个条件要换一个变量 |
| `;pos=8..3=a;` | 第 2 段的 'pos=8..3=a' 无法解析：区间 'pos=8..3' 的低值 8 比高值 3 大，永远不会匹配；请把小的写在前面 |
| `;pos<0=a;` | 第 2 段的 'pos<0=a' 无法解析：条件 'pos<0' 永远不成立 |
| `;speed<=6=a;`<br>`;POS<=2=a;` | 第 2 段的 'speed<=6=a' 无法解析：无法识别的条件片段 'speed<=6'；可用变量：consist, pos, tailpos, unitpos |
| `;pos!=2=a;` | 第 2 段的 'pos!=2=a' 无法解析：条件 'pos!=2' 不支持取反，请改用相反的比较 |
| `;pos<=2&consist<=6=a;` | 第 2 段的 'pos<=2&consist<=6=a' 无法解析：条件 '&consist<=6' 含 & 或 \|；编组变量只能作为开关的选择器，请拆成多条规则（用 \| 分隔）让生成器嵌套开关 |
| `;pos/3==1=a;` | 第 2 段的 'pos/3==1=a' 无法解析：条件 'pos/3==1' 不受支持。一个条件只能是“变量 比较 数字”的简单形式，例如 consist <= 9、pos == 0、tailpos >= 3、unitpos == 1；一个上下都有界的区间写成 pos=3..8；不支持算式（如 pos / 3）。同一段里需要多个条件时请写多条规则，生成器会把它们编成嵌套开关 |
| `;pos<=2=A_b;` | 第 2 段的 'pos<=2=A_b' 无法解析：每一条规则是「条件=条件=…=贴图基名」，基名只能用小写字母、数字、下划线和连字符（涂装表里的贴图基名，例如 df4c-korea-1，可以直接写在这里） |
| `;consist<=6=a-b \| a_b;` | ERROR: df4c: 贴图基名 a-b 和 a_b 折成同一个 NML 标识符 spriteset_df4c_gfx_a_b（连字符和下划线都折成下划线）；请改掉其中一个 |

**条件本身写错时，报的是上面那种具体原因**（哪一段、哪条规则、错在哪）；只有**基名**
写错时才是那句通用的「基名只能用小写字母、数字、下划线和连字符」，因为它说的正是基名。
**连字符是合法的**（`a-b`、`tm2-a`、`df4c-korea-1` 都能写）；但 NML 标识符会把 `-` 和
`_` 都折成下划线，所以同一个基名的两种写法（`a-b` 与 `a_b`）会撞在同一个精灵集上——
生成器直接报错，而不是让其中一张图悄悄消失。

想确认自己的写法行不行，跑：

```bash
python3 tools/check_graphics_parts.py
```

它把每一种**合法**写法生成出来再用 `nmlc` 编译一遍（空表、空段、纯分段、
同变量多区间、混合变量链、嵌套树……），再把每一种**该被拒绝**的写法对照它该报的
消息检查一遍，跑完自动恢复数据表。

### 7.7 需要几张图，以及在工作台上怎么搭

规则里出现的每个基名都要有 `gfx/<目录>/<基名>.vox`，缺的会在生成时列出来，
例如 `genpnml: 1 model(s) still to be drawn: gfx/dprk/df4c/df4c-korean-2.vox`。
**另外还有两张图是必须存在的**：每行涂装自己那张（`sprite_suffix` 决定的），以及
**这辆车第一行涂装的购买菜单小图**（`purchase_suffix` 可以把它换成另一张，见 §6.1）；
其余没被任何开关用到的图不必画——nmlc 只解析**被引用**的精灵集。
`python3 tools/check_purchase_sprite.py` 会把这条链子完整编译一遍验证。
**图没画出来之前 `make` 会在 nmlc 那一步失败**，因为精灵路径不存在——这是
「先有模型后装车」的正常流程，不是生成器的问题。第 3 层「分节图像一览」会把
当前涂装用到的每个基名连同文件状态列出来。

**第 2 层每一行涂装里的「分节图像规则」是图形化的**，控件和 NML 一一对应：

| 界面上的东西 | 对应的 NML |
| ------------ | ---------- |
| 一段的模式「隐形」 | 这一段是 `empty_sprites` |
| 模式「一张图」+ 模型下拉 | 这一段直接是那个精灵集 |
| 模式「按条件分」 | 这一段是 `switch (…)` |
| 块头「按 [变量] 判断」 | `switch` 的选择器 |
| 「当 [运算符][数值] → 模型」 | 一个 `case`，`return spriteset…`；运算符下拉只有 `<=`、`==`、`>=`、区间四种 —— `<` / `>` 会被写成等价的 `<=` / `>=`，所以不列出来 |
| 「当 区间 [从][到] → 模型」 | 一个两头都算的 `case`，例如 `3..8: return spriteset…`；在 `<=6` 这种 case 上选「区间」，两个数字框会摊成真正的区间（`0..6` 就是 `<=6`，不摊开就退不回来） |
| 「当 … → 再筛一层」 | 该 `case` 里 `return switch…`（嵌套开关） |
| 「其余 → 模型」 | `default: return spriteset…` |
| 最外层「其余 → 再筛一层」 | `default: return switch…`（串联的下一层） |

改动不会只放在浏览器里：每次操作都把整棵树发给服务器的
`POST /api/graphics-parts`，由 `genpnml.py` 写回单元格**再解析一遍**，界面上
显示的永远是编译时会读到的那一格。所以工作台不可能做出生成器不接受的规则；
真做不出来（例如表格语言表达不了的嵌套）会直接把原因显示出来。
写回失败（校验没过、或请求本身出错）时，「保存这一行」会**拒绝保存**并说明原因：
这时候屏幕上的开关块并不是单元格里的内容，硬存下去会把刚搭好的规则悄悄换回旧的。
想手写整格时，展开「直接编辑文本」即可，两边会互相刷新。

第 3 层另有**缩进树**只读视图，和编译出的开关一一对应：一层开关一行
「按 `pos` 判断」，分支各缩进一级，叶子写成「`pos 0..2` → `基名`」，
兜底写成「其余情况 → `基名`」，空段写成「这一段隐形（用 `empty_sprites`）」。
它走 `/api/rules`，同样由生成器的解析器算出来（生成器文件一变就重新加载），
所以**预览与生成的 NML 不会说两套话**。

---

## 8. 购买菜单：分组与排序

车库里的购买列表是一张平铺的车表，数据表里**每一行就是一条**。有三列专门管这台车
在列表里怎么出现——它们就在四张车辆表 `comment` 前面的最后三列：

| 列 | 说明 |
| -- | ---- |
| `variant_group` | 这台车**折叠到哪台车下面**，填对方的 **id**（如 `df4c`），不是引擎编号。这一列就是 OpenTTD 13 的「可展开购买列表里的车辆变体」（NML 的 `variant_group` 属性），自动替换菜单用的是同一套分组。留空 = 自己独立一条 |
| `menu_order` | 在购买菜单里的位置，非负整数。**留空（或写 0）的车排在所有设了顺序的车之后**，并按表格行序排列 |
| `series_string` | 折叠起来那一级显示的名字，填 `docs/str.csv` 里已有的 `STR_` 常量；留空 = 用共享的系列名 |

老工程（或表里还没这三列时）补列：

```bash
python3 tools/migrate_menu_columns.py     # 只补缺的列，可以重复运行
```

> **这是每台车的属性，不是每种涂装的属性。** 同一台车的两种涂装是在**改装菜单**
> （`cargo_subtype`）里选的，永远不会变成购买列表里的两条，也就没有东西可以折叠。

### 8.1 为什么顺序是一列，而不是把表格行拖来拖去

靠「把表格行排好」来决定菜单顺序是行不通的：`assign_ids()` 按**行序**走完四张表，
在各自类别的 ID 区段里依次发号，所以把一行拖到另一行前面，会改变这台车拿到的
**引擎 ID**——而存档记的正是引擎 ID，重排一行就会让存档里的车对不上号。

所以顺序单独占一列：生成器按 `menu_order` 排序（留空的车当作无穷大排在最后，
再按表与行的序号定序），把结果写成 `src/vehiclesort.pnml` 里的
`sort (FEAT_TRAINS, [...])`。行序完全不动，引擎 ID 也就不动。

### 8.2 两级名字：折叠行与组内行

一台车同时是「组头」和「组里的一项」时，两个位置要显示不同的文字：**折叠起来的那
一行显示系列名，展开后组里的那一行显示这台车自己的名字**。

生成器因此给设了 `series_string` 的车**单独写一个名字回调**（`switch_<id>_name`），
没设的车继续共用 `src/functions.pnml` 里的 `switch_name_series`：

```nml
item (FEAT_TRAINS, df4c) {
    property {
        name:                           string(STR_NAME_DF4C);
    }
    graphics {
        name:                           switch_df4c_name;
    }
}

switch (FEAT_TRAINS, SELF, switch_df4c_name, getbits(extra_callback_info1, 0, 8) == 0x20? getbits(extra_callback_info1, 8, 8) : 0xFFFF) {
    0: return string(STR_EXPORT_SERIES);
    return CB_RESULT_NO_TEXT;
}
```

购买菜单问「折叠项叫什么」时用的就是 0 号槽；其他槽一律回 `CB_RESULT_NO_TEXT`，
也就是「不额外给文字」，于是仍然由 `property` 里的 `name` 说了算。这样同一个 `id`
在折叠行读作系列名，在组里读作自己的车名。写法与《中国包：火车》的
`switch_<vehicle>_name` 一致。

### 8.3 生成器接受的写法

分组规则只写在一个地方（`genpnml.check_variant_groups()`），工作台调用的也是它，
所以两边不会各说各话：

* **父项必须在同一张表里**：机车和货车永远不会共用一个购买列表，跨表折叠会直接报
  「同一张表里没有这台车」；
* **不能指向自己**：一台车要让别的车折在自己下面，它自己的 `variant_group` 就得
  留空。写自己会被拒绝：`variant_group 不能指向自己`；
* **不能成环**：`a→b→a` 这种链接会被报出来（`variant_group 形成了环`）；
* **父项自己也分组了只是警告**：嵌套能用，但上游把它标为实验性，本包的约定是
  **只用一层**，所以生成器提醒而不阻止。

`series_string` 必须是**字符串表里已经有的** `STR_` 常量。它已经进了
`collect_referenced_strings()`，所以 `genpnml.py --check` 会把它当普通引用查，
缺了直接报 `MISSING`，而不是等到 nmlc 报 `Unknown string`。

### 8.4 在工作台的「车队总览」里改

> **工作台 → 车队总览（阶段 1）**

车队总览就是按**购买菜单顺序**排的，每张卡片上带这三列的控件：

| 控件 | 作用 |
| ---- | ---- |
| `顺序 N / M` + `▲` `▼` | 在购买菜单里上移 / 下移一位。它会**把整份名单的 `menu_order` 按 10 递重重排**（10、20、30…），所以以后想插到两行之间还有空位 |
| `折叠到` 下拉框 | 合法的父项：**同一张表**、不是自己、也不是自己的后代（否则会成环）。第一项「独立一条」= 清空 `variant_group` |
| `折叠项名称` 输入框 | `series_string`。常量不在字符串表里时旁边会标红「字符串不存在」 |

卡片上还有两个提示标签：「N 个变体折在这里」表示有别的车折在它下面；「自己也折叠了」
表示这台车自己又折在别人下面——就是 8.3 里那个**嵌套警告**。

每次改动都走 `POST /api/fleet-menu`，请求体是
`{"rows":[{"table","id","variant_group","menu_order","series_string"}]}`：
**没带的键保持原样**（所以拖顺序不必重发分组），**带了不认识的键会被拒绝**，改到的
每张表**先全部校验通过才落盘**。存完记得跑一次「生成车辆代码」或 `make gen`，
让 `src/vehiclesort.pnml` 与名字回调跟上。

### 8.5 一次端到端校验

```bash
python3 tools/check_variant_menu.py
```

它临时造出一台机车（`df4ctest`）、折到 `df4c` 下面，然后**完整编译一遍 GRF**，检查分组、
名字回调、两级名字和排序，最后把数据表恢复原样。想自己确认时，这是唯一一个把三列
放在一起跑的检查。

---

## 9. 校核实车数据

`data/*.csv` 中的性能参数目前是**合理工程估算值**，每行 `comment` 都标了
`(estimate)`。要改成真实数据：

1. 查实车铭牌 / 维基 / 厂商资料，得到：轴式、整备重量、牵引功率、
   最高速度、起动牵引力、车长、载客量或载货量。
2. 换算：

   | PNML 字段 | 换算方式 |
   | --------- | -------- |
   | `weight` | 吨 |
   | `power` + `power_unit` | `kW` 或 `hp` |
   | `speed` | km/h（通常取持续速度或构造速度） |
   | `tractive_effort_coefficient` | 见下 |
   | `cost_factor` | 与同类车横向比较，按造价比例给值 |
   | `running_cost_factor` | 与同类车横向比较，按功率/油耗比例给值 |

   `tractive_effort_coefficient` 是 NML 里 0~1 之间的系数，经验换算：

   ```
   系数 ≈ 起动牵引力(kN) / (重量(t) × 9.81)
   ```

   例如 138 t、起动牵引力 440 kN → `440 / (138 × 9.81) ≈ 0.325`。

3. 改 CSV 后 `make`，在游戏里试跑一段，按体感微调 `cost_factor` /
   `running_cost_factor`（这两个直接影响游戏平衡，不必与实车严格对应）。

4. 把 `comment` 里的 `(estimate)` 去掉，并在 `docs/contributor.csv` 里署名。

> **建议**：一次只改一类车，改完 `git commit`，方便回退和比较。

---

## 10. 疑难排查

### 10.1 构建类

| 现象 | 原因与处理 |
| ---- | ---------- |
| `nmlc ERROR: ... does not exist` | 精灵 PNG 没生成。跑 `make sprites`，或先 `make gen` 再 `make` |
| `nmlc ERROR: Image file "gfx/empty.png": 8bpp image does not have a palette` | `gfx/empty.png` 被覆盖成了普通 RGBA PNG。从仓库恢复：`git checkout gfx/empty.png` |
| `nmlc ERROR: Expected a (literal) string` | `string()` 里传了整数或空字符串。NML 的 `string()` **只接受字符串参数**；把数值信息交给游戏自带属性栏显示 |
| `nmlc ERROR: ... Unknown string "STR_XXX"` | `docs/str.csv` 缺这条字符串。跑 `python3 genpnml.py --strings` 补齐，或手工加一行 |
| `nmlc ERROR: Spriteset parameter 1 'name' should be an identifier` | 标识符里含 `-`。应让 `sprite_suffix` 用于**文件基名**，NML 侧会自动把 `-` 换成 `_`；若你手改了生成文件则撤销 |
| `Range overlaps with existing ranges` | 涂装年份区间重复。把两行涂装的年份或 `0..9999` 调整开 |
| `make` 报 `git: ambiguous argument` | `min_compatible_version` 里不是有效的 git 提交号。写一个存在的提交号，或写 `git rev-parse HEAD` 的输出 |
| `make` 报 `*** missing separator` | `Makefile` 的缩进被编辑器换成了空格。**recipe 行必须是 Tab** |

### 10.2 生成器类

| 现象 | 原因与处理 |
| ---- | ---------- |
| `ERROR: vehicle id 'xxx' is declared twice` | 同一个 `id` 在表里出现两次（可能在两个文件里）。改名或删除 |
| `ERROR: ... unknown category 'xxx'` | `category` 拼错。合法值见 `data/README.md` |
| `ERROR: ... name_string 'STR_BAD THING' looks like an NML string but is not valid` | `name_string` 以 `STR_` 开头，但含空格或括号。要么写**纯显示名**（如 `CKD8W (Export)`，生成器会映射成 `STR_NAME_CKD8W`），要么写合法的 `STR_XXX` |
| `ERROR: ... id must be lower case letters, digits and underscores only` | `id` 含大写、连字符或空格。改成 `ckd8w` 这种形式 |
| `ERROR: ID band for category 'xxx' is exhausted` | 该类别 ID 用满了（每段 1024 个，一般不会）。检查是否误加了大量车辆，或改用其他 `category` |
| 加的行「没生效」 | CSV 某格含逗号却没加引号，导致整行**列错位**。用 `python3 tools/vehicle_row.py` 重新写这一行，或先删掉再加 |
| `nmlc ERROR: ... Unknown string "STR_NAME_XXX"` | 忘了跑 `--strings`。直接 `make gen`（它会顺带刷新语言表），或 `python3 genpnml.py --strings` |
| `make check` 报 `MISSING` | 代码引用了 `docs/str.csv` 里没有的字符串。跑 `python3 genpnml.py --strings` 补齐 |
| `make check` 报 `unused` | 语言表里有死字符串。可以删掉，或说明你还在用它（无害） |
| 生成的某辆车没有货物外观开关 | `cargo_variants.csv` 的 `id` 与 `wagons.csv` 对不上，或该行 `sprite_suffix` 为空（空表示"空车"，不生成精灵） |

### 10.3 游戏内类

| 现象 | 原因与处理 |
| ---- | ---------- |
| GRF 加载时红字报错，说需要 `dynamic_engines` | 控制台执行 `set dynamic_engines 1` |
| 报错要求 OpenTTD 13.1 | 升级游戏版本 |
| 车辆不出现 | 引入了但年份未到；或 `dynamic_engines` 没开；或没启用 GRF |
| 涂装菜单只有一项 | 该车在 `liveries.csv` 里只有一行。加行即可；注意第 1 行是"自动" |
| 模型朝向反了 | 在 `data/liveries.csv` 的 `templates` 列改用 `template_reversed`，或在 MagicaVoxel 里把模型绕竖轴转 180° |
| 三节车只有中间一节有车体 | 正常。`power_section` 决定哪一段是车身段，其他段是 `empty_sprites` |
| 某项规则/参数好像按段生效了 | 只有 `cargo_capacity` 是 OpenTTD 按段读取的。功率、重量、速度写成整车普通属性，**不按段下发** |
| 车体浮在轨道上方/陷进去 | 换 `template_speciel_0`（偏低）或 `template_speciel_1`（偏高） |

### 10.4 工作台类

| 现象 | 原因与处理 |
| ---- | ---------- |
| 「保存这一行」说「分节图像有改动没能写回表格」 | 上一步写回失败了（校验没过或请求出错），屏幕上的开关块不是单元格里的内容，所以先按提示改好，或再点一次让它写回。硬存下去会把刚搭好的规则换回旧的 |
| 某个按钮点了没反应，状态栏也没有提示 | 前端请求的路径不对。`app.js` 的 `jsonFetch()` 会自己补 `/api`，调用点写的是**前缀之后**的那一段；写成 `/api/xxx` 会请求 `/api/api/xxx`，服务器只回 404。`python3 tools/check_workbench_routes.py` 不启动服务器就能查出来 |
| 页面还是旧行为 | 改的是 `server.py` / `app.js` 时浏览器要刷新；只改 `genpnml.py` 不用重启（服务器按修改时间自动重载） |
| 端口 4174 上还是旧代码 | 老进程还占着端口。先结束它再启动，否则新进程起不来、页面连的还是旧的 |
| 保存时报「文件在读取之后被改过」 | 数据表在此期间被别的程序改了（比如同时跑校验脚本）。刷新页面重新载入再改一次即可 |
| 运算符下拉里找不到 `<` 和 `>`；选了「区间」有时又变回 `<=` | 都不是控件坏了。`<` / `>` 是糖：`pos>2` 与 `pos>=3`、`pos<2` 与 `pos<=1` 是同一批值，单元格只存 `<=`、`==`、`>=`、区间四种，所以下拉框只列这四种；手写文本里仍可写 `<` / `>`，写回时会被规范化成等价的那种。区间同理：`0..6` 就是 `<=6`、`3..255` 就是 `>=3`、`3..3` 就是 `==3`，两头一旦落回这几种锚点，存回去的就是短写法——想留在区间模式，把小的那头挪开（如 `1..6`），选中「区间」时控件也正是这么摊开的 |

### 10.5 想从头重建

```bash
make clean              # 删除 grf/nml/custom_tags 与所有渲染 PNG
make clean_gen          # 删除三个生成的 PNML
make -j 8               # 完全重建
```

`.nmlcache/` 是 nmlc 的精灵缓存，一般不用删；怀疑缓存坏了就删掉它。

---

## 11. 命令速查

```bash
# ---------- 构建 ----------
make                          # 全套：生成 → 渲染 → 语言 → 编译
make -j 8                     # 并行
make gen                      # 生成 PNML + 补齐 gfx 目录 + 刷新 docs/str.csv（不写 .vox）
make check                    # 校验字符串表（有无缺失 / 死条目）
make sprites                  # 仅渲染 .vox → .png
make lang                     # 仅生成 lang/*.lng
make clean                    # 清理构建产物
make clean_gen                # 删除生成的所有 PNML
make bundle                   # 打包发布 tar

# ---------- 生成器 ----------
python3 genpnml.py --data data --out src          # 等价于 make gen 的第二步
python3 genpnml.py --strings                     # 刷新 docs/str.csv（保留已有译文）
python3 genpnml.py --check                       # 校验字符串表
python3 genpnml.py --clean                       # 删除生成的 PNML
python3 genpnml.py --help                        # 全部选项

# ---------- 数据表工具 ----------
python3 tools/vehicle_row.py columns data/locomotives.csv      # 查看列
python3 tools/vehicle_row.py copy  <表> <源id> <新id> key=value …   # 复制一行并改
python3 tools/vehicle_row.py add   <表> id=… key=value …            # 新增一行
python3 tools/vehicle_row.py remove <表> <id> [--prune]             # 删除一行
python3 tools/clear_vehicle_data.py            # 试运行：清空全部车辆数据
python3 tools/clear_vehicle_data.py --apply    # 真的清空（含体素模型）
python3 tools/build_data_tables.py   # 只重建 liveries.csv 与 cargo_variants.csv
python3 tools/verify_assets.py       # 校验 PNML 引用的精灵是否都存在
python3 tools/check_graphics_parts.py  # 每种分节规则写法都生成并用 nmlc 编译一遍
python3 tools/check_section_lengths.py # 每种 parts 形状都生成并用 nmlc 编译一遍
python3 tools/check_gfx_config.py      # manifest.json / ttd_palette.json 是否与生成器一致
python3 tools/check_string_table.py    # 字符串表的读写与引用是否自洽
python3 tools/check_workbench_routes.py # 工作台前端调的 API 路径都有对应路由（不需要启动服务器）
python3 tools/check_markdown_tables.py  # 文档：表格列数是否对齐、文件是否是 UTF-8
python3 tools/check_purchase_sprite.py # 购买菜单小图能否单独指定（完整编译一遍验证）
python3 str-csv.py docs/str.csv      # docs/str.csv → lang/*.lng

# ---------- 可视化工作台 ----------
make workbench                       # 启动后打开 http://127.0.0.1:4174/workbench/
python3 web/workbench/server.py --port 4174   # 等价写法

# ---------- 只想快速检查语法 ----------
gcc -E -x c chinasettrainsexport.pnml -D REPO_REVISION=1 \
    -D VERSION_STRING=test -D MIN_COMPATIBLE_VERSION=0 -o out.nml
nmlc -c out.nml -o out.grf
```

---

## 12. 进一步阅读

| 文档 | 内容 |
| ---- | ---- |
| `data/README.md` | 每一个数据列的完整说明 |
| `docs/pnml-generation.md` | 生成原理、母包机制映射、NML 语法约束、生成器改写点 |
| `README.md` / `README-zh.md` | 项目简介、构建方式、许可证 |
| `docs/changelog.txt` | 变更记录 |
| `src/template.pnml` | 精灵模板定义（含坐标注释） |
| `src/railtypetable.pnml` | 轨道类型标签的命名规则 |
| `src/functions.pnml` | 共享开关库（编组限制、成本因子、长度开关） |
