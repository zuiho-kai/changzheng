import tempfile
import unittest
from pathlib import Path

from companion.store import Store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'memory.db'
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_restart_persists_history_memory_settings_and_tasks(self):
        session = self.store.new_session('work')
        source = self.store.add_message(session, 'user', '我的项目叫长征', scene='work')
        memory = self.store.add_memory('项目叫长征', scene='work', source_id=source['id'])
        task = self.store.create_task('检查语音延迟', 'E:/project', 'thread-1')
        self.store.update_task(task['id'], status='completed', summary='检查完成')
        self.store.set_setting('voice', {'enabled': True})
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.history(session)[0]['content'], '我的项目叫长征')
        self.assertEqual(self.store.memories()[0]['id'], memory['id'])
        self.assertEqual(self.store.memories()[0]['source_text'], source['content'])
        self.assertEqual(self.store.get_setting('voice'), {'enabled': True})
        self.assertEqual(self.store.tasks()[0]['summary'], '检查完成')

    def test_recall_has_relevance_scene_and_public_boundaries(self):
        self.store.add_memory('语音助手应该支持打断恢复', scene='work', visibility='public')
        self.store.add_memory('工作语音密码是秘密', scene='all', visibility='private')
        self.store.add_memory('语音直播喜欢简短回答', scene='all', visibility='public')
        self.store.add_memory('语音聊天希望温柔一些', scene='chat', visibility='public')
        self.store.add_memory('晚饭喜欢牛肉', scene='all', visibility='public')
        work = self.store.recall('怎么降低语音助手的打断延迟', scene='work')
        self.assertEqual(work[0]['content'], '语音助手应该支持打断恢复')
        self.assertNotIn('语音聊天希望温柔一些', [x['content'] for x in work])
        live = self.store.recall('语音', scene='live')
        self.assertEqual([x['content'] for x in live], ['语音直播喜欢简短回答'])
        self.assertEqual(self.store.recall('太空火箭发动机'), [])

    def test_correction_removes_old_context_but_preserves_provenance(self):
        session = self.store.new_session()
        source = self.store.add_message(session, 'user', '我喜欢喝咖啡')
        self.store.add_message(session, 'assistant', '记住了，你喜欢咖啡')
        self.store.add_message(session, 'user', '今天下雨')
        mem = self.store.add_memory('喜欢咖啡', source_id=source['id'])
        changed = self.store.update_memory(mem['id'], '喜欢喝茶')
        self.assertEqual(changed['source_id'], source['id'])
        self.assertEqual(changed['source_text'], '我喜欢喝咖啡')
        self.assertEqual([x['content'] for x in self.store.history(session)], ['今天下雨'])
        self.assertEqual(self.store.recall('咖啡'), [])
        self.assertEqual(self.store.recall('喝茶')[0]['id'], mem['id'])

    def test_forget_purges_source_and_assistant_history(self):
        session = self.store.new_session()
        source = self.store.add_message(session, 'user', '我的住址是秘密街')
        self.store.add_message(session, 'assistant', '记住秘密街了')
        mem = self.store.add_memory('住址秘密街', source_id=source['id'])
        self.store.forget_memory(mem['id'])
        self.assertEqual(self.store.memories(), [])
        self.assertEqual(self.store.history(session), [])

    def test_forget_also_removes_recalled_fact_from_other_session(self):
        first = self.store.new_session()
        second = self.store.new_session('work')
        source = self.store.add_message(first, 'user', '我住秘密街')
        mem = self.store.add_memory('住秘密街', source_id=source['id'])
        self.store.add_message(second, 'user', '我要出门')
        self.store.add_message(second, 'assistant', '从秘密街出发吧')
        self.store.forget_memory(mem['id'])
        self.assertEqual([m['content'] for m in self.store.history(second)], ['我要出门'])
        self.store.forget_memory(mem['id'])  # Deletion retries are safe.

    def test_public_recall_never_exposes_private_source_snapshot(self):
        session = self.store.new_session()
        source = self.store.add_message(session, 'user', '我喜欢画画，密码是秘密')
        mem = self.store.add_memory('喜欢画画', visibility='public', source_id=source['id'])
        recalled = self.store.recall('画画', scene='live')[0]
        self.assertEqual(recalled['id'], mem['id'])
        self.assertNotIn('source_text', recalled)
        self.assertNotIn('密码', str(recalled))

    def test_clear_history_does_not_remove_saved_memory(self):
        session = self.store.new_session()
        source = self.store.add_message(session, 'user', '喜欢薄荷')
        self.store.add_memory('喜欢薄荷', source_id=source['id'])
        self.store.clear_session(session)
        self.assertEqual(self.store.history(session), [])
        self.assertEqual(self.store.memories()[0]['source_text'], '喜欢薄荷')

    def test_message_ids_idempotent_and_memory_dedup_normalized(self):
        session = self.store.new_session()
        first = self.store.add_message(session, 'assistant', '实际听到的话', message_id='played-1')
        again = self.store.add_message(session, 'assistant', '实际听到的话', message_id='played-1')
        self.assertEqual(first, again)
        self.assertEqual(len(self.store.history(session)), 1)
        a = self.store.add_memory(' 喜欢   Python ', source_id=first['id'])
        b = self.store.add_memory('喜欢 python')
        self.assertEqual(a['id'], b['id'])
        self.assertEqual(b['source_id'], first['id'])
        self.assertEqual(self.store.get_setting('missing', 'fallback'), 'fallback')
        with self.assertRaises(ValueError):
            self.store.add_message(session, 'assistant', '另一句话', message_id='played-1')

    def test_dedup_can_attach_previously_missing_provenance(self):
        mem = self.store.add_memory('喜欢薄荷')
        session = self.store.new_session()
        source = self.store.add_message(session, 'user', '我喜欢薄荷')
        linked = self.store.add_memory('喜欢薄荷', source_id=source['id'])
        self.assertEqual(linked['id'], mem['id'])
        self.assertEqual(linked['source_text'], source['content'])

    def test_deduplicated_sources_all_invalidated_on_edit_and_forget(self):
        for operation in ('edit', 'forget'):
            with self.subTest(operation=operation):
                sessions = [self.store.new_session(), self.store.new_session()]
                sources = [self.store.add_message(s, 'user', f'{operation}喜欢咖啡') for s in sessions]
                memories = [self.store.add_memory(f'{operation}喜欢咖啡', source_id=s['id']) for s in sources]
                self.assertEqual(memories[0]['id'], memories[1]['id'])
                if operation == 'edit':
                    self.store.update_memory(memories[0]['id'], '喜欢茶')
                else:
                    self.store.forget_memory(memories[0]['id'])
                for session in sessions:
                    self.assertEqual(self.store.history(session), [])

    def test_stale_source_extraction_cannot_recreate_corrected_or_forgotten_fact(self):
        for operation in ('edit', 'forget'):
            with self.subTest(operation=operation):
                session = self.store.new_session()
                source = self.store.add_message(session, 'user', f'{operation}喜欢咖啡')
                memory = self.store.add_memory(source['content'], source_id=source['id'])
                if operation == 'edit':
                    self.store.update_memory(memory['id'], '喜欢茶')
                else:
                    self.store.forget_memory(memory['id'])
                with self.assertRaisesRegex(ValueError, 'source'):
                    self.store.add_memory(source['content'], source_id=source['id'])
        with self.assertRaisesRegex(ValueError, 'source'):
            self.store.add_memory('不存在的来源', source_id='missing-source')


if __name__ == '__main__':
    unittest.main()
