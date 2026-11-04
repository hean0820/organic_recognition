# 结构简式视听识别与 3D 展示系统

基于 AMD Zynq-7020 的有机物识别与分子可视化作品。本 README 提供项目概览、提交目录说明及从最终模型参数构建硬件、制作运行包和上板验证的步骤。

## 项目简介

本项目是一套面向化学学习的有机物识别与分子可视化系统，基于 **AMD Zynq-7020** 平台，将纸面手写结构简式、语音选择和分子三维展示连接起来，支持 **22 类预设有机物**。可用于化学课堂演示、知识复习和科普互动，帮助使用者理解结构简式与分子空间结构之间的联系。

作品针对课堂演示中书写结构简式、查找物质信息和切换三维模型往往分开进行的问题，将摄像输入、化学名称语音输入及三维观察组织为统一交互流程。与通用化学图像结构重建工具的目标不同，本作品侧重资源受限 Zynq 平台上的定点 CNN、软硬件协同和教学展示集成。

### 主要功能

- **手写结构简式识别：**用户将支持类别的手写结构简式置于摄像头识别区域。系统采集画面、完成图像预处理，形成 64×64 单通道输入，再通过定点卷积神经网络输出类别，显示名称、化学式、相关性质及对应的预置三维模型。
- **语音选择：**通过开发板的板载麦克风输入有机物名称，由板端完成语音识别，并更新分子选择和展示。
- **分子三维观察：**支持观察预置分子的原子、化学键和空间结构。HDMI 展示旋转球棍模型；网页提供拖拽旋转、缩放、平移、自动旋转、速度调节、暂停及复位视角等操作。
- **HDMI 与网页交互：**开发板通过 HDMI 显示预览和本地三维内容；电脑通过局域网网页选择分子、发起识别和查看结果。网页与 HDMI 的视角独立，网页不是 HDMI 视频画面的镜像。
- **本地运行：**识别与三维资源在本地运行，正常使用不依赖云端推理。网页与开发板交互需要局域网连接。
- **请求与退出管理：**支持模式切换、手动选择、结果清空和取消；对空白、过暗、笔迹触边及低置信度输入给出提示，并校验请求身份以避免迟到结果覆盖当前显示。使用结束后通过统一停止入口关闭任务并释放硬件资源。

系统执行的是预设类别识别，并调用相应的预置分子模型；不将其表述为可以识别任意有机物结构或由任意图像自动生成三维分子。

### 软硬件分工

系统采用 Zynq 的 PS/PL 协同结构。PL 是 FPGA 可编程逻辑，PS 是 ARM 处理器系统。

- **PL：**负责 OV5640 摄像采集、HLS 实现的 ROI 缩小、灰度转换、滤波和背景校正、完整手写 RTL CNN 推理、音频采集及视频输出。CNN 包含三层卷积和两层全连接，Conv3 使用四路输出通道并行，一次 START 完成整网并输出 22 个有符号 INT32 分值。音频通路负责 I2S 接收、滤波抽取及 FIFO 缓冲，向 PS 提供 16 kHz 单声道 PCM16。
- **PS：**负责应用调度、后段图像整形、硬件控制、语音识别、HDMI 端三维及界面渲染和网页服务。其中图像整形包括连通域筛选、目标定位与裁剪、无效输入拒识、灰度归一化，再等比例缩放最长边至 56 像素，居中放入 64×64 输入画布。语音分支由 PS C 程序执行 VAD、Log Mel 特征提取及独立语音 CNN，不经过摄像 RTL CNN。
- **电脑浏览器：**通过 HTTP 命令和 JSON 状态轮询与 PS 通信，基于 3Dmol.js/WebGL 在浏览器中完成交互式分子渲染。网页与 HDMI 同步有效分子类别，观察视角独立。

规则像素处理、连续采集和定点乘加具有明确的数据通路，放入 PL；笔迹定位、拒识、请求调度和交互控制存在较多数据相关分支，保留在 PS。摄像源帧、显示帧和 CNN 尾部参数通过 DDR 共享，层间特征保留片内，减少 PS 的逐层调度与中间数据交接。

