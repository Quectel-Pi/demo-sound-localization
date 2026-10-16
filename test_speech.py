import json
import unittest
import numpy as np
from app import synthetic
from speech import SpeechDetector, ArraySpeechDetector, Pipeline


class FakeVAD:
    def __init__(self, positives):
        self.positives = iter(positives)
        self.frames = []

    def set_mode(self, mode):
        self.mode = mode

    def is_speech(self, frame, rate):
        assert len(frame) == 1920 and rate == 48000
        self.frames.append(frame)
        return next(self.positives)


class SpeechTests(unittest.TestCase):
    def setUp(self):
        with open('config.json') as file:
            self.cfg = json.load(file)
        self.cfg.update(vad_enabled=True, vad_mode=2, gate_dbfs=-43)

    def test_stream_alignment_and_channel(self):
        fake = FakeVAD([False]*30)
        detector = SpeechDetector(self.cfg, fake)
        stream = np.arange(2048*4*8, dtype=np.int16).reshape(-1, 8)
        for block in np.split(stream, 4):
            detector.process(block)
        consumed = b''.join(fake.frames)
        expected = stream[:960*8, 0].astype('<i2').tobytes()
        self.assertEqual(consumed, expected)
        self.assertEqual(bytes(detector.buffer), stream[960*8:, 0].astype('<i2').tobytes())

    def test_onset_and_release(self):
        detector = SpeechDetector(self.cfg, FakeVAD([True, True]+[False]*10))
        one = np.zeros((960, 8), dtype=np.int16)
        self.assertFalse(detector.process(one)['speech'])
        self.assertTrue(detector.process(one)['speech'])
        for _ in range(9):
            self.assertTrue(detector.process(one)['speech'])
        self.assertFalse(detector.process(one)['speech'])

    def test_voice_gate_keeps_direction_but_rejects_animation(self):
        self.cfg['vad_enabled'] = False
        pipeline = Pipeline(self.cfg)
        pcm = synthetic(self.cfg, 80)
        sound = pipeline.process(pcm)
        self.assertTrue(sound['active'])
        self.cfg['vad_enabled'] = True
        pipeline.detector = SpeechDetector(self.cfg, FakeVAD([False]*10))
        voice = pipeline.process(pcm)
        self.assertEqual(sound['angle'], voice['angle'])
        self.assertFalse(voice['active'])
        self.assertFalse(voice['speech'])

    def test_real_engine_silence(self):
        try:
            import webrtcvad
        except ImportError:
            self.skipTest('WebRTC VAD dependency unavailable')
        detector = SpeechDetector(self.cfg)
        for _ in range(30):
            result = detector.process(np.zeros((2048, 8), dtype=np.int16))
            self.assertFalse(result['speech'])

    def test_asr_keeps_speech_when_localization_gate_rejects_sound(self):
        self.cfg.update(vad_enabled=False, asr_enabled=True, gate_dbfs=-5)
        pipeline = Pipeline(self.cfg)
        pipeline.detector = SpeechDetector(self.cfg, FakeVAD([True]*10))
        result = pipeline.process(synthetic(self.cfg, 80))
        self.assertFalse(result['active'])
        self.assertTrue(result['speech'])
        self.assertEqual(result['speech_ratio'], 1.0)

    def test_quiet_speech_survives_high_manual_gate(self):
        self.cfg.update(vad_enabled=True, gate_dbfs=-20)
        pipeline = Pipeline(self.cfg)
        pipeline.detector = SpeechDetector(self.cfg, FakeVAD([True]*10))
        result = pipeline.process(synthetic(self.cfg, 60, amplitude=0.01))
        self.assertLess(result['dbfs'], self.cfg['gate_dbfs'])
        self.assertTrue(result['active'])
        self.assertTrue(result['sentence_direction_valid'])
        self.assertLess(abs(result['angle']-60), 4)

    def test_non_speech_does_not_get_human_gate_bypass(self):
        self.cfg.update(vad_enabled=True, gate_dbfs=-20)
        pipeline = Pipeline(self.cfg)
        pipeline.detector = SpeechDetector(self.cfg, FakeVAD([False]*10))
        result = pipeline.process(synthetic(self.cfg, 60, amplitude=0.01))
        self.assertFalse(result['active'])
        self.assertFalse(result['sentence_direction_valid'])

    def test_one_false_positive_microphone_does_not_trigger_speech(self):
        array = ArraySpeechDetector(self.cfg)
        class Detector:
            def __init__(self, speech):
                self.cfg = {}
                self.speech = speech
            def process(self, pcm):
                return {'speech': self.speech, 'speech_ratio': float(self.speech)}
        array.detectors = [Detector(True), Detector(False), Detector(False)]
        self.assertFalse(array.process(np.zeros((2048, 8), dtype=np.int16))['speech'])
        array.detectors = [Detector(True), Detector(False), Detector(True)]
        self.assertTrue(array.process(np.zeros((2048, 8), dtype=np.int16))['speech'])


if __name__ == '__main__':
    unittest.main()
