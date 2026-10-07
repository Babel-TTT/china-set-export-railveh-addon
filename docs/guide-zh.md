# 操作指南

本文是《中国包：出口铁路载具附加包》的完整操作手册。
如果你只想**加一辆车**，直接看[第 4 章](#4-加一辆新车完整流程)；
想**画模型**看[第 5 章](#5-制作模型vox)；
**出错**看[第 8 章](#8-疑难排查)。

---

## 目录

1. [环境准备](#1-环境准备)
2. [五分钟上手](#2-五分钟上手)
3. [工程结构与生成物](#3-工程结构与生成物)
4. [加一辆新车（完整流程）](#4-加一辆新车完整流程)
5. [制作模型（.vox）](#5-制作模型vox)
6. [加涂装与货物外观](#6-加涂装与货物外观)
7. [校核实车数据](#7-校核实车数据)
8. [疑难排查](#8-疑难排查)
9. [命令速查](#9-命令速查)

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
    ├── clear_vehicle_data.py     ★ 清空全部车辆数据与占位模型
    ├── build_data_tables.py      重新生成 data/*.csv（保证引号正确）
    └── verify_assets.py          校验：PNML 引用的精灵是否都存在
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
                         └─► gfx/<目录>/*.vox（占位模型）

gfx/**/*.vox ──renderobject──► gfx/**/*_32bpp.png
docs/str.csv ──str-csv.py────► lang/*.lng
chinasettrainsexport.pnml ──gcc -E──► .nml ──nmlc──► .grf
```

### 3.3 常用 make 目标

| 命令 | 作用 |
| ---- | ---- |
| `make` | 全套：生成 → 渲染 → 语言 → 编译 |
| `make -j 8` | 同上，8 个任务并行 |
| `make gen` | **只**从 `data/` 重新生成 PNML、占位模型与语言表 |
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
    category=wagon folder=wagons model=triple "parts=2|2|2" power_section=1 \
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
| `folder` | `diesel` | `gfx/` 与 `src/` 下的子目录 |
| `model` | `single` | `single` = 单体车；`triple` = 三段铰接 |
| `parts` | `6` | 长度。三段车写 `2\|8\|2` 这种形式 |
| `power_section` | `0` | 哪一段承载车体、功率、载量 |
| `intro_year` | `2022` | 引入年份 |
| `model_life` | `VEHICLE_NEVER_EXPIRES` | 或写年数 |
| `track_type` | `BACN` | 取自 `src/railtypetable.pnml` |
| `speed` / `power` / `weight` | `120` / `2800` / `138` | 性能参数 |
| `tractive_effort_coefficient` | `0.26` | 机车用 |
| `cost_factor` / `running_cost_factor` | `84` / `66` | 成本因子 |
| `capacity` | `1` | 机车固定写 `1` |
| `ac_supply` | `1` | 能给车厢供电（机车/发电车） |
| `comment` | `... (estimate)` | 仅给人看，生成器忽略 |

> **不要写车辆 ID、不要写 sprite_id、不要写开关名。** 这些都由生成器算出来。

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
4. 在 `src/vehiclesort.pnml` 里把它排在机车表的位置；
5. 在 `docs/str.csv` 补上 `STR_NAME_CKD8W`、`STR_FULL_NAME_CKD8W`；
6. 在 `gfx/diesel/` 生成 `ckd8w.vox` 占位模型。

### 步骤 3：编译

```bash
make
```

此时 `ckd8w.vox` 还是占位模型，但**已经可以编译通过**。先用它验证 NML 逻辑正确，
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

`--prune` 会删掉该车的 `.pnml` 与占位 `.vox`；即使不用 `--prune`，
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

### 5.2 用占位模型起步（最快）

`make gen` 已经为每个需要的精灵生成了 `.vox`：

* 一个 `<id>.vox`（车体基础涂装）
* 每个涂装一个 `<id>-<涂装后缀>.vox`
* 每个货物外观一个 `<货物后缀>.vox` 及 `<货物后缀>-<涂装>.vox`

这些占位模型**形状正确、颜色可区分**，可以直接编译进游戏。
你可以：

* **直接用**：先玩起来，以后再替换；
* **在它的基础上改**：用 MagicaVoxel 打开，把方块改掉；
* **完全重画**：只需保持**画布尺寸与坐标方向一致**。

### 5.3 用 MagicaVoxel 画

1. 打开 MagicaVoxel，新建模型。
2. **画布尺寸要够长**：长度方向建议 ≥ 32 体素（对应约 192 px 的侧视图），
   宽 8 体素左右，高 12~16 体素。
   参考 `gfx/manifest.json` 的 `size`：`{"x": 192, "y": 48, "z": 80}`。
3. 让**车体纵轴沿着长度方向**（占位模型就是这样摆的）。
4. 导出为 `.vox`，覆盖 `gfx/<目录>/<基名>.vox`。
5. 渲染并检查：

```bash
make sprites
```

   然后打开 `gfx/<目录>/<基名>_32bpp.png` 目视检查——它应当是一张宽 992 px 的
   长条图，8 个视角从左到右排列。**如果车头朝向不对、或车体偏上偏下**，
   在同一张图里就能看出来。

6. 位置微调：如果车体相对轨道偏高/偏低，把 `src/usercode.pnml` 里该车用的
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

如果列出缺失文件，说明某个涂装/货物外观的 `.vox` 还没生成或没渲染——
跑 `make gen && make sprites` 即可。

---

## 6. 加涂装与货物外观

### 6.1 加一套涂装

编辑 `data/liveries.csv`，为同一个 `id` 追加行。**行序即涂装序号**：

```csv
id,sprite_suffix,string,from_year,to_year,purchase_suffix,templates
ckd8w,,STR_BUILD_YEAR,0,2019,,
ckd8w-exblue,exblue,STR_EXPORT_BLUE,2020,9999,,
ckd8w-gray,gray,STR_EXPORT_GRAY,0,9999,,
```

规则：

* **第 1 行 = 索引 0 = 自动涂装**。若存在真实年份区间的涂装，会自动按
  `build_year` 选择。
* `0` 与 `9999` 表示「始终可用」，**不会**生成多余的 case（避免母包里的
  `Range overlaps` 警告）。
* 索引 1、2… 是玩家在**改装菜单**里能显式选的涂装。
* `sprite_suffix` = 精灵基名后缀 → 需要 `gfx/<目录>/<id>-<后缀>.vox`。
* `string` 是菜单里的显示文字，需是 `docs/str.csv` 中已有的 `STR_` 常量，
  否则在 `docs/str.csv` 里补一行。

然后：

```bash
make gen          # 生成新涂装的 spriteset + 占位 .vox
make              # 渲染并编译
```

`make gen` 会为 `exblue`、`gray` 生成**颜色不同**的占位模型，便于一眼区分。

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

## 7. 校核实车数据

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

## 8. 疑难排查

### 8.1 构建类

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

### 8.2 生成器类

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

### 8.3 游戏内类

| 现象 | 原因与处理 |
| ---- | ---------- |
| GRF 加载时红字报错，说需要 `dynamic_engines` | 控制台执行 `set dynamic_engines 1` |
| 报错要求 OpenTTD 13.1 | 升级游戏版本 |
| 车辆不出现 | 引入了但年份未到；或 `dynamic_engines` 没开；或没启用 GRF |
| 涂装菜单只有一项 | 该车在 `liveries.csv` 里只有一行。加行即可；注意第 1 行是"自动" |
| 模型朝向反了 | 在 `data/liveries.csv` 的 `templates` 列改用 `template_reversed`，或在 MagicaVoxel 里把模型绕竖轴转 180° |
| 三节车只有中间一节有车体 | 正常。`power_section` 决定哪一段显示车体，其他段是 `empty_sprites` |
| 车体浮在轨道上方/陷进去 | 换 `template_speciel_0`（偏低）或 `template_speciel_1`（偏高） |

### 8.4 想从头重建

```bash
make clean              # 删除 grf/nml/custom_tags 与所有渲染 PNG
make clean_gen          # 删除三个生成的 PNML
make -j 8               # 完全重建
```

`.nmlcache/` 是 nmlc 的精灵缓存，一般不用删；怀疑缓存坏了就删掉它。

---

## 9. 命令速查

```bash
# ---------- 构建 ----------
make                          # 全套：生成 → 渲染 → 语言 → 编译
make -j 8                     # 并行
make gen                      # 生成 PNML + 占位 .vox + 刷新 docs/str.csv
make check                    # 校验字符串表（有无缺失 / 死条目）
make sprites                  # 仅渲染 .vox → .png
make lang                     # 仅生成 lang/*.lng
make clean                    # 清理构建产物
make clean_gen                # 删除生成的所有 PNML
make bundle                   # 打包发布 tar

# ---------- 生成器 ----------
python3 genpnml.py --data data --out src --vox   # 等价于 make gen 的第二步
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
python3 tools/clear_vehicle_data.py --apply    # 真的清空（含占位模型）
python3 tools/build_data_tables.py   # 重新生成 data/*.csv（保证 CSV 引号正确）
python3 tools/verify_assets.py       # 校验 PNML 引用的精灵是否都存在
python3 str-csv.py docs/str.csv      # docs/str.csv → lang/*.lng

# ---------- 只想快速检查语法 ----------
gcc -E -x c chinasettrainsexport.pnml -D REPO_REVISION=1 \
    -D VERSION_STRING=test -D MIN_COMPATIBLE_VERSION=0 -o out.nml
nmlc -c out.nml -o out.grf
```

---

## 10. 进一步阅读

| 文档 | 内容 |
| ---- | ---- |
| `data/README.md` | 每一个数据列的完整说明 |
| `docs/pnml-generation.md` | 生成原理、母包机制映射、NML 语法约束、生成器改写点 |
| `README.md` / `README-zh.md` | 项目简介、构建方式、许可证 |
| `docs/changelog.txt` | 变更记录 |
| `src/template.pnml` | 精灵模板定义（含坐标注释） |
| `src/railtypetable.pnml` | 轨道类型标签的命名规则 |
| `src/functions.pnml` | 共享开关库（编组限制、成本因子、长度开关） |
