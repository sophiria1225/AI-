import contextlib
import io
import json
from pathlib import Path
import runpy
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import close_choice_context_reporting as closure
import build_budget_report
import run_handoff_factors
from test_choice_context_reporting import fixture as reporting_fixture

ROOT=Path(__file__).resolve().parents[1]


class ChoiceContextClosureTests(unittest.TestCase):
    def fixture(self,base):
        storage=base/'storage';rt=storage/'.runtime';rt.mkdir(parents=True)
        execution=base/'execution';(execution/'reports').mkdir(parents=True)
        fixed=dict(executed_head='a'*40,replacement_script_sha256=closure.sha(Path(closure.__file__)),
            original_watcher_stages=[],original_watcher_absent=True,original_watcher_pid=123,
            generation_conditions_changed=False,generation_outcomes_read=False)
        path=rt/'P101_reporting_command_correction_20261025.json';path.write_text(json.dumps(fixed))
        return storage,execution,path

    def test_corrected_command_parses_with_the_actual_frozen_report_CLI(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);root=reporting_fixture(base)
            command=closure.report_command(Path(sys.executable),root)
            actual=ROOT/'scripts/build_choice_context_report.py'
            with patch.object(run_handoff_factors,'ROOT',root),patch.object(sys,'argv',[str(actual)]+list(map(str,command[2:]))),\
                 patch.object(build_budget_report,'export') as export,\
                 patch.object(build_budget_report,'STEM',build_budget_report.STEM),\
                 contextlib.redirect_stdout(io.StringIO()):
                runpy.run_path(str(actual),run_name='__main__')
            out=root/'materials/20261024_p101_results'
            export.assert_called_once_with(out)
            self.assertEqual(json.loads((out/'build_manifest.json').read_text())['all_planned_rows'],36)

    def test_existing_original_watcher_prevents_a_second_closer(self):
        with tempfile.TemporaryDirectory() as temp:
            storage,execution,path=self.fixture(Path(temp))
            with patch.object(closure.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='123')):
                with self.assertRaisesRegex(ValueError,'original_watcher_still_present'):
                    closure.run(storage,execution,'a'*40,closure.sha(path))
            self.assertFalse((storage/'.runtime/P101_closure_operations_v02').exists())

    def test_saved_failed_audit_is_not_retried(self):
        with tempfile.TemporaryDirectory() as temp:
            storage,execution,path=self.fixture(Path(temp))
            (execution/'reports/P101_choice_context_audit_failure.json').write_text('{}')
            with patch.object(closure.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='')):
                with self.assertRaisesRegex(FileExistsError,'never_retry_existing'):
                    closure.run(storage,execution,'a'*40,closure.sha(path))

    def test_changed_correction_receipt_is_rejected_before_state_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            storage,execution,_=self.fixture(Path(temp))
            with self.assertRaisesRegex(ValueError,'fixed_correction_receipt'):
                closure.run(storage,execution,'a'*40,'0'*64)
            self.assertFalse((storage/'.runtime/P101_closure_operations_v02').exists())


if __name__=='__main__':unittest.main()
