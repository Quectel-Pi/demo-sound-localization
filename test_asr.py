import json
import threading
import time
import unittest
import numpy as np
from asr import AsrService, Utterance, UtteranceSegmenter, validate_asr, format_transcript


class SegmenterTests(unittest.TestCase):
    def setUp(self):
        with open('config.json') as file:
            self.cfg = json.load(file)
        self.cfg.update(rate=1000, asr_pre_roll_seconds=0.3, asr_silence_seconds=0.8,
                        asr_min_speech_seconds=0.24, asr_max_seconds=3)

    def test_pre_roll_and_trailing_pause_keep_exact_audio(self):
        segmenter = UtteranceSegmenter(self.cfg)
        for i in range(5):
            segmenter.feed(np.full(100, i, dtype=np.int16), False)
        for i in range(3):
            self.assertEqual(segmenter.feed(np.full(100, 10+i, dtype=np.int16), True), [])
        for _ in range(7):
            self.assertEqual(segmenter.feed(np.zeros(100, dtype=np.int16), False), [])
        result = segmenter.feed(np.zeros(100, dtype=np.int16), False)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0].samples), 1400)
        self.assertEqual(result[0].samples[:300].tolist(), [2]*100+[3]*100+[4]*100)
        self.assertEqual(result[0].samples[300:600].tolist(), [10]*100+[11]*100+[12]*100)
        self.assertFalse(segmenter.recording)

    def test_internal_pause_does_not_cut_sentence(self):
        segmenter = UtteranceSegmenter(self.cfg)
        self.assertEqual(segmenter.feed(np.ones(300, dtype=np.int16), True), [])
        self.assertEqual(segmenter.feed(np.zeros(700, dtype=np.int16), False), [])
        self.assertEqual(segmenter.feed(np.ones(300, dtype=np.int16), True), [])
        result = segmenter.feed(np.zeros(800, dtype=np.int16), False)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0].samples), 2100)

    def test_short_noise_rejected_and_eof_keeps_last_word(self):
        segmenter = UtteranceSegmenter(self.cfg)
        segmenter.feed(np.ones(100, dtype=np.int16), True)
        self.assertEqual(segmenter.feed(np.zeros(800, dtype=np.int16), False), [])
        segmenter.feed(np.arange(300, dtype=np.int16), True)
        result = segmenter.finish()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].samples[-300:].tolist(), list(range(300)))
        self.assertEqual(segmenter.finish(), [])

    def test_long_speech_split_has_no_lost_or_duplicated_samples(self):
        segmenter = UtteranceSegmenter(self.cfg)
        original = np.arange(6800, dtype=np.int16)
        results = []
        for block in np.array_split(original, 17):
            results.extend(segmenter.feed(block, True))
        results.extend(segmenter.finish())
        self.assertEqual([len(item.samples) for item in results], [3000, 3000, 800])
        np.testing.assert_array_equal(np.concatenate([item.samples for item in results]), original)

    def test_reset_discards_old_sentence(self):
        segmenter = UtteranceSegmenter(self.cfg)
        segmenter.feed(np.ones(300, dtype=np.int16), True)
        segmenter.reset()
        self.assertEqual(segmenter.finish(), [])

    def test_invalid_segment_parameters(self):
        self.cfg['asr_silence_seconds'] = -1
        with self.assertRaises(ValueError):
            validate_asr(self.cfg)

    def direction(self, angle, confidence=1.0, active=True):
        return {'angle': angle, 'confidence': confidence, 'active': active}

    def test_circular_average_and_silence_do_not_change_direction(self):
        segmenter = UtteranceSegmenter(self.cfg)
        segmenter.feed(np.ones(300, dtype=np.int16), True, self.direction(358))
        segmenter.feed(np.ones(300, dtype=np.int16), True, self.direction(2))
        result = segmenter.feed(np.zeros(800, dtype=np.int16), False, self.direction(180))[0]
        error = abs((result.direction_deg+180) % 360-180)
        self.assertLess(error, 0.1)
        self.assertAlmostEqual(result.direction_seconds, 0.6)
        self.assertEqual(format_transcript('你好', result.direction_deg), '[Direction 000°] 你好')

    def test_low_confidence_outlier_has_less_weight(self):
        segmenter = UtteranceSegmenter(self.cfg)
        segmenter.feed(np.ones(300, dtype=np.int16), True, self.direction(60))
        segmenter.feed(np.ones(100, dtype=np.int16), True, self.direction(180, 0.1))
        result = segmenter.finish()[0]
        self.assertLess(abs(result.direction_deg-60), 3)

    def test_uncertain_if_missing_sparse_or_conflicting_directions(self):
        segmenter = UtteranceSegmenter(self.cfg)
        segmenter.feed(np.ones(300, dtype=np.int16), True)
        self.assertIsNone(segmenter.finish()[0].direction_deg)
        segmenter.feed(np.ones(1700, dtype=np.int16), True, self.direction(90, active=False))
        segmenter.feed(np.ones(300, dtype=np.int16), True, self.direction(60))
        self.assertIsNone(segmenter.finish()[0].direction_deg)
        segmenter.feed(np.ones(300, dtype=np.int16), True, self.direction(0))
        segmenter.feed(np.ones(300, dtype=np.int16), True, self.direction(180))
        self.assertIsNone(segmenter.finish()[0].direction_deg)
        self.assertEqual(format_transcript('你好', None), '[Direction unknown] 你好')

    def test_consecutive_sentences_do_not_share_directions(self):
        segmenter = UtteranceSegmenter(self.cfg)
        segmenter.feed(np.ones(300, dtype=np.int16), True, self.direction(40))
        first = segmenter.feed(np.zeros(800, dtype=np.int16), False)[0]
        segmenter.feed(np.ones(300, dtype=np.int16), True, self.direction(220))
        second = segmenter.finish()[0]
        self.assertAlmostEqual(first.direction_deg, 40)
        self.assertAlmostEqual(second.direction_deg, 220)

    def test_direction_observations_split_exactly_at_max_duration(self):
        segmenter = UtteranceSegmenter(self.cfg)
        segmenter.feed(np.ones(2800, dtype=np.int16), True, self.direction(0))
        first = segmenter.feed(np.ones(400, dtype=np.int16), True, self.direction(90))[0]
        segmenter.feed(np.ones(800, dtype=np.int16), True, self.direction(90))
        second = segmenter.finish()[0]
        self.assertAlmostEqual(first.direction_deg, np.degrees(np.arctan2(200, 2800)))
        self.assertAlmostEqual(first.direction_seconds, 3.0)
        self.assertAlmostEqual(second.direction_deg, 90)
        self.assertAlmostEqual(second.direction_seconds, 1.0)

    def test_sentence_direction_independent_of_arrow_display_gate(self):
        segmenter = UtteranceSegmenter(self.cfg)
        info = self.direction(60, active=False)
        info['sentence_direction_valid'] = True
        segmenter.feed(np.ones(300, dtype=np.int16), True, info)
        self.assertAlmostEqual(segmenter.finish()[0].direction_deg, 60)


