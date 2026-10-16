#!/usr/bin/env python3
"""Sound Direction: local desktop direction and speech visualizer for MA-USB8."""
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
from asr import AsrService, UtteranceSegmenter, validate_asr, format_transcript


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
    pcm = np.zeros((n, 8))
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
    squares = np.zeros(8)
    clips = np.zeros(8, dtype=int)
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
    print(json.dumps({'device': cfg['device'], 'frames': count, 'audio_seconds': total/cfg['rate'],
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
        cfg.update(vad_enabled=not args.demo, asr_enabled=not args.demo)
        self.root = tk.Tk()
        self.root.title('Sound Direction')
        self.root.geometry('1120x800')
        self.root.minsize(900, 700)
        self.root.configure(bg='#070B14')
        self.queue = queue.Queue(maxsize=2)
        self.stop = threading.Event()
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
        self.asr_message = 'Transcription disabled in demo mode' if args.demo else 'Loading offline speech model…'
        self.asr_error = None
        self.asr_pending = set()
        self.transcripts = []
        from neon_ui import CyberpunkView
        self.view = CyberpunkView(self)
        if cfg['asr_enabled']:
            self.asr_service = AsrService(dict(cfg))
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.worker = threading.Thread(target=self.work, daemon=True)
        self.worker.start()
        self.root.after(30, self.tick)
        if args.smoke_seconds:
            self.root.after(int(args.smoke_seconds*1000), self.close)

    def put(self, value):
        try:
            self.queue.put_nowait(value)
        except queue.Full:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                pass
            self.queue.put_nowait(value)

    def work(self):
        try:
            localizer = Pipeline(self.cfg)
            segmenter = UtteranceSegmenter(self.cfg)
            if self.args.demo:
                step = 0
                while not self.stop.is_set():
                    angle = (step*1.8) % 360
                    amplitude = 0.13 if step % 180 < 130 else 0.0001
                    pcm = synthetic(self.cfg, angle, seed=step, amplitude=amplitude)
                    self.put(localizer.process(pcm))
                    step += 1
                    self.stop.wait(self.cfg['frame_size']/self.cfg['rate'])
            else:
                self.capture = Capture(self.cfg, self.args.wav)
                for pcm in self.capture.frames():
                    if self.stop.is_set():
                        break
                    result = localizer.process(pcm)
                    if self.asr_service:
                        mono = pcm[:, self.cfg.get('asr_channel', 0)]
                        for utterance in segmenter.feed(mono, result.get('speech_ratio', 0) >= 0.5, result):
                            self.asr_service.submit(utterance)
                        self.asr_recording = segmenter.recording
                    self.put(result)
                    if self.args.wav:
                        self.stop.wait(self.cfg['frame_size']/self.cfg['rate'])
                if self.asr_service:
                    for utterance in segmenter.finish():
                        self.asr_service.submit(utterance)
                self.asr_recording = False
                self.put({'done': True})
        except Exception as exc:
            self.put({'error': str(exc)})
        finally:
            if self.capture:
                self.capture.close()

    def save(self):
        try:
            path = Path(self.args.config)
            saved = json.loads(path.read_text())
            saved['gate_dbfs'] = float(self.gate.get())
            validate(saved)
            temp = path.with_suffix('.json.tmp')
            temp.write_text(json.dumps(saved, ensure_ascii=False, indent=2)+'\n')
            temp.replace(path)
            self.view.notify('Threshold saved.')
        except (ValueError, OSError, self.tk.TclError) as exc:
            self.view.notify(f'Save failed: {exc}', error=True)

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
            if 'error' in value:
                self.error = value['error']
            elif 'done' in value:
                self.done = True
            else:
                self.latest = value
                self.last_result = now
                self.display_angle, self.alive = self.tracker.update(value, now)
        if now-self.last_result > self.cfg['hold_seconds'] or self.error or self.done:
            self.alive = False
        else:
            self.alive = now-self.tracker.last_active < self.cfg['hold_seconds']
        self.draw(now)
        self.poll_asr()
        self.root.after(33, self.tick)

    def clear_transcripts(self):
        self.transcripts.clear()
        self.render_transcripts()

    def copy_transcripts(self):
        if self.transcripts:
            self.root.clipboard_clear()
            self.root.clipboard_append('\n'.join(self.transcripts))

    def render_transcripts(self):
        widget = self.transcript_text
        widget.configure(state='normal', fg='#DEECF7' if self.transcripts else '#809AAF')
        widget.delete('1.0', 'end')
        widget.insert('end', '\n'.join(self.transcripts) if self.transcripts else
                      'Waiting for speech…')
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
                        self.transcripts.append(format_transcript(event['text'], event.get('direction_deg')))
                        self.transcripts = self.transcripts[-20:]
                        self.render_transcripts()
                        self.asr_message = f'Transcribed / {event["recognition_seconds"]:.2f} s'
                    else:
                        self.asr_message = 'No text detected. Please speak clearly.'
                elif kind == 'error':
                    self.asr_error = event['message']
                    if 'sequence' in event:
                        self.asr_pending.discard(event['sequence'])
                    else:
                        self.asr_pending.clear()
                elif kind in ('loading', 'ready', 'busy'):
                    self.asr_message = event['message']
        message, color = self.asr_message, '#40F2FF'
        if self.asr_error:
            message, color = 'Recognition error: '+self.asr_error, '#FF7488'
        elif self.asr_recording:
            message = 'Listening…'
        elif self.asr_pending:
            message = 'Transcribing…'
        self.asr_label.configure(text=message, fg=color)

    def draw(self, now):
        self.view.render()

    def close(self):
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
    parser = argparse.ArgumentParser(description='Sipeed MA-USB8 voice direction and offline transcription')
    parser.add_argument('--config', default='config.json')
    parser.add_argument('--device', help='ALSA hardware device, e.g. hw:MicArray,0')
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument('--demo', action='store_true', help='Synthetic audio demo')
    sources.add_argument('--wav', help='Replay an 8-channel PCM WAV file')
    parser.add_argument('--probe', action='store_true', help='Headless capture diagnostics as JSON')
    parser.add_argument('--seconds', type=float, default=5)
    parser.add_argument('--smoke-seconds', type=float, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        cfg = json.loads(Path(args.config).read_text())
        if args.device:
            cfg['device'] = args.device
        cfg.update(vad_enabled=not args.demo, asr_enabled=not (args.demo or args.probe))
        validate(cfg)
        validate_asr(cfg)
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
