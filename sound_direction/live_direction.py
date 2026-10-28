"""Low-latency voice direction tracking, independent of transcription."""
from collections import deque
import math


class LiveDirection:
    def __init__(self, cfg):
        self.window = cfg.get('live_direction_window_seconds', 0.25)
        self.minimum = cfg.get('live_direction_min_seconds', 0.16)
        self.minimum_consistency = cfg.get('live_direction_min_consistency', 0.7)
        self.hold = cfg.get('live_direction_hold_seconds', 0.4)
        self.speech_gap = cfg.get('live_direction_speech_gap_seconds', 0.45)
        self.jump_confirm = cfg.get('live_direction_jump_confirm_seconds', 0.35)
        self.min_snr = cfg.get('live_direction_min_snr_db', 3.0)
        self.lock_degrees = cfg.get('live_direction_lock_degrees', 55.0)
        self.handoff_window = cfg.get('live_direction_handoff_window_seconds', 0.55)
        self.handoff_minimum = cfg.get('live_direction_handoff_min_seconds', 0.4)
        self.handoff_consistency = cfg.get('live_direction_handoff_min_consistency', 0.85)
        self.handoff_relaxed_consistency = cfg.get('live_direction_handoff_relaxed_consistency', 0.8)
        self.handoff_share = cfg.get('live_direction_handoff_min_share', 0.75)
        self.handoff_old_evidence_window = cfg.get('live_direction_handoff_old_evidence_window_seconds', 0.25)
        self.handoff_old_evidence_max_frames = cfg.get('live_direction_handoff_old_evidence_max_frames', 1)
        self.frame_seconds = cfg['frame_size']/cfg['rate']
        self.samples = deque()
        self.handoff_samples = deque()
        self.evidence_history = deque()
        self.angle = None
        self.anchor_angle = None
        self.consistency = 0.0
        self.speech_active = False
        self.speech_ended_at = None
        self.speech_gap_started_at = None
        self.pending_angle = None
        self.pending_since = None

    def update(self, result, now):
        new_valid = False
        new_handoff = False
        raw_speech = result.get('speech') is True
        if raw_speech:
            self.speech_gap_started_at = None
        elif self.speech_active and self.speech_gap_started_at is None:
            self.speech_gap_started_at = now
        speech = raw_speech or (self.speech_active and self.speech_gap_started_at is not None
                                and now-self.speech_gap_started_at < self.speech_gap)
        if speech and not self.speech_active:
            if (self.speech_ended_at is not None
                    and now-self.speech_ended_at >= self.hold):
                self.angle = None
                self.anchor_angle = None
                self.consistency = 0.0
                self.handoff_samples.clear()
                self.evidence_history.clear()
            self.speech_ended_at = None
        elif not speech and self.speech_active:
            self.speech_ended_at = now
        self.speech_active = speech

        if not speech:
            self.samples.clear()
            self.handoff_samples.clear()
            self.evidence_history.clear()
            self.pending_angle = None
            self.pending_since = None
        else:
            snr = result.get('snr_db')
            if (raw_speech and result.get('sentence_direction_valid')
                    and (snr is None or snr >= self.min_snr)):
                angle = result.get('angle')
                confidence = result.get('confidence', 0.0)
                within_lock = (self.anchor_angle is None or angle is None or
                               abs((angle-self.anchor_angle+180) % 360-180) <= self.lock_degrees)
                if (angle is not None and math.isfinite(angle)
                        and math.isfinite(confidence) and confidence > 0):
                    if within_lock:
                        self.samples.append((now, angle % 360, confidence))
                        self.evidence_history.append((now, False))
                        new_valid = True
                    else:
                        self.handoff_samples.append((now, angle % 360, confidence))
                        self.evidence_history.append((now, True))
                        new_handoff = True
            while self.samples and now-self.samples[0][0] >= self.window:
                self.samples.popleft()
            while self.handoff_samples and now-self.handoff_samples[0][0] >= self.handoff_window:
                self.handoff_samples.popleft()
            while self.evidence_history and now-self.evidence_history[0][0] >= self.handoff_window:
                self.evidence_history.popleft()
            if new_handoff and self._confirm_handoff(now):
                return self.snapshot(now)
            if not new_valid:
                self.pending_angle = None
                self.pending_since = None
            duration = len(self.samples)*self.frame_seconds
            if new_valid and duration >= self.minimum:
                sine = sum(math.sin(math.radians(angle))*confidence
                           for _, angle, confidence in self.samples)
                cosine = sum(math.cos(math.radians(angle))*confidence
                             for _, angle, confidence in self.samples)
                weight = sum(confidence for _, _, confidence in self.samples)
                consistency = min(1.0, math.hypot(sine, cosine)/weight)
                if consistency >= self.minimum_consistency:
                    candidate = math.degrees(math.atan2(sine, cosine)) % 360
                    if self.angle is None:
                        self.angle = candidate
                        self.anchor_angle = candidate
                    else:
                        delta = (candidate-self.angle+180) % 360-180
                        if abs(delta) > 45:
                            if (self.pending_angle is None or
                                    abs((candidate-self.pending_angle+180) % 360-180) > 25):
                                self.pending_angle, self.pending_since = candidate, now
                            else:
                                self.pending_angle = candidate
                            if now-self.pending_since < self.jump_confirm:
                                return self.snapshot(now)
                            self.angle = candidate
                        else:
                            self.angle = (self.angle+0.35*delta) % 360
                    self.pending_angle = None
                    self.pending_since = None
                    self.consistency = consistency
                else:
                    self.pending_angle = None
                    self.pending_since = None
        return self.snapshot(now)

    def _confirm_handoff(self, now):
        """Switch only when a stable off-lock voice dominates recent evidence."""
        if len(self.handoff_samples)*self.frame_seconds < self.handoff_minimum:
            return False
        if (sum(is_candidate for _, is_candidate in self.evidence_history)
                / len(self.evidence_history) < self.handoff_share):
            return False
        sine = sum(math.sin(math.radians(angle))*confidence
                   for _, angle, confidence in self.handoff_samples)
        cosine = sum(math.cos(math.radians(angle))*confidence
                     for _, angle, confidence in self.handoff_samples)
        weight = sum(confidence for _, _, confidence in self.handoff_samples)
        consistency = math.hypot(sine, cosine)/weight
        old_recent_frames = sum(
            not is_candidate for timestamp, is_candidate in self.evidence_history
            if now-timestamp < self.handoff_old_evidence_window
        )
        threshold = (self.handoff_relaxed_consistency
                     if old_recent_frames <= self.handoff_old_evidence_max_frames
                     else self.handoff_consistency)
        if consistency < threshold:
            return False
        self.angle = math.degrees(math.atan2(sine, cosine)) % 360
        self.anchor_angle = self.angle
        self.consistency = consistency
        self.samples = deque(sample for sample in self.handoff_samples
                             if now-sample[0] < self.window)
        self.handoff_samples.clear()
        self.evidence_history.clear()
        self.pending_angle = None
        self.pending_since = None
        return True

    def snapshot(self, now):
        visible = (self.angle is not None and
                   (self.speech_active or
                    (self.speech_ended_at is not None
                     and now-self.speech_ended_at < self.hold)))
        valid_until = (float('inf') if self.speech_active else
                       self.speech_ended_at+self.hold if self.speech_ended_at is not None else now)
        return {'angle': self.angle if visible else None,
                'consistency': self.consistency if visible else 0.0,
                'valid_until': valid_until if visible else now}
