# STAS 起飞性能计算工具重构版

本项目用于重构旧版 STAS 桌面工具。目标是把旧版单文件程序拆成清晰、可维护、可测试、可扩展的 Python 项目，为后续新增机型、批量计算、报告扩展和历史记录打基础。

## 当前状态

项目处于第一阶段重构中，已完成基础业务模块：

- `APTRWY.RWY` 跑道数据解析。
- 机型配置注册表。
- `738` 和 `777F` 机型配置。
- `738` 和 `777F` STAS 输入模板。
- STAS 输入文件生成器。
- 性能计算参数校验。
- STAS 外部程序调用服务。
- 独立输出目录和运行元数据保存。
- Word 报告导出模块。
- PDF 报告转换模块。
- 队列级 Word/PDF 合并报告。
- 临时起飞分析格式与手册起飞分析格式两套 Word/PDF 输出，按当前报告选择互斥生成。
- 报告导出前可从运行用 `APTRWY.RWY` 补全 STAS 截断的 AIRPORT2 特殊程序文本。
- 单次性能计算编排服务。
- 应用级 TOML 配置读取。
- 最小命令行联调入口。
- DearPyGui 桌面 UI 第一版。
- 基础自动化测试。

旧版 `733` 机型已从新版支持范围中移除。旧资料仍保留在 `examples/` 中，仅作为历史参考。

## 本次跑道数据更新

- AIRPORT2 `#INT` 复合交叉口会拆分为多个非全跑道，例如 `D4-C8` 生成 `D4-15L` 和 `C8-15L`，不再生成超过 STAS 限制的 `D4/C8-15L`。
- 非全跑道标识长度超过 8 个字符时会直接报错；已有 `H4/G6-15L` 这类复合标识会先拆成 `H4-15L` 和 `G6-15L`。
- 跑道数据模型记录 TORA 和是否为非全跑道；桌面界面可勾选启用最小 TORA 过滤。
- 机场跑道数据导入区域已移入“机场跑道数据管理”折叠区，减少左侧常用计算表单拥挤。

## 支持机型

新版第一阶段只支持：

- `738`
- `777F`

后续新增机型应优先新增：

```text
config/aircraft/新机型.toml
templates/新机型.inp
```

不要在 UI 或主流程中为每个机型写硬编码判断。

## 真实 STAS 最小联调

当前已提供命令行入口，用于在迁移 UI 前验证真实 `STAS.exe` 链路。

建议先把 STAS 运行目录复制到本地忽略目录，避免直接改动 `examples/` 中的旧版资料：

```powershell
New-Item -ItemType Directory -Force runtime
Copy-Item -Recurse -Force "examples\STAS old\STAS" "runtime\stas"
Copy-Item -Force config\app.example.toml config\app.local.toml
```

然后按需修改：

```text
config/app.local.toml
```

运行一次最小计算：

```powershell
python run_stas.py calculate --config config/app.local.toml --aircraft 738 --airport EGNX --runway 09
```

说明：

- `config/app.local.toml`、`runtime/` 和 `output/` 已被 `.gitignore` 忽略。
- 命令行入口只用于本地联调，后续正式界面仍应调用 `PerformanceService.calculate()`。
- Word/PDF 依赖不可用时会显示警告，但 STAS 原始输出仍会归档到 `output/`。
- 当前本机已用 `EGNX/09 + 738` 跑通真实 STAS 核心计算，并成功生成 Word 报告。
- 当前本机安装 `comtypes` 和 `pywin32` 后，已成功生成 PDF 报告。

## 安装方法

核心模块优先使用 Python 标准库。桌面界面和报告导出存在可选依赖：

- 桌面界面：需要 `dearpygui`。
- Word 报告：需要 `python-docx`。
- PDF 转换：需要 Windows、Microsoft Word、`comtypes` 和 `pywin32/pythoncom`。

缺少报告依赖时，导出模块会返回清晰失败结果，不影响 STAS 原始输出保存。

