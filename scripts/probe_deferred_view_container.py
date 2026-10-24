"""One bounded two-policy container smoke check; no model or task environment."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import time

from appworld_native_tools import NativeCatalog
from container_api_python import ApiChannel
from deferred_read_obligations import Assumptions
from deferred_view_protocol import ReadAuthority
from persistent_read_view_python import PersistentReadViewPython, ReadViewProgram
from public_api_envelope import PROTOCOL
from public_api_result_transport import PublicResultTransport
from shared_api_reservations import RequestBudget

PLAN = dict(policies=['eager','deferred'], fresh_fixture_per_policy=True, user_programs_per_policy=3,
    client_setup_programs_per_policy=1, max_fixture_requests_per_policy=4,
    requested_program_timeout_seconds=30, active_deadline_checked_before_each_program_seconds=240,
    inherited_container_setup_command_timeouts_seconds={'create':30,'inspect':15},
    automatic_retries=0, model_generations=0, environment_api_requests=0,
    task_evaluations=0, authority='explicit handwritten fixture premises; not inferred from real APIs')
PROGRAMS = [
    "saved=read_view('fixture','read_record',record_id='track')\nprint(saved['title'])",
    "call_api('fixture','change_record',record_id='track',rating=9)\nprint(saved['rating'])",
    "del saved\nv=read_view('fixture','read_record',record_id='track')\nprint(v['title'])\ndel v\nprint(call_api('fixture','note',value='done'))",
]
EXPECTED_STDOUT = ['alpha\n','1\n','alpha\ndone\n']


def fixture_catalog():
    parameters={'read_record':['record_id'],'change_record':['record_id','rating'],'note':['value']}
    catalog=NativeCatalog([{'type':'function','function':{'name':'fixture__'+name,
        'parameters':{'type':'object','properties':{key:{} for key in keys}}}}
        for name,keys in parameters.items()])
    catalog.visible.update(catalog.catalog)
    return catalog


class HandwrittenFixture:
    def __init__(self):
        self.objects = {'track':{'title':'alpha','rating':1}}
        self.requests = []

    def authority(self, action, epoch):
        if (action['app']=='fixture' and action['api']=='read_record'
                and action['args']=={'record_id':'track'}):
            return ReadAuthority(epoch,{'title':self.objects['track']['title']},Assumptions(True,True,True))
        return None

    def request(self, command):
        if command['op']!='call_typed' or len(self.requests)>=PLAN['max_fixture_requests_per_policy']:
            raise ValueError('outside_handwritten_fixture_budget')
        self.requests.append(copy.deepcopy(command))
        action = command['call']; args = action['args']
        if action['app']!='fixture':raise ValueError('not_fixture')
        if action['api']=='read_record':value=copy.deepcopy(self.objects[args['record_id']])
        elif action['api']=='change_record':
            self.objects[args['record_id']]['rating']=args['rating'];value={'changed':True}
        elif action['api']=='note':value=args['value']
        else:raise ValueError('unknown_fixture_api')
        envelope=json.dumps(dict(protocol=PROTOCOL,nonce=command['nonce'],status='returned',value=value))
        return {'ok':True,'result':{'protocol':PROTOCOL,'observation':envelope,'declared_complete':False}}


def probe(storage, output, repo):
    preparation=json.loads((repo/'reports/deferred_view_runtime_preparation_20261024.json').read_text())
    for name, expected in preparation['source_sha256'].items():
        if hashlib.sha256((repo/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('prepared_source_changed: '+name)
    output.mkdir(parents=True,exist_ok=False)
    started=time.monotonic()
    report=dict(plan=PLAN,status='running',source_sha256=preparation['source_sha256'],
        conditions=[dict(policy=p,status='not_attempted',fixture_requests=None) for p in PLAN['policies']])
    def save():
        report['wall_seconds']=time.monotonic()-started
        (output/'status.json').write_text(json.dumps(report,indent=2)+'\n')
    save()
    try:
        for condition in report['conditions']:
            folder=output/condition['policy'];folder.mkdir()
            fixture=HandwrittenFixture();transport=PublicResultTransport(fixture)
            catalog=fixture_catalog()
            budget=RequestBudget(PLAN['max_fixture_requests_per_policy'])
            session=PersistentReadViewPython(storage,folder/'session')
            program=ReadViewProgram(session,budget,authority=fixture.authority,
                                    defer=condition['policy']=='deferred')
            condition.update(status='running',programs=[])
            try:
                for index, source in enumerate(PROGRAMS):
                    remaining=PLAN['active_deadline_checked_before_each_program_seconds']-(time.monotonic()-started)
                    if remaining<=0:raise TimeoutError('fixed_smoke_active_deadline')
                    result=program(source,{},ApiChannel(catalog,transport,budget.limit-budget.spent),
                        storage_root=storage,record_dir=folder/f'program_{index+1}',
                        timeout=min(PLAN['requested_program_timeout_seconds'],remaining))
                    condition['programs'].append(result)
                    if result['status']!='ok' or result['stdout']!=EXPECTED_STDOUT[index]:
                        raise ValueError('handwritten_fixture_observation_mismatch')
                if budget.pending!=0 or budget.spent!=(4 if condition['policy']=='eager' else 3):
                    raise ValueError('handwritten_fixture_accounting_mismatch')
                condition['status']='complete'
            finally:
                condition.update(fixture_requests=len(fixture.requests),budget=budget.snapshot(),
                                 controls=session.controls,cleanup=session.close())
                save()
        report['status']='complete'
        report['observations_equal']=True
    except BaseException as error:
        report.update(status='stopped',error_type=type(error).__name__,error=str(error))
        save()
        raise
    finally:save()
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=probe(args.storage_root.resolve(),args.output.resolve(),Path(__file__).resolve().parents[1])
    print(json.dumps({'status':result['status'],'output':str(args.output)}))


if __name__=='__main__':main()
