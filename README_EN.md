[简体中文](README.md) · [Architecture (Chinese)](docs/arch.md) · [Next-version plan (Chinese)](docs/next-version-plan.md) · [Open-source guide (Chinese)](docs/opensource.md)

# Sound Direction

A local voice-direction and offline multilingual transcription application for the **Quectel PI M2** and **Quectel VA60X-GL** six-microphone array.

In the current default mode, the live pointer updates after about 0.16 seconds of valid voice-direction evidence, without waiting for transcription. While VAD continues to detect speech, the last stable direction remains visible through brief gaps in valid localization frames. SenseVoice transcribes in the background and attaches the utterance's direction to its text; when it is unknown, the UI shows only the transcript. Audio and transcripts stay on the device.

## Features

- Automatic detection of VA60X-GL eight-channel USB audio by VID:PID `0bda:4cf0`, without relying on a fixed ALSA card number.
- Horizontal GCC-PHAT / SRP localization using six physical microphones; the empty and loopback channels are excluded.
- Majority-vote WebRTC VAD across three spaced microphones for speech confirmation and utterance segmentation.
- Offline SenseVoice INT8 recognition; the current configuration fixes Chinese (`zh`), and `auto` enables model-supported language detection.
- Live voice direction uses a short circular average and jump confirmation, with a 0.25-second window and a 0.4-second hold after speech.
- Each transcript separately aggregates the utterance direction into a 30° sector such as `[Direction ~060° ±15°] Hello`.
- Chinese and English UI with persisted language and base-level gate settings.
- A **Detect device again** action for USB reconnects and ALSA card-number changes.
- Live capture diagnostics, eight-channel WAV replay, and a synthetic demo mode.

## Hardware and Channel Mapping

The tested firmware exposes **8-channel, 16 kHz, signed 16-bit, interleaved PCM**. Hardware documentation numbers channels from 1; the application uses zero-based indices:

| Position | Hardware channel | Software index | Use |
| --- | ---: | ---: | --- |
| MIC_1 | 1 | 0 | Localization, VAD, default ASR |
| MIC_2 | 5 | 4 | Localization |
| MIC_4 | 6 | 5 | Localization and VAD vote |
| MIC_5 | 2 | 1 | Localization |
| MIC_6 | 3 | 2 | Localization and VAD vote |
| MIC_8 | 4 | 3 | Localization |
| Empty | 7 | 6 | Unused |
| Loopback | 8 | 7 | Unused |

Keep `channels` set to `8`. The six microphones are reordered into their physical ring order with:

```json
"mic_channels": [0, 4, 5, 1, 2, 3]
```

The current geometry assumes MIC_1, MIC_2, MIC_4, MIC_5, MIC_6, and MIC_8 are clockwise at 60° intervals, with the MIC_1 radial direction defined as 0°. This software coordinate system is not necessarily the installed device's “front.” Calibrate it using a known source: use `angle_offset_deg` for global rotation and `mirror: true` if the angle direction is reversed. The current `radius_m: 0.035` is an estimate from board dimensions and should be replaced when exact microphone-center coordinates are available.

## Setup

From a terminal in the PI M2 graphical desktop:

```bash
sudo apt install python3 python3-venv python3-numpy python3-tk alsa-utils fonts-noto-cjk
cd /path/to/demo-sound-localization
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements-asr.txt
python3 setup_asr.py
bash run.sh
```

`setup_asr.py` downloads the approximately 230 MB SenseVoice INT8 model from the official sherpa-onnx release URL into `models/`. The model and virtual environment are excluded from Git.

A plain SSH session normally has no graphical display. Use `--probe` first when only a terminal is available.

## Run and Diagnose

```bash
bash run.sh                         # Full GUI: localization, VAD, offline ASR
bash run.sh --probe --seconds 5     # Headless capture diagnostics as JSON
bash run.sh --no-vad --no-asr      # Live localization without optional dependencies
bash run.sh --wav recording.wav    # Replay 8ch/16kHz/S16_LE PCM WAV
bash run.sh --demo                 # Synthetic direction demo without VAD/ASR
bash test.sh                       # Run all unit and integration tests
```

`run.sh` prefers the project's `.venv`. If WebRTC VAD or SenseVoice is missing, it prints a warning and disables the affected feature instead of failing silently.

Basic device checks:

```bash
cat /proc/asound/cards
arecord -l
bash run.sh --probe --seconds 5
```