```text
手写结构简式 → 摄像头 → PL 采集与前段预处理
             → PS 图像整形 → PL 定点 CNN → 有机物类别
                                               ↓
语音输入 → PS 本地语音识别 ───────────────→ 分子选择
                                               ↓
                               名称、化学式与预置三维模型
                                               ↓
                                      HDMI / 局域网网页
```

### 主要技术特点

- **视听输入与双端展示集成：**摄像识别和化学名称语音识别共用类别映射及结果管理，关联名称、化学式、性质和预置分子模型。
- **完整手写 RTL CNN：**将卷积、量化、池化和全连接纳入一次启动的整网计算；Conv3 通过输入广播、四输出通道并行和局部权重缓存减少计算耗时。
- **资源约束下的存储与计算复用：**尾部模型参数从 DDR 按需加载，中间特征保存在片内，复用加载器、缓存及量化资源。四路优化相对单路整网增加 358 个 LUT、397 个 FF 和 0.5 个 BRAM tile，DSP 保持 123 个。
- **自制数据与数值验证：**摄像训练及开发验证数据由团队采集制作，采用量化感知训练并冻结整数参数；以输入、逐层张量及最终分值对拍检查部署一致性，区分模型分类准确率与硬件部署正确性。


## 本说明的复现范围

按下文完成“打开工程 → 仿真 → 生成硬件 → 制作 ZIP → 上板验证”。复现从提供的最终模型参数开始。直接使用已有运行包时，从步骤 4 开始。

## 使用工具及版本

- **Vivado 2020.2**：用于 FPGA 工程创建、综合、布局布线和 bitstream 生成。已有实际构建记录为 SW Build 3064766、IP Build 3064653。
- **Vitis HLS 2020.2**：用于将 PREP 图像预处理 C++ 生成为硬件 IP；随包导出的硬件代码标注该版本。
- **PYNQ 2.7.0**：开发板端运行框架，用于加载配套硬件、访问硬件接口并运行 PS 应用。板端架构为 `armv7l`。

电脑端硬件重建需要 Vivado 2020.2（含 Zynq-7000 器件支持）、Python 3.8 或以上及 NumPy。标准构建直接使用随附的 PREP 导出 IP，因此本流程无需再次执行 Vitis HLS。板端依赖见步骤 1。

## 提交目录结构

下面列出主要提交目录、复现入口和报告文件。各目录内的源码、模型参数及工具生成的明细文件按用途保留，未在目录树中逐一展开。

