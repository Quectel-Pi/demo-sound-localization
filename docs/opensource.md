Copyright © Quectel Wireless Solutions Co., Ltd. 2026. All rights reserved.

# Sound Localization 开源使用说明

## 修订记录

| 版本 | 日期 | 作者 | 变更描述 |
| --- | --- | --- | --- |
| - | 2026-10-22 | - | 文档创建 |
| 0.0.1 | 2026-10-22 | - | 临时版本 |
| 0.1.0 | 2026-10-26 | - | 适配 VA60X-GL，更新通道映射、自动设备检测、双语界面、设备重检、语句级方向范围和板端验证说明 |
| 0.2.0 开发中 | 2026-10-28 | - | 初版实时人声指向，ASR 作为独立转写结果 |

## 项目简介

Sound Localization 是一套面向 Quectel PI M2 的本地人声方向与离线语音转写应用。项目通过 USB 接入 Quectel VA60X-GL 六麦阵列板，在开发板上完成八通道音频采集、人声活动检测、水平面声源定位、SenseVoice 离线语音识别和桌面可视化。

本项目用于展示 Quectel PI M2 对 USB 多通道音频、Python/NumPy 信号处理、本地 ONNX 模型推理和桌面图形交互的整合能力，适合阵列算法验证、边缘语音交互原型和现场调试。实时音频不会上传，转写结果默认只保存在当前进程内存中。

## 本次更新

本次改动基于 VA60X-GL 重新烧录后的 USB 音频固件和实测通道关系完成，主要内容如下：

1. 将采集硬件从旧版 Sipeed 6+1 麦克风阵列及 MA-USB8 改为 Quectel VA60X-GL 六麦阵列板。
2. 将实时采集格式更新为八通道、16 kHz、S16_LE；定位块从 2048 点调整为 512 点，每块约 32 ms。
3. 按实物通道重新排列六个麦克风：MIC_1→0、MIC_2→4、MIC_4→5、MIC_5→1、MIC_6→2、MIC_8→3；索引 6 为空，索引 7 为回采。
4. 新增按 USB VID:PID `0bda:4cf0` 自动解析 ALSA 声卡，避免 USB 重插后卡号变化导致启动失败。
5. 新增“重新检测设备”入口。用户可在修复 USB 连接后停止旧采集并重新查找设备，无需退出应用。
6. 新增中文和英文界面切换；点击“保存”可同时持久化界面语言和基础门限。
7. 实时指针使用最近 0.25 秒有效人声方向，经过圆周平均和跳变确认，不等待 ASR。
8. 一句话期间的有效方向另行汇总，并量化为默认 30° 范围附在转写前。
9. 该段方向未知时，识别文字仍进入界面，只显示转写内容。
10. 有效实时方向消失后指针最多保持 0.4 秒；ASR 结果不会清除或移动指针。
11. 更新启动脚本的依赖检查：缺少 WebRTC VAD 或 SenseVoice 时会明确提示并降级运行。
12. 自动化测试覆盖 VA60X-GL 映射、设备重检、双语界面、方向门控、实时跟踪、语句方向聚合和扇区显示。

## 功能概览

- 按 USB VID:PID 自动寻找 VA60X-GL，不依赖固定 ALSA 卡号。
- 通过 ALSA `arecord` 采集 16 kHz、16 位、八通道 PCM。
- 使用六路物理麦克风和 GCC-PHAT/SRP 估计水平面声源方向。
- 在三个分散麦克风上执行 WebRTC VAD 投票，并结合语音频段质量筛选人声。
- 在后台线程中切分语音并使用本地 SenseVoice INT8 模型离线识别。
- 每句话使用说话期间的有效定位证据计算代表方向，不取识别完成时的瞬时方向。
- 默认把结果量化为 30° 扇区，例如 `[方向约 060° ±15°] 你好`。
- 方向证据不足时只显示转写文字，不显示方向标签；实时指针由自身的有效证据决定。
- 支持实时输入、八通道 WAV 回放、合成演示、无界面诊断和独立 WAV 转写。
- 支持中英文界面、复制和清空文字、保存基础门限及界面语言。
- 支持运行中重新检测 USB 音频设备。

## 开发配件清单

