"""No model server can start outside the fixed deadline or after user stop."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_whole_task_checkpoint_inventory as driver
import run_whole_task_checkpoint_inventory_pipeline as pipeline


class PipelineBoundsTests(unittest.TestCase):
    def test_explicit_stop_precedes_repository_or_network_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'.runtime').mkdir();(root/'.runtime/P130.stop').touch()
            with patch.object(pipeline.subprocess,'check_output') as network:
                with self.assertRaises(InterruptedError):pipeline.run(root,'a'*40)
                network.assert_not_called()

    def test_expired_lease_rejects_before_source_or_process_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.object(pipeline.subprocess,'check_output',side_effect=['a'*40,'']), \
                 patch.object(pipeline,'check_resume',return_value={}), \
                 patch.object(pipeline,'checked_ci',return_value=[]), \
                 patch.object(pipeline,'read',return_value={'deadline_jst':'2000-01-01T06:00:00+09:00','server_max_lifetime_seconds':14400}), \
                 patch.object(driver,'sources') as sources, \
                 patch.object(pipeline.subprocess,'Popen') as spawn:
                with self.assertRaisesRegex(ValueError,'lease_would_exceed'):pipeline.run(root,'a'*40)
                sources.assert_not_called();spawn.assert_not_called()
                self.assertFalse((root/'records').exists())

    def test_deadline_is_rechecked_after_preparation_before_spawn(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.object(pipeline.subprocess,'check_output',side_effect=['a'*40,'']), \
                 patch.object(pipeline,'check_resume',return_value={}), \
                 patch.object(pipeline,'checked_ci',return_value=[]), \
                 patch.object(pipeline,'read',return_value={'deadline_jst':'2000-01-01T00:00:00+00:00','server_max_lifetime_seconds':14400}), \
                 patch.object(driver,'sources',return_value=({}, {'model_selection':'synthetic'}, [], [])), \
                 patch.object(driver,'predecessor_closed',return_value={}), \
                 patch.object(driver,'launch_predecessor_closed',return_value={}), \
                 patch.object(pipeline.time,'time',side_effect=[0,1000000000]), \
                 patch.object(pipeline.subprocess,'Popen') as spawn:
                self.assertEqual(pipeline.run(root,'a'*40),1)
                spawn.assert_not_called()
                import json
                record=json.loads((root/'records/context_pilot/P130_pipeline_v01/status.json').read_text())
                self.assertEqual(record['status'],'stopped')
                self.assertFalse(record['server_owned'])
                self.assertEqual(record['stages'],[])


if __name__=='__main__':unittest.main()
