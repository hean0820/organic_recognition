# 结构简式视听识别与 3D 展示系统

基于 AMD Zynq-7020 的有机物识别与分子可视化作品。本 README 提供项目概览、提交目录说明及完整运行包的上板复现步骤。

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

本说明介绍 **使用本文件夹提供的完整运行包，把整个作品在开发板上运行起来**。无需重新训练、执行 Vivado 综合或重新制作运行包。

直接使用这两个文件：

1. `board/deliveries/psv7_runtime.zip`：完整应用、模型参数、配套 bit/HWH、网页与分子资源，以及固定输入验证工具。
2. `board/unpack_runtime.py`：运行包检查与解压脚本。

按顺序执行：**准备环境 → 上传 → 解压 → Notebook 启动 → 摄像/语音/三维操作 → 按需固定输入验证 → 正常停止并保存结果**。所有路径和 IP 示例应按实际环境修改。

## 使用工具及版本

- **Vivado 2020.2**：用于 FPGA 工程创建、综合、布局布线和 bitstream 生成。已有实际构建记录为 SW Build 3064766、IP Build 3064653。
- **Vitis HLS 2020.2**：用于将 PREP 图像预处理 C++ 生成为硬件 IP；随包导出的硬件代码标注该版本。
- **PYNQ 2.7.0**：开发板端运行框架，用于加载配套硬件、访问硬件接口并运行 PS 应用。板端架构为 `armv7l`。

Vivado 和 Vitis HLS 是工程开发、生成硬件时使用的工具。本指南使用已提供的完整运行包，使用者无需先安装或执行这两个工具；开发板端需要准备匹配的 PYNQ 2.7.0 系统。其他板端依赖见“步骤 1：准备开发板和环境”。

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
│   ├── run_checks.py                  离线验证统一入口
│   ├── check_parameters.py            模型参数与构建映射一致性检查
│   ├── integer_reference.py           软件整数 CNN 参考实现
│   ├── verify_cnn3_package.py          最终参数包及固定参考结果检查
│   ├── infer_cnn3_int8.py              单个输入的软件参考推理
│   ├── audit_board_results.py          当前四路版本板测记录审核
│   ├── ps_vs_rtl/                     CPU/FPGA 固定输入对照工具
│   └── results/
│       ├── model_verification.json    模型参数包与参考结果检查记录
│       ├── latest_verification.json   离线验证汇总记录
│       ├── layout_verification.json   构建布局及文件引用核对记录
│       └── organization_verification.json 技能工具正反例验证等记录
├── build/                             构建脚本、IP 配置、工程依赖及报告
│   ├── build_hardware.py              硬件构建入口
│   ├── prepare_workspace.py           构建文件布局恢复与组装
│   ├── verify_submission.py           整个提交包的完整性检查
│   ├── layout_manifest.json           构建所需路径及文件校验信息
│   ├── submission_manifest.json       提交文件清单与 SHA-256
│   ├── hls/                          HLS 构建脚本
│   ├── ip_repo/                      CNN 封装信息与 PREP 导出 IP
│   ├── vivado/                       Vivado 脚本及基础平台依赖
│   └── reports/
│       ├── reproduction/             最新实际重建的综合、实现报告
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
│   │   ├── psv7_runtime.zip           本次使用的完整运行包
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
└── report/                            设计报告（含大模型协作记录）
    └── design_report.pdf             正式技术报告