| 配件名称 | 数量 | 规格或要求 |
| --- | ---: | --- |
| Quectel PI M2 智能开发板 | 1 块 | 负责 USB 音频接入、端侧算法、离线识别和界面显示；当前部署平台为 aarch64 Linux |
| Quectel VA60X-GL 六麦阵列板 | 1 块 | 当前固件提供八通道、16 kHz、S16_LE USB 音频，USB VID:PID 为 `0bda:4cf0` |
| USB 数据线 | 1 根 | 连接阵列板和 PI M2 USB Host，需要支持稳定数据传输与供电 |
| 显示器 | 1 台，可选 | 展示图形界面时使用；SSH 或无屏环境可运行 `--probe` |

## 硬件通道说明

硬件资料使用 1 起始通道号，Python 数组和 `config.json` 使用 0 起始索引。

| 物理麦克风 | 硬件通道 | 程序索引 | 用途 |
| --- | ---: | ---: | --- |
| MIC_1 | 1 | 0 | 定位、VAD、默认 ASR |
| MIC_2 | 5 | 4 | 定位 |
| MIC_4 | 6 | 5 | 定位、VAD 投票 |
| MIC_5 | 2 | 1 | 定位 |
| MIC_6 | 3 | 2 | 定位、VAD 投票 |
| MIC_8 | 4 | 3 | 定位 |
| 空通道 | 7 | 6 | 不参与定位 |
| 回采通道 | 8 | 7 | 不参与定位 |

六麦必须按物理环形顺序配置：

```json
"mic_channels": [0, 4, 5, 1, 2, 3]
```

采集通道数仍须保持为 8，不能为了只使用六个麦克风而改成 6。程序先采集完整八通道数据，再按上述顺序提取六路定位信号。

当前算法假定 MIC_1、MIC_2、MIC_4、MIC_5、MIC_6、MIC_8 在圆环上顺时针排列、相隔 60°，MIC_1 径向为软件 0°。实际安装后需要确认设备正前方和角度增长方向：

- 正前方与 MIC_1 径向不一致时，调整 `angle_offset_deg`；
- 角度变化方向相反时，将 `mirror` 设置为 `true`；
- 当前 `radius_m` 为 0.035 m，是依据板形尺寸的估计值；取得准确麦克风中心坐标后应重新标定。

## 快速上手

### 环境要求

- Quectel PI M2，aarch64 Linux，带图形桌面时可运行 GUI。
- Python 3、Tkinter、ALSA 工具和 NumPy。
- VA60X-GL 能被系统识别为 USB 多通道音频设备。
- Python 依赖：`numpy>=1.23,<3`、`webrtcvad-wheels==2.0.14`、`sherpa-onnx==1.13.8`。
- SenseVoice INT8 模型及词表，下载量约 230 MB。

### 安装依赖

```bash
sudo apt install python3 python3-venv python3-numpy python3-tk alsa-utils fonts-noto-cjk
cd /path/to/demo-sound-localization
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements-asr.txt
python3 setup_asr.py
```

`setup_asr.py` 从脚本记录的 sherpa-onnx 官方发布地址下载 SenseVoice INT8 模型，并写入：

```text
models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/
```

模型已存在时不会重复下载。模型、虚拟环境、录音和诊断输出均被 `.gitignore` 排除。

### 检查音频设备

```bash
cat /proc/asound/cards
arecord -l
bash run.sh --probe --seconds 5
```

默认配置使用 `device: auto`，程序通过 `usb_vid_pid: 0bda:4cf0` 查找当前 ALSA 卡号。一次枚举出的 `hw:3,0` 之类卡号可能在重插后变化，不建议长期写入配置。

如需临时指定设备，可运行：

```bash
bash run.sh --device 'hw:<CARD>,0' --probe --seconds 5
```

### 启动应用

```bash
cd /path/to/demo-sound-localization
bash run.sh
```

正常启动后，界面左侧显示方向雷达，右侧显示角度、人声状态、电平和门限，下方显示离线转写。首次运行先保持安静 2–3 秒，使程序学习稳定背景噪声频谱。

只有 SSH 会话且没有图形显示时，Tk 窗口无法打开；应先运行 `--probe`，或在开发板已登录的图形桌面终端中启动应用。

