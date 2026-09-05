from companion.speech import SpeechLedger, split_speech


def test_interrupt_keeps_only_completed_audio_and_rejects_late_ack():
    ledger = SpeechLedger()
    turn = ledger.begin()
    a = ledger.stage('先检查日志。')
    b = ledger.stage('再重启服务。')
    assert ledger.ack(turn, a['id']) is True
    assert ledger.finish(interrupted=True) == '先检查日志。'
    assert ledger.ack(turn, b['id']) is False
    assert ledger.heard == ''


def test_unheard_entire_reply_never_enters_context():
    ledger = SpeechLedger()
    ledger.begin()
    ledger.stage('这是尚未说出的秘密。')
    assert ledger.finish(interrupted=True) == ''


def test_out_of_order_or_duplicate_ack_does_not_invent_speech():
    ledger = SpeechLedger()
    turn = ledger.begin()
    a, b = ledger.stage('甲。'), ledger.stage('乙。')
    assert not ledger.ack(turn, b['id'])
    assert ledger.ack(turn, a['id'])
    assert not ledger.ack(turn, a['id'])
    assert ledger.ack(turn, b['id'])
    assert ledger.finish() == '甲。乙。'


def test_previous_turn_cannot_commit_into_next_turn():
    ledger = SpeechLedger()
    old = ledger.begin()
    a = ledger.stage('旧消息')
    ledger.finish(interrupted=True)
    current = ledger.begin()
    ledger.stage('新消息')
    assert old != current
    assert not ledger.ack(old, a['id'])
    assert ledger.finish() == ''


def test_short_speech_chunks_preserve_content_without_long_queue():
    text = '你好，我在这里陪你。我们先从今天的事情说起，然后再决定下一步。'
    parts = split_speech(text, limit=16)
    assert ''.join(parts) == text
    assert all(0 < len(x) <= 16 for x in parts)
