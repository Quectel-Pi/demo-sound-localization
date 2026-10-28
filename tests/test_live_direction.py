"""Real-time voice direction is stable and does not depend on ASR."""
import unittest

from sound_direction.live_direction import LiveDirection


class LiveDirectionTests(unittest.TestCase):
    def setUp(self):
        self.tracker = LiveDirection({'frame_size': 512, 'rate': 16000})

    def frame(self, angle, now, *, valid=True, speech=True):
        return self.tracker.update({'speech': speech, 'sentence_direction_valid': valid,
                                    'angle': angle, 'confidence': 0.8}, now)

    def test_points_after_five_valid_audio_blocks_and_holds_briefly(self):
        for index in range(4):
            self.assertIsNone(self.frame(60, index*0.032)['angle'])
        self.assertAlmostEqual(self.frame(60, 0.128)['angle'], 60)
        self.assertIsNotNone(self.frame(None, 0.160, speech=False)['angle'])
        self.assertIsNotNone(self.frame(None, 0.53, speech=False)['angle'])
        self.assertIsNotNone(self.frame(None, 0.62, speech=False)['angle'])
        self.assertIsNone(self.frame(None, 1.03, speech=False)['angle'])

    def test_circular_mean_and_outlier_rejection(self):
        for index, angle in enumerate((350, 355, 0, 5, 10)):
            result = self.frame(angle, index*0.032)
        self.assertLess(min(result['angle'], 360-result['angle']), 5)
        previous = result['angle']
        self.frame(180, 0.160, valid=False)
        self.assertEqual(self.tracker.angle, previous)

    def test_new_speaker_can_take_over_after_confirmed_pause(self):
        for index in range(5):
            self.frame(30, index*0.032)
        self.frame(None, 0.160, speech=False)
        self.frame(None, 0.62, speech=False)
        self.assertIsNone(self.frame(None, 1.05, speech=False)['angle'])
        for index in range(4):
            self.assertIsNone(self.frame(210, 1.10+index*0.032)['angle'])
        self.assertAlmostEqual(self.frame(210, 1.228)['angle'], 210)

    def test_short_vad_dropout_keeps_direction(self):
        for index in range(5):
            self.frame(60, index*0.032)
        self.frame(None, 0.16, speech=False)
        self.assertAlmostEqual(self.frame(None, 0.42, speech=False)['angle'], 60)
        self.assertAlmostEqual(self.frame(60, 0.45)['angle'], 60)
        self.assertAlmostEqual(self.frame(None, 0.70, speech=False)['angle'], 60)

    def test_brief_large_jump_does_not_steal_direction(self):
        for index in range(5):
            self.frame(60, index*0.032)
        for index in range(10):
            result = self.frame(220, 0.16+index*0.032)
        self.assertLess(abs((result['angle']-60+180) % 360-180), 5)

    def test_sustained_competing_direction_does_not_steal_active_voice(self):
        for index in range(5):
            self.frame(60, index*0.032)
        for index in range(50):
            result = self.frame(220, 0.16+index*0.032)
        self.assertAlmostEqual(result['angle'], 60)

    def test_low_snr_does_not_move_direction(self):
        for index in range(5):
            self.frame(60, index*0.032)
        for index in range(12):
            result = self.tracker.update({'speech': True, 'sentence_direction_valid': True,
                                          'angle': 220, 'confidence': 0.8, 'snr_db': 1.0},
                                         0.16+index*0.032)
        self.assertLess(abs((result['angle']-60+180) % 360-180), 5)


if __name__ == '__main__':
    unittest.main()
