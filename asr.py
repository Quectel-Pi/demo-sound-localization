"""Offline sentence ASR. Capture never waits for model loading or inference."""
from collections import deque
from dataclasses import dataclass
from pathlib import Path
import math
import queue
import re
import threading
import time
import numpy as np

ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = 'models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17'


def validate_asr(cfg):
    sector = cfg.get('direction_sector_deg', 30)
    if not isinstance(sector, int) or isinstance(sector, bool) or sector < 10 or 360 % sector or sector % 2:
        raise ValueError('direction_sector_deg must be an even divisor of 360, at least 10 degrees')
    if cfg.get('asr_channel', 0) not in range(cfg['channels']):
        raise ValueError(f'asr_channel must be in 0..{cfg["channels"]-1}')
    if cfg.get('asr_threads', 2) not in range(1, 9):
        raise ValueError('asr_threads must be in 1..8')
    pre = cfg.get('asr_pre_roll_seconds', 0.3)
    silence = cfg.get('asr_silence_seconds', 0.8)
    minimum = cfg.get('asr_min_speech_seconds', 0.24)
    maximum = cfg.get('asr_max_seconds', 15.0)
    if not (0 <= pre <= 1 and 0.2 <= silence <= 3 and 0.05 <= minimum <= 2 and 3 <= maximum <= 30):
        raise ValueError('Speech segmentation parameters out of range')
    if pre+silence+minimum >= maximum:
        raise ValueError('Maximum utterance length must exceed pre-roll, silence, and minimum speech duration')
    if not 0 <= cfg.get('asr_direction_min_seconds', 0.12) <= 2:
        raise ValueError('Minimum direction duration must be in 0..2 seconds')
    for key in ('asr_direction_min_coverage', 'asr_direction_min_consistency'):
        if not 0 <= cfg.get(key, 0.2 if key.endswith('coverage') else 0.6) <= 1:
            raise ValueError('Direction aggregation thresholds must be in 0..1')


@dataclass(frozen=True)
class Utterance:
    samples: np.ndarray
    sample_rate: int
    reason: str
    direction_deg: float | None = None
    direction_consistency: float = 0.0
    direction_seconds: float = 0.0

    def direction_info(self):
        return {'direction_deg': self.direction_deg,
                'direction_consistency': self.direction_consistency,
                'direction_seconds': self.direction_seconds}


def format_transcript(text, direction_deg):
    label = 'Direction unknown' if direction_deg is None else f'Direction {round(direction_deg) % 360:03d}°'
    return f'[{label}] {text}'


def direction_sector(angle, width=30):
    """Nearest fixed-width direction sector, represented by its center and half-width."""
    if angle is None:
        return None
    center = int(math.floor((angle % 360 + width/2) / width) * width) % 360
    return center, width//2


