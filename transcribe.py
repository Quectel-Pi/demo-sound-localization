#!/usr/bin/env python3
"""Repeatable offline transcription of PCM WAV, without a desktop or microphone."""
import argparse
import json
from pathlib import Path
import sys
import time
import wave
import numpy as np
from asr import SenseVoiceRecognizer, Utterance, UtteranceSegmenter, validate_asr
from speech import SpeechDetector


def transcribe_file(path, cfg, channel=0, segmented=False):
    validate_asr(cfg)
    with wave.open(str(path), 'rb') as audio:
        rate, channels = audio.getframerate(), audio.getnchannels()
        if audio.getsampwidth() != 2 or audio.getcomptype() != 'NONE':
            raise ValueError('WAV 必须是 16 位 PCM')
        if channel not in range(channels):
            raise ValueError(f'通道必须为 0..{channels-1}')
        if segmented and rate not in (8000, 16000, 32000, 48000):
            raise ValueError('自动分句支持 8/16/32/48 kHz WAV')
        if not segmented and audio.getnframes()/rate > 30:
            raise ValueError('超过 30 秒的录音请使用 --segment 自动分句')
        start = time.monotonic()
        recognizer = SenseVoiceRecognizer(cfg)
        initialization = time.monotonic()-start
        results = []
        if not segmented:
            pcm = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2').reshape(-1, channels)
            if len(pcm):
                results.append(recognizer.recognize(Utterance(pcm[:, channel], rate, 'file')))
        else:
            local_cfg = dict(cfg, rate=rate, vad_channel=0)
            detector = SpeechDetector(local_cfg)
            segmenter = UtteranceSegmenter(local_cfg)
            while True:
                data = audio.readframes(rate*20//1000)
                if not data:
                    break
                mono = np.frombuffer(data, dtype='<i2').reshape(-1, channels)[:, channel]
                decision = detector.process(mono[:, None])
                for utterance in segmenter.feed(mono, decision['speech_ratio'] >= 0.5):
                    results.append(recognizer.recognize(utterance))
            for utterance in segmenter.finish():
                results.append(recognizer.recognize(utterance))
    return {'text': '\n'.join(result['text'] for result in results if result['text']),
            'segments': results, 'model_initialization_seconds': initialization,
            'sample_rate': rate, 'channel': channel}


def main():
    parser = argparse.ArgumentParser(description='离线 WAV 语音识别验证')
    parser.add_argument('--file', required=True)
    parser.add_argument('--config', default=str(Path(__file__).with_name('config.json')))
    parser.add_argument('--channel', type=int, default=0)
    parser.add_argument('--segment', action='store_true', help='使用 VAD 分句，支持长录音')
    args = parser.parse_args()
    try:
        cfg = json.loads(Path(args.config).read_text())
        result = transcribe_file(args.file, cfg, args.channel, args.segment)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, wave.Error) as exc:
        print('识别失败：'+str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
