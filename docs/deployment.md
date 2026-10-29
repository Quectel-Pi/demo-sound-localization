# 开发板部署

本文面向没有项目环境和本地 ASR 模型的新开发板。源码仓库不负责分发 SenseVoice 模型；模型需要单独下载到配置指定目录。`scripts/deploy.sh` 只准备运行环境、校验模型和运行测试，不包含模型下载或解压逻辑。

## 1. 获取源码

```bash
git clone <repository-url> demo-sound-localization
cd demo-sound-localization
git switch sound-localization-v2.0
```

如果仓库已经存在：

```bash
cd /path/to/demo-sound-localization
git status --short
git pull --ff-only
```

## 2. 单独下载模型

模型来源是 sherpa-onnx 官方发布包：

```text
https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/
sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2
```

在项目根目录执行：

```bash
model_url='https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2'
model_archive='/tmp/sherpa-onnx-sense-voice-int8.tar.bz2'

mkdir -p models
curl --fail --location --retry 3 "$model_url" --output "$model_archive"
echo '7d1efa2138a65b0b488df37f8b89e3d91a60676e416f515b952358d83dfd347e  /tmp/sherpa-onnx-sense-voice-int8.tar.bz2' | sha256sum --check
tar -xjf "$model_archive" -C models
rm "$model_archive"
```

也可以在另一台机器下载、校验并解压后，将完整模型目录复制到开发板。模型与 CPU 架构无关，但 `.venv` 与架构和 Python 版本有关，不要从其他机器复制虚拟环境。

## 3. 模型目录位置

`config.json` 的 `asr_model_dir` 默认指向：

```text
demo-sound-localization/
└── models/
    └── sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/
        ├── model.int8.onnx   # 必需，239233841 字节
        ├── tokens.txt        # 必需，315894 字节
        ├── LICENSE           # 上游授权说明
        ├── README.md         # 上游模型说明
        └── test_wavs/        # 可选测试音频
```

应用运行只依赖同一目录下的 `model.int8.onnx` 和 `tokens.txt`。目录名称或位置发生变化时，应同步修改 `config.json` 的 `asr_model_dir`。

下载包约 163 MB，解压后的模型目录约 230 MB。建议至少预留 700 MB 空间，用于源码、模型、虚拟环境和安装缓存。

## 4. 准备运行环境

模型准备完成后，在项目根目录执行：

```bash
bash scripts/deploy.sh
```

部署脚本只执行：

1. 安装 Python、Tkinter、ALSA、字体等系统依赖；
2. 创建项目本地 `.venv` 并安装 Python 依赖；
3. 校验配置指定的 ONNX 模型与 token 表是否存在且大小合理；
4. 默认运行自动化测试。

可选参数：

```bash
# 系统包已经准备好
bash scripts/deploy.sh --skip-system-packages

# 暂时跳过测试
bash scripts/deploy.sh --skip-tests
```

部署脚本没有模型下载参数，也不会修改 `config.json`。模型缺失或不完整时脚本会停止，并提示按本文单独准备模型。

## 5. 运行验证

先验证 USB 阵列采集和原始方向：

```bash
bash run.sh --probe --seconds 5
```

再在开发板已登录的图形桌面终端启动应用：

```bash
bash run.sh
```

纯 SSH 会话可能缺少 `DISPLAY` 或桌面授权，此时优先使用 `--probe`。

## 6. 常见问题

| 现象 | 处理方式 |
| --- | --- |
| `curl` 下载失败 | 检查网络和 GitHub Releases 访问；也可在其他机器下载后复制模型目录 |
| SHA-256 校验失败 | 删除压缩包并重新下载，不要解压或使用损坏文件 |
| `Speech model missing` | 检查 `asr_model_dir` 及两个必需文件的位置 |
| 模型文件过小 | 重新下载并确认压缩包 SHA-256；不要使用网页错误响应代替模型 |
| `USB audio device 0bda:4cf0 not found` | 检查数据线、供电、`lsusb` 和 `arecord -l` |
| GUI 无法打开 | 在已登录的图形桌面运行，或先使用 `--probe` |
