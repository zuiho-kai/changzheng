from companion.local_speech import boundaries
from companion.speech import SpeechLedger


def test_no_uniform_character_estimates_and_numbers_are_atomic():
    text='我有30%电量。'
    marks=[{'position':0,'count':1,'seconds':.1,'text':'我'},
        {'position':1,'count':1,'seconds':.3,'text':'有'},
        {'position':2,'count':3,'seconds':.6,'text':'30%'},
        {'position':2,'count':3,'seconds':1.,'text':'30%'},
        {'position':5,'count':2,'seconds':1.4,'text':'电量'}]
    assert boundaries(text,marks,2.)==[{'end':1,'seconds':.3},{'end':2,'seconds':.6},
        {'end':5,'seconds':1.4},{'end':8,'seconds':2.}]


def test_invalid_engine_offsets_disable_partial_commits():
    assert boundaries('你好',[{'position':0,'count':2,'seconds':0,'text':'再见'}],1)==[]


def test_utf16_offsets_convert_to_codepoints():
    marks=[{'position':2,'count':1,'seconds':.2,'text':'你'},{'position':3,'count':1,'seconds':.5,'text':'好'}]
    assert boundaries('🐈你好',marks,1)==[{'end':2,'seconds':.5},{'end':3,'seconds':1}]


def test_partial_progress_keeps_only_confirmed_word_prefix():
    ledger=SpeechLedger(); tid=ledger.begin()
    ledger.stage('先查看日志然后重启', [{'end':3,'seconds':.8},{'end':5,'seconds':1.4}], 3)
    assert not ledger.progress(tid,1,.81)  # safety margin
    assert ledger.progress(tid,1,.9)
    assert ledger.heard=='先查看'
    assert not ledger.progress(tid,1,.7)
    assert not ledger.progress(tid,2,2)
    assert not ledger.progress(tid,1,float('nan'))
    assert not ledger.progress(tid,1,100)
    assert ledger.finish(True)=='先查看'


def test_final_ack_after_partial_does_not_repeat_prefix():
    ledger=SpeechLedger(); tid=ledger.begin()
    ledger.stage('你好世界',[{'end':2,'seconds':.5}],2)
    ledger.progress(tid,1,1)
    ledger.ack(tid,1)
    assert ledger.finish()=='你好世界'


def test_no_timestamps_means_no_partial_commit():
    ledger=SpeechLedger(); tid=ledger.begin(); ledger.stage('云端完整短句',duration=3)
    assert not ledger.progress(tid,1,2.5)
    assert ledger.finish(True)==''
