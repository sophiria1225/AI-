"""Read only P107 program, shared-budget and schema-forwarding receipts."""
import hashlib
import json
import re


def require(value,reason):
    if not value:raise ValueError(reason)


def read(path,lines=False):
    require(not path.is_symlink() and path.stat().st_size<=16*1024*1024,'bounded_private_receipt_required')
    return [json.loads(x) for x in path.read_text().splitlines()] if lines else json.loads(path.read_text())


def check_call_programs(folder,call_id,events,spans,before):
    outer=[spans[e['span_id']] for e in events if e['call']==call_id and e['stage']=='model_tool']
    records=[]
    parent=folder/'programs'
    if parent.exists():
        records=sorted((p for p in parent.glob(call_id+'_*')
                        if re.fullmatch(call_id+r'_\d{2,}',p.name)),key=lambda p:int(p.name.rsplit('_',1)[1]))
    result=before
    for record in records:
        index=int(record.name.rsplit('_',1)[1])-1
        require(0<=index<len(outer),'program_without_outer_submission')
        action=outer[index]['action']; require(action['name']=='run_python','program_without_run_python')
        submitted=json.loads(action['arguments'])
        payload=read(record/'input_private.json')
        evidence=read(record/'view_program_private.json')
        require(payload['code']==submitted['code'],'generated_source_changed')
        require(evidence['budget_before']==result,'program_reservation_continuity_differs')
        after=evidence['budget_after']; runtime=evidence['result']; observed=outer[index]['observation']
        for key in ('status','stdout','stdout_truncated','api_requests','declared_complete','unknown_effects'):
            require(runtime[key]==observed[key],'model_program_observation_differs:'+key)
        require(after['spent']-result['spent']==runtime['api_requests'],'program_API_budget_disagrees')
        require(0<=after['spent']+after['pending']<=after['limit']
                and after['available']==after['limit']-after['spent']-after['pending'],
                'program_budget_invariant_differs')
        wire=read(record/'wire_private.jsonl',lines=True)
        controls=[x for x in wire if x.get('kind')=='api']
        require(all(x['app']=='__harness_views__' and x['api']=='control' for x in controls),
                'raw_API_bypassed_view_control')
        require(len(controls)==evidence['control_requests'],'control_request_count_differs')
        require(sum(len(json.dumps(x['arguments']['packet'],allow_nan=False).encode()) for x in controls)
                ==evidence['control_request_bytes'],'control_request_bytes_differ')
        forwarded=read(record/'schema_forwarding_private.json')
        require(forwarded['source_sha256']==hashlib.sha256(payload['code'].encode()).hexdigest()
                and forwarded['extra_API_requests']==0,'schema_forwarding_source_differs')
        require(len(forwarded['exchanges'])==len(controls)
                and forwarded['reply_wire_bytes']==sum(x['reply_wire_bytes'] for x in forwarded['exchanges'])
                and forwarded['schema_deliveries']==sum(len(x['new_schema_names']) for x in forwarded['exchanges']),
                'schema_forwarding_totals_differ')
        require(all(e['control_id']==c['id'] for e,c in zip(forwarded['exchanges'],controls,strict=True)),
                'schema_forwarding_request_ids_differ')
        result=after
    return result


def check_budget_events(folder,runtime,api_requests):
    events=read(folder/'request_budget_events_private.json')
    pending=set();seen=set();spent=0
    limit=runtime['budget']['limit']
    for row in events:
        number=row['reservation'];kind=row['kind']
        require(type(number)is int,'reservation_identity_required')
        if kind=='reserve':
            require(number not in seen,'reservation_identity_reused');seen.add(number);pending.add(number)
        else:
            require(kind in ('sent','cancel_unused','not_dispatched') and number in pending,
                    'invalid_reservation_consumption')
            pending.remove(number)
            if kind=='sent':spent+=1
        require(spent+len(pending)<=limit,'historical_reservation_budget_exceeded')
    require(spent==runtime['budget']['spent']==api_requests
            and len(pending)==runtime['budget']['pending'],'final_reservation_event_totals_differ')
    controls=read(folder/'view_control_events_private.json')
    require(sum(x['op']=='read' for x in controls)==runtime['read_requests'],'read_request_inventory_differs')


def program_costs(folder):
    rows=[]
    for path in sorted((folder/'programs').glob('*/view_program_private.json')):
        value=read(path);forwarded=read(path.with_name('schema_forwarding_private.json'))
        rows.append(dict(program=path.parent.name,status=value['result']['status'],
            API_requests=value['result']['api_requests'],budget_before=value['budget_before'],
            budget_after=value['budget_after'],control_requests=value['control_requests'],
            control_request_bytes=value['control_request_bytes'],
            control_reply_bytes_without_schema=value['control_reply_bytes'],
            reply_wire_bytes_including_schema=forwarded['reply_wire_bytes'],
            schema_deliveries=forwarded['schema_deliveries'],
            bootstrap_included=value['setup'] is not None,
            wall_seconds_including_bootstrap=value['result']['wall_seconds']))
    return rows
