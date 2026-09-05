import tempfile
import unittest
from pathlib import Path

from companion.notifications import TaskNotices
from companion.store import Store


class TaskNoticeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'notices.db'
        self.store = Store(self.path)
        self.notices = TaskNotices(self.store)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def task(self, task_id='task-1', version='2026-09-05T10:00:00+00:00', status='completed'):
        return {'id': task_id, 'updated_at': version, 'status': status,
                'prompt': '检查日志', 'summary': '已完成检查'}

    def restart(self):
        self.store.close()
        self.store = Store(self.path)
        self.notices = TaskNotices(self.store)

    def test_pending_and_acknowledged_versions_survive_process_restart(self):
        task = self.task()
        self.assertTrue(self.notices.observe(task))
        self.restart()
        self.assertFalse(self.notices.observe(task))
        pending = self.notices.peek('chat', True)
        self.assertEqual(len(pending), 1)
        self.assertEqual(self.notices.acknowledge(pending), 1)
        self.restart()
        self.assertFalse(self.notices.observe(task))
        self.assertEqual(self.notices.peek('chat', True), [])

    def test_peek_is_repeatable_and_interruption_does_not_acknowledge(self):
        self.notices.observe(self.task())
        first = self.notices.peek('work', True)
        self.assertEqual(self.notices.peek('work', True), first)
        self.assertEqual(self.notices.peek('work', False), [])
        self.assertEqual(self.notices.peek('work', True), first)
        first[0]['summary'] = 'caller mutation'
        self.assertEqual(self.notices.peek('work', True)[0]['summary'], '已完成检查')

    def test_private_scene_and_idle_are_required(self):
        self.notices.observe(self.task())
        for scene, idle in [('live', True), ('live', False), ('chat', False), ('unknown', True)]:
            with self.subTest(scene=scene, idle=idle):
                self.assertEqual(self.notices.peek(scene, idle), [])
        self.assertEqual(len(self.notices.peek('chat', True)), 1)

    def test_new_run_same_task_is_distinct_and_stale_ack_cannot_consume_it(self):
        old = self.task()
        new = self.task(version='2026-09-05T11:00:00+00:00')
        self.notices.observe(old)
        self.notices.acknowledge([old])
        self.assertTrue(self.notices.observe(new))
        self.assertEqual(self.notices.acknowledge([old]), 0)
        self.assertEqual(self.notices.peek('chat', True)[0]['updated_at'], new['updated_at'])
        self.assertFalse(self.notices.observe(old))

    def test_three_notice_cap_keeps_all_remaining_unseen_tasks(self):
        for i in range(7):
            self.notices.observe(self.task(task_id=f'task-{i}'))
        delivered = []
        for expected in (3, 3, 1):
            batch = self.notices.peek('chat', True)
            self.assertEqual(len(batch), expected)
            delivered.extend(row['id'] for row in batch)
            self.notices.acknowledge(batch)
        self.assertEqual(len(set(delivered)), 7)
        self.assertEqual(self.notices.peek('chat', True), [])

    def test_restart_discovers_terminal_task_without_observed_event(self):
        task = self.store.create_task('检查任务', '.')
        self.store.update_task(task['id'], status='failed', summary='需要重试')
        self.restart()
        self.assertEqual(self.notices.peek('work', True)[0]['status'], 'failed')

    def test_nonterminal_updates_and_unknown_ack_are_ignored(self):
        for status in ('running', 'queued', 'paused'):
            self.assertFalse(self.notices.observe(self.task(status=status)))
        self.assertEqual(self.notices.acknowledge([self.task()]), 0)
        self.assertTrue(self.notices.observe(self.task()))

    def test_rerun_supersedes_old_pending_even_when_event_was_missed(self):
        task = self.store.create_task('检查', '.')
        completed = self.store.update_task(task['id'], status='completed')
        self.notices.observe(completed)
        self.store.update_task(task['id'], status='running')
        self.assertEqual(self.notices.peek('work',True), [])
        self.restart()
        self.assertEqual(self.notices.peek('work',True), [])
        self.assertFalse(self.notices.observe(completed))

    def test_newer_pending_supersedes_previous_completion(self):
        self.notices.observe(self.task())
        latest=self.task(version='2026-09-05T11:00:00+00:00')
        self.notices.observe(latest)
        self.assertEqual(len(self.notices.peek('work',True)),1)
        self.assertEqual(self.notices.acknowledge([self.task()]),0)


if __name__ == '__main__':
    unittest.main()
