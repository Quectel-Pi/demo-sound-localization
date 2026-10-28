[English](README_EN.md) · [架构设计](arch.md) · [开源与贡献](opensource.md)

# 声向 · Sound Direction

面向 **Quectel PI M2** 与 **Quectel VA60X-GL** 六麦阵列板的本地人声方向定位和中英文离线转写应用。

默认工作方式不是让指针随每个音频块抖动，而是等待一句话结束并完成转写后，再显示该句话的稳定方向范围。方向证据不足时仍显示文字，但标记为 `[方向未知]` 并隐藏指针。音频和转写均在本机处理，不上传。

## 当前能力

- VA60X-GL 八通道 USB 音频自动检测，USB VID:PID 为 `0bda:4cf0`；不依赖固定 ALSA 卡号。
- 六个物理麦克风参与 GCC-PHAT / SRP 水平方位估计；空通道与回采通道不参与定位。
- 三路分散麦克风的 WebRTC VAD 多数投票，用于确认人声和切分语句。
- SenseVoice INT8 离线识别，默认自动识别中文、英文等模型支持的语言。
- 一句话结束后汇总方向证据，量化为默认 30° 扇区，例如 `[方向约 060° ±15°] 你好`。
- 中英文界面即时切换；保存按钮持久化界面语言和基础电平门限。
- USB 重插或声卡号变化后，可在界面点击“重新检测设备”。
- 提供真实采集探测、八通道 WAV 回放和合成演示模式。

## 硬件与通道

当前固件采集格式为 **8 通道、16 kHz、16 位有符号 PCM、交错采样**。硬件说明使用 1 起始通道号，程序配置使用 0 起始索引：

| 物理位置 | 硬件通道 | 程序索引 | 用途 |
| --- | ---: | ---: | --- |
| MIC_1 | 1 | 0 | 定位、VAD、默认 ASR |
| MIC_2 | 5 | 4 | 定位 |
| MIC_4 | 6 | 5 | 定位、VAD 投票 |
| MIC_5 | 2 | 1 | 定位 |
| MIC_6 | 3 | 2 | 定位、VAD 投票 |
| MIC_8 | 4 | 3 | 定位 |
| 空 | 7 | 6 | 不使用 |
| 回采 | 8 | 7 | 不使用 |

因此 `channels` 必须保持为 `8`，六麦的物理环形顺序配置为：

```json
"mic_channels": [0, 4, 5, 1, 2, 3]
```

算法暂按 MIC_1、MIC_2、MIC_4、MIC_5、MIC_6、MIC_8 顺时针、间隔 60° 建模，并把 MIC_1 径向定义为 0°。这只是软件坐标系，不等于设备安装后的“正前方”。实际安装后应从已知方向发声进行标定：用 `angle_offset_deg` 修正整体旋转，角度增大方向相反时设置 `mirror: true`。当前 `radius_m: 0.035` 是依据板形尺寸的估计值，获得精确麦克风中心坐标后应替换。

## 环境准备

在 PI M2 图形桌面的终端中执行：

```bash
sudo apt install python3 python3-venv python3-numpy python3-tk alsa-utils fonts-noto-cjk
cd /path/to/demo-sound-localization
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements-asr.txt
python3 setup_asr.py
bash run.sh
```

`setup_asr.py` 从 sherpa-onnx 官方发布地址下载约 230 MB 的 SenseVoice INT8 模型到本地 `models/`。模型和虚拟环境不会提交到 Git。

只有 SSH 终端而没有图形会话时，GUI 无法打开；可先用 `--probe` 验证采集。

## 运行与诊断

```bash
bash run.sh                         # 完整 GUI：定位、VAD、离线转写
bash run.sh --probe --seconds 5     # 无界面采集诊断，输出 JSON
bash run.sh --no-vad --no-asr      # 不加载可选依赖的实时定位界面
bash run.sh --wav recording.wav    # 回放 8ch/16kHz/S16_LE PCM WAV
bash run.sh --demo                 # 合成方向演示，不启用 VAD/ASR
bash test.sh                       # 运行全部单元与集成测试
```