```text
42754/
├── README.md                          项目介绍、目录说明与复现操作指南
├── src/                               设计源码及应用运行依赖
│   ├── rtl/
│   │   ├── cnn/                       手写 CNN RTL、接口与初始化文件
│   │   └── platform/                  摄像头、音频等平台 RTL
│   ├── hls/prep_only/                 前段预处理 C++ 与头文件
│   └── ps/psv7_pynq/                  ARM 端完整应用
├── sim/                               当前版本验证脚本和验证结果
│   ├── testbench/                     按功能分类的测试平台
│   │   ├── network/                  整网 TB、存储器模型、头文件和 network.wcfg
│   │   │   └── vectors/              整网的固定输入、标准输出、权重和偏置
│   │   ├── prep/                     PREP 测试平台和 prep.wcfg
│   │   └── audio/                    音频测试平台和 audio.wcfg
│   ├── run_checks.py                  离线验证统一入口
│   ├── check_parameters.py            模型参数与构建映射一致性检查
│   ├── integer_reference.py           软件整数 CNN 参考实现
│   ├── verify_cnn3_package.py          最终参数包及固定参考结果检查
│   ├── infer_cnn3_int8.py              单个输入的软件参考推理
│   ├── audit_board_results.py          当前四路版本板测记录审核
│   ├── ps_vs_rtl/                     CPU/FPGA 固定输入对照工具
│   └── results/
│       ├── gui/                       整网、PREP、音频的仿真结果及功能自检
│       ├── latest_verification.json   离线验证汇总记录
│       ├── layout_verification.json   构建布局及文件引用核对记录
│       └── organization_verification.json 技能工具正反例验证等记录
├── build/                             构建脚本、IP 配置、工程依赖及报告
│   ├── project/camera_bridge.xpr      双击打开整机工程，引用 sim/testbench/
│   ├── build_hardware.py              硬件构建入口
│   ├── prepare_workspace.py           构建文件布局恢复与组装
│   ├── verify_submission.py           整个提交包的完整性检查
│   ├── layout_manifest.json           构建所需路径及文件校验信息
│   ├── submission_manifest.json       提交文件清单与 SHA-256
│   ├── hls/                          HLS 构建脚本
│   ├── ip_repo/                      CNN 封装信息与 PREP 导出 IP
│   ├── vivado/                       Vivado 脚本及基础平台依赖
│   └── reports/
│       ├── gui_rebuild/              本次 GUI 工程重建的资源、时序和导出记录
│       ├── reproduction/             脚本重建的综合、实现报告
│       ├── comparison/                优化前后资源对比及来源依据
│       │   ├── resource_comparison.csv 资源对比表
│       │   ├── comparison_sources.json 性能与资源对比来源索引
│       │   ├── baseline_resources.json 早期资源与接口提取记录
│       │   └── unified_resource_audit.json 单路统一 RTL 整机资源审查
│       └── organization/
│           └── source_selection.json 文件来源、选择与材料位置映射
├── board/                             上板运行材料与实测记录
│   ├── prepare_runtime.py             制作运行包的工具
│   ├── unpack_runtime.py              本次使用的解压检查工具
│   ├── deliveries/
│   │   ├── psv7_runtime.zip           带板测记录的参考运行包
│   │   └── psv7_rebuilt_runtime.zip   源码复现产生的对照包
│   └── results/
│       ├── baseline/                  优化前板测对照证据
│       ├── current/                   当前四路版本板测证据
│       ├── acceptance/                功能验收摘要与停止记录
│       │   └── final_runtime/         chem_run_01 下载的实测、停止及版本核对材料
│       └── comparison/
│           ├── performance_comparison.csv 性能对比汇总表
│           └── benchmark_source_manifest.json 测试输入与参数来源清单
├── data/
│   └── model/final_parameters/         最终整数模型及参考数据
│       ├── class_names.json           22 类名称与类别顺序
│       ├── manifest.json              参数包说明与量化信息
│       ├── file_hashes.json           参数包文件校验信息
│       ├── conv_weight_rows/          卷积权重的硬件存储布局文件
│       ├── golden/                    固定输入、逐层及最终参考输出
│       └── source_snapshot/           导出与参考计算相关代码快照
├── skill/
│   ├── README.md                      技能提炼过程、用法、验证与边界
│   ├── scripts/
│   │   ├── validate_overlay.py        bit/HWH 文件及 IP 地址检查
│   │   └── compare_arrays.py          NPY/NPZ 数组严格逐值比对
│   └── profiles/
│       └── current.json               当前工程的文件哈希与 IP 地址配置
└── report/                            设计报告与独立大模型交互记录
    ├── design_report.pdf              正式技术报告（同时含大模型协作记录）
    └── llm_interaction_records.md      大模型交互记录
```

## 复现步骤

### 1. 打开工程并运行仿真

本步在电脑上检查硬件的计算和接口。

1. 将完整提交包解压到短英文路径，在 Vivado **2020.2** 打开 `build/project/camera_bridge.xpr`。
2. 打开 `system.bd` 可查看整机连接。
3. 在 **Simulation Sources** 中右键目标仿真集，选择 **Make Active**。
4. 点击 **Run Behavioral Simulation → Run All**，等待以下通过标志，再点击 **Zoom Fit** 查看波形。切换测试前先关闭当前仿真。

- `sim_network`：测试完整 CNN，含 Conv1、Conv2、四路 Conv3 和全连接。通过标志为 `S5_PASS_NETWORK`。
- `sim_prep`：测试预处理接口及红色图案首行输出。通过标志为 `S6_PREP_IDENTITY_RTL_PASS` 和 `PREP_PIXEL_PASS`。
- `sim_audio`：测试 I²S 接收和 FIR 滤波抽取。通过标志为 `AUDIO_PASS`。

