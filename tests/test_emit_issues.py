"""Offline regression tests; never create real GitHub issues."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    'emit_issues', Path(__file__).resolve().parents[1] / 'scripts/emit_issues.py'
)
emitter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(emitter)


class EmitIssuesTests(unittest.TestCase):
    def test_json_fields_are_one_argument(self):
        result = subprocess.CompletedProcess([], 0, '[{"number":1,"title":" Existing "}]', '')
        with patch.object(emitter.subprocess, 'run', return_value=result) as run:
            self.assertEqual(emitter.get_existing_titles('owner/board'), {'existing'})
        args = run.call_args.args[0]
        self.assertEqual(args[args.index('--json') + 1:], ['number,title'])

    def test_lookup_failures_do_not_look_like_empty_board(self):
        for stdout, code in [('', 1), ('not json', 0), ('[{}]', 0)]:
            with self.subTest(stdout=stdout, code=code):
                result = subprocess.CompletedProcess([], code, stdout, '')
                with patch.object(emitter.subprocess, 'run', return_value=result):
                    with self.assertRaises(RuntimeError):
                        emitter.get_existing_titles('owner/board')

    def test_lookup_timeout_fails_closed(self):
        with patch.object(emitter.subprocess, 'run', side_effect=subprocess.TimeoutExpired('gh', 30)):
            with self.assertRaises(RuntimeError):
                emitter.get_existing_titles('owner/board')

    def test_empty_board_is_valid(self):
        result = subprocess.CompletedProcess([], 0, '[]', '')
        with patch.object(emitter.subprocess, 'run', return_value=result):
            self.assertEqual(emitter.get_existing_titles('owner/board'), set())

    def test_issue_labels_include_scope_project_and_capped_priority(self):
        for repo, priority, expected in [('auditor', 'P4', 'P4'), ('', 'P0', 'P3')]:
            with self.subTest(repo=repo):
                result = subprocess.CompletedProcess([], 0, 'https://example.com/1', '')
                with patch.object(emitter.subprocess, 'run', return_value=result) as run:
                    ok, _ = emitter.create_issue('owner/board', {
                        'title': 'Handle snapshot parse failures', 'repo': repo, 'priority': priority,
                    })
                self.assertTrue(ok)
                args = run.call_args.args[0]
                labels = [args[i + 1] for i, arg in enumerate(args) if arg == '--label']
                self.assertCountEqual(labels, [f'priority:{expected}', 'status:new',
                    'tag:auto-audit', 'tag:cross-device', f'project:{repo or "general"}'])

    def test_dry_run_has_no_external_calls(self):
        with patch.object(emitter.subprocess, 'run') as run:
            ok, message = emitter.create_issue('owner/board', {'title': 'Fix snapshot parser'}, dry_run=True)
        self.assertTrue(ok)
        self.assertIn('tag:cross-device', message)
        run.assert_not_called()

    def test_main_stops_before_create_when_lookup_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'proposals.json'
            path.write_text(json.dumps([{'title': 'Fix snapshot parser'}]))
            with patch.object(emitter.sys, 'argv', ['emit_issues.py', str(path)]), \
                 patch.object(emitter, 'get_existing_titles', side_effect=RuntimeError('lookup failed')), \
                 patch.object(emitter, 'create_issue') as create:
                self.assertEqual(emitter.main(), 1)
                create.assert_not_called()


if __name__ == '__main__':
    unittest.main()
