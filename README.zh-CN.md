[English](README.md)

# 声向 · Sound Direction / 人声方向与语音转写

当前界面的标题、按钮、状态和方向标签均为英文。识别语言采用 `auto`：中文语音输出中文，英文语音输出英文。
文字示例：`[Direction 060°] 你好`；未知方向显示 `[Direction unknown]`。

基于 Quectel PI M2、Sipeed 6+1 阵列和 MA-USB8 驱动板的人声方向应用。
赛博朋克界面左侧为方向雷达，右侧显示角度、人声状态、电平和门限，下方显示离线语音转写。
人声检测、自适应语音电平和方向一致性同时通过时，青色箭头指向声源；安静时显示待机准星。

Quectel PI M2 版本默认同时提供人声指向与语音转文字，保持精简界面，不增加功能切换控件。
说完一句，停顿约一秒后显示识别文字；文字可复制、清空，保留最近 20 段。
识别在独立后台线程运行，定位持续处理，语音不上传。
每句话同时显示说话期间的代表方向，例如 `[Direction 060°] 你好`；复制文字时也包含方向。
方向根据这句话期间通过人声、语音频段信号质量及方向一致性检查的原始定位结果汇总，
按一致性评分和音频时长加权做圆周平均，不取识别完成时的方向，也不取动画的滞后角度。
句尾静音和开头预留音频不参与方向汇总；长句切段后，每段分别计算方向。
默认至少需要 120 ms 有效方向、覆盖 20% 以上语音时长，且方向集中程度至少 0.6。
证据不足或方向相互冲突时显示 `[Direction unknown]`，文字仍正常输出。
这些门限可分别通过 `asr_direction_min_seconds`、`asr_direction_min_coverage`、
`asr_direction_min_consistency` 在配置中调整，修改后重启生效。
门限可拖动粉色滑块或点击 − / + 调整，每次 1 dB；“保存门限”将门限值写入配置。

## 启动

在 Quectel PI M2 图形桌面的终端中进入项目目录并执行：

```bash
cd /path/to/sound_loca_demo
bash run.sh
```

将 `/path/to` 替换为项目在开发板上的实际存放路径。

默认始终启用 WebRTC VAD 人声筛选，三个分散的原始麦克风投票，至少两路判断有人声才通过。
识别的是音频是否包含语音，播放的人声也可能触发，
音乐和噪声仍可能误判。声音结束后，方向短暂保持约 0.55 秒。
文字识别使用 Quectel PI M2 本地存储的 SenseVoice INT8 模型，按每段语音自动判断语言。可通过 `asr_language` 固定为 `zh` 或 `en`，修改后重启。
保留 300 ms 开头音频，句尾等待 800 ms，
最长每段 15 秒。文字分句独立于定位门限，避免较轻的词被漏掉；实际文字仍可能识错。

```bash
bash run.sh --probe --seconds 5   # 无界面真实采集诊断
bash run.sh --wav recording.wav  # 回放 8 通道、48 kHz、16 位 PCM WAV
bash run.sh --demo               # 明确标记的合成方向演示；合成信号不做人声筛选
bash test.sh                     # 定位、人声门控、分句与离线识别测试
```

## 调节门限

先保持安静，观察声音电平，再用正常音量说话。
将门限设在大部分环境声音之上、正常说话电平之下。
例如安静时 -45 dBFS、说话时 -32 dBFS，可先试 -39 至 -37 dBFS。
负值越小（例如 -40），越容易触发；越接近零（例如 -30），越不容易触发。
电平条上的粉色标线表示当前门限，点击“保存门限”后重启仍使用该值。
该值现在是**基础门限**：确认人声后，根据语音频段的环境噪声自动放宽，
不会仅因为人声低于基础门限就停止方向计算。界面同时显示实际使用的人声门限。
文字方向不再依赖箭头是否通过显示门限，较轻的词也可提供方向证据。

首次启动先保持安静 2–3 秒，使程序学习稳定噪声频谱。噪声模型只在未检测到人声时更新，
定位时降低稳定风扇声、嗡声等频段的权重。大幅方向跳变需要连续三个相近结果确认，
减少短暂干扰造成的箭头转动；真实说话者换方向时可能增加约百毫秒的确认延迟。
这不等于分离多个同时发声的人：强噪声、多声源或混响仍可能影响结果，证据不足时仍显示方向不确定。

语音频段采用 250–4000 Hz，`speech_floor_dbfs` 默认 -58 dBFS；
`speech_snr_db` 默认 2 dB，决定环境噪声以上的人声门限裕量。
这些是不同于完整音频电平的处理后频段电平，配置修改后重启生效。