## 应用使用方法

### 中英文界面

界面默认语言由 `ui_language` 决定。点击顶部语言按钮可即时切换中文或英文；点击“保存”会把当前界面语言和 `gate_dbfs` 写回 `config.json`。

界面语言只改变按钮和标签，不翻译 SenseVoice 的识别结果。当前 `asr_language: zh` 固定中文；可配置为 `auto` 按音频内容自动判断语言，或设为 `en` 固定英文。

### 校准基础门限

1. 启动后保持安静 2–3 秒，观察环境输入电平。
2. 在预期距离以正常音量说话。
3. 将基础门限设在大部分环境声之上、正常语音电平之下。
4. 点击“保存”，将数值写回 `config.json`。

数值越负越容易触发。例如安静时约 -45 dBFS、正常语音约 -32 dBFS，可先尝试 -39 至 -37 dBFS。当前配置为 -40 dBFS；方向未知时可检查正常说话的电平、VAD 状态和转写区显示。

基础门限是语句方向证据的硬门限。低于它的语音仍可用于转写，但不会进入方向汇总。自适应语音频段门限只用于辅助人声检测，不替代基础门限。

### 查看带方向的转写

面向阵列说完一句，然后保持约 0.6 秒静音。完成离线识别且方向已知后，界面会追加带方向的结果；方向未知时只追加转写文字：

```text
[方向约 060° ±15°] 你好
今天天气很好。
```

英文界面对应显示：

```text
[Direction ~060° ±15°] Hello
The weather is nice today.
```

当前模式下，实时指针由最近 0.25 秒有效人声方向驱动，累计至少 0.16 秒有效音频后出现。转写在后台完成：

- 方向已知：文字附上该段方向扇区；指针继续显示当前实时方向；
- 方向未知：界面只显示文字；指针继续按实时证据更新；
- 持续检测到人声但短暂缺少定位帧时，保留最近稳定指向；人声结束后最多保持 0.4 秒，然后隐藏；清空文字不影响实时指针。

界面最多保留最近 20 条转写，只存在于当前进程内存。程序不会自动保存实时录音或转写文本。

### 重新检测设备

USB 重新插入、声卡号变化或采集错误排除后，点击“重新检测设备”：

1. 停止旧采集线程和旧 `arecord` 进程；
2. 按 VID:PID 重新解析声卡号；
3. 重建采集、VAD、定位和分句状态；
4. 清除旧指针，但保留已显示的转写历史。

此操作不能修复供电、数据线、驱动或物理连接问题。硬件仍不可用时会显示新的采集错误。

### 无界面采集诊断

```bash
bash run.sh --probe --seconds 5
```

诊断模式不创建窗口，也不加载 VAD 和 ASR 可选组件。输出 JSON 包含：

- 实际解析的 ALSA 设备；
- 采集帧数和音频秒数；
- 八通道 RMS、dBFS 和削波计数；
- 活动帧、人声帧和有效语句方向帧计数；
- 最后角度、方向评分、门限和信噪信息。

单次整体电平统计可以发现无声、削波和异常通道，但不能独立证明每个物理 MIC 的编号。通道映射仍需要逐麦克风近场测试确认。

### 回放八通道录音

```bash
bash run.sh --wav recording.wav
```

WAV 必须是未压缩的八通道、16 kHz、16 位 PCM。回放使用与实时输入相同的定位、VAD、分句、识别和界面路径。

### 合成方向演示

```bash
bash run.sh --demo
```

演示模式使用合成六麦远场信号，并关闭 VAD 和 ASR。它用于展示定位管线和界面，不代表实物环境中的定位精度。

### 仅运行实时定位

```bash
bash run.sh --no-vad --no-asr
```

此模式不做人声筛选和转写，使用原有实时方向跟踪和 `hold_seconds`，与默认的人声方向稳定器不同。

### 独立转写 WAV

```bash
.venv/bin/python transcribe.py --file recording.wav --channel 0
.venv/bin/python transcribe.py --file recording.wav --channel 0 --segment
```

该入口接受单声道或多声道的未压缩 16 位 PCM WAV。长录音使用 `--segment`。单独选择的一个通道没有阵列几何信息，因此只转写，不计算声源方向。