Do not permanently configure a card number observed once, such as `hw:3,0`; it can change after a USB reconnect. With `device: auto`, the application resolves the card again from its VID:PID.

## How Sentence Direction Is Produced

Each 512-sample block is approximately 32 ms. The localizer evaluates all 15 microphone pairs with GCC-PHAT in the 250–4000 Hz speech band and scans 0–358° in 2° steps. A block contributes directional evidence only when all of these checks pass:

1. Majority-vote VAD reports speech.
2. Speech-band level and signal-to-noise checks pass.
3. The six-microphone aggregate level reaches the hard `gate_dbfs` threshold.
4. The frame direction score reaches `min_confidence`.

The live pointer uses valid voice directions from the latest 0.25 seconds. It appears after at least 0.16 seconds of evidence with concentration of at least 0.7. Brief VAD dropouts can last up to 0.45 seconds without ending the tracked speech. Normal updates use frames within 55° of the locked direction; a stable, dominant direction outside that range can take over after a handoff check. Calibrated frames below 3 dB SNR do not move the pointer. It holds for 0.4 seconds after speech is confirmed to have ended and shows a default ±15° sector.

Each transcript independently combines valid directions across its utterance, weighted by duration and score. The current configuration requires at least 0.2 seconds of valid direction, at least 30% coverage of voiced duration, and concentration of at least 0.7. A passing result is rounded to the nearest 30° sector: 68° becomes `60° ±15°`, while 352° becomes `0° ±15°`. When a speaker moves, the current pointer can differ from a completed transcript's direction.

Speech below the base gate may still be transcribed. Unknown-direction text appears without a direction label in the UI, while diagnostics are printed to the terminal by default. Set `direction_unknown_log_enabled` to `false` to disable that terminal output. See [architecture](docs/arch.md) for data flow, formulas, threads, and state handling.

## Adjust the Gate

Keep the room quiet for two to three seconds after startup so the application can learn the stable noise spectrum. Then speak at a normal level and expected distance. Place the base gate above ambient sound and below ordinary speech. If ambient sound is about -45 dBFS and speech is about -32 dBFS, start around -39 to -37 dBFS.

- A more negative value such as -40 is more sensitive, but accepts more noise.
- A value closer to zero such as -30 is stricter and produces more unknown directions.
- The pink level-meter line is the base gate; **Save** writes it to `config.json`.
- The adaptive speech gate helps VAD but never replaces the hard direction-evidence gate.

## Why “Direction unknown” Appears

It means the full evidence chain did not pass, rather than identifying one specific fault. Diagnose it in this order:

1. Run `--probe` and verify that all six microphone channels have plausible levels. Software indices 6 and 7 must not be used as microphones.
2. If ordinary speech often stays below the current `gate_dbfs: -40`, adjust the gate in small steps and see whether the direction stabilizes.
3. Very short words may not meet `asr_direction_min_seconds: 0.2`; compare using a complete sentence.
4. Reverberation, simultaneous speakers, playback, or a moving source may fail `asr_direction_min_consistency: 0.7`.
5. Too few valid frames may fail `asr_direction_min_coverage: 0.3`.
6. If channel order, 0°, or clockwise direction is wrong, calibrate the geometry before relaxing consistency thresholds.

Change one parameter at a time and keep source direction, distance, and voice level comparable.

## Configuration Reference