```

## 复现操作步骤

### 步骤 1： 准备开发板和环境

准备与原作品匹配的 Zynq-7020 开发板（工程器件为 `xc7z020clg400-2`）、OV5640 摄像头、HDMI 显示设备，以及配套的 WM8960 音频电路和板载麦克风。本作品实际使用板载麦克风采音，复现时无需外接 LINE_IN 音频源。断电连接外设，按板卡说明确认连接方向与供电，再上电。

使用原来已能运行作品的 PYNQ 系统即可。板端要求：

- PYNQ **2.7.0**，架构 **armv7l**。
- Python **3.8 或以上**，已有板测使用 **3.8.2**。
- NumPy 可导入，GCC 可执行，已有板测 GCC 为 **9.3.0**。
- Jupyter 可以访问，电脑与开发板处于可互通的局域网。

本文件夹不包含 SD 卡系统镜像。使用空白 SD 卡时，先取得适配该板卡的 PYNQ 镜像；不能直接假定任意 Zynq-7020 镜像都兼容。镜像获取地址和实物接线照片未随包提供。管脚依据在 `build/vivado/hardware/platform_base/design/ov5640_lcd.xdc`、`src/rtl/platform/audio/audio.xdc` 和工程 BD 中。

### 步骤 2： 上传两个文件

通过开发板的 Jupyter 文件页面，将电脑上的以下两个文件上传到开发板的 `/home/xilinx/jupyter_notebooks/` 目录。下面列的是电脑提交包中的位置，上传后两个文件应直接位于上述板端目录，不需要创建 `board/` 子目录：

```text
board/deliveries/psv7_runtime.zip
board/unpack_runtime.py
```

ZIP 已包含应用、模型参数、配套 bit/HWH、网页与分子资源和测试工具。不需要上传整个提交目录，也不需要先安装电脑端 Vivado。

**请使用本提交目录提供的完整运行包和解压脚本。**上传后，保持文件名分别为 `psv7_runtime.zip` 和 `unpack_runtime.py`，并将两个文件放在同一目录下。随后按步骤 3 完成校验与解压，再打开解压目录中的 Notebook 启动项目。

在 Jupyter 打开 **Terminal**。终端可能从根目录 `/` 开始，因此先明确切换到上传目录，再检查：

```bash
cd /home/xilinx/jupyter_notebooks
pwd
ls -lh psv7_runtime.zip unpack_runtime.py
sha256sum psv7_runtime.zip
uname -m
python3 --version
python3 -c "import pynq, numpy; print(pynq.__version__, numpy.__version__)"
gcc --version
hostname -I
```

`pwd` 应输出 `/home/xilinx/jupyter_notebooks`，`ls` 应列出两个文件。如果提示 `No such file or directory`，先确认文件已经上传到这个目录；文件未找到时不要继续解压。若你的 Jupyter 根目录经过自定义，请将本节及下一节中的目录改为实际上传位置。确认环境符合步骤 1，并记下开发板的实际局域网 IP。

`sha256sum` 输出的校验值应为：

```text
3afa8487ca95f5ffebbac951c3009b630e038215533ef57625fa5f5ce6714168
```

校验值不一致时，先重新上传本提交目录里的完整 ZIP，不要跳过校验或把命令中的校验值改成旧包的值。文件名和文件大小相近不能证明是同一个包。

### 步骤 3： 解压并检查运行包

仍在**开发板 Terminal** 执行：

```bash
python3 /home/xilinx/jupyter_notebooks/unpack_runtime.py /home/xilinx/jupyter_notebooks/psv7_runtime.zip --output /home/xilinx/jupyter_notebooks/chem_run_01 --sha256 3afa8487ca95f5ffebbac951c3009b630e038215533ef57625fa5f5ce6714168
```

输出目录必须不存在。如果已有 `chem_run_01`，使用下面这条命令解压到 `chem_run_02`，不覆盖旧目录：

```bash
python3 /home/xilinx/jupyter_notebooks/unpack_runtime.py /home/xilinx/jupyter_notebooks/psv7_runtime.zip --output /home/xilinx/jupyter_notebooks/chem_run_02 --sha256 3afa8487ca95f5ffebbac951c3009b630e038215533ef57625fa5f5ce6714168
```

以上两条命令按目录情况选择一条执行；如果 `chem_run_02` 也存在，继续选用未使用的目录名。若 Jupyter 根目录不同，改为实际可访问的目录。

解压检查应正常结束，没有 Traceback；工程检查输出应包含 `"host_assets_checked": 7`，最后的解压结果应包含 `"passed": true` 和实际输出目录 `directory`。前者检查网页文件及引用路径，后者表示本次文件检查与解压完成。使用 `chem_run_01` 时得到：

```text
chem_run_01/
├── psv7_pynq/                  完整应用与硬件、参数、网页资源
│   └── notebooks/
│       └── 01_application.ipynb
└── ps_vs_rtl/                  固定输入验证工具
```

使用 `chem_run_02` 时目录结构相同，只是最外层目录名不同。记住最终输出的 `directory`，下一步从这个目录打开 Notebook。

这一步只检查和解压文件，下一步才启动硬件。文件校验通过不等于摄像头、语音、HDMI 和网页已在板上运行成功。

### 步骤 4： 在 Notebook 中启动

如果板上有旧应用，先在其原 Notebook 正常停止。停止成功后关闭旧 Notebook 的内核，在 Jupyter 文件页面进入步骤 3 打印的输出目录，打开其中的 `psv7_pynq/notebooks/01_application.ipynb`。例如解压到 `chem_run_02`，应打开：

```text
/home/xilinx/jupyter_notebooks/chem_run_02/psv7_pynq/notebooks/01_application.ipynb
```

使用新的 Python 内核，**逐个执行代码单元，不要 Run All**。不要继续使用浏览器里已经打开的 `chem_run_01` Notebook，也不要让两个目录的应用同时运行。

1. 执行第一个代码单元，完成工程检查并创建 `session`。确认没有异常再继续。
2. 在第二个代码单元中，将 `BOARD_IP` 改成 步骤 2 查到的实际 IP。
3. 根据开发板状态设置启动方式：

真实断电重新上电、尚未运行本应用时：

```python
STARTUP_MODE = 'cold_start'
CLEAN_BOARD_POWER_UP = True
BOARD_IP = '192.168.2.99'  # 示例，换成实际 IP
```

旧应用已正常停止、开发板没有断电时：

```python
STARTUP_MODE = 'reuse'
CLEAN_BOARD_POWER_UP = False
BOARD_IP = '192.168.2.99'  # 示例，换成实际 IP
```

重启 Notebook 内核、上传 ZIP 和解压到新目录都不等于断电重新上电。设置后执行第二个代码单元；首次运行可能在板端编译 C 库。

**第二个代码单元执行完毕、没有 Traceback，且最终返回的 `host` 中 `host_running` 为 `True`，才继续步骤 5。**返回内容应包含以下关键字段（其他字段省略，IP 以实际值为准）：

```python
{'host': {'host_running': True,
          'port': 8765,
          'urls': ['http://192.168.2.99:8765/']}}
