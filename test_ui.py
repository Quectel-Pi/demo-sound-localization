"""Language and reconnect state checks that do not require a desktop display."""
import threading
from types import SimpleNamespace
import unittest

from app import Application
from i18n import STRINGS


class InterfaceTests(unittest.TestCase):
    def test_both_languages_have_the_same_ui_keys(self):
        self.assertEqual(set(STRINGS['zh']), set(STRINGS['en']))

    def test_transcripts_change_direction_label_with_interface(self):
        application = Application.__new__(Application)
        application.transcripts = [('你好', 59.6), ('hello', None)]
        application.language = 'zh'
        self.assertEqual(application.transcript_lines(), ['[方向 060°] 你好', '[方向未知] hello'])
        application.language = 'en'
        self.assertEqual(application.transcript_lines(), ['[Direction 060°] 你好', '[Direction unknown] hello'])

    def test_retry_requests_old_worker_stop_before_reopening(self):
        application = Application.__new__(Application)
        application.args = SimpleNamespace(demo=False, wav=None)
        application.language = 'zh'
        application.retry_pending = False
        application.stop = threading.Event()
        application.error = 'old error'
        application.done = True
        application.asr_recording = True
        application.asr_pending = {1}
        application.asr_service = None
        application.view = SimpleNamespace(notify=lambda message: None)
        application.retry_device()
        self.assertTrue(application.stop.is_set())
        self.assertTrue(application.retry_pending)
        self.assertIsNone(application.error)
        self.assertFalse(application.done)
        self.assertFalse(application.asr_recording)
        self.assertFalse(application.asr_pending)

    def test_live_arrow_hides_as_soon_as_voice_or_direction_is_lost(self):
        application = Application.__new__(Application)
        application.cfg = {'hold_seconds': 0.55, 'vad_enabled': True}
        application.error = None
        application.done = False
        application.last_result = 10.0
        application.tracker = SimpleNamespace(last_active=10.0, pending_angle=None)
        application.latest = {'speech': True, 'active': True, 'angle': 60}
        self.assertTrue(application.direction_visible(10.1))
        application.latest['speech'] = False
        self.assertFalse(application.direction_visible(10.1))
        application.latest['speech'] = True
        application.latest['active'] = False
        self.assertFalse(application.direction_visible(10.1))
        application.latest['active'] = True
        application.latest['angle'] = None
        self.assertFalse(application.direction_visible(10.1))
        application.latest['angle'] = 60
        application.tracker.pending_angle = 200
        self.assertFalse(application.direction_visible(10.1))
        application.tracker.pending_angle = None
        self.assertFalse(application.direction_visible(10.6))

    def test_demo_without_vad_keeps_short_hold(self):
        application = Application.__new__(Application)
        application.cfg = {'hold_seconds': 0.55, 'vad_enabled': False}
        application.error = None
        application.done = False
        application.last_result = 10.0
        application.tracker = SimpleNamespace(last_active=10.0)
        application.latest = {'speech': None, 'active': False, 'angle': 60}
        self.assertTrue(application.direction_visible(10.1))
        self.assertFalse(application.direction_visible(10.6))


if __name__ == '__main__':
    unittest.main()
