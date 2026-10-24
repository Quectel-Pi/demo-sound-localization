[English](README_EN.md)

# 声向 · Sound Direction / 人声方向与语音转写

界面默认中文，可用顶部“English”按钮即时切换为英文；点击“保存”会将界面语言与门限写入配置。
识别语言采用 `auto`：中文语音输出中文，英文语音输出英文。界面语言只改变标签，不翻译识别结果。
文字示例：`[方向 060°] 你好`；未知方向显示 `[方向未知]`。

实时模式顶部有“重新检测设备”按钮。USB 设备断开、重新插入或声卡号变化后，点击它会先停止旧采集，再按 `usb_vid_pid` 重新查找并打开声卡；转写历史保留。演示和 WAV 回放模式不显示此按钮。若仍提示采集错误，请检查 USB 连接及 `cat /proc/asound/cards`；重检无法修复物理断连。

基于 Quectel PI M2 和 Quectel VA60X-GL 六麦阵列板的人声方向应用。
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
门限可拖动粉色滑块或点击 − / + 调整，每次 1 dB；“保存”将门限值和界面语言写入配置。

## 启动

在 Quectel PI M2 图形桌面的终端中进入项目目录并执行：

```bash
cd /path/to/demo-sound-localization
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
bash run.sh --no-vad --no-asr    # 仅运行实时方向界面，不加载可选的人声/转写依赖
bash run.sh --wav recording.wav  # 回放 8 通道、16 kHz、16 位 PCM WAV
bash run.sh --demo               # 明确标记的合成方向演示；合成信号不做人声筛选
bash test.sh                     # 定位、人声门控、分句与离线识别测试
```

在当前 x86_64 桌面上，`./run.sh` 会优先使用本项目环境；若尚未安装，
则复用相邻 `sound_loca_demo` 目录中的本地依赖和离线模型。
如果 WebRTC VAD 或 SenseVoice 仍不可用，启动时会明确提示并暂时关闭相应功能。
若提示找不到 `0bda:4cf0`，先检查阵列板 USB 连接以及 `cat /proc/asound/cards`。

## 调节门限

先保持安静，观察声音电平，再用正常音量说话。
将门限设在大部分环境声音之上、正常说话电平之下。
例如安静时 -45 dBFS、说话时 -32 dBFS，可先试 -39 至 -37 dBFS。
负值越小（例如 -40），越容易触发；越接近零（例如 -30），越不容易触发。
电平条上的粉色标线表示当前门限，点击“保存”后重启仍使用该值。
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

高级参数保留在 `config.json` 中，修改后重启生效。

| 参数 | 作用 |
| --- | --- |
| `device` | ALSA 设备；默认 `auto`，按 USB VID:PID 自动查找 VA60X-GL |
| `ui_language` | 界面语言，`zh` 或 `en`；默认中文，不改变 ASR 识别语言 |
| `usb_vid_pid` | 新固件 USB 标识，当前实测为 `0bda:4cf0` |
| `mic_channels` | 依 MIC_1、MIC_2、MIC_4、MIC_5、MIC_6、MIC_8 物理顺序排列的零起始索引：`[0,4,5,1,2,3]` |
| `mic_labels` | 与 `mic_channels` 对应的物理位号，默认 MIC_1、MIC_2、MIC_4、MIC_5、MIC_6、MIC_8 |
| `radius_m` | 麦克风环半径；手册未给中心坐标，当前按 Ø80/Ø60 环形板中心线估算为 0.035 米 |
| `gate_dbfs` | 基础门限，人声确认后可自动放宽 |
| `min_confidence` | 方向一致性门限，默认 0.2；启发式评分，不是正确率 |
| `vad_mode` | 人声筛选强度 0–3，默认 2；越大越严格 |
| `vad_channel` | 人声检测使用的原始通道，默认 CH0 |
| `angle_offset_deg` | 显示方向整体旋转角度 |
| `mirror` | 翻转显示方向 |
| `hold_seconds` | 声音结束后保持方向的时间 |

## 软件与硬件原理

VA60X-GL 新固件通过 USB 提供 8 通道、16 kHz、16 位 PCM。设备说明中的通道 1–8
在配置中写作零起始索引 0–7：MIC_1→0、MIC_2→4、MIC_4→5、MIC_5→1、MIC_6→2、MIC_8→3；
索引 6（通道 7）为空，索引 7（通道 8）为回采，不参与定位。定位使用上述六路的 GCC-PHAT / SRP，
每个 512 采样块约 32 ms；采集仍须保持 `channels: 8`。
程序根据 `0bda:4cf0` 自动查找声卡，避免重新插拔后 ALSA 卡号变化。
WebRTC VAD 使用原始通道按 20 ms 连续分帧检测人声，采集块尾部保留并接到下一块。
定位结果经过圆周角度平滑，再由 Tk Canvas 绘制方向箭头。
只估计水平面方位，不估计人与阵列的距离。

六麦物理顺序按 MIC_1、MIC_2、MIC_4、MIC_5、MIC_6、MIC_8，间隔 60° 建模；
当前按用户提供的通道对应关系配置。算法假定这六个位号依次为顺时针，且 MIC_1 指向为 0°。
通道映射不等于安装方向标定：应从 MIC_1 径向与相邻麦克风方向分别发声，确认 0° 参考线和角度增长方向。
若安装中的“正前方”并非 MIC_1 所指方向，用 `angle_offset_deg` 旋转；若角度反向，用 `mirror` 翻转。
`bash run.sh --probe --seconds 3` 可检查各通道电平，但单次整体电平统计不能独立证明每个 MIC 的位号。

- `app.py`：启动、采集线程、方向跟踪。
- `neon_ui.py`：赛博朋克界面、方向箭头、门限控件。
- `audio.py`：八通道采集、设备超时和退出清理。
- `localization.py`：定位算法和方向平滑。
- `speech.py`：离线人声检测和门控。
- `asr.py`：分句、离线多语言模型与后台识别队列。
- `transcribe.py`：WAV 文件的独立识别入口，也用于真实模型测试。
- `setup_asr.py`：模型下载与安装入口。
- `env.sh` / `run.sh`：项目运行环境与启动。

## Quectel PI M2 环境准备

已记录的开发板环境为 aarch64、Debian 13。首次部署时，在项目目录执行以下命令安装系统组件、创建虚拟环境、安装 Python 依赖并准备 SenseVoice 模型：

```bash
sudo apt install python3 python3-venv python3-numpy python3-tk alsa-utils fonts-noto-cjk
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements-asr.txt
python3 setup_asr.py
bash run.sh
```

设备异常先检查 `arecord -l`；设备占用可检查 `fuser /dev/snd/*`。
仅通过 SSH 登录时不会自动创建图形桌面会话，可先使用 `--probe` 完成板端诊断。

## 离线录音验证与识别参数

可通过同一录音反复比较识别效果，无需重新采集：

```bash
.venv/bin/python transcribe.py --file models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/test_wavs/zh.wav
.venv/bin/python transcribe.py --file your_recording.wav --channel 0 --segment
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

硬件依据：Quectel VA60X-GL 用户手册 V1.0.0 Preliminary（2026-03-06）及当前固件实测 USB 描述符。