```

日志中的 `PSV7_FORMAL_APP_RUNNING` 在启动网页服务之前打印，单独出现这行不能说明第二个单元全部成功。若之后出现异常并打印 `PSV7_APP_STOP`，说明启动流程进入了停止处理，不应继续访问网页或进行识别。先核对停止报告；确认错误列表为空、活动缓冲区为 0、DMA 已释放、后台线程已停止，再处理报错。

如果失败后的停止报告确认清理成功，且开发板此后没有断电，再次启动应使用 `reuse` 和 `False`；只有真实断电重新上电才按上面的冷启动条件设置。

启动成功后先继续步骤 5，不要马上执行第三个停止单元；它用于使用结束后停止应用。

### 步骤 5： 操作网页、摄像头和语音

在**电脑浏览器**访问：

```text
http://实际开发板IP:8765
```

例如 IP 为 `192.168.2.99`，则访问 `http://192.168.2.99:8765`。浏览器需支持 JavaScript 和 WebGL，从开发板服务打开网页，不直接双击电脑上的 HTML 文件。

**网页与三维展示：**

1. 页面应出现“分子观察台”和 22 种分子列表。
2. 点击“连接开发板”，等待状态显示已连接或已同步。
3. 选择一种分子，核对名称、化学式及网页/HDMI 展示。
4. 左键拖动旋转、滚轮缩放，也可以使用“暂停旋转”和“复位视角”。网页与 HDMI 视角独立。

**手写识别：**

1. 确认 HDMI 有摄像头预览画面，网页处于摄像头模式。
2. 将支持类别的手写结构简式放入识别区域，保持画面清晰、稳定。
3. 点击“开始识别”，等待结果，核对名称、化学式和分子模型。
4. 换一份样例重复，确认结果会更新。

**语音选择：**

1. 点击“切换识别模式”，确认处于语音模式并已就绪。
2. 将“音频输入”选择为“板载麦克风”；本作品使用该输入方式。
3. 点击“开始识别”，说出一个支持的有机物名称，等待一次结果。
4. 核对识别文字、分子选择及网页/HDMI 展示。

分别保存上述功能的实际结果或截图。网页未连接时可以显示本地模型，但这不能代替开发板交互验证。

