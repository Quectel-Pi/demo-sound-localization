"""Real-model checks run when the optional local model is installed."""
import importlib.util
import json
from pathlib import Path
import unittest
from sound_direction.asr import DEFAULT_MODEL
from transcribe import transcribe_file


class RealModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = Path(DEFAULT_MODEL)/'test_wavs/zh.wav'
        if not cls.fixture.is_file():
            cls.fixture = Path('../sound_loca_demo')/DEFAULT_MODEL/'test_wavs/zh.wav'
        if not cls.fixture.is_file() or importlib.util.find_spec('sherpa_onnx') is None:
            raise unittest.SkipTest('optional SenseVoice model/dependency not installed')
        with open('config.json') as file:
            cls.cfg = json.load(file)

    def assert_chinese_sentence(self, result):
        self.assertIn('时间', result['text'])
        self.assertIn('9点', result['text'])
        self.assertIn('5点', result['text'])
        self.assertGreater(sum(segment['audio_seconds'] for segment in result['segments']), 5)

    def test_official_chinese_recording(self):
        self.assert_chinese_sentence(transcribe_file(self.fixture, self.cfg))

    def test_vad_segmentation_preserves_final_sentence_at_eof(self):
        # Keep this fixture in one segment so this test exercises EOF flushing,
        # independently of the application's current five-second split setting.
        # Use the reference VAD sensitivity for this EOF test; mode 3 trims
        # more of this sample and changes its retained audio duration.
        result = transcribe_file(self.fixture, dict(self.cfg, asr_max_seconds=15, vad_mode=2), segmented=True)
        self.assert_chinese_sentence(result)
        self.assertEqual(result['segments'][-1]['reason'], 'end_of_input')
