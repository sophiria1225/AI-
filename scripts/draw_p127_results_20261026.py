"""Private P127 publication renderer. Actual results require completed collection.

Only closed public audit/session/material artifacts are read after the collector
and closure gate. Synthetic preview uses four handwritten pairs and is visibly
marked. No model, API, tokenizer, evaluator, stored code or Docker is executed.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, MaxNLocator

HEAD='0219f774326e7e4e2fdacc6aaaf0c45ea381cfc0'
PLAN_SHA='49edf3731b6d4caf79ef7b90f84b928cb7269ebb541148687e444c2bb9557bff'
COLLECTOR_SHA='dad310c133b37503de270968453935526b1635233874c42cab55d29e6b5c3dd8'
POLICIES=('explicit_joined_fields','automatic_region_joined_fields')
LABELS=('Shared explicit fields','Shared explicit fields + automatic regions')
TASKS=('Photo','Expenses','Refund','CSV')
COLORS=('#4477AA','#228877')
MATERIALS='materials/20261026_p127_results'
REPORT='reports/P127_comparison.json'; SESSION='reports/P127_server_session.json'
PLAN='configs/P127_whole_task_region_projection_v01.json'
ACTIVATION='reports/P127_activation_v01.json'; PREFLIGHT='reports/P127_initial_checks.json'
STATUSES=('evaluated','unevaluated','not_run','incomplete_worker','audit_error')
MECHANISMS=('automatic_region_partial_hits','explicit_field_partial_hits','ordinary_complete_cache_hits')
MECHANISM_LABELS=('Automatic region partial hits','Shared explicit-field partial hits','Ordinary complete-cache hits')
RUNTIME_FIELDS=('program_attempts','program_evidence_records','static_eligible_programs','transformed_programs',
 'ordinary_complete_cache_hits','projection_lookup_requests','projection_partial_hits','projection_complete_lookup_hits',
 'projection_lookup_misses','projection_failure_events','explicit_field_requests','explicit_field_partial_hits',
 'automatic_region_partial_hits','known_control_requests','known_control_request_bytes','known_control_reply_bytes',
 'schema_deliveries','known_schema_reply_wire_bytes','program_wall_seconds','control_wall_seconds_including_backend',
 'projection_lookup_wall_seconds','control_accounting_complete','schema_accounting_complete','execution_trace_accounting_complete')
CORE=('run_id','task_id','projection_policy','checkpoint_policy','record_status','success')

def require(ok,reason):
 if not ok:raise ValueError(reason)
def count(v):return type(v) is int and v>=0
def sha(p):
 p=Path(p);require(p.is_file() and not p.is_symlink() and p.stat().st_size<=64*1024*1024,'bounded_regular_input_required')
 return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
 sha(p);return json.loads(Path(p).read_text())
def same(a,b):return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)
def public_path(root,name):
 require(type(name) is str and not Path(name).is_absolute() and '..' not in Path(name).parts
  and name.split('/')[0] in ('scripts','tests','configs','docs','reports','materials'),'public_relative_source_required')
 p=root/name;require(p.resolve().is_relative_to(root),'public_source_escape');return p
def identity(row):
 m=re.fullmatch(r'BOC_P127_0([1-4])_(EXPLICIT_JOINED_FIELDS|AUTOMATIC_REGION_JOINED_FIELDS)',row['run_id'])
 require(m is not None and row['projection_policy']==m.group(2).lower(),'fixed_slot_identity_required')
 return int(m.group(1)),row['projection_policy']
def aggregate(rows):
 known=[r['known_total_tokens'] for r in rows if count(r.get('known_total_tokens'))]
 unknown=[r['unknown_usage_calls'] for r in rows if count(r.get('unknown_usage_calls'))]
 exact=bool(rows) and len(known)==len(unknown)==len(rows) and sum(unknown)==0
 return dict(planned_conditions=len(rows),accounted_conditions=len(known),
  evaluated_conditions=sum(r['record_status']=='evaluated' for r in rows),
  successful_conditions=sum(r['success'] is True for r in rows),known_token_subtotal=sum(known),
  recorded_unknown_usage_calls=sum(unknown),unknown_usage_count_missing_conditions=len(rows)-len(unknown),
  exact_total_tokens=sum(known) if exact else None,all_condition_usage_known=exact)

def validate_rows(rows,summary,error_count):
 expected={(n,p) for n in range(1,5) for p in POLICIES}
 require(type(rows) is list and len(rows)==8 and {identity(r) for r in rows}==expected,'all_eight_unique_slots_required')
 index={identity(r):r for r in rows};task_ids=[];common=set()
 for n in range(1,5):
  a,b=[index[n,p] for p in POLICIES]
  require(type(a['task_id']) is str and a['task_id']==b['task_id'],'paired_task_identity_required')
  task_ids.append(a['task_id'])
  if a['success'] is b['success'] is True:common.add(n)
 require(len(set(task_ids))==4,'four_distinct_known_tasks_required')
 for row in rows:
  status=row['record_status'];require(status in STATUSES,'known_status_required')
  require(type(row['success']) is bool if status=='evaluated' else row['success'] is None,'official_success_status_disagrees')
  require(row['checkpoint_policy']=='rolling_separate','shared_rolling_checkpoint_required')
  if status not in ('evaluated','unevaluated'):
   require(all(v is None for k,v in row.items() if k not in CORE),'unaccounted_slot_cannot_gain_measurements')
  if status in ('evaluated','unevaluated'):
   require(all(count(row.get(k)) for k in ('known_total_tokens','unknown_usage_calls','model_calls','api_requests','input_tokens','output_tokens')),'accounted_row_requires_known_subtotal_and_attempt_counts')
  for flag in ('execution_trace_accounting_complete','control_accounting_complete','schema_accounting_complete'):
   require(row.get(flag) is None or type(row[flag]) is bool,'runtime_accounting_flag_type')
  for field in ('known_total_tokens','exact_total_tokens','unknown_usage_calls','model_calls','api_requests','projection_hits',*MECHANISMS):
   require(row.get(field) is None or count(row[field]),'nonnegative_count_or_null_required')
  known,unknown=row.get('known_total_tokens'),row.get('unknown_usage_calls')
  require(row.get('exact_total_tokens')==(known if count(known) and unknown==0 else None),'unknown_usage_is_not_exact')
  require(row.get('projection_contract_failed') is None or type(row['projection_contract_failed']) is bool,'contract_flag_type')
  require(row.get('automatic_region_partial_hits')==row.get('projection_hits'),'automatic_hit_alias_differs')
  if row['projection_policy']==POLICIES[0]:require(row.get('automatic_region_partial_hits') in (None,0),'ordinary_arm_cannot_have_automatic_hits')
  if count(row.get('explicit_field_partial_hits')):
   require(count(row.get('explicit_field_requests')) and row['explicit_field_partial_hits']<=row['explicit_field_requests'],'explicit_hits_exceed_requests')
  if count(row.get('input_tokens')) and count(row.get('output_tokens')):
   require(row['input_tokens']+row['output_tokens']==known,'token_subtotal_differs')
  if count(unknown) and count(row.get('model_calls')):require(unknown<=row['model_calls'],'unknown_attempts_exceed_calls')
 groups=[(rows,summary['all_conditions'])]
 require(set(summary['by_policy'])==set(summary['common_success_costs_by_policy'])==set(POLICIES),'fixed_policy_aggregates_required')
 for policy in POLICIES:
  groups.extend([([r for r in rows if r['projection_policy']==policy],summary['by_policy'][policy]),
   ([index[n,policy] for n in sorted(common)],summary['common_success_costs_by_policy'][policy])])
 for subset,given in groups:
  require(all(type(given.get(k)) is type(v) and given[k]==v for k,v in aggregate(subset).items()),'row_derived_aggregate_differs')
 require(type(summary['common_successful_tasks']) is int and summary['common_successful_tasks']==len(common),'common_success_count_differs')
 complete=all(r['record_status']=='evaluated' and count(r.get('known_total_tokens')) and r.get('unknown_usage_calls')==0 for r in rows)
 losses=sum(index[n,POLICIES[0]]['success'] is True and index[n,POLICIES[1]]['success'] is False for n in range(1,5))
 delta=sum(index[n,POLICIES[1]]['known_total_tokens']-index[n,POLICIES[0]]['known_total_tokens'] for n in range(1,5)) if complete else None
 common_delta=sum(index[n,POLICIES[1]]['known_total_tokens']-index[n,POLICIES[0]]['known_total_tokens'] for n in common) if complete else None
 hits=[index[n,POLICIES[1]]['automatic_region_partial_hits'] for n in common]
 gate=bool(complete and error_count==0 and losses==0 and delta<0 and common_delta<0 and common
  and all(count(v) for v in hits) and sum(hits)>=1 and all(r.get('projection_contract_failed') is False for r in rows))
 require(summary['audited_criteria'].get('development_gate_met') is gate,'fixed_gate_disagrees_with_all_rows')
 return dict(phase='P127',fixed_slots=8,model_seed=157,rows=sorted(rows,key=identity),
  by_policy=summary['by_policy'],common_success_costs_by_policy=summary['common_success_costs_by_policy'],
  common_successful_tasks=len(common),audit_error_count=error_count,development_gate_met=gate,
  all_condition_token_difference=delta,common_success_token_difference=common_delta,
  synthetic=False,unknown_is_not_zero=True,general_quality_preservation_claim=False,novel_method_claim=False)

def load_closed(root,closure_path,collector_path,collector_start_path):
 # This must run before reading any P127 report or materials.
 collector=read(collector_path)
 require(collector.get('status')=='complete','completed_collector_required_before_any_results_read')
 start=read(collector_start_path);closure=read(closure_path)
 require(start.get('source_head')==HEAD and start.get('wrapper_sha256')==COLLECTOR_SHA
  and start.get('closure_sha256')==sha(closure_path),'fixed_collector_source_and_closure_required')
 stages=closure.get('stages')
 require(type(stages) is list and [s.get('stage') for s in stages]==['audit','session','report']
  and all(type(s.get('exit_code')) is int and s['exit_code']>=0 for s in stages)
  and all(s['exit_code']==0 for s in stages[1:]),'closed_audit_session_material_stages_required')
 root=Path(root).resolve();hashes={};external={name:sha(p) for name,p in
  [('closure',closure_path),('collector',collector_path),('collector_start',collector_start_path)]}
 copied=collector.get('copied_source_sha256')
 required={REPORT,SESSION,PREFLIGHT,ACTIVATION,*[MATERIALS+'/'+n for n in ('summary.json','conditions.csv','build_manifest.json')]}
 require(type(copied) is dict and required.issubset(copied),'collector_all_public_artifacts_required')
 def bind(name):
  p=public_path(root,name);hashes[name]=sha(p);return p
 for name,value in copied.items():require(sha(bind(name))==value,'collector_copy_changed')
 report,session,summary,manifest,plan,activation=[read(bind(n)) for n in
  (REPORT,SESSION,MATERIALS+'/summary.json',MATERIALS+'/build_manifest.json',PLAN,ACTIVATION)]
 require(hashes[PLAN]==PLAN_SHA,'fixed_P127_plan_bytes_required')
 require(report.get('phase')==session.get('phase')==summary.get('phase')==manifest.get('phase')=='P127'
  and plan.get('experiment')=='P127' and plan.get('model_seed')==157,'fixed_phase_seed_required')
 require(report.get('batch_status') in ('complete','stopped') and report.get('owned_processes_absent') is True
  and session.get('status')=='stopped' and session.get('owned_processes_absent') is True,'closed_owned_cohort_required')
 require(closure.get('audit_sha256')==hashes[REPORT]==session.get('audit_source_sha256')
  and closure.get('session_sha256')==hashes[SESSION]
  and closure.get('report_manifest_sha256')==hashes[MATERIALS+'/build_manifest.json'],'closure_hash_binding_differs')
 for name,value in manifest['source_sha256'].items():require(sha(bind(name))==value,'materials_source_changed')
 for name,value in manifest['artifact_sha256'].items():require('/' not in name and sha(bind(MATERIALS+'/'+name))==value,'materials_artifact_changed')
 for mapping in (activation['source_hashes'],plan['source_sha256']):
  require(type(mapping) is dict and mapping,'frozen_source_map_required')
  for name,value in mapping.items():require(sha(bind(name))==value,'frozen_source_changed')
 require(report.get('auditor_sha256')==hashes.get('scripts/audit_whole_task_region_projection.py')
  and session.get('inspector_sha256')==hashes.get('scripts/inspect_whole_task_region_projection_session.py'),'auditor_inspector_source_binding')
 require(manifest.get('activation_bound_source_count')==len(activation['source_hashes'])
  and manifest.get('activation_source_mapping_sha256')==hashlib.sha256(json.dumps(activation['source_hashes'],sort_keys=True).encode()).hexdigest(),'activation_source_mapping_binding')
 require(report.get('plan_sha256')==hashes[PLAN] and report.get('activation_sha256')==hashes[ACTIVATION]
  and activation.get('preflight_sha256')==hashes[PREFLIGHT],'plan_activation_preflight_binding')
 require(session.get('pipeline_source_sha256')==report.get('pipeline_status_sha256')
  and session.get('source_sha256')==report.get('server_final_sha256'),'pipeline_server_binding')
 errors=report.get('audit_errors')
 require(type(errors) is list and summary.get('audit_error_count')==closure.get('audit_errors')==collector.get('audit_errors')==len(errors),'audit_error_count_disagrees')
 require(all(same(report.get(k),v) for k,v in summary['audited_criteria'].items()),'audited_criteria_disagree')
 rows=summary['conditions'];raw_rows=report.get('rows')
 require(type(raw_rows) is list and len(raw_rows)==8 and len({identity(r) for r in raw_rows})==8,'eight_audit_slots_required')
 raw={identity(r):r for r in raw_rows}
 with bind(MATERIALS+'/conditions.csv').open(newline='') as handle:csv_rows=list(csv.DictReader(handle))
 require(len(csv_rows)==8 and len({identity(r) for r in csv_rows})==8,'eight_csv_slots_required')
 csv_map={identity(r):r for r in csv_rows}
 for row in rows:
  original=raw[identity(row)];csv_row=csv_map[identity(row)]
  require(set(row)==set(csv_row) and all(csv_row[k]==('' if v is None else str(v)) for k,v in row.items()),'csv_material_fields_disagree')
  for field,value in row.items():
   if field=='exact_total_tokens':continue
   if row['record_status'] not in ('evaluated','unevaluated') and field not in CORE:continue
   wanted=(original.get('projection_runtime') or {}).get(field) if field in RUNTIME_FIELDS else original.get(field)
   require(same(value,wanted),'audited_public_field_disagrees')
 data=validate_rows(rows,summary,len(errors))
 for key in ('planned_conditions','evaluated_conditions','known_token_subtotal','recorded_unknown_usage_calls','unknown_usage_count_missing_conditions','exact_total_tokens'):
  require(same(collector.get(key),summary['all_conditions'][key]),'collector_aggregate_differs')
 require(collector.get('development_gate_met') is data['development_gate_met'] and collector.get('audit_passed') is (not errors),'collector_gate_or_audit_status_differs')
 for name in ('additional_model_calls','additional_API_requests','additional_evaluations'):
  require(type(collector.get(name)) is int and collector[name]==0,'collector_cannot_add_experiment_calls')
 require(all(sha(public_path(root,n))==v for n,v in hashes.items()),'source_changed_during_read')
 return data,hashes,external

def outcome(row):
 text='Success' if row['success'] is True else 'Failure' if row['success'] is False else 'Not evaluated'
 if row.get('projection_contract_failed') is True:text+='; contract stop'
 return text

def draw_bars(ax,records,field,*,tokens=False):
 width=.36;values=[r.get(field) for r in records if r.get(field) is not None];maximum=max(values+[1]);ceiling=maximum*1.50
 for r in records:
  n,p=identity(r);arm=POLICIES.index(p);x=n-1+(arm-.5)*width;value=r.get(field)
  incomplete=tokens and r.get('exact_total_tokens') is None
  if value is None:
   label='NA\nNot measured'
   if r['record_status'] not in ('evaluated','unevaluated'):label+='\n'+r['record_status'].replace('_',' ')
  else:
   ax.bar(x,value,width*.88,color=COLORS[arm],edgecolor='#263238',lw=.5,hatch='///' if incomplete else None,zorder=3)
   label=f'{value:,}'+(' known' if incomplete else '')
  if tokens:
   label+='\n'+outcome(r).replace('; ','\n')
   if incomplete and value is not None:label+='\nTotal unknown'
  elif value is not None and r.get('execution_trace_accounting_complete') is False:label+='\nTrace incomplete'
  y=(value or 0)+maximum*.025 if value is not None else maximum*.05
  ax.text(x,y,label,ha='center',va='bottom',fontsize=8,linespacing=1.15)
 ax.set_xticks(range(4),TASKS);ax.set_xlim(-.65,3.65);ax.set_ylim(0,ceiling)
 ax.yaxis.set_major_locator(MaxNLocator(nbins=5,integer=True));ax.yaxis.grid(True,alpha=.2);ax.set_axisbelow(True)
 if tokens:ax.yaxis.set_major_formatter(FuncFormatter(lambda value,_:f'{value/1000:,.0f}k'))

def save(fig,path):
 for ext in ('png','pdf'):fig.savefig(path.with_suffix('.'+ext),dpi=220,metadata={'Creator':Path(__file__).name})
 plt.close(fig)

def render(data,output):
 plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'pdf.fonttype':42,'ps.fonttype':42,'axes.spines.top':False,'axes.spines.right':False})
 badge='SYNTHETIC PREVIEW — NOT P127 RESULTS' if data['synthetic'] else 'P127 — fixed known-task development comparison'
 legend=[Patch(facecolor=c,label=l) for c,l in zip(COLORS,LABELS)]
 fig,(ax,total)=plt.subplots(2,1,figsize=(13,10),gridspec_kw={'height_ratios':[2.4,1]})
 draw_bars(ax,data['rows'],'known_total_tokens',tokens=True);ax.set_ylabel('Whole-job logical input + output tokens')
 ax.set_title('All eight task–policy conditions (official outcomes retained)',loc='left',fontsize=11)
 groups=[('All four tasks',data['by_policy']),('Common-success subset',data['common_success_costs_by_policy'])]
 width=.32;maxima=[]
 for i,(label,group) in enumerate(groups):
  for arm,p in enumerate(POLICIES):
   a=group[p];value=a['known_token_subtotal'] if a['accounted_conditions'] else None;maxima.append(value or 0)
   x=i+(arm-.5)*width
   if value is None:total.text(x,.08,'NA',transform=total.get_xaxis_transform(),ha='center',fontweight='bold');continue
   exact=a['exact_total_tokens'] is not None
   total.bar(x,value,width*.88,color=COLORS[arm],edgecolor='#263238',lw=.5,hatch=None if exact else '///')
   total.annotate(f'{value:,}'+(' known\nTotal unknown' if not exact else ''),(x,value),xytext=(0,5),textcoords='offset points',ha='center',fontsize=8)
 total.set_ylim(0,max(maxima+[1])*1.42);total.set_xticks(range(2),[f'All four tasks (4 pairs)',f'Common success ({data["common_successful_tasks"]} pairs)'])
 total.set_ylabel('Logical tokens');total.yaxis.set_major_formatter(FuncFormatter(lambda v,_:f'{v/1000:,.0f}k'));total.grid(axis='y',alpha=.2);total.set_axisbelow(True)
 total.set_title('Whole-cohort and common-success costs are separate summaries',loc='left',fontsize=11)
 fig.suptitle(badge,fontsize=16,y=.985);fig.legend(handles=legend+[Patch(facecolor='white',hatch='///',edgecolor='black',label='Known subtotal only')],loc='upper center',bbox_to_anchor=(.5,.948),ncol=2,frameon=False)
 note=('All roles, separate summaries, failures and recovery are included. NA is missing, not zero; failed cheap cells stay visible.\n'
  f'Fixed adoption gate: {data["development_gate_met"]}. Audit errors: {data["audit_error_count"]}. Common-success cost does not replace all-task cost.\n'
  'Four already exposed tasks; seed 157; shared rolling-separate checkpoint. No general quality, noninferiority or novelty claim.')
 fig.text(.075,.025,note,fontsize=9,linespacing=1.5)
 fig.subplots_adjust(left=.09,right=.98,top=.85,bottom=.15,hspace=.42);save(fig,output/'p127_tokens_outcomes')
 fig,axes=plt.subplots(3,1,figsize=(13,11.2))
 for ax,field,label in zip(axes,MECHANISMS,MECHANISM_LABELS):
  draw_bars(ax,data['rows'],field);ax.set_ylabel('Observed host count');ax.set_title(label,loc='left',fontsize=11)
 fig.suptitle(badge,fontsize=16,y=.985);fig.legend(handles=legend,loc='upper center',bbox_to_anchor=(.5,.945),ncol=2,frameon=False)
 note=('Automatic partial use is separate from the explicit-field capability and ordinary cache shared by both policies.\n'
  'Each mechanism is shown independently. Hits are not net API savings, and neither hits nor wire bytes are model tokens.\n'
  'NA is missing, not zero. Incomplete trace flags remain visible. These counts alone do not establish the token or quality goal.')
 fig.text(.075,.02,note,fontsize=9,linespacing=1.5);fig.subplots_adjust(left=.09,right=.98,top=.865,bottom=.13,hspace=.48)
 save(fig,output/'p127_mechanism_use')

def synthetic_data():
 # Handwritten unrelated values; deliberately includes failures, unknown usage,
 # a missing slot, and successful official evaluation plus a contract stop.
 specs=[(120000,0,True,0,2,3,False),(105000,0,True,7,4,2,False),
        (80000,0,True,0,0,1,False),(99000,0,True,3,2,1,True),
        (60000,0,False,0,1,2,False),(15000,0,False,2,0,1,False),
        (132000,1,None,0,0,0,False),(None,None,None,None,None,None,None)]
 rows=[]
 for i,(tokens,unknown,success,automatic,explicit,cache,failed) in enumerate(specs):
  n=i//2+1;p=POLICIES[i%2];status='not_run' if tokens is None else 'unevaluated' if success is None else 'evaluated'
  row=dict(run_id=f'BOC_P127_0{n}_{p.upper()}',task_id=f'SYNTHETIC_TASK_{n}',projection_policy=p,checkpoint_policy='rolling_separate',record_status=status,success=success,
   known_total_tokens=tokens,unknown_usage_calls=unknown,exact_total_tokens=tokens if unknown==0 else None,
   input_tokens=tokens-3000 if tokens is not None else None,output_tokens=3000 if tokens is not None else None,
   model_calls=5 if tokens is not None else None,api_requests=12 if tokens is not None else None,
   projection_hits=automatic,automatic_region_partial_hits=automatic,explicit_field_partial_hits=explicit,
   explicit_field_requests=explicit,ordinary_complete_cache_hits=cache,projection_contract_failed=failed,
   execution_trace_accounting_complete=True if tokens is not None else None)
  rows.append(row)
 common={1,2}
 summary=dict(all_conditions=aggregate(rows),by_policy={p:aggregate([r for r in rows if r['projection_policy']==p]) for p in POLICIES},
  common_successful_tasks=2,common_success_costs_by_policy={p:aggregate([r for r in rows if identity(r)[0] in common and r['projection_policy']==p]) for p in POLICIES},
  audited_criteria={'development_gate_met':False})
 data=validate_rows(rows,summary,0);data['synthetic']=True;return data

def main(args):
 if args.synthetic_preview:
  require(not any((args.repo_root,args.closure_record,args.collector_record,args.collector_start)),'synthetic_mode_cannot_read_real_artifacts')
  data=synthetic_data();hashes={};external={}
 else:
  require(all((args.repo_root,args.closure_record,args.collector_record,args.collector_start)),'closed_artifact_and_collector_paths_required')
  data,hashes,external=load_closed(args.repo_root,args.closure_record,args.collector_record,args.collector_start)
 output=Path(args.output_dir).resolve();require(not output.exists() and not output.is_symlink(),'new_output_directory_required')
 output.mkdir(parents=True,exist_ok=False)
 render(data,output)
 (output/'figure_data.json').write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
 command=(f'python {Path(__file__).name} --synthetic-preview --output-dir NEW_DIRECTORY' if data['synthetic'] else
  f'python {Path(__file__).name} --repo-root CLOSED_PUBLIC_REPO --closure-record P127_closure_once_end.json --collector-record P127_report_collector_once_end.json --collector-start P127_report_collector_once_start.json --output-dir NEW_DIRECTORY')
 note=f'''# P127 figures {'— SYNTHETIC PREVIEW, NOT ACTUAL RESULTS' if data['synthetic'] else ''}

Reproduction: `{command}` with Python and matplotlib {matplotlib.__version__}. Both figures are saved as PNG and PDF. Existing output directories are never overwritten.

The cost figure retains every task/policy, official success/failure/unevaluated state and contract-stop flag. A hatched bar is a known subtotal; NA is missing data, never zero. Successful official evaluation can coexist with a harness contract stop. All-task totals and common-success totals are distinct. A cheap failed task is not quality-preserving savings.

The mechanism figure separately shows automatic-region partial hits, shared explicit-field partial hits and ordinary full-cache hits. No sum is called net API savings or token savings. Counts with incomplete execution traces are marked. No overlapping time quantities are stacked; durations are deliberately outside these two figures.

Only four already exposed tasks, seed 157, and shared rolling-separate checkpoint are represented. A positive fixed development gate would still not establish general quality preservation, noninferiority or novelty. A false gate is retained unchanged. All missing slots and audit errors remain visible.

Actual rendering requires the fixed collector source/head and complete collector record, closed audit/server/manifest hashes, every frozen source, all eight public rows, exact CSV correspondence and independently recomputed all/common aggregates and fixed gate. This renderer never reads raw task records, stored generated programs, prompts, reasoning or evaluator text. Synthetic preview uses handwritten data only and does not claim closure or measured outcomes.
'''
 (output/'README.md').write_text(note)
 if not data['synthetic']:require(all(sha(public_path(Path(args.repo_root).resolve(),n))==v for n,v in hashes.items()),'source_changed_during_render')
 result=dict(phase='P127',synthetic_preview=data['synthetic'],actual_results=not data['synthetic'],source_sha256=hashes,
  closure_collector_sha256=external,renderer_sha256=sha(__file__),matplotlib_version=matplotlib.__version__,
  artifact_sha256={p.name:sha(p) for p in sorted(output.iterdir())},all_eight_slots_retained=True,
  collector_and_closed_public_artifacts_verified=not data['synthetic'],unknown_is_not_zero=True,
  model_API_evaluator_tokenizer_calls=0,stored_program_execution=0,outcome_based_selection=False)
 (output/'output_manifest.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
 return dict(synthetic=data['synthetic'],conditions=8,output_directory=str(output))

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo-root',type=Path);p.add_argument('--closure-record',type=Path)
 p.add_argument('--collector-record',type=Path);p.add_argument('--collector-start',type=Path)
 p.add_argument('--synthetic-preview',action='store_true');p.add_argument('--output-dir',type=Path,required=True)
 print(json.dumps(main(p.parse_args())))
