"""The original Python/receipt executor plus one bounded, API-free ledger read.

The whole response retains call ordering and original program directory indexes.
Generated Python remains confined to the existing container execution path.
"""
import copy
import json
from container_api_python import ApiChannel, run_program
from native_data_compute import selected_receipts
from observed_obligation_tools import checked_arguments


def execute_obligation_response(message, catalog, bridge, prior, record, *, out, storage,
                     call_id, remaining_api, may_continue, remaining_wall, read_archive,
                     program=run_program, obligation_runtime):
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
                elif fn['name']=='read_obligations':
                    arguments=checked_arguments(fn['arguments'])
                    row['observation']=obligation_runtime.query(arguments,call_id=call_id,tool_index=number)
                    row['obligation_query_index']=len(obligation_runtime.queries)-1
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
                    raise ValueError('use run_python, read_span or read_obligations')
            except (ValueError,KeyError,TypeError) as exc:
                row['observation']={'format_error':str(exc)}
        rows.append(row);record(row)
    return rows