class UtteranceSegmenter:
    def __init__(self, cfg):
        validate_asr(cfg)
        self.rate = cfg['rate']
        self.pre_limit = round(cfg.get('asr_pre_roll_seconds', 0.3)*self.rate)
        self.silence_limit = round(cfg.get('asr_silence_seconds', 0.8)*self.rate)
        self.min_speech = round(cfg.get('asr_min_speech_seconds', 0.24)*self.rate)
        self.max_samples = round(cfg.get('asr_max_seconds', 15.0)*self.rate)
        self.direction_min_samples = round(cfg.get('asr_direction_min_seconds', 0.12)*self.rate)
        self.direction_min_coverage = cfg.get('asr_direction_min_coverage', 0.2)
        self.direction_min_consistency = cfg.get('asr_direction_min_consistency', 0.6)
        self.reset()

    def reset(self):
        self.pre = deque()
        self.pre_samples = 0
        self.parts = []
        self.total = self.voiced = self.silent = 0
        self.recording = False
        self.direction_spans = []
        self.speech_spans = []

    def _remember(self, samples):
        self.pre.append(samples)
        self.pre_samples += len(samples)
        while self.pre and self.pre_samples > self.pre_limit:
            excess = self.pre_samples-self.pre_limit
            first = self.pre.popleft()
            removed = min(excess, len(first))
            self.pre_samples -= removed
            if removed < len(first):
                self.pre.appendleft(first[removed:])

    def _speech_samples(self, limit):
        return sum(max(0, min(end, limit)-start) for start, end in self.speech_spans)

    def _direction_info(self, limit):
        sine = cosine = weight_sum = valid_samples = 0.0
        for start, end, angle, confidence in self.direction_spans:
            length = max(0, min(end, limit)-start)
            weight = length*confidence
            radians = math.radians(angle)
            sine += weight*math.sin(radians)
            cosine += weight*math.cos(radians)
            weight_sum += weight
            valid_samples += length
        consistency = min(1.0, math.hypot(sine, cosine)/weight_sum) if weight_sum else 0.0
        coverage = valid_samples/max(1, self._speech_samples(limit))
        known = (valid_samples > 0 and valid_samples >= self.direction_min_samples
                 and coverage >= self.direction_min_coverage
                 and consistency >= self.direction_min_consistency)
        angle = math.degrees(math.atan2(sine, cosine)) % 360 if known else None
        return {'direction_deg': angle, 'direction_consistency': consistency,
                'direction_seconds': valid_samples/self.rate}

    def feed(self, mono, speech, direction=None):
        samples = np.array(mono, dtype=np.int16, copy=True)
        if not len(samples):
            return []
        if not self.recording:
            if not speech:
                self._remember(samples)
                return []
            self.parts = list(self.pre)
            self.total = self.pre_samples
            self.pre.clear()
            self.pre_samples = 0
            self.recording = True
        if speech:
            self.speech_spans.append((self.total, self.total+len(samples)))
        if speech and direction and direction.get('sentence_direction_valid', direction.get('active')):
            angle = direction.get('angle')
            confidence = direction.get('confidence', 0.0)
            if (angle is not None and math.isfinite(angle) and math.isfinite(confidence)
                    and confidence > 0):
                self.direction_spans.append((self.total, self.total+len(samples),
                                             angle % 360, min(1.0, confidence)))
        self.parts.append(samples)
        self.total += len(samples)
        if speech:
            self.voiced += len(samples)
            self.silent = 0
        else:
            self.silent += len(samples)
        utterances = []
        while self.total >= self.max_samples:
            joined = np.concatenate(self.parts)
            if self._speech_samples(self.max_samples) >= self.min_speech:
                utterances.append(Utterance(joined[:self.max_samples], self.rate, 'max_duration',
                                             **self._direction_info(self.max_samples)))
            self.direction_spans = [(max(0, start-self.max_samples), end-self.max_samples, angle, confidence)
                                    for start, end, angle, confidence in self.direction_spans
                                    if end > self.max_samples]
            self.speech_spans = [(max(0, start-self.max_samples), end-self.max_samples)
                                 for start, end in self.speech_spans if end > self.max_samples]
            remainder = joined[self.max_samples:]
            self.parts = [remainder] if len(remainder) else []
            self.total = len(remainder)
            self.voiced = self._speech_samples(self.total)
            self.silent = 0 if speech else len(remainder)
            self.recording = bool(len(remainder))
        if self.recording and self.silent >= self.silence_limit:
            utterances.extend(self.finish('silence'))
        return utterances

    def finish(self, reason='end_of_input'):
        result = []
        if self.parts and self.voiced >= self.min_speech:
            result.append(Utterance(np.concatenate(self.parts), self.rate, reason,
                                    **self._direction_info(self.total)))
        self.reset()
        return result


