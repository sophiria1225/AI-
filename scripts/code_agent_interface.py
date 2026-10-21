"""Public-data code interface; inner API calls remain separately accountable."""
import copy
import json

from container_api_python import ApiChannel, run_program
from context_preservation import AGENT_TOOLS
from native_data_compute import selected_receipts

CODE_GUIDE = '''
Use run_python to work with the simulated public APIs. In each fresh Python 3.12
program, call_api(app, api, **arguments) calls one discovered public API and
returns its JSON value (or its exact text if it is not JSON). Initially only
api_docs and supervisor APIs are available. Discover APIs with
call_api("api_docs", "show_api_descriptions", app_name="...") or
call_api("api_docs", "show_api_doc", app_name="...", api_name="...").
api_schemas maps each currently exposed app__api name to its exact public schema;
it updates automatically after documentation discovery. Inspect it for parameters.
After discovery, you may use the API within the same program. Use Python loops,
sets, dictionaries, csv, json and arithmetic to process data and pass computed
values directly to subsequent calls. Each API call is charged individually.
Print the facts/results you need for your next decision. No Python variables
persist across programs. To reuse earlier results, provide the recorded span_ids;
observations then contains those complete prior records (id, action, observation).
Raw API receipts are archived even if not printed; read_span retrieves them.
The container has no host files or network; file operations must use the public
file_system API. No code can use the independent evaluator. Stop after completion.
Code execution is not an independent check of correctness or completeness.
'''
CODE_TOOL = {'type':'function','function':{'name':'run_python',
    'description':'Run bounded Python over prior public receipts and discovered simulated APIs. Print concise results. Each API call consumes the same task API budget.',
    'parameters':{'type':'object','properties':{
        'code':{'type':'string','maxLength':20000},
        'span_ids':{'type':'array','items':{'type':'string'},'uniqueItems':True,'maxItems':160}},
        'required':['code','span_ids'],'additionalProperties':False}}}
CODE_TOOLS = [CODE_TOOL, copy.deepcopy(AGENT_TOOLS[1])]


def execute_response(message, catalog, bridge, prior, record, *, out, storage,
                     call_id, remaining_api, may_continue, remaining_wall, read_archive,
                     program=run_program):
    rows=[]
    calls=message.get('tool_calls') or []
    if not calls:
        row={'action':None,'observation':{'format_error':'tool call required'},
             'api_request_sent':False,'new_tools':[]}
        record(row);return [row]
    snapshot={row['id']:row for row in prior}
    blocked=False
    for number, call in enumerate(calls,1):
        fn=call.get('function',{})
        row={'action':fn,'api_request_sent':False,'new_tools':[]}
        if blocked or not may_continue():
            row['observation']={'not_executed':'completion, unknown effects or run budget'}
        else:
            try:
                args=json.loads(fn['arguments'])
                if fn['name']=='read_span':
                    decoded=catalog.decode(fn)
                    row['observation']=read_archive(decoded['span_id'],decoded.get('offset',0))
                elif fn['name']=='run_python':
                    if (type(args) is not dict or set(args)!={'code','span_ids'}
                            or type(args['code']) is not str or not 0<len(args['code'])<=20000
                            or type(args['span_ids']) is not list or len(args['span_ids'])>160
                            or any(type(x) is not str for x in args['span_ids'])
                            or len(args['span_ids'])!=len(set(args['span_ids']))):
                        raise ValueError('invalid Python arguments')
                    observations=selected_receipts(args['span_ids'],snapshot)
                    channel=ApiChannel(catalog,bridge,remaining_api(),may_continue)
                    inner=[]; receipts=[]
                    def inner_record(item):
                        inner.append(copy.deepcopy(item))
                        sid=record(item,display=False)
                        receipts.append({"span_id":sid,"api":item["action"]["name"],
                                         "api_request_sent":item["api_request_sent"]})
                    result=program(args['code'],observations,channel,storage_root=storage,
                        record_dir=out/'programs'/f'{call_id}_{number:02d}',
                        timeout=max(.01,min(90,remaining_wall())),on_record=inner_record)
                    blocked |= result['status']=='harness_error' or channel.fatal
                    row['effects_unknown']=channel.fatal
                    row['observation']={k:result[k] for k in
                        ('status','stdout','stdout_truncated','api_requests','declared_complete','unknown_effects')}
                    # Stable source IDs are those assigned by the caller. The
                    # caller records inner operations before this outer receipt.
                    row['observation']['api_receipts']=receipts
                    row['observation']['error']=result.get('error',result.get('error_type'))
                    rows.extend(inner)
                else:
                    raise ValueError('use run_python or read_span')
            except (ValueError,KeyError,TypeError) as exc:
                row['observation']={'format_error':str(exc)}
        rows.append(row);record(row)
    return rows
