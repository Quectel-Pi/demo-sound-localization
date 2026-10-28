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
        self.frame_seconds = cfg['frame_size']/cfg['rate']
        self.samples = deque()
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
            self.speech_ended_at = None
        elif not speech and self.speech_active:
            self.speech_ended_at = now
        self.speech_active = speech

        if not speech:
            self.samples.clear()
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
                        and math.isfinite(confidence) and confidence > 0 and within_lock):
                    self.samples.append((now, angle % 360, confidence))
                    new_valid = True
            while self.samples and now-self.samples[0][0] >= self.window:
                self.samples.popleft()
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
