#!/usr/bin/env python3
"""Sound Direction: local desktop direction and speech visualizer for VA60X-GL."""
import argparse
import json
import math
from pathlib import Path
import queue
import sys
import threading
import time

try:
    import numpy as np
except ImportError:
    raise SystemExit('NumPy missing. Debian: sudo apt install python3-numpy python3-tk alsa-utils; then bash run.sh')
from audio import Capture
from localization import Tracker, validate
from speech import Pipeline
from asr import AsrService, UtteranceSegmenter, validate_asr
from i18n import translate


def synthetic(cfg, angle, seed=7, amplitude=0.13):
    """Independent far-field fixture with sub-sample delays and noise."""
    rng = np.random.default_rng(seed)
    n = cfg['frame_size']
    frequencies = np.fft.rfftfreq(n, 1/cfg['rate'])
    base = np.fft.rfft(rng.normal(size=n))
    base[(frequencies < 300) | (frequencies > 3500)] = 0
    source = np.fft.irfft(base, n=n)
    base *= amplitude/max(float(np.std(source)), 1e-9)
    phi = np.arange(6)*np.pi/3
    positions = cfg['radius_m']*np.column_stack((np.sin(phi), np.cos(phi)))
    u = np.array([math.sin(math.radians(angle)), math.cos(math.radians(angle))])
    delays = -positions @ u / 343.0
    pcm = np.zeros((n, cfg['channels']))
    for i, channel in enumerate(cfg['mic_channels']):
        pcm[:, channel] = np.fft.irfft(base*np.exp(-2j*np.pi*frequencies*delays[i]), n=n)
    pcm += rng.normal(scale=0.001, size=pcm.shape)
    return np.clip(pcm*32768, -32768, 32767).astype('<i2')


def probe(cfg, seconds, wav_path):
    localizer = Pipeline(cfg)
    capture = Capture(cfg, wav_path)
    start = time.monotonic()
    count = 0
    maximum = -180.0
    last = None
    squares = np.zeros(cfg['channels'])
    clips = np.zeros(cfg['channels'], dtype=int)
    total = 0
    active_count = 0
    speech_count = 0
    direction_count = 0
    effective_gate = cfg['gate_dbfs']
    try:
        for pcm in capture.frames():
            last = localizer.process(pcm)
            count += 1
            active_count += int(last['active'])
            speech_count += int(last.get('speech') is True)
            direction_count += int(last.get('sentence_direction_valid', False))
            effective_gate = last.get('effective_gate_dbfs', cfg['gate_dbfs'])
            maximum = max(maximum, last['dbfs'])
            squares += np.sum((pcm.astype(float)/32768)**2, axis=0)
            clips += np.sum(np.abs(pcm.astype(int)) >= 32760, axis=0)
            total += len(pcm)
            if (not wav_path and time.monotonic()-start >= seconds) or (wav_path and total >= seconds*cfg['rate']):
                break
    finally:
        capture.close()
    if not count:
        raise RuntimeError('No complete audio block received')
    rms = np.sqrt(squares/total)
    print(json.dumps({'device': capture.device or str(wav_path), 'frames': count, 'audio_seconds': total/cfg['rate'],
        'max_dbfs': maximum, 'channel_rms': rms.tolist(),
        'channel_dbfs': (20*np.log10(np.maximum(rms, 1e-9))).tolist(),
        'channel_clipped_samples': clips.tolist(), 'active_frames': active_count,
        'last_angle': last['angle'], 'last_confidence': last['confidence'],
        'vad_enabled': bool(cfg.get('vad_enabled', False)), 'speech_frames': speech_count,
        'sentence_direction_frames': direction_count, 'effective_gate_dbfs': effective_gate,
        'last_snr_db': last.get('snr_db')}, ensure_ascii=False, indent=2))


