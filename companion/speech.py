"""Only playback acknowledgements turn generated drafts into conversation."""
import re
import uuid
import math


def split_speech(text: str, limit: int = 18) -> list[str]:
    parts = []
    while text:
        window = text[:limit]
        marks = list(re.finditer(r'[。！？!?；;，,\n]', window))
        end = marks[-1].end() if marks else len(window)
        parts.append(text[:end])
        text = text[end:]
    return parts


class SpeechLedger:
    def __init__(self):
        self.turn_id = None
        self.pending = []
        self.heard = ''
        self.next_id = 0

    def begin(self):
        if self.turn_id:
            raise RuntimeError('Finish the previous utterance first')
        self.turn_id = uuid.uuid4().hex
        self.heard = ''
        self.pending = []
        self.next_id = 0
        return self.turn_id

    def stage(self, text, boundaries=None, duration=0):
        if not self.turn_id:
            raise RuntimeError('No active utterance')
        self.next_id += 1
        segment = {'id': self.next_id, 'text': text, 'boundaries': boundaries or [],
                   'duration': duration, 'committed': 0, 'progress': 0}
        self.pending.append(segment)
        return segment

    def ack(self, turn_id, segment_id):
        if not self.turn_id or turn_id != self.turn_id or not self.pending:
            return False
        if self.pending[0]['id'] != segment_id:
            return False
        segment = self.pending.pop(0)
        self.heard += segment['text'][segment['committed']:]
        return True

    def progress(self, turn_id, segment_id, seconds):
        if turn_id != self.turn_id or not self.pending or self.pending[0]['id'] != segment_id:
            return False
        if not isinstance(seconds, (float,int)) or not math.isfinite(seconds):
            return False
        segment = self.pending[0]
        if seconds <= segment['progress'] or not 0 <= seconds <= segment['duration']:
            return False
        segment['progress'] = seconds
        # Guard against clock/report jitter. Boundaries are provided by the
        # synthesizer, never manufactured by dividing text by audio duration.
        end = max([segment['committed']] + [b['end'] for b in segment['boundaries']
            if b['seconds'] + .04 <= seconds and 0 <= b['end'] <= len(segment['text'])])
        if end <= segment['committed']:
            return False
        self.heard += segment['text'][segment['committed']:end]
        segment['committed'] = end
        return True

    def finish(self, interrupted=False):
        heard = self.heard
        self.turn_id = None
        self.pending = []
        self.heard = ''
        return heard
