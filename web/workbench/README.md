# 出口铁路载具制作工作台

一个**本地运行**的可视化工作台，把本工程的操作链路（数据表 → 单车 PNML → 体素模型 →
精灵图 → GRF）搬到浏览器里。参考并沿用 `openttd-newgrf-builder` 的
`web/workbench` 结构：纯 Python 标准库的 HTTP 服务 + 原生 JavaScript 前端，
不需要 npm、不需要打包步骤。

## 启动

```bash
python3 web/workbench/server.py
# 或
make workbench
```

然后打开 <http://127.0.0.1:4174/workbench/>。

只监听回环地址，面向单人制作与审核，不提供多用户权限或远程部署能力。

## 设计原则

**工作台不重新实现任何生成逻辑。** 服务器只做三件事：

1. 读 `data/*.csv`；
2. 看 `src/` 与 `gfx/` 里的文件状态；
3. 用 `subprocess` 调用仓库里已有的工具。

所有真实工作仍由这些命令完成：

| 命令 | 作用 |
| ---- | ---- |
| `genpnml.py --strings` | 刷新 `docs/str.csv` |
| `genpnml.py --data data --out src --vox` | 写每台车的 `.pnml` 与占位 `.vox` |
| `genpnml.py --check` | 字符串表双向核对 |
| `tools/verify_assets.py` | 贴图引用与渲染结果核对 |
| `make sprites` | `renderobject` 渲染 8 方向精灵图 |
| `make` | 预处理 + `nmlc` 编译出 `.grf` |

界面里的每个表单字段都来自 `schema.py`，所以给数据表加一列时**只需要改
`schema.py`**，前端会自动出现对应控件。

## 八个阶段

| 阶段 | 内容 |
| ---- | ---- |
| 1 车队账本 | 四张表的汇总，显示 ID 段分配、轨距标签、贴图是否就绪；可搜索、按表筛选 |
| 2 车辆明细 | 46 列按语义分组渲染，右侧实时显示该车将生成的 PNML |
| 3 涂装方案 | `liveries.csv`，行序即涂装索引 |
| 4 货运外观 | `cargo_variants.csv`，附开关链路示意 |
| 5 模型与精灵图 | 每个 basename 的裁剪预览（按 `manifest.json` 的真实坐标，不是等分网格） |
| 6 一致性检查 | 字符串表与贴图引用检查，输出滚动显示 |
| 7 构建 GRF | `make` 的完整日志与产物体积 |
| 8 指南 | 离线浏览仓库内的中文文档 |

左栏的「确定性操作」与各阶段的按钮都走同一条作业通道：任务在后台线程里跑，
前端轮询增量日志，因此长编译不会让页面卡住。

## 接口

| 方法 | 路径 | 作用 |
| ---- | ---- | ---- |
| GET | `/api/schema` | 列元数据、类别、ID 段、轨距标签、货物标签 |
| GET | `/api/state` | 车队、涂装、外观、ID 分配、贴图状态、GRF 体积 |
| GET | `/api/vehicle?table=&id=` | 一台车的完整数据行 |
| GET | `/api/pnml?table=&id=` | 该车已生成的 PNML 文本 |
| GET | `/api/sheet?path=` | 精灵图里 8 个视图的精确裁剪框 |
| GET | `/api/file?path=` | 仓库内文件（预览 PNG / GRF） |
| GET | `/api/text?path=` | 仓库内文本（指南） |
| GET | `/api/job?job=&cursor=` | 增量读取作业输出 |
| POST | `/api/save` `/api/copy` `/api/delete` | 增删改数据行 |
| POST | `/api/run` | 白名单动作：`gen` `vox` `render` `check` `build` `clean_gen` |

## 写入安全

工作台会直接修改编译源数据，因此有四道闸门：

1. **写前校验**（与 `genpnml.py` 同样的规则）：id 合规、表内不重名、`folder`
   是单层目录、`parts` 与 `power_section` 自洽、`track_type` 必须在
   `src/railtypetable.pnml` 里、涂装与外观的 `id` 必须指向真实存在的车。
   校验失败时不写盘，错误逐条列在状态栏。
2. **原子写 + 备份**：先写临时文件再 `os.replace`，原文件留
   `<table>.workbench.bak`。
3. **路径围栏**：所有路径经 `repo_path()` 解析，拒绝逃出仓库。
4. **未知列不丢**：保存时以读到的原始行为基底做合并，将来给 CSV 加列不会被
   工作台抹掉。

## 关于精灵图裁剪

`renderobject` 输出的 `_32bpp.png` **不是等分网格**：8 个视图宽度不同
（36 / 120 / 192 px），每格后带 8 px 透明内边距，高度方向居中。服务器读取同目录的
`manifest.json` 与 PNG 头部尺寸算出每格的精确裁剪框，和 `src/template.pnml` 里
手写的坐标一致。前端如果按固定网格切图会把车切成两半，所以必须走 `/api/sheet`。

## 文件位置

- 界面：`web/workbench/index.html`、`app.js`、`style.css`
- 服务：`web/workbench/server.py`
- 列元数据：`web/workbench/schema.py`
- 精灵图基名缓存：`gfx/.workbench-sprites.json`（由 `--sprite-manifest` 写出）
- 表格备份：`data/<table>.csv.workbench.bak`