class ServiceTests(unittest.TestCase):
    def wait_until(self, predicate, timeout=2):
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.005)
        self.fail('background operation did not complete')

    def test_loading_never_blocks_capture_and_queue_is_bounded(self):
        release = threading.Event()
        def factory(cfg):
            release.wait(2)
            return None
        service = AsrService({}, factory)
        try:
            utterance = Utterance(np.zeros(100, dtype=np.int16), 48000, 'test')
            start = time.monotonic()
            self.assertTrue(service.submit(utterance))
            self.assertTrue(service.submit(utterance))
            self.assertFalse(service.submit(utterance))
            self.assertLess(time.monotonic()-start, 0.1)
            self.assertTrue(any(event['kind'] == 'busy' for event in service.poll()))
        finally:
            release.set()
            service.close()

    def test_disable_suppresses_inflight_result(self):
        began, release = threading.Event(), threading.Event()
        class Engine:
            def recognize(self, utterance):
                began.set()
                release.wait(2)
                return {'text': 'stale', 'recognition_seconds': 0.1}
        service = AsrService({}, lambda cfg: Engine())
        try:
            service.submit(Utterance(np.zeros(100, dtype=np.int16), 48000, 'test'))
            self.assertTrue(began.wait(1))
            service.set_enabled(False)
            release.set()
            time.sleep(0.03)
            self.assertFalse(any(event['kind'] == 'result' for event in service.poll()))
            service.set_enabled(True)
            service.submit(Utterance(np.zeros(100, dtype=np.int16), 48000, 'test'))
            results = []
            def complete():
                results.extend(service.poll())
                return any(event['kind'] == 'result' for event in results)
            self.wait_until(complete)
        finally:
            release.set()
            service.close()

    def test_model_failure_is_reported(self):
        def factory(cfg):
            raise RuntimeError('missing model')
        service = AsrService({}, factory)
        try:
            self.wait_until(lambda: service.failed)
            errors = [event for event in service.poll() if event['kind'] == 'error']
            self.assertEqual(errors[0]['message'], 'missing model')
        finally:
            service.close()

    def test_delayed_recognition_keeps_each_sentences_direction(self):
        began, release = threading.Event(), threading.Event()
        class Engine:
            def recognize(self, utterance):
                began.set()
                release.wait(2)
                return {'text': '你好', 'recognition_seconds': 0.1}
        service = AsrService({}, lambda cfg: Engine())
        try:
            service.submit(Utterance(np.ones(300, dtype=np.int16), 1000, 'test', direction_deg=60))
            self.assertTrue(began.wait(1))
            service.submit(Utterance(np.ones(300, dtype=np.int16), 1000, 'test', direction_deg=240))
            release.set()
            results = []
            def complete():
                results.extend(event for event in service.poll() if event['kind'] == 'result')
                return len(results) == 2
            self.wait_until(complete)
            self.assertEqual([event['direction_deg'] for event in results], [60, 240])
        finally:
            release.set()
            service.close()


if __name__ == '__main__':
    unittest.main()