class Application:
    def __init__(self, tk, cfg, args):
        self.tk = tk
        self.cfg, self.args = dict(cfg), args
        cfg = self.cfg
        cfg.update(vad_enabled=not (args.demo or args.no_vad),
                   asr_enabled=not (args.demo or args.no_asr))
        self.root = tk.Tk()
        self.language = cfg.get('ui_language', 'zh')
        self.root.title(self.tr('title'))
        self.root.geometry('1120x800')
        self.root.minsize(900, 700)
        self.root.configure(bg='#070B14')
        self.queue = queue.Queue(maxsize=2)
        self.stop = threading.Event()
        self.run_id = 0
        self.retry_pending = False
        self.closing = False
        self.capture = None
        self.tracker = Tracker(cfg['hold_seconds'])
        self.latest = {'dbfs': -90, 'confidence': 0, 'active': False, 'angle': None, 'rms': [0]*6}
        self.error = None
        self.done = False
        self.last_result = -1e9
        self.display_angle = 0.0
        self.alive = False
        self.gate = tk.DoubleVar(value=cfg['gate_dbfs'])
        self.asr_service = None
        self.asr_recording = False
        self.asr_message_key = 'asr_demo' if args.demo else ('asr_disabled' if not cfg['asr_enabled'] else 'asr_loading')
        self.asr_result_seconds = 0.0
        self.asr_error = None
        self.asr_pending = set()
        self.transcripts = []
        from neon_ui import CyberpunkView
        self.view = CyberpunkView(self)
        if cfg['asr_enabled']:
            self.asr_service = AsrService(dict(cfg))
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.start_capture()
        self.root.after(30, self.tick)
        if args.smoke_seconds:
            self.root.after(int(args.smoke_seconds*1000), self.close)

    def tr(self, key, **values):
        return translate(self.language, key, **values)

    def set_language(self):
        self.language = 'en' if self.language == 'zh' else 'zh'
        self.cfg['ui_language'] = self.language
        self.root.title(self.tr('title'))
        self.view.set_language()
        self.render_transcripts()
        self.update_asr_label()

    def start_capture(self):
        self.run_id += 1
        self.stop = threading.Event()
        self.error = None
        self.done = False
        self.retry_pending = False
        self.capture = None
        self.asr_recording = False
        self.last_result = -1e9
        self.alive = False
        self.tracker = Tracker(self.cfg['hold_seconds'])
        self.latest = {'dbfs': -90, 'confidence': 0, 'active': False, 'angle': None, 'rms': [0]*6}
        if self.asr_service:
            self.asr_service.set_enabled(True)
        self.worker = threading.Thread(target=self.work, args=(self.run_id, self.stop), daemon=True)
        self.worker.start()

    def retry_device(self):
        if self.args.demo or self.args.wav:
            self.view.notify(self.tr('retry_unavailable'), error=True)
            return
        if self.retry_pending:
            return
        self.retry_pending = True
        self.stop.set()
        self.error = None
        self.done = False
        self.asr_recording = False
        self.asr_pending.clear()
        if self.asr_service:
            self.asr_service.set_enabled(False)
        self.view.notify(self.tr('retrying'))

    def put(self, value, run_id):
        value = dict(value, _run_id=run_id)
        try:
            self.queue.put_nowait(value)
        except queue.Full:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                pass
            self.queue.put_nowait(value)

    def work(self, run_id, stop):
        capture = None
        try:
            localizer = Pipeline(self.cfg)
            segmenter = UtteranceSegmenter(self.cfg)
            if self.args.demo:
                step = 0
                while not stop.is_set():
                    angle = (step*1.8) % 360
                    amplitude = 0.13 if step % 180 < 130 else 0.0001
                    pcm = synthetic(self.cfg, angle, seed=step, amplitude=amplitude)
                    self.put(localizer.process(pcm), run_id)
                    step += 1
                    stop.wait(self.cfg['frame_size']/self.cfg['rate'])
            else:
                capture = Capture(self.cfg, self.args.wav)
                self.capture = capture
                for pcm in capture.frames():
                    if stop.is_set():
                        break
                    result = localizer.process(pcm)
                    if self.asr_service:
                        mono = pcm[:, self.cfg.get('asr_channel', 0)]
                        for utterance in segmenter.feed(mono, result.get('speech_ratio', 0) >= 0.5, result):
                            self.asr_service.submit(utterance)
                        self.asr_recording = segmenter.recording
                    self.put(result, run_id)
                    if self.args.wav:
                        stop.wait(self.cfg['frame_size']/self.cfg['rate'])
                if self.asr_service and not stop.is_set():
                    for utterance in segmenter.finish():
                        self.asr_service.submit(utterance)
                self.asr_recording = False
                if not stop.is_set():
                    self.put({'done': True}, run_id)
        except Exception as exc:
            if not stop.is_set():
                self.put({'error': str(exc)}, run_id)
        finally:
            if capture:
                capture.close()

    def save(self):
        try:
            path = Path(self.args.config)
            saved = json.loads(path.read_text())
            saved['gate_dbfs'] = float(self.gate.get())
            saved['ui_language'] = self.language
            validate(saved)
            temp = path.with_suffix('.json.tmp')
            temp.write_text(json.dumps(saved, ensure_ascii=False, indent=2)+'\n')
            temp.replace(path)
            self.view.notify(self.tr('saved'))
        except (ValueError, OSError, self.tk.TclError) as exc:
            self.view.notify(self.tr('save_failed', error=exc), error=True)

    def tick(self):
        try:
            self.cfg['gate_dbfs'] = float(self.gate.get())
        except (ValueError, self.tk.TclError):
            pass
        now = time.monotonic()
        while True:
            try:
                value = self.queue.get_nowait()
            except queue.Empty:
                break
            if value['_run_id'] != self.run_id:
                continue
            if 'error' in value:
                self.error = value['error']
            elif 'done' in value:
                self.done = True
            else:
                self.latest = value
                self.last_result = now
                self.display_angle, _ = self.tracker.update(value, now)
        if self.retry_pending and not self.worker.is_alive():
            self.start_capture()
        self.alive = self.direction_visible(now)
        self.draw(now)
        self.poll_asr()
        self.root.after(33, self.tick)

    def direction_visible(self, now):
        # Keep Tracker's angle smoothing, but do not keep its old arrow on screen
        # after the latest VAD result says speech has ended.
        freshness = max(0.2, self.cfg['hold_seconds'])
        if self.error or self.done or now-self.last_result > freshness:
            return False
        if self.cfg.get('vad_enabled', False):
            return (self.latest.get('speech') is True and self.latest.get('active') is True
                    and self.latest.get('angle') is not None
                    and self.tracker.pending_angle is None)
        # Synthetic demo and explicit --no-vad retain their existing behaviour.
        return now-self.tracker.last_active < self.cfg['hold_seconds']

    def clear_transcripts(self):
        self.transcripts.clear()
        self.render_transcripts()

    def copy_transcripts(self):
        if self.transcripts:
            self.root.clipboard_clear()
            self.root.clipboard_append('\n'.join(self.transcript_lines()))

    def transcript_lines(self):
        return [f'[{self.tr("direction_unknown") if direction is None else self.tr("direction_value", angle=round(direction) % 360)}] {text}'
                for text, direction in self.transcripts]

    def render_transcripts(self):
        widget = self.transcript_text
        widget.configure(state='normal', fg='#DEECF7' if self.transcripts else '#809AAF')
        widget.delete('1.0', 'end')
        widget.insert('end', '\n'.join(self.transcript_lines()) if self.transcripts else
                      self.tr('waiting_transcript'))
        widget.configure(state='disabled')
        widget.see('end')

    def poll_asr(self):
        if self.asr_service:
            for event in self.asr_service.poll():
                kind = event['kind']
                if kind == 'queued':
                    self.asr_pending.add(event['sequence'])
                elif kind == 'result':
                    self.asr_pending.discard(event['sequence'])
                    self.asr_error = None
                    if event['text']:
                        self.transcripts.append((event['text'], event.get('direction_deg')))
                        self.transcripts = self.transcripts[-20:]
                        self.render_transcripts()
                        self.asr_message_key = 'asr_result'
                        self.asr_result_seconds = event['recognition_seconds']
                    else:
                        self.asr_message_key = 'asr_empty'
                elif kind == 'error':
                    self.asr_error = event['message']
                    if 'sequence' in event:
                        self.asr_pending.discard(event['sequence'])
                    else:
                        self.asr_pending.clear()
                elif kind in ('loading', 'ready', 'busy'):
                    self.asr_message_key = 'asr_'+kind
        self.update_asr_label()

    def update_asr_label(self):
        message, color = self.tr(self.asr_message_key, seconds=self.asr_result_seconds), '#40F2FF'
        if self.asr_error:
            message, color = self.tr('asr_error', error=self.asr_error), '#FF7488'
        elif self.asr_recording:
            message = self.tr('listening')
        elif self.asr_pending:
            message = self.tr('transcribing')
        self.asr_label.configure(text=message, fg=color)

    def draw(self, now):
        self.view.render()

    def close(self):
        self.closing = True
        self.retry_pending = False
        self.stop.set()
        # Capture select has a short timeout; worker owns and closes its resources.
        self.worker.join(timeout=3)
        if self.asr_service:
            self.asr_service.close()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
        if self.error:
            print('Capture failed: '+self.error, file=sys.stderr)
            return 1
        return 0