class SenseVoiceRecognizer:
    def __init__(self, cfg):
        folder = Path(cfg.get('asr_model_dir', DEFAULT_MODEL))
        if not folder.is_absolute():
            folder = ROOT/folder
            if not folder.is_dir():
                legacy = ROOT.parent/'sound_loca_demo'/cfg.get('asr_model_dir', DEFAULT_MODEL)
                if legacy.is_dir():
                    folder = legacy
        model, tokens = folder/'model.int8.onnx', folder/'tokens.txt'
        if not model.is_file() or not tokens.is_file():
            raise RuntimeError('Speech model missing. Run python3 setup_asr.py')
        try:
            import sherpa_onnx
        except ImportError as exc:
            raise RuntimeError('Recognition dependency missing. Install requirements-asr.txt in the project virtual environment') from exc
        self.engine = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(model), tokens=str(tokens), num_threads=cfg.get('asr_threads', 2),
            language=cfg.get('asr_language', 'auto'), use_itn=True, debug=False, provider='cpu')

    def recognize(self, utterance):
        start = time.monotonic()
        stream = self.engine.create_stream()
        normalized = utterance.samples.astype(np.float32)/32768.0
        # sherpa-onnx resamples accepted input to the model's 16 kHz feature rate.
        stream.accept_waveform(utterance.sample_rate, normalized)
        self.engine.decode_stream(stream)
        text = re.sub(r'<\|[^|]+\|>', '', stream.result.text).strip()
        return {'text': text, 'audio_seconds': len(normalized)/utterance.sample_rate,
                'recognition_seconds': time.monotonic()-start, 'reason': utterance.reason,
                **utterance.direction_info()}


class AsrService:
    def __init__(self, cfg, factory=SenseVoiceRecognizer):
        self.cfg = cfg
        self.factory = factory
        self.jobs = queue.Queue(maxsize=2)
        self.events = queue.Queue(maxsize=64)
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.enabled = True
        self.epoch = 0
        self.ready = False
        self.failed = False
        self.sequence = 0
        self.thread = threading.Thread(target=self._work, daemon=True, name='sentence-asr')
        self.thread.start()

    def _emit(self, event):
        try:
            self.events.put_nowait(event)
        except queue.Full:
            try:
                self.events.get_nowait()
            except queue.Empty:
                pass
            self.events.put_nowait(event)

    def set_enabled(self, enabled):
        with self.lock:
            if self.enabled == enabled:
                return
            self.enabled = enabled
            self.epoch += 1
            while True:
                try:
                    self.jobs.get_nowait()
                except queue.Empty:
                    break

    def submit(self, utterance):
        with self.lock:
            if not self.enabled or self.failed or self.stop.is_set():
                return False
            self.sequence += 1
            sequence, epoch = self.sequence, self.epoch
            try:
                self.jobs.put_nowait((epoch, sequence, utterance))
            except queue.Full:
                self._emit({'kind': 'busy', 'message': 'Recognition busy; one segment skipped', 'epoch': epoch})
                return False
            self._emit({'kind': 'queued', 'sequence': sequence, 'epoch': epoch})
            return True

    def _work(self):
        self._emit({'kind': 'loading', 'message': 'Loading offline speech model…'})
        try:
            engine = self.factory(self.cfg)
            self.ready = True
            self._emit({'kind': 'ready', 'message': 'Ready. Speak to begin.'})
        except Exception as exc:
            self.failed = True
            self._emit({'kind': 'error', 'message': str(exc)})
            return
        while not self.stop.is_set():
            try:
                epoch, sequence, utterance = self.jobs.get(timeout=0.1)
            except queue.Empty:
                continue
            with self.lock:
                valid = self.enabled and epoch == self.epoch
            if not valid:
                continue
            self._emit({'kind': 'recognizing', 'sequence': sequence, 'epoch': epoch})
            try:
                result = engine.recognize(utterance)
                result.update(kind='result', sequence=sequence, epoch=epoch, **utterance.direction_info())
            except Exception as exc:
                result = {'kind': 'error', 'message': str(exc), 'epoch': epoch, 'sequence': sequence}
            with self.lock:
                if self.enabled and epoch == self.epoch and not self.stop.is_set():
                    self._emit(result)

    def poll(self):
        result = []
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            if 'epoch' not in event or event['epoch'] == self.epoch:
                result.append(event)
        return result

    def close(self):
        self.stop.set()
        self.set_enabled(False)
        self.thread.join(timeout=2)