PDF 依赖安装命令：

```powershell
python -m pip install dearpygui
python -m pip install comtypes pywin32
```

当前本机已安装 `dearpygui 2.3.1`，不再依赖 `tkinter` / Tcl/Tk。

## 桌面界面

启动命令：

```powershell
python run_desktop.py
```

第一版桌面界面已迁移到 `src/stas_app/ui/`，使用 DearPyGui 制作，只负责收集输入、调用 `PerformanceService.calculate()`、展示输出路径和错误提示。

当前已实现：

- 机型选择：只加载 `738` 和 `777F`。
- 机场和跑道选择：优先来自 `APTRWY_MASTER.RWY` 主库；AIRPORT2 的 `#INT` 交叉口会在内存中生成短跑道供界面选择；计算前自动生成 STAS 实际读取的 `APTRWY.RWY`。
- 跑道过滤：勾选启用后按最小 TORA 筛选可见跑道，被过滤掉的跑道不会显示也不能被选择；跑道列表只显示跑道名。
- 机场数据导入：GUI 可在“机场跑道数据管理”折叠区通过文件选择器选择外部 `.RWY`、`.rwy` 或 `.stx` 文件；后缀判断大小写不敏感，预览新增/覆盖/跳过机场，并导入到 `APTRWY_MASTER.RWY`。
- QNHREF 输出标注：默认在 `DESCRIBE $...$` 中标注 `QNHREF = 当前值`；取消“输出中标注 QNHREF”后保留 `DESCRIBE $$`，但实际计算参数 `QNHREF = 当前值` 仍会写入 STAS 输入。
- 跑道使用复选框支持多选，并提供全选、全不选和反选；批量选择只作用于当前过滤后可见的跑道。
- QNH、QNHREF 输出标注、温度范围、风速范围等全局计算参数输入。
- 防冰、引气/空调、道面条件、污染深度和推力按“当前顺序项”维护。
- 推力（顺序项）改为下拉框：`738` 固定为“正常”且不可输入；`777F` 支持“正常”“减推力10%”“减推力20%”“1L1BUMP”。
- 右侧面板按“报告输出 / 已保存队列方案 / 当前输出顺序 / 计算结果”排列；报告输出区域保留手册起飞分析格式选择，并放置“加入当前顺序项”“加入默认四项”“只算当前”和“重置”操作按钮。
- 当前输出顺序列表会压缩跑道号显示，例如 `RWY 10L/10R/+3`，避免跑道过多挤掉后续计算条件。
- 报告生成会保留 `STASOUT.out` 原始输出，同时在需要时生成 `STASOUT.enriched.out` 作为 Word/PDF 读取源，补全超长 `ENG-OUT PROCEDURE`；`NO EMERGENCY TURN` 不做补全。
- 已保存队列方案会保存温度范围、风速范围、QNH、QNHREF 输出标注和每条顺序项条件，但不保存机型、机场、跑道和手册格式。
- 污染深度会随道面条件联动：积水、雪浆、干雪启用输入，其他道面条件自动清空并禁用。
- 后台线程执行计算，避免界面卡死。
- 查看原始输出、输出目录和报告文件；临时 Word/PDF 与手册 Word/PDF 在计算结果区分别通过下拉菜单打开。
- 执行 Scenario 队列后，可查看队列级合并原始输出、Word 报告、PDF 报告和输出目录。

当前限制：

- 如果缺少 `dearpygui`，`run_desktop.py` 会给出安装命令提示。
- 本轮已完成不打开窗口的 DearPyGui 控件构建检查；仍建议在桌面环境中人工点击验证一次完整流程。
- SMB 同步、历史记录和批量计算尚未迁移。
- AIRPORT2 `#INT` 交叉口短跑道已在界面/校验/运行文件生成中自动处理；当前导入仍保留机场完整原始块，不直接改写主库内容。

建议 Python 版本：

```text
Python 3.13 或更高
```

## 如何运行测试

