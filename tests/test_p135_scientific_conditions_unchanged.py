"""P135 repairs launch/reporting only: preserve P134's six scientific conditions."""
from copy import deepcopy
import hashlib,json
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import whole_task_observed_obligations as old
import whole_task_observed_obligations_p135 as new
from tool_choice_local_llama import payload_for
from test_public_output_grounding import TASK
ROOT=Path(__file__).resolve().parents[1]


class RecoveryDoesNotChangeScience(unittest.TestCase):
    def test_all_frozen_p134_sources_still_match_actual_repository(self):
        plan=json.loads((ROOT/old.PLAN).read_text())
        self.assertEqual(len(plan['source_sha256']),1483)
        for name,expected in plan['source_sha256'].items():
            with self.subTest(source=name):
                self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),expected)
    def test_six_worker_configs_and_native_initial_payloads_match(self):
        source=json.loads((ROOT/'configs/P29_stateful_code_v01.json').read_text())
        plan=json.loads((ROOT/old.PLAN).read_text());newplan={**deepcopy(plan),**new.fixed_fields()}
        self.assertEqual(old.MODES,new.MODES);self.assertEqual(old.SEEDS,new.SEEDS)
        self.assertEqual(old.run_order(),new.run_order())
        task=plan['known_tasks'][0]['task_id']
        for rep,num,mode in old.run_order():
            with self.subTest(replication=rep,mode=mode):
                a=old.config_for(source,plan,task,mode,rep);b=new.config_for(source,newplan,task,mode,rep)
                expected=deepcopy(a);expected['run_id']=new.cell_id(rep,num,mode)
                self.assertEqual(b,expected)
                am=old.initial_conversation(source,TASK,mode).for_model(a['observation_page_characters'])[0]
                bm=new.initial_conversation(source,TASK,mode).for_model(b['observation_page_characters'])[0]
                self.assertEqual(am,bm);self.assertEqual(old.tools_for(mode),new.tools_for(mode))
                ac={**a['model'],'seed':a['seed'],'temperature':a['agent_temperature'],'num_predict':a['max_output_tokens']}
                bc={**b['model'],'seed':b['seed'],'temperature':b['agent_temperature'],'num_predict':b['max_output_tokens']}
                self.assertEqual(payload_for(ac,am,old.tools_for(mode)),payload_for(bc,bm,new.tools_for(mode)))

if __name__=='__main__':unittest.main()