| Key | Default | Purpose |
| --- | ---: | --- |
| `device` | `auto` | Find ALSA device by USB VID:PID; a temporary `hw:CARD,DEV` override is supported |
| `ui_language` | `zh` | UI language, `zh` or `en`; independent from ASR language |
| `usb_vid_pid` | `0bda:4cf0` | USB identity of the currently verified firmware |
| `rate` / `channels` | `16000` / `8` | Capture sample rate and channel count |
| `frame_size` | `512` | Per-channel samples in each localization block |
| `mic_channels` | `[0,4,5,1,2,3]` | Software indices in physical ring order |
| `radius_m` | `0.035` | Estimated microphone-ring radius in metres |
| `gate_dbfs` | `-40` | Hard gate for sentence-direction evidence |
| `min_confidence` | `0.2` | Per-block heuristic direction-score threshold, not an accuracy probability |
| `angle_offset_deg` | `0` | Global display rotation |
| `mirror` | `false` | Reverse the angle direction |
| `hold_seconds` | `0.55` | Original tracker hold used without VAD or in demo mode |
| `live_direction_window_seconds` | `0.25` | Rolling window for live voice direction |
| `live_direction_min_seconds` | `0.16` | Valid audio duration required before the live pointer appears |
| `live_direction_min_consistency` | `0.7` | Minimum circular concentration in the live window |
| `live_direction_hold_seconds` | `0.4` | Short hold after speech is confirmed to have ended |
| `live_direction_speech_gap_seconds` | `0.45` | Grace period for brief VAD dropouts during speech |
| `live_direction_jump_confirm_seconds` | `0.35` | Continuous evidence needed for a large direction change |
| `live_direction_min_snr_db` | `3.0` | Minimum calibrated SNR for a live direction frame |
| `live_direction_lock_degrees` | `55.0` | Maximum deviation from the first direction during continuous speech |
| `live_direction_handoff_window_seconds` | `0.55` | Window for directions outside the current lock |
| `live_direction_handoff_min_seconds` | `0.4` | Minimum valid audio duration before a handoff |
| `live_direction_handoff_min_consistency` | `0.85` | Minimum circular concentration of a new direction |
| `live_direction_handoff_min_share` | `0.75` | Minimum share of recent valid direction evidence from the candidate |
| `vad_mode` | `3` | WebRTC VAD aggressiveness, 0–3; higher is stricter |
| `vad_channel` | `0` | Starting physical microphone for the three VAD selections |
| `asr_language` | `zh` | Currently fixed to Chinese; may be set to `auto` or `en` |
| `asr_channel` | `0` | Raw software channel used for ASR |
| `asr_pre_roll_seconds` | `0.3` | Audio retained before speech onset |
| `asr_silence_seconds` | `0.6` | Continuous silence that ends an utterance |
| `asr_min_speech_seconds` | `0.24` | Minimum speech duration for an utterance |
| `asr_max_seconds` | `5` | Maximum duration of one recognition segment; configurable up to 30 seconds |
| `asr_direction_min_seconds` | `0.2` | Minimum valid direction duration per utterance |
| `asr_direction_min_coverage` | `0.3` | Minimum valid-direction share of voiced duration |
| `asr_direction_min_consistency` | `0.7` | Minimum circular concentration within an utterance |
| `direction_unknown_log_enabled` | `true` | Print detailed unknown-direction diagnostics to the terminal |
| `direction_sector_deg` | `30` | Live pointer range and transcript sector width, currently ±15° |

## Troubleshooting

### `Capture error: overrun` / `xrun: prepare error: Input/output error`

ALSA/USB capture was not drained in time and driver recovery then failed. Common causes include an unstable USB link, another process using the device, a stale fixed card number after reconnect, or scheduling delays under load. Stop other recording processes, reconnect the board, and use **Detect device again**. If the error remains:

```bash
fuser /dev/snd/*
cat /proc/asound/cards
bash run.sh --probe --seconds 5
```

### ASR Does Not Print or Display Text

If startup says SenseVoice is unavailable, inspect `.venv`, `requirements-asr.txt`, and the model directory, then run:

```bash
.venv/bin/python setup_asr.py
.venv/bin/python transcribe.py \
  --file models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/test_wavs/zh.wav
```

The background queue can hold at most two utterances. When inference cannot keep up, a new segment is skipped so capture remains responsive. Normal operation keeps the latest 20 transcripts in memory and does not save audio or text to disk.

### Standalone WAV Transcription

```bash
.venv/bin/python transcribe.py --file your.wav --channel 0 --segment
```

This accepts mono or multichannel 16-bit PCM WAV. Use `--segment` for long recordings. A mono file has no array geometry, so this command transcribes it without estimating direction.

## Project Layout

- `sound_direction/`: capture, localization, speech detection, ASR, UI, and translation modules.
- `tests/`: unit tests and optional real-model integration tests.
- `docs/`: architecture, direction-decision, and open-source guides.
- `app.py` / `transcribe.py` / `setup_asr.py`: application, WAV transcription, and model-setup entry points.
- `run.sh` / `test.sh` / `env.sh`: launch, test, and environment scripts.
- `config.json`: hardware, localization, VAD, ASR, and display settings.

Hardware basis: Quectel VA60X-GL User Manual V1.0.0 Preliminary (2026-03-06) plus the tested firmware's USB/ALSA behavior.