### 步骤 6： 固定输入验证（验收时执行，日常使用可跳过）

保持应用运行，在**同一个 Notebook 内核**新增代码单元：

```python
import sys
sys.path.insert(0, str(PROJECT_ROOT.parent / 'ps_vs_rtl'))
from board_benchmark import run
benchmark_result = run(session.app)
print(benchmark_result['passed'])
print(benchmark_result['report_directory'])
```

测试期间不要从网页发起识别、录音或切换模型。工具使用 44 份固定输入、3 轮共 132 对 CPU/FPGA 测试，比对每次的 22 个整数输出。

通过标准：`passed` 为 `True`，132 条正式记录的 `exact_logits_match` 均为 `true`。结果目录由程序打印，原始文件名为 `board_result.json`。测试耗时是 CNN 完整调用耗时，不是摄像头到显示的整机耗时。

### 步骤 7： 正常停止并保存结果

完成使用或测试后，执行 `01_application.ipynb` 的第三个代码单元。它会正常停止应用，显示报告并提供下载链接。

检查：错误列表为空、分配和释放的缓冲区数量相等、活动缓冲区为 0、DMA 和后台线程已停止、网页服务已关闭。不要仅关闭浏览器或重启内核代替停止。

需要集中保存时，在停止成功后新增单元：

```python
import json
import shutil
from pathlib import Path

evidence_dir = PROJECT_ROOT.parent / 'board_evidence'
evidence_dir.mkdir(exist_ok=True)
(evidence_dir / 'normal_stop.json').write_text(
    json.dumps(stop_report, ensure_ascii=False, indent=2), encoding='utf-8')
if 'benchmark_result' in globals():
    source = Path(benchmark_result['report_directory']) / 'board_result.json'
    shutil.copyfile(source, evidence_dir / 'board_result.json')
print(evidence_dir)
```

通过 Jupyter 下载该目录中的结果和功能截图，保留运行 ZIP 的校验值。停止失败时保留当前内核和资源所有者，查看停止报告及 `skill/README.md`，不要强制释放或另外加载第二套 Overlay。

## 复现完成的判断

完成本次运行后，应确认以下项目：

1. 完整运行包解压和文件检查通过，Notebook 工程检查、应用启动无异常。
2. 摄像头有画面，手写识别能返回结果并更新对应分子展示。
3. 语音输入能返回识别结果并更新选择。
4. HDMI 与网页展示可用，网页连接、手动分子选择及视角操作正常。
5. 验收时执行 步骤 6，保存固定输入与参考结果一致的板测记录。
6. 正常停止检查通过，实测与停止记录已下载保存。

以本次实际运行结果为准。包内已有板测记录用于参考，不代替复现者自己的操作结果；单独看到网页中的分子模型也不等于摄像、语音和硬件交互全部通过。

## 遇到错误时

- **输出目录已存在：**换新的目录名，例如 `chem_run_02`，不要覆盖或混用旧应用。
- **文件哈希或 ZIP 校验失败：**核对上传的是否是 `psv7_runtime.zip`、文件是否完整，以及校验值是否与 步骤 3 一致。
- **启动时报 `host/vendor/3Dmol-min.js` 不存在：**旧包中曾有网页文件名引用与实际小写文件名不一致的问题。重新上传与本 README 校验值一致的完整 ZIP，解压到新目录，并从新目录启动；仅替换上传的 ZIP 或重启旧 Notebook 不会更新旧目录的代码。当前完整包在解压时检查网页资源路径，无需手动改名或安装补丁。
- **板端环境不匹配：**使用匹配的 PYNQ 2.7.0 系统、ARM 环境和板端 GCC，不修改检查代码强行通过。
- **网页连不上：**先确认 Notebook 第二个单元启动成功，再核对 `BOARD_IP`、实际网络地址和 8765 端口。
- **网页能显示模型但识别无效：**确认已连接开发板、模式已就绪，再检查摄像头或实际音频输入。
- **硬件超时或停止失败：**保留当前会话和日志，不另开第二套应用；按 `skill/README.md` 定位。

原作品已经可用的开发板系统可以继续使用，不需要重复刷卡。对于空白 SD 卡，仍需先准备匹配系统镜像；本运行包提供的是完整应用及硬件文件，不包含操作系统镜像。