`run.sh` 会优先使用项目 `.venv`。若缺少 WebRTC VAD 或 SenseVoice，它会打印提示并关闭相应功能，而不是静默失败。

设备基础检查：

```bash
cat /proc/asound/cards
arecord -l
bash run.sh --probe --seconds 5
```

不要把一次枚举出的 `hw:3,0` 长期写死；USB 重插后卡号可能变化。默认的 `device: auto` 会按 VID:PID 重新解析设备。

## 一句话的方向如何产生

每个 512 采样块约 32 ms，定位器在 250–4000 Hz 语音频段对六麦的 15 个麦克风对做 GCC-PHAT 延时估计，并以 2° 步长扫描 0–358°。只有同时满足以下条件的块才进入该句话的方向汇总：

1. VAD 多数投票认为当前有人声；
2. 语音频段电平和相对噪声的信噪比通过检查；
3. 六麦综合电平达到基础硬门限 `gate_dbfs`；
4. 当前方向评分达到 `min_confidence`。

一句话结束后，程序按有效时长和评分做圆周加权平均。默认还要求：有效方向累计至少 0.25 秒、覆盖语音时长至少 30%、圆周集中程度至少 0.7。通过后，结果四舍五入到最近的 30° 扇区；例如 68° 显示为 `60° ±15°`，352° 显示为 `0° ±15°`。指针与转写文本使用同一个扇区，并保持到下一条有效结果、清空记录或重新检测设备。

低于基础门限的语音仍可进入 ASR，因此“有转写但方向未知”是允许的设计结果。详细公式、线程和状态流参见 [arch.md](arch.md)。

## 门限调节

首次启动后先安静 2–3 秒，让程序学习稳定噪声频谱，再以正常音量从预期距离说话。将基础门限放在环境声之上、正常语音之下。例如环境约 -45 dBFS、语音约 -32 dBFS时，可从 -39 至 -37 dBFS开始尝试。

- 更负的值（如 -40）更灵敏，也更容易接收噪声。
- 更接近 0 的值（如 -30）更严格，也更容易得到“方向未知”。
- 粉色标线是当前基础门限；点击“保存”写入 `config.json`。
- 自适应人声门限只辅助 VAD，不会替代 `gate_dbfs` 这个方向证据硬门限。

## 为什么经常显示“方向未知”

这不是单一错误，而是方向证据没有通过完整判定链。按以下顺序排查：

1. 用 `--probe` 确认六个有效通道都有合理电平，程序索引 6、7 不应被当作麦克风。
2. 正常说话时若综合电平经常低于 `gate_dbfs: -35`，先把门限逐步降到 -38 或 -40，避免一次调整过大。
3. 短词可能达不到 `asr_direction_min_seconds: 0.25`；连续说完整一句再比较。
4. 混响、多个人同时说话、播放声和移动声源会降低 `asr_direction_min_consistency: 0.7`。
5. 说话片段中有效定位过少会低于 `asr_direction_min_coverage: 0.3`。
6. 通道顺序、0° 方位或顺逆时针假设错误时，先做几何标定，不要用降低一致性门限掩盖映射问题。

需要调试时一次只修改一个参数，并保留同一距离、同一方向和近似音量作为对照。

## 配置速查

