import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_public_only_history_summary import build, sha, write
from whole_task_public_only_history import HISTORICAL_POLICIES, summarize


class PublicOnlyReportTests(unittest.TestCase):
    def test_new_costs_exclude_historical_runs_and_unknown_use_remains_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'repo';storage=Path(folder)/'storage'
            (root/'reports').mkdir(parents=True);(root/'materials').mkdir()
            rows=[];historical=[]
            for n in range(1,5):
                rid=f'fixture_{n}';trial=storage/'records/context_pilot'/rid;trial.mkdir(parents=True)
                usage=[dict(id='call_001',status='ok',input_tokens=30,output_tokens=20)]
                if n==4:usage.append(dict(id='call_002',status='error',input_tokens=None,output_tokens=None))
                write(trial/'usage.json',usage)
                rows.append(dict(run_id=rid,task_id=str(n),reasoning_display_policy='public_only',
                    record_status='evaluated',success=n!=4,known_total_tokens=50,unknown_usage_calls=int(n==4),
                    model_calls=len(usage),api_requests=1,input_tokens=30,output_tokens=20,cached_input_tokens=5,
                    history_views_sha256=None,usage_sha256=sha(trial/'usage.json')))
                historical.extend(dict(run_id=f'old_{n}_{p}',task_id=str(n),reasoning_display_policy=p,
                    record_status='evaluated',success=True,known_total_tokens=100,unknown_usage_calls=0,
                    model_calls=2,api_requests=2) for p in HISTORICAL_POLICIES)
            write(root/'reports/P111_comparison.json',dict(rows=historical,audit_errors=[]))
            audit=dict(phase='P114',batch_status='complete',rows=rows,audit_errors=[],owned_processes_absent=True,
                **summarize(rows,[],historical))
            write(root/'reports/P114_comparison.json',audit)
            write(root/'reports/P114_server_session.json',dict(status='stopped',owned_processes_absent=True,
                audit_source_sha256=sha(root/'reports/P114_comparison.json')))
            build(root,storage)
            out=root/'materials/20261025_p114_results'
            summary=json.loads((out/'summary.json').read_text())
            self.assertEqual(summary['model_attempts'],5)
            self.assertEqual(summary['known_logical_tokens'],200)
            self.assertEqual(summary['unknown_usage_attempts'],1)
            self.assertEqual(summary['sent_API_requests'],4)
            self.assertFalse(summary['development_gate_met'])
            self.assertEqual(len(list(csv.DictReader((out/'historical_P111_conditions.csv').open()))),12)
            conditions=list(csv.DictReader((out/'all_conditions.csv').open()))
            self.assertEqual(len(conditions),4)
            self.assertEqual(conditions[-1]['full_logical_tokens'],'')
            manifest=json.loads((out/'build_manifest.json').read_text())
            self.assertEqual(manifest['historical_P111_audit_sha256'],sha(root/'reports/P111_comparison.json'))
            with self.assertRaises(FileExistsError):build(root,storage)


if __name__=='__main__':unittest.main()