工程初始只运行 **1 μs**。继续执行 `run all`，完整 CNN 样例约在 **24.2423 ms 仿真时刻**结束，电脑实际需等待数分钟。`.wcfg` 会自动加载，日志和已有波形在 `sim/results/gui/`。

### 2. 生成 bit/HWH

本步生成配套的 bit/HWH。**方式一和方式二任选一种，完成后都执行步骤 3 的同一个打包命令。**

#### 方式一：打开提供的工程，在 Vivado 界面生成硬件

1. 在已打开的工程中点击 **Generate Bitstream**，等待生成成功。
2. 在**提交根目录**打开 Windows PowerShell，执行下列命令，把同一轮生成的 bit/HWH 复制成打包工具需要的名称。输出目录须尚不存在。

```powershell
$out = Join-Path (Split-Path (Get-Location).Path -Parent) 'chem_gui_build_01'
if (Test-Path -LiteralPath $out) { throw 'Choose a new output directory' }
$bit = 'build/project/camera_bridge.runs/impl_1/system_wrapper.bit'
$hwh = 'build/project/camera_bridge.gen/sources_1/bd/system/hw_handoff/system.hwh'
Get-Item -LiteralPath $bit, $hwh
$hardwareOutput = Join-Path $out 'hardware'
New-Item -ItemType Directory -Path $hardwareOutput | Out-Null
Copy-Item -LiteralPath $bit -Destination "$hardwareOutput/psv7_camera_audio.bit"
Copy-Item -LiteralPath $hwh -Destination "$hardwareOutput/psv7_camera_audio.hwh"
```

完成方式一后，跳过方式二，在同一个 PowerShell 窗口执行步骤 3。

#### 方式二：运行脚本，从源码自动构建硬件

选择方式二时，在提交根目录打开 PowerShell，修改 Vivado 安装路径。脚本调用 Vivado 创建工程、综合、布局布线并生成 bit/HWH。完成后继续执行步骤 3。

```powershell
$vivado = 'C:/Xilinx/Vivado/2020.2/bin/vivado.bat'
$out = Join-Path (Split-Path (Get-Location).Path -Parent) 'chem_script_build_01'
python -B build/build_hardware.py --vivado "$vivado" --output "$out"
if ($LASTEXITCODE -ne 0) { throw 'Hardware build failed' }
$hardwareOutput = Join-Path $out 'run/output'
```


### 3. 制作上板运行 ZIP

两种方式到这里汇合。本步使用同一个 prepare_runtime.py，把刚生成的 bit/HWH、PS 应用、模型和网页资源合成运行 ZIP。使用能导入 NumPy 的 Python，在步骤 2 的同一个 PowerShell 窗口执行：

```powershell
python -B sim/check_parameters.py
if ($LASTEXITCODE -ne 0) { throw 'Parameter check failed' }
$runtimeZip = Join-Path $out 'chem_runtime.zip'
python -B board/prepare_runtime.py --hardware-output "$hardwareOutput" --output "$runtimeZip"
if ($LASTEXITCODE -ne 0) { throw 'Runtime packaging failed' }
```

确认 `passed` 和 `rebuilt_pair_used` 均为 `true`。记下 ZIP 位置 `$runtimeZip` 和打印的 **SHA-256**。

### 4. 上传、校验并解压

本步把运行包部署到真板。准备匹配的 Zynq-7020 板（`xc7z020clg400-2`）、OV5640、HDMI 显示器及 WM8960 板载麦克风，断电接线后上电。板端使用适配本板的 **PYNQ 2.7.0 / armv7l** 系统，并具备 Python、NumPy、GCC 和 Jupyter。提交包提供应用，不含 SD 卡系统镜像。

1. 让电脑和开发板接入可互通的局域网，打开 Jupyter。
2. 上传步骤 3 的 `chem_runtime.zip` 和 `board/unpack_runtime.py` 到 `/home/xilinx/jupyter_notebooks/`。
3. 打开 Jupyter **Terminal**，执行下列命令。把校验值替换为步骤 3 打印的完整值；输出目录已存在时换成新的目录名。