## 方向判定原理

### 帧级定位

每个 512 点采集块约 32 ms。定位器：

1. 按物理环形顺序提取六个麦克风通道；
2. 对信号去直流、加 Hann 窗并做 1024 点 FFT；
3. 保留 250–4000 Hz 语音频段；
4. 对六麦的 15 个麦克风对计算 GCC-PHAT；
5. 按圆环几何，以 2° 步长扫描 0–358°；
6. 选择总评分最高的方向，再应用 `mirror` 和 `angle_offset_deg`。

`min_confidence` 是麦克风对相干性和相关峰锐度组合得到的启发式门限，不是正确率或概率。

### 语句方向证据

一个采集块只有同时满足以下条件才参与该句话的方向计算：

```text
VAD 确认人声
AND 语音频段电平达到最低要求
AND 噪声模型未校准或信噪比合格
AND 六麦综合电平达到 gate_dbfs
AND 方向评分达到 min_confidence
```

### 语句级聚合

一句话结束后，程序按“有效采样长度 × 方向评分”对所有有效角度做圆周加权平均。默认还要求：

- 有效方向累计至少 0.2 秒；
- 有效方向覆盖至少 30% 的人声时长；
- 方向圆周集中程度至少 0.7。

满足条件后，结果量化到最近的 30° 扇区，例如 68° 显示为 `60° ±15°`，352° 显示为 `0° ±15°`。条件不满足时方向为未知。

30° 是显示和稳定性的颗粒度，不是统计置信区间，也不代表定位误差一定小于 ±15°。

## 配置说明

应用启动时读取 [`config.json`](../config.json)。除界面可保存的基础门限和语言外，手动修改其他参数后需要重启。

| 配置键 | 当前值或回退值 | 作用 |
| --- | --- | --- |
| `device` | `auto` | 按 USB VID:PID 自动寻找 ALSA 设备 |
| `ui_language` | `zh` | 界面语言，支持 `zh`、`en` |
| `usb_vid_pid` | `0bda:4cf0` | 当前固件的 USB 标识 |
| `rate` | `16000` | 实时采样率 |
| `channels` | `8` | USB PCM 采集通道数 |
| `mic_channels` | `[0,4,5,1,2,3]` | 六麦按物理圆环顺序排列的程序索引 |
| `mic_labels` | MIC_1、MIC_2、MIC_4、MIC_5、MIC_6、MIC_8 | 与 `mic_channels` 对应的物理标号 |
| `radius_m` | `0.035` | 麦克风环估计半径，单位米 |
| `frame_size` | `512` | 每通道每个定位块的采样数 |
| `gate_dbfs` | `-40.0` | 语句方向证据必须达到的基础门限 |
| `min_confidence` | `0.2` | 单块方向评分下限，不代表正确率 |
| `angle_offset_deg` | `0.0` | 显示方向整体旋转角度 |
| `mirror` | `false` | 翻转角度增长方向 |
| `hold_seconds` | `0.55` | 无 VAD 或演示模式的原有跟踪器保持时间 |
| `live_direction_window_seconds` | `0.25` | 实时人声方向的滚动观察窗口 |
| `live_direction_min_seconds` | `0.16` | 首次显示实时方向所需的有效音频时长 |
| `live_direction_min_consistency` | `0.7` | 实时窗口方向集中程度下限 |
| `live_direction_hold_seconds` | `0.4` | 有效实时方向消失后的短时保持 |
| `live_direction_speech_gap_seconds` | `0.45` | 连续语音中容许的短暂 VAD 掉票 |
| `live_direction_jump_confirm_seconds` | `0.35` | 大角度变化的持续确认时间 |
| `live_direction_min_snr_db` | `3.0` | 已校准噪声上的实时方向最低信噪比 |
| `live_direction_lock_degrees` | `55.0` | 一段连续语音内相对首次方向的最大偏移 |
| `vad_mode` | `3` | WebRTC VAD 严格度，范围 0–3 |
| `vad_channel` | `0` | 三路分散 VAD 选点的起始麦克风 |
| `speech_floor_dbfs` | 回退值 `-58.0` | 最低语音频段分析电平 |
| `speech_snr_db` | 回退值 `2.0` | 相对噪声的语音频段门限裕量 |
| `asr_enabled` | `true` | 默认启用离线识别，命令行参数可覆盖 |
| `asr_language` | `zh` | 当前固定中文，也可改为 `auto` 或 `en` |
| `asr_channel` | `0` | 送入 ASR 的原始程序通道 |
| `asr_threads` | `2` | CPU 推理线程数 |
| `asr_model_dir` | `models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17` | 模型和词表目录 |
| `asr_pre_roll_seconds` | `0.3` | 人声开始前保留的音频 |
| `asr_silence_seconds` | `0.6` | 结束语句所需的尾部静音 |
| `asr_min_speech_seconds` | `0.24` | 语句最短人声时长 |
| `asr_max_seconds` | `5.0` | 单个识别片段最长时长，允许配置到 30 秒 |
| `asr_direction_min_seconds` | `0.2` | 一句话所需的最短有效方向时间 |
| `asr_direction_min_coverage` | `0.3` | 有效方向占人声时长的最低比例 |
| `asr_direction_min_consistency` | `0.7` | 句内方向集中程度下限 |
| `direction_unknown_log_enabled` | `true` | 是否在终端打印方向未知的详细诊断 |
| `direction_sector_deg` | `30` | 指针和文字的方向扇区宽度 |