在项目根目录执行：

```powershell
python -m unittest discover -s tests -p 'test_*.py'
```

当前测试覆盖：

- 跑道文件解析。
- 机型配置读取。
- STAS 输入文件生成。
- 参数校验。
- STAS 外部程序执行流程。
- 单次性能计算编排流程。
- 应用配置读取和服务组装。
- 命令行联调入口参数解析。
- DearPyGui 桌面 UI 表单值到 `PerformanceRequest` 的转换。
- 真实 STAS 联调中的临时目录设置。
- 运行输出归档和元数据保存。
- Word/PDF 报告导出。
- 队列级合并报告导出。
- `733` 从新版支持中移除。

## 如何打包试用版

当前使用 PyInstaller 目录版打包，配置文件为：

```text
FlightDeviationTool.spec
```

打包命令：

```powershell
python -m PyInstaller --noconfirm FlightDeviationTool.spec
```

打包后的试用目录位于：

```text
dist/FlightDeviationTool/
```

当前试用目录按外置 STAS 方式组织：

```text
dist/FlightDeviationTool/
├── FlightDeviationTool.exe
├── config/
│   └── app.local.toml
├── runtime/
│   └── stas/
│       ├── STAS.exe
│       ├── APTRWY.RWY
│       └── APTRWY_MASTER.RWY
├── templates/
└── output/
```

`STAS.exe` 不打进主程序 exe 内部，而是放在 `runtime/stas/`。程序启动时会以 `FlightDeviationTool.exe` 所在目录作为基准读取 `config/app.local.toml`，再按配置寻找 STAS、模板和输出目录。

## 项目结构

```text
.
├── config
│   └── aircraft
│       ├── 738.toml
│       └── 777F.toml
├── docs
├── examples
│   └── STAS old
├── src
│   └── stas_app
│       ├── exporters
│       ├── models
│       ├── parsers
│       ├── services
│       ├── ui
│       └── storage
├── templates
│   ├── 738.inp
│   └── 777F.inp
└── tests
```

## 核心模块说明

### parsers

`src/stas_app/parsers/runway_parser.py`

负责解析 `APTRWY.RWY`，输出结构化机场和跑道数据。

### models

`src/stas_app/models/`

定义机型配置、推力选项、用户请求和跑道数据结构。

### services

`src/stas_app/services/`

当前包含：

- `aircraft_registry.py`：读取机型 TOML 配置。
- `app_factory.py`：根据应用配置组装 `PerformanceService`。
- `input_builder.py`：根据模板和用户参数生成 STAS 输入文件。
- `performance_service.py`：统一编排参数校验、输入生成、STAS 执行和报告导出。
- `runway_intersection_generator.py`：根据 AIRPORT2 `#INT` 自动生成交叉口短跑道，并合并多行 EOSID 文本。
- `runway_procedure_enricher.py`：报告导出前从运行用 `APTRWY.RWY` 提取完整特殊程序，生成报告用 `STASOUT.enriched.out`。
- `runway_runtime_file.py`：计算前从主库提取机场块，生成 STAS 实际读取的 `APTRWY.RWY`。
- `stas_engine.py`：调用外部 STAS 程序，归档原始输出和错误信息。
- `validation.py`：校验机型、机场、跑道、温度、风、QNH 和推力选项。

### ui

`src/stas_app/ui/`

当前包含：

- `desktop_app.py`：DearPyGui 主界面。
- `forms.py`：表单值转换和结果摘要格式化，不依赖 GUI 框架，便于测试。

### exporters

队列级合并报告已经由 `queue_report.py` 接管。Scenario 队列执行完成后，成功的计算结果会按队列顺序合并到一个队列级输出目录中，生成 `STAS_QUEUE.out`、`STAS_QUEUE.docx`，并在 PDF 环境可用时生成 `STAS_QUEUE.pdf`。失败的 Scenario 会保留在界面摘要和警告中，不阻断成功项合并。