```bash
cd /home/xilinx/jupyter_notebooks
runtime_zip='chem_runtime.zip'
expected_sha='填入步骤3打印的64位sha256'
ls -lh "$runtime_zip" unpack_runtime.py
sha256sum "$runtime_zip"
python3 unpack_runtime.py "$runtime_zip" --output chem_run_01 --sha256 "$expected_sha"
hostname -I
```

确认哈希一致，解压显示 `host_assets_checked: 7` 和 `passed: true`，记下开发板 IP。

#### 直接使用已有运行包时

上传 `board/deliveries/psv7_runtime.zip` 和 `board/unpack_runtime.py` 后，在 Jupyter Terminal 执行：

```bash
cd /home/xilinx/jupyter_notebooks
runtime_zip='psv7_runtime.zip'
expected_sha='3afa8487ca95f5ffebbac951c3009b630e038215533ef57625fa5f5ce6714168'
sha256sum "$runtime_zip"
python3 unpack_runtime.py "$runtime_zip" --output chem_run_01 --sha256 "$expected_sha"
hostname -I
```

确认校验和解压通过后，继续步骤 5。


### 5. 启动作品

本步加载硬件并启动应用。

1. 在 Jupyter 中打开本次解压目录下的 `psv7_pynq/notebooks/01_application.ipynb`。如有旧应用，先在其 Notebook 正常停止并关闭旧内核。
2. 逐个执行代码单元。第一个单元完成文件检查。
3. 在第二个单元填写实际 IP，并根据开发板状态设置启动参数。

真实断电上电后首次启动：

```python
STARTUP_MODE = 'cold_start'
CLEAN_BOARD_POWER_UP = True
BOARD_IP = '192.168.2.99'  # 改为实际 IP
```

旧应用已正常停止、此后未断电：

```python
STARTUP_MODE = 'reuse'
CLEAN_BOARD_POWER_UP = False
BOARD_IP = '192.168.2.99'  # 改为实际 IP
```

执行第二个单元，等待无异常结束并返回 `host_running: True`、端口 `8765`。第三个单元留到使用结束时执行。

### 6. 检查摄像、语音和三维展示

本步确认真实输入能驱动分子展示。

1. 在电脑浏览器打开 `http://开发板实际IP:8765`，点击“连接开发板”。
2. 手动选择一种分子，核对名称、化学式和网页/HDMI 模型；用鼠标旋转、缩放。
3. 切到摄像模式，将支持类别的结构简式放入摄像头框内，点击“开始识别”，核对结果。
4. 切到语音模式，选择“板载麦克风”，点击“开始识别”并说出支持的有机物名称，核对结果。
5. 保存实际功能截图。

### 7. 运行板端固定输入验证

本步检查 PS 与 PL 完整 CNN 输出是否一致。保持应用运行，在**同一个 Notebook 内核**新增单元，执行下面代码。测试期间暂停网页识别、录音和模式切换。

```python
import sys
sys.path.insert(0, str(PROJECT_ROOT.parent / 'ps_vs_rtl'))
from board_benchmark import run
benchmark_result = run(session.app)
print(benchmark_result['passed'])
print(benchmark_result['report_directory'])
```

通过标准为 `passed=True`，44 份输入重复 3 轮，共 132 条记录的 22 个分值逐项一致。结果文件为打印目录中的 `board_result.json`，计时范围是 CNN 完整调用。

### 8. 正常停止并下载结果

本步关闭任务和硬件，保存复现记录。

1. 执行原 Notebook 的第三个代码单元。
2. 确认错误列表为空、活动缓冲区为 0、分配与释放数量相等、DMA 和后台线程已停止。
3. 使用单元提供的链接下载停止报告。再从步骤 7 的结果目录下载 `board_result.json`，一并保留功能截图和实际运行 ZIP 的 SHA-256。
4. 摄像、语音、网页/HDMI、固定输入对拍和正常停止均通过后，本次整机复现完成。

停止失败时保留原内核，依据停止报告和 `skill/README.md` 排查。

