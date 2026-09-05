"""Only playback acknowledgements turn generated drafts into conversation."""
import re
import uuid


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

    def stage(self, text):
        if not self.turn_id:
            raise RuntimeError('No active utterance')
        self.next_id += 1
        segment = {'id': self.next_id, 'text': text}
        self.pending.append(segment)
        return segment

    def ack(self, turn_id, segment_id):
        if not self.turn_id or turn_id != self.turn_id or not self.pending:
            return False
        if self.pending[0]['id'] != segment_id:
            return False
        self.heard += self.pending.pop(0)['text']
        return True

    def finish(self, interrupted=False):
        heard = self.heard
        self.turn_id = None
        self.pending = []
        self.heard = ''
        return heard
