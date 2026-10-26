"""Language and reconnect state checks that do not require a desktop display."""
from contextlib import redirect_stderr
import io
import threading
import queue
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
        application.cfg = {'direction_sector_deg': 30, 'gate_dbfs': -35,
                           'min_confidence': 0.2, 'asr_direction_min_seconds': 0.25,
                           'asr_direction_min_coverage': 0.3,
                           'asr_direction_min_consistency': 0.7}
        self.assertEqual(application.transcript_lines(), ['[方向约 060° ±15°] 你好', '[方向未知] hello'])
        application.language = 'en'
        self.assertEqual(application.transcript_lines(), ['[Direction ~060° ±15°] 你好', '[Direction unknown] hello'])

    def test_completed_sentence_locks_pointer_to_transcript_sector(self):
        application = Application.__new__(Application)
        application.language = 'zh'
        application.cfg = {'direction_sector_deg': 30, 'gate_dbfs': -35,
                           'min_confidence': 0.2, 'asr_direction_min_seconds': 0.25,
                           'asr_direction_min_coverage': 0.3,
                           'asr_direction_min_consistency': 0.7}
        application.sentence_mode = True
        application.transcripts = []
        application.asr_pending = set()
        application.asr_error = None
        application.asr_recording = False
        application.asr_message_key = 'asr_ready'
        application.asr_result_seconds = 0.0
        application.asr_label = SimpleNamespace(configure=lambda **kwargs: None)
        application.render_transcripts = lambda: None
        event = {'kind': 'result', 'sequence': 1, 'text': '你好', 'direction_deg': 68,
                 'direction_consistency': 0.8, 'recognition_seconds': 0.4}
        application.asr_service = SimpleNamespace(poll=lambda: [event])
        application.poll_asr()
        self.assertEqual(application.sentence_direction, 60)
        self.assertEqual(application.display_angle, 60)
        self.assertEqual(application.transcript_lines(), ['[方向约 060° ±15°] 你好'])
        self.assertEqual(application.sentence_consistency, 0.8)
        event['sequence'] = 2
        event['direction_deg'] = None
        event.update(direction_reasons=('insufficient_coverage',), direction_seconds=0.2,
                     direction_speech_seconds=1.0, direction_coverage=0.2,
                     direction_rejected_seconds={'gate_dbfs': 0.8})
        log = io.StringIO()
        with redirect_stderr(log):
            application.poll_asr()
        self.assertIsNone(application.sentence_direction)
        self.assertIn('[方向未知 #2] ASR：你好', log.getvalue())
        self.assertIn('方向覆盖不足', log.getvalue())
        self.assertIn('覆盖 20.0%（门限 30%）', log.getvalue())
        self.assertIn('基础电平门限(-35.0 dBFS) 0.800s', log.getvalue())
        self.assertEqual(application.transcript_lines(), ['[方向约 060° ±15°] 你好'])

    def test_live_capture_cannot_move_a_locked_sentence_pointer(self):
        application = Application.__new__(Application)
        application.cfg = {'gate_dbfs': -35, 'hold_seconds': 0.55}
        application.gate = SimpleNamespace(get=lambda: -35)
        application.tk = SimpleNamespace(TclError=Exception)
        application.queue = queue.Queue()
        application.queue.put({'_run_id': 1, 'active': True, 'angle': 220, 'speech': True})
        application.run_id = 1
        application.tracker = SimpleNamespace(update=lambda value, now: (220, True))
        application.retry_pending = False
        application.sentence_mode = True
        application.sentence_direction = 60
        application.display_angle = 60
        application.error = None
        application.done = False
        application.poll_asr = lambda: None
        application.draw = lambda now: None
        application.root = SimpleNamespace(after=lambda delay, callback: None)
        application.tick()
        self.assertEqual(application.display_angle, 60)
        self.assertTrue(application.alive)

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