无效配置会在启动阶段被拒绝。扇区宽度必须是 360 的偶数因子且不小于 10°。

## 常见问题排查

### 找不到 `0bda:4cf0`

1. 检查 VA60X-GL 的 USB 连接和供电。
2. 执行 `cat /proc/asound/cards` 和 `arecord -l`。
3. 确认当前固件 USB VID:PID 与 `config.json` 一致。
4. 如果连接了多块相同 VID:PID 的设备，程序会拒绝自动猜测目标声卡。

### `Audio capture timed out` 或 `Audio device disconnected`

1. 检查声卡是否仍存在：`cat /proc/asound/cards`。
2. 检查设备是否被其他进程占用：`fuser /dev/snd/*`。
3. 修复连接后点击“重新检测设备”。
4. 仍失败时运行 `bash run.sh --probe --seconds 5` 并保留完整错误。

### `Capture error: overrun` 或 `xrun: prepare error: Input/output error`

这表示 ALSA/USB 采集缓冲未及时读取，并且驱动恢复失败。可能原因包括 USB 链路不稳定、设备被占用、固定声卡号失效或系统负载导致调度延迟。

1. 关闭其他录音程序并确认设备占用情况。
2. 重新连接阵列板，避免使用不稳定的 USB 线或 Hub。
3. 使用 `device: auto`，不要长期写死 `hw:<CARD>,0`。
4. 点击“重新检测设备”，再用 `--probe` 做最小采集验证。

### `Unable to open window`

1. 确认程序运行在已登录的图形桌面会话中。
2. 仅 SSH 登录时改用 `bash run.sh --probe --seconds 5`。
3. 确认已安装 `python3-tk`。

### `WebRTC VAD missing` 或 `Recognition dependency missing`

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements-asr.txt
bash run.sh
```

`run.sh` 会明确提示缺少的组件。VAD 缺失时关闭人声筛选；SenseVoice 或模型缺失时关闭转写。

### `Speech model missing`

1. 检查 `asr_model_dir` 中是否同时存在 `model.int8.onnx` 和 `tokens.txt`。
2. 执行 `.venv/bin/python setup_asr.py`。
3. 确认设备能访问模型下载地址并有足够存储空间。

### ASR 不显示文字

先使用模型自带样例验证识别链路：

```bash
.venv/bin/python transcribe.py \
  --file models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/test_wavs/zh.wav
