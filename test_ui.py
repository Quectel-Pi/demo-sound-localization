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


if __name__ == '__main__':
    unittest.main()