def main():
    parser = argparse.ArgumentParser(description='Quectel VA60X-GL voice direction and offline transcription')
    parser.add_argument('--config', default='config.json')
    parser.add_argument('--device', help='ALSA hardware device override, e.g. hw:3,0')
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument('--demo', action='store_true', help='Synthetic audio demo')
    sources.add_argument('--wav', help='Replay an 8-channel PCM WAV file')
    parser.add_argument('--probe', action='store_true', help='Headless capture diagnostics as JSON')
    parser.add_argument('--no-vad', action='store_true', help='Disable WebRTC voice filtering')
    parser.add_argument('--no-asr', action='store_true', help='Disable offline speech transcription')
    parser.add_argument('--seconds', type=float, default=5)
    parser.add_argument('--smoke-seconds', type=float, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        cfg = json.loads(Path(args.config).read_text())
        if args.device:
            cfg['device'] = args.device
        # Probe mode diagnoses raw capture and localization without optional VAD/ASR packages.
        cfg.update(vad_enabled=not (args.demo or args.probe or args.no_vad),
                   asr_enabled=not (args.demo or args.probe or args.no_asr))
        validate(cfg)
        validate_asr(cfg)
        if cfg.get('ui_language', 'zh') not in ('zh', 'en'):
            raise ValueError('ui_language must be zh or en')
        if args.seconds <= 0:
            raise ValueError('seconds must be positive')
        if args.probe:
            if args.demo:
                raise ValueError('--probe requires live audio or WAV; incompatible with --demo')
            probe(cfg, args.seconds, args.wav)
            return 0
        try:
            import tkinter as tk
        except ImportError:
            raise RuntimeError('Tk missing: sudo apt install python3-tk; use --probe without a display')
        try:
            return Application(tk, cfg, args).run()
        except tk.TclError as exc:
            raise RuntimeError(f'Unable to open window: {exc}; run on a graphical desktop or use --probe')
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        print(f'Startup failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