`src/stas_app/exporters/`

当前包含：

- `queue_report.py`：按 Scenario 队列顺序生成队列级合并报告。
- `word_report.py`：从 STAS 输出或补全后的报告输出生成 Word 报告。
- `pdf_report.py`：通过 Microsoft Word COM 把 Word 转 PDF。

### storage

`src/stas_app/storage/`

当前包含：

- `config_repository.py`：读取应用级 TOML 配置，并解析真实 STAS 路径、工作目录和输出目录。
- `output_manager.py`：为每次计算创建独立输出目录，并写入 `run_metadata.json`。

## 常见问题

### 为什么不再支持 733？

这是已确认的新版范围调整。`733` 不进入新版功能和测试范围，旧资料只保留在 `examples/` 中。

### 为什么机型配置使用 TOML？

TOML 可由 Python 标准库 `tomllib` 读取，不需要额外安装依赖。这样第一阶段更容易部署和测试。

### 当前能直接打开桌面界面吗？

代码层面已提供第一版 DearPyGui UI，启动命令是 `python run_desktop.py`。如果提示缺少 DearPyGui，请先执行 `python -m pip install dearpygui`。

### 当前会调用 STAS.exe 吗？

新版服务层已经封装了外部程序调用能力，但当前自动化测试使用模拟 STAS 脚本，不依赖真实 `STAS.exe`。

### 后续 UI 应该调用哪个入口？

后续 UI 扩展时，优先调用 `PerformanceService.calculate()`。界面只负责收集输入和展示结果，不需要知道校验、模板、STAS 执行和报告导出的内部细节。

### 当前能生成报告吗？

Word/PDF 导出层已经拆出。原有输出已命名为“临时起飞分析格式”。未选择手册格式时，单条计算生成 `临时起飞分析.docx` 和可选 `临时起飞分析.pdf`，Scenario 队列生成 `STAS_QUEUE.out`、`队列_临时起飞分析.docx` 和可选 `队列_临时起飞分析.pdf`；选择手册格式时，单条和队列都只生成手册起飞分析 Word/PDF，不再同时生成临时起飞分析报告。

手册起飞分析格式已新增 4 个模板选项：`738 正常`、`777F 正常`、`777F 减推力`、`777F BUMP`。模板来自 `templates/reports/manual_takeoff/`，配置入口为 `templates/reports/manual_takeoff/templates.toml`。桌面界面会把当前选择的手册格式作为报告格式统一应用到本次单条或队列计算；选择“不生成手册格式”时只生成临时起飞分析格式，选择具体手册模板时只生成手册起飞分析格式。

手册格式正文会保留样例中的 `      ELEVATION` 前导空格。每个 `ELEVATION` 计算段按独立页面输出，导出器会根据段落长度自动使用正常、紧凑或更紧凑的字号和行距，并用段首分页方式减少额外空白页。

Word 导出需要 `python-docx`；PDF 转换需要 Windows 和 Microsoft Word COM。依赖不可用时会返回失败结果，但不会影响原始 STAS 输出。

## 后续扩展方向

优先级建议：

1. 实机打开 DearPyGui 版 `run_desktop.py`，人工验证完整计算和打开报告流程。
2. 迁移 SMB 跑道文件同步。
3. 增加批量计算。
4. 增加历史记录和结果对比。
5. 增加更多机型配置和模板。
# 2026-05-22 临时起飞分析模板补充

临时起飞分析 Word/PDF 现在也使用 Word 模板生成。模板文件放在与手册模板相同的目录：

```text
templates/reports/manual_takeoff/temporary_default.docx
templates/reports/manual_takeoff/temporary_templates.toml
```

`temporary_default.docx` 保留页眉、logo、页边距和正文样式，导出器只清空正文并重新写入 STAS 报告内容。以后调整临时起飞分析样式时，优先修改这个 Word 模板；手册模板仍由 `templates.toml` 管理，临时模板由 `temporary_templates.toml` 管理。
# 2026-05-22 报告日期自定义