| 参数 | 默认值 | 作用 |
| --- | ---: | --- |
| `device` | `auto` | 按 USB VID:PID 自动寻找 ALSA 设备；也可临时指定 `hw:CARD,DEV` |
| `ui_language` | `zh` | 界面语言：`zh` 或 `en`，不改变识别语言 |
| `usb_vid_pid` | `0bda:4cf0` | 当前已验证固件的 USB 标识 |
| `rate` / `channels` | `16000` / `8` | 采样率与采集通道数 |
| `frame_size` | `512` | 每个定位块的每通道采样数 |
| `mic_channels` | `[0,4,5,1,2,3]` | 六麦按物理环形顺序排列的程序索引 |
| `radius_m` | `0.035` | 麦克风环半径估计值，单位米 |
| `gate_dbfs` | `-35` | 语句方向证据的基础硬门限 |
| `min_confidence` | `0.2` | 单块方向评分门限；是启发式分数，不是正确率 |
| `angle_offset_deg` | `0` | 显示方向整体旋转角度 |
| `mirror` | `false` | 翻转角度增长方向 |
| `hold_seconds` | `0.55` | 仅用于无 ASR 或演示模式的实时指针保持 |
| `vad_mode` | `2` | WebRTC VAD 严格度，范围 0–3，数值越大越严格 |
| `vad_channel` | `0` | 三路 VAD 选点的起始物理麦克风 |
| `asr_language` | `auto` | 识别语言；也可固定为 `zh` 或 `en` |
| `asr_channel` | `0` | ASR 使用的原始程序通道索引 |
| `asr_pre_roll_seconds` | `0.3` | 人声触发前保留音频 |
| `asr_silence_seconds` | `0.8` | 判定句尾的连续静音 |
| `asr_min_speech_seconds` | `0.24` | 丢弃过短触发片段的下限 |
| `asr_max_seconds` | `15` | 单个识别片段最大时长 |
| `asr_direction_min_seconds` | `0.25` | 一句话所需的最短有效方向时长 |
| `asr_direction_min_coverage` | `0.3` | 有效方向占语音时长的最低比例 |
| `asr_direction_min_consistency` | `0.7` | 句内方向圆周集中程度下限 |
| `direction_sector_deg` | `30` | 指针及文字的扇区宽度，当前为中心 ±15° |

## 常见问题

### `Capture error: overrun` / `xrun: prepare error: Input/output error`

这表示 ALSA/USB 采集缓冲未被及时读取，随后驱动恢复失败。常见原因是 USB 链路不稳、设备被另一进程占用、重插后仍使用旧卡号，或系统负载导致调度延迟。先关闭其他录音进程，重新插拔阵列板，然后点击“重新检测设备”；仍失败时检查：

```bash
fuser /dev/snd/*
cat /proc/asound/cards
bash run.sh --probe --seconds 5
```

### ASR 不打印或界面一直没有文字

启动日志若提示 SenseVoice 不可用，检查 `.venv`、`requirements-asr.txt` 与模型目录；再运行：

```bash
.venv/bin/python setup_asr.py
.venv/bin/python transcribe.py \
  --file models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/test_wavs/zh.wav
```

后台识别队列最多等待两段语音；计算繁忙时新片段会被跳过，以免阻塞持续采集。正常运行只在内存中保留最近 20 条转写，不把录音或文本写入磁盘。

### 独立 WAV 转写

```bash
.venv/bin/python transcribe.py --file your.wav --channel 0 --segment
```

接受单声道或多声道 16 位 PCM WAV；长录音应加 `--segment`。单声道文件没有阵列几何信息，因此只转写、不计算方向。

## 项目结构

- `app.py`：启动、采集工作线程、UI 状态协调与设备重检。
- `audio.py`：按 VID:PID 定位 ALSA 设备、`arecord` 采集与 WAV 输入。
- `localization.py`：六麦 GCC-PHAT / SRP 定位与实时跟踪。
- `speech.py`：语音频段质量判断、噪声模型与三路 VAD 投票。
- `asr.py`：分句、方向汇总、SenseVoice 和后台识别队列。
- `neon_ui.py` / `i18n.py`：界面绘制及中英文文案。
- `transcribe.py`：独立 WAV 转写验证入口。
- `setup_asr.py`：离线模型下载与完整性记录。
- `config.json`：硬件、定位、VAD、ASR 与显示参数。

硬件依据：Quectel VA60X-GL 用户手册 V1.0.0 Preliminary（2026-03-06）及当前固件实测 USB/ALSA 描述。
