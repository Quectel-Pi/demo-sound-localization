"""Unmixed ALSA capture with arecord; no Python audio binding required."""
import os
import select
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path
import numpy as np


def resolve_device(cfg, sound_root=Path('/sys/class/sound')):
    """Resolve a USB sound card by VID:PID so ALSA card-number changes are harmless."""
    configured = str(cfg.get('device', 'auto')).strip()
    if configured and configured != 'auto':
        return configured
    identity = str(cfg.get('usb_vid_pid', '')).lower().strip()
    if ':' not in identity:
        raise ValueError('device=auto requires usb_vid_pid in VID:PID form')
    wanted_vid, wanted_pid = identity.split(':', 1)
    matches = []
    for card in sound_root.glob('card[0-9]*'):
        try:
            card_number = int(card.name[4:])
            device_path = (card / 'device').resolve()
        except (OSError, ValueError):
            continue
        for parent in (device_path, *device_path.parents):
            try:
                vid = (parent / 'idVendor').read_text().strip().lower()
                pid = (parent / 'idProduct').read_text().strip().lower()
            except OSError:
                continue
            if (vid, pid) == (wanted_vid, wanted_pid):
                matches.append(card_number)
            break
    if not matches:
        raise RuntimeError(f'USB audio device {identity} not found; reconnect VA60X-GL and check /proc/asound/cards')
    if len(matches) > 1:
        raise RuntimeError(f'Multiple USB audio devices match {identity}: ALSA cards {matches}')
    return f'hw:{matches[0]},0'


class Capture:
    def __init__(self, cfg, wav_path=None):
        self.cfg = cfg
        self.process = None
        self.wav = None
        self.device = None
        self.stopped = threading.Event()
        self.error_log = tempfile.TemporaryFile()
        if wav_path:
            self.wav = wave.open(wav_path, 'rb')
            expected = (cfg['channels'], cfg['rate'], 2)
            actual = (self.wav.getnchannels(), self.wav.getframerate(), self.wav.getsampwidth())
            if actual != expected:
                self.close()
                raise ValueError(f'WAV must be {cfg["channels"]}-channel, {cfg["rate"]} Hz, 16-bit PCM')
        else:
            try:
                self.device = resolve_device(cfg)
                self.process = subprocess.Popen(['arecord', '-q', '-D', self.device, '-f',
                    'S16_LE', '-r', str(cfg['rate']), '-c', str(cfg['channels']), '-t', 'raw'],
                    stdout=subprocess.PIPE, stderr=self.error_log,
                    env=dict(os.environ, LC_ALL='C'))
            except Exception:
                self.close()
                raise

    def frames(self):
        n = self.cfg['frame_size']
        size = n*self.cfg['channels']*2
        if self.wav:
            while not self.stopped.is_set():
                chunk = self.wav.readframes(n)
                if len(chunk) < size:
                    return
                yield np.frombuffer(chunk, dtype='<i2').reshape(n, self.cfg['channels'])
            return
        buffer = bytearray()
        deadline = time.monotonic()+4
        while not self.stopped.is_set():
            readable, _, _ = select.select([self.process.stdout], [], [], 0.2)
            if not readable:
                if time.monotonic() > deadline:
                    raise RuntimeError('Audio capture timed out. Check USB connection and device availability')
                continue
            data = os.read(self.process.stdout.fileno(), max(4096, size-len(buffer)))
            if not data:
                self.process.wait()
                self.error_log.seek(0)
                error = self.error_log.read().decode(errors='replace').strip()
                if not self.stopped.is_set():
                    raise RuntimeError(error or 'Audio device disconnected')
                return
            deadline = time.monotonic()+4
            buffer.extend(data)
            while len(buffer) >= size:
                chunk = bytes(buffer[:size])
                del buffer[:size]
                yield np.frombuffer(chunk, dtype='<i2').reshape(n, self.cfg['channels'])

    def close(self):
        self.stopped.set()
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            self.process.stdout.close()
        if self.wav:
            self.wav.close()
        self.error_log.close()