报告输出区域新增“自定义报告日期”。默认不勾选时继续使用 STAS 输出里的 `DATED` 日期；勾选后可选择日、英文月份缩写和年份，例如 `04-APR-2026`。

该设置只影响生成的 Word/PDF 报告，不修改原始 `STASOUT.out`。执行队列时，所有成功项统一使用当前界面选择的同一个报告日期；队列方案不保存该日期。

# 2026-05-24 单点计算

桌面界面新增独立的“单点计算”页面，通过顶部按钮在“报告/队列计算”和“单点计算”之间切换。该页面不生成手册 Word/PDF，只调用 STAS 的 `OUTPUT OPTION VARIABLE` 表格输出，按单条跑道和单个起飞重量返回结果。

当前支持 `777F` 和 `738`。输出分为：

- `FULL`：实际温度结果，显示 `OAT`、`V1/VR/V2`、`VREF30` 或 `VREF`、`TO` 和 `ACCEL HT`。
- `ATM`：假设温度结果，默认计算最大假设温度，也可输入指定假设温度；显示 `ATM TEMP`、`V1/VR/V2`、`VREF30` 或 `VREF`、`D-TO`、`REDUCTION` 和 `ACCEL HT`。

字段来源：

- `V1 = CLIMIT(019)`
- `VR = CLIMIT(006)`
- `V2 = CLIMIT(005)`
- `VREF30 / VREF = SPOUTA(005)`，777F 显示 `VREF30`，738 显示 `VREF`
- `TO / D-TO = CLIMIT(028)`
- `REDUCTION = SPOUTA(032)`
- `ACCEL HT = ACCSEG(002)`

速度、`VREF30/VREF` 和 `ACCEL HT` 使用传统四舍五入输出整数；`ACCEL HT` 显示单位 `ft AGL`；`TO / D-TO` 保留 1 位小数；`REDUCTION` 保留 1 位小数并显示 `%`。

结果右侧新增 `Runway Distance`，随 `FULL/ATM` 当前显示项一起切换：

- `AE-GO = CLIMIT(026) + POPT(012)`，最后四舍五入取整。
- `EO-GO = CLIMIT(023) + POPT(012)`，最后四舍五入取整。
- `ACCEL-STOP = CLIMIT(024) + POPT(013)`，最后四舍五入取整。
- `POPT(012)` 和 `POPT(013)` 从渲染后的单点输入模板 `POPT` 段读取；当前 777F 为 `51/77`，738 为 `30/45`。
- `TORA/TODA/ASDA/SLOPE` 从当前跑道的 `APTRWY.RWY` 记录解析。

注意：单点计算模板会始终写入 `POPT(024) 对比重量,目标起飞重量`。`777F` 的对比重量为 `25000 KG`，`738` 的对比重量为 `20000 KG`，用于满足 STAS `STASTBL` 表格输出要求。

### 2026-05-24 单点计算界面补充

单点计算页面改为上方输入、下方结果显示。跑道选择复用手册界面的最小 TORA 过滤逻辑，但单点页面只允许选择一条跑道。计算按钮固定在输入区顶部，避免需要滚动后才能点击；`重置` 按钮会恢复单点页面所有输入初始值并清空结果。

新增输入：
- `FLAP`：777F 默认 `FLAP 15`，可选 `FLAP 5/15/20`；738 默认 `FLAP 5`，可选 `FLAP 1/5/10/15/25`。
- `使用改进爬升`：默认开启；开启时 `POPT(7)=0`，关闭时 `POPT(7)=1`，`POPT(8)` 保持模板原值不变。

结果区默认显示 `FULL`，可用 `FULL/ATM` 按钮切换同一次计算的两组结果。`Engine Failure Procedure` 从运行用 `APTRWY.RWY` 当前跑道记录读取；`*** NO EMERGENCY TURN ***` 只显示标题，特殊程序会保留换行显示详细内容。