```

如果样例可以识别但实时界面没有结果，检查 VAD 是否进入人声状态、语音是否达到最短 0.24 秒，以及 ASR 队列是否繁忙。后台最多等待两段语音；队列满时会跳过新片段，以保证 USB 采集不中断。

### 文字可以识别，但方向显示未知

“方向未知”表示语句方向证据没有通过完整判定，不表示 ASR 失败。按以下顺序排查：

1. 用 `--probe` 检查六个麦克风通道是否都有合理电平。
2. 正常说话时如果综合电平低于当前 `gate_dbfs: -40`，小幅调整门限并观察方向是否改善。
3. 使用完整句子测试，避免短词达不到 0.2 秒有效方向。
4. 排除多人同时说话、扬声器播放、强混响和移动声源。
5. 确认通道映射、0° 方向、`mirror` 和 `angle_offset_deg`。
6. 不要只为消除未知结果而大幅降低覆盖率或集中度门限，否则可能显示错误方向。

### 方向镜像、旋转或不稳定

1. 确认 `mic_channels` 为 `[0,4,5,1,2,3]`，且不包含空通道和回采。
2. 从 MIC_1 径向及相邻麦克风方向分别发声，确认角度增长方向。
3. 使用 `angle_offset_deg` 修正整体旋转，使用 `mirror` 修正方向反转。
4. 测试前保持安静，让噪声模型完成初始学习。
5. 降低墙面反射、风扇直吹和阵列附近播放声的影响。

## 测试与板端验证

在项目根目录运行：

```bash
bash test.sh
```

当前测试集共 45 项，覆盖：

- VA60X-GL 物理通道映射和配置校验；
- 合成远场信号的六麦定位；
- 方向平滑与大角度跳变确认；
- 三路 VAD 投票、进入/退出迟滞和跨块缓存；
- 噪声学习、语音频段质量和基础门限；
- 分句、预留音频、尾部静音和长句切段；
- 语句级圆周方向聚合、时长、覆盖率和集中度；
- 实时指针短时稳定、30° 转写扇区量化和方向未知；
- SenseVoice 真实模型样例、队列和错误上报；
- 双语界面、保存和设备重新检测。

本版本的 45 项测试已通过。自动化测试验证算法约定和软件状态，但不能代替实物方向标定。正式展示或交付前仍应在目标 PI M2 和目标 VA60X-GL 固件上执行：

```bash
bash test.sh
bash run.sh --probe --seconds 5
bash run.sh
```

现场至少检查六个固定方向、不同说话距离和音量、安静与风扇环境、USB 重插、持续说话、方向未知场景和长时间运行稳定性。

## 已知限制

- 应用只估计单一主声源的水平面方向，不估计距离或俯仰角，也不分离多个同时说话者。
- 当前 0.035 m 阵列半径和 MIC_1 为 0° 的约定仍需根据实物安装校准。
- 30° 扇区是显示颗粒度，不是定位精度保证或统计置信区间。
- 方向质量受通道顺序、安装朝向、墙面反射、噪声和声源移动影响。
- `min_confidence` 是启发式评分，不是定位正确率。
- 播放的人声可能触发 VAD，音乐或噪声也可能造成误判。
- 实时录音和转写不会持久化；最近 20 条记录仅存在于当前进程。
- ASR 队列已有两个任务等待时会跳过新语句。
- USB 音频设备不会自动循环重连；排除设备问题后需要点击“重新检测设备”。

## 开源依赖与发布注意事项

运行依赖由 `requirements-asr.txt` 和 `requirements-vad.txt` 声明，SenseVoice 模型由 `setup_asr.py` 单独下载。Python 包、模型、字体及其他第三方组件分别受其上游许可证和使用条款约束。

当前仓库根目录未包含项目级 `LICENSE` 文件。对外发布源码前，应由项目权利方确认项目许可证、第三方声明、模型分发条件及测试素材授权。不得在提交或发布包中包含开发板口令、私钥、访问令牌、内部地址或未经授权的真实录音。

## 技术支持与贡献

如在使用过程中遇到问题，欢迎在移远官方论坛提交技术咨询。报告问题时建议提供：

- Git 提交或发布版本；
- PI M2 系统版本和 VA60X-GL 固件版本；
- 启动命令及相关配置；
- 预期行为、实际行为和复现步骤；
- 脱敏后的 `--probe` 输出及完整错误日志；
- 涉及方向问题时的实际角度、距离、0° 朝向和现场环境。

提交代码前应运行 `bash test.sh` 和 `git diff --check`。硬件映射、配置默认值、用户界面或方向判定发生变化时，需要同步更新 README、架构文档和本说明。
