"""Unmixed ALSA capture with arecord; no Python audio binding required."""
import os
import select
import subprocess
import tempfile
import threading
import time
import wave
import numpy as np


class Capture:
    def __init__(self, cfg, wav_path=None):
        self.cfg = cfg
        self.process = None
        self.wav = None
        self.stopped = threading.Event()
        self.error_log = tempfile.TemporaryFile()
        if wav_path:
            self.wav = wave.open(wav_path, 'rb')
            if (self.wav.getnchannels(), self.wav.getframerate(), self.wav.getsampwidth()) != (8, 48000, 2):
                self.close()
                raise ValueError('WAV must be 8-channel, 48000 Hz, 16-bit PCM')
        else:
            try:
                self.process = subprocess.Popen(['arecord', '-q', '-D', cfg['device'], '-f',
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
                yield np.frombuffer(chunk, dtype='<i2').reshape(n, 8)
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
                yield np.frombuffer(chunk, dtype='<i2').reshape(n, 8)

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