## 配置

高级参数保留在 `config/config.json` 中，修改后重启生效。

| 参数 | 作用 |
| --- | --- |
| `device` | ALSA 设备，默认 `hw:MicArray,0` |
| `mic_channels` | 按顺时针排列的六路原始麦克风，默认 CH0–CH5 |
| `radius_m` | 外圈麦克风半径，当前 0.04 米 |
| `gate_dbfs` | 基础门限，人声确认后可自动放宽 |
| `min_confidence` | 方向一致性门限，默认 0.2；启发式评分，不是正确率 |
| `vad_mode` | 人声筛选强度 0–3，默认 2；越大越严格 |
| `vad_channel` | 人声检测使用的原始通道，默认 CH0 |
| `angle_offset_deg` | 显示方向整体旋转角度 |
| `mirror` | 翻转显示方向 |
| `hold_seconds` | 声音结束后保持方向的时间 |

## 软件与硬件原理

USB 八通道音频通过 Quectel PI M2 上的 ALSA 和 `arecord` 采集；定位使用 CH0–CH5 的 GCC-PHAT / SRP，
每个 2048 采样块约 42.7 ms。CH6 是官方波束成形输出，不作为独立麦克风定位。
WebRTC VAD 使用原始通道按 20 ms 连续分帧检测人声，采集块尾部保留并接到下一块。
定位结果经过圆周角度平滑，再由 Tk Canvas 绘制方向箭头。
只估计水平面方位，不估计人与阵列的距离。

- `src/sound_localization/`：应用、音频采集、定位、人声检测、语音识别和界面模块。
- `tests/`：单元测试与可选集成测试。
- `tools/transcribe.py`：WAV 文件的独立识别入口，也用于真实模型测试。
- `tools/setup_asr.py`：模型下载与安装入口。
- `config/config.json`：运行配置。
- `requirements/`：VAD 与 ASR 可选依赖清单。
- `scripts/env.sh`：共享运行环境；根目录的 `run.sh` 和 `test.sh` 保持为稳定入口。

## Quectel PI M2 环境准备

已记录的开发板环境为 aarch64、Debian 13。首次部署时，在项目目录执行以下命令安装系统组件、创建虚拟环境、安装 Python 依赖并准备 SenseVoice 模型：

```bash
sudo apt install python3 python3-venv python3-numpy python3-tk alsa-utils fonts-noto-cjk
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements/asr.txt
python3 tools/setup_asr.py
bash run.sh
```

设备异常先检查 `arecord -l`；设备占用可检查 `fuser /dev/snd/*`。
仅通过 SSH 登录时不会自动创建图形桌面会话，可先使用 `--probe` 完成板端诊断。

## 离线录音验证与识别参数

可通过同一录音反复比较识别效果，无需重新采集：

```bash
.venv/bin/python tools/transcribe.py --file models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/test_wavs/zh.wav
.venv/bin/python tools/transcribe.py --file your_recording.wav --channel 0 --segment
```

该入口接受单声道或多声道 16 位 PCM WAV；`--channel` 选择零起始通道。
超过 30 秒的录音需使用 `--segment`，分句支持 8/16/32/48 kHz。
单声道 WAV 没有阵列几何信息，因此独立录音识别不会计算声源方向。

| 参数 | 默认值 | 作用 |
| --- | --- | --- |
| `asr_language` | auto | 自动判断语言；也可固定为 zh 或 en |
| `asr_channel` | 0 | 文字识别使用的音频通道 |
| `asr_threads` | 2 | 模型 CPU 线程数量 |
| `asr_pre_roll_seconds` | 0.3 | 人声触发前保留的音频 |
| `asr_silence_seconds` | 0.8 | 句尾等待时间 |
| `asr_min_speech_seconds` | 0.24 | 丢弃非常短的触发片段 |
| `asr_max_seconds` | 15 | 每个识别片段的最大时长 |

后台最多等待两段语音，繁忙时跳过新片段而不阻塞采集。正常运行不将录音或识别文字写入磁盘。
模型和词表位于 `models/`，Python 运行依赖位于 `.venv/`；这些文件不可当作缓存删除。

参考：[Sipeed MA-USB8 官方指南](https://wiki.sipeed.com/hardware/en/modules/micarray_usbboard_bl616.html)。


## 技术支持与贡献

如在使用过程中遇到问题，欢迎在[移远官方论坛](https://forumschinese.quectel.com/c/quectel-pi/58)提交技术咨询，移远技术支持团队将及时为您解答。
