#!/usr/bin/env python3
"""Build editable native Excel tables from the frozen manuscript results.

No charts, pictures, model calls, API requests or new experiments are created.
Edit the two run-data sheets in Excel to recalculate the result tables and
comparison formulas. --output-dir must name a new directory.
"""
from __future__ import annotations
import argparse, hashlib, json, re, zipfile
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET
import xlsxwriter

FONT='Hiragino Sans'
MODES={'single_checkpoint':'専用1回方式','rolling_separate':'専用反復方式','rolling_inline':'行動併記方式'}
TASKS={'34d9492_1':'写真操作','3c13f5a_1':'精算','60d0b5b_1':'返金','6104387_1':'CSV処理'}
INTERFACES={'documented':'文書必須','named':'名前参照'}
CONDITIONS={'ordinary':'通常継続','evidence_stop':'終了制御'}
SHEETS=['表1_要約方式','表2_終了制御','実験A_実行','実験B_実行','集計','説明']
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def make_workbook(data,path):
 wb=xlsxwriter.Workbook(path)
 wb.set_properties({'title':'履歴要約方式と終了制御の結果表','author':'','created':datetime(2026,10,30),'comments':'Frozen study A/B results; independent studies; no result graphs.'})
 wb.set_calc_mode('auto')
 text=wb.add_format({'font_name':FONT,'font_size':11})
 header=wb.add_format({'font_name':FONT,'font_size':11,'bold':True,'font_color':'#202020','bg_color':'#EAF0F7','text_wrap':True,'valign':'vcenter'})
 integer=wb.add_format({'font_name':FONT,'font_size':11,'num_format':'#,##0'})
 total=wb.add_format({'font_name':FONT,'font_size':11,'bold':True,'num_format':'#,##0','top':1})
 percent=wb.add_format({'font_name':FONT,'font_size':11,'num_format':'0.00%;-0.00%'})
 sheets=[wb.add_worksheet(name) for name in SHEETS]
 t1,t2,a,b,s,info=sheets
 for ws in sheets:
  ws.hide_gridlines(2);ws.set_column('A:A',18,text);ws.set_column('B:J',20,integer);ws.set_default_row(20);ws.freeze_panes(1,1);ws.set_margins(.3,.3,.4,.4);ws.set_paper(9);ws.set_landscape();ws.fit_to_pages(1,1)
 formulas={};raw_values={}
 def formula(ws,cell,expr,value,fmt=integer):
  ws.write_formula(cell,expr,fmt,value);formulas[(ws.name,cell)]=(expr,value)
 def table(ws,name,heads,rows):
  ws.add_table(0,0,len(rows),len(heads)-1,{'name':name,'style':'Table Style Light 9','autofilter':False,'columns':[{'header':h,'header_format':header,'format':text if i<2 else integer} for i,h in enumerate(heads)],'data':rows})
  ws.set_row(0,30);ws.print_area(0,0,len(rows)+3,len(heads)-1)
 heads_a=['課題','方式','総トークン数','入力トークン数','出力トークン数','モデル呼出し数','API要求数','成功','要約採用回数','使用量不明件数']
 rows_a=[[TASKS[r['task_id']],MODES[r['checkpoint_policy']],r['known_total_tokens'],r['input_tokens'],r['output_tokens'],r['model_calls'],r['api_requests'],int(r['success']),r['checkpoint_installations'],r['unknown_usage_calls']] for r in data['study_A']['rows']]
 heads_b=['API条件','終了方法','総トークン数','入力トークン数','出力トークン数','モデル呼出し数','API要求数','成功','使用量不明件数']
 rows_b=[[INTERFACES[r['interface']],CONDITIONS[r['condition']],r['known_total_tokens'],r['input_tokens'],r['output_tokens'],r['model_calls'],r['api_requests'],int(r['official_success']),r['unknown_usage_calls']] for r in data['study_B']['rows']]
 table(a,'StudyARuns',heads_a,rows_a);table(b,'StudyBRuns',heads_b,rows_b)
 raw_values[a.name]=rows_a;raw_values[b.name]=rows_b
 for ws in [a,b]:ws.freeze_panes(1,2);ws.set_column('A:B',18,text)
 table(t1,'SummaryResults',['課題',*MODES.values()],[[task,None,None,None] for task in TASKS.values()])
 t1.set_column('B:D',20,integer)
 mode_totals=[]
 for i,(task_id,task) in enumerate(TASKS.items(),2):
  for j,(mode,label) in enumerate(MODES.items(),1):
   col=chr(ord('A')+j);value=next(r['known_total_tokens'] for r in data['study_A']['rows'] if r['task_id']==task_id and r['checkpoint_policy']==mode)
   formula(t1,f'{col}{i}',f'=SUMIFS(\'実験A_実行\'!$C$2:$C$13,\'実験A_実行\'!$A$2:$A$13,$A{i},\'実験A_実行\'!$B$2:$B$13,{col}$1)',value)
 t1.write('A6','合計',total)
 for j,mode in enumerate(MODES,1):
  col=chr(ord('A')+j);value=sum(r['known_total_tokens'] for r in data['study_A']['rows'] if r['checkpoint_policy']==mode);mode_totals.append(value)
  formula(t1,f'{col}6',f'=SUM({col}2:{col}5)',value,total)
 t1.write('A8','単位はトークン。全12実行で成功し、使用量の欠測はなかった。',text);t1.print_area('A1:D8')
 order=[(interface,condition) for interface in INTERFACES for condition in CONDITIONS]
 table(t2,'TerminationResults',['API条件','終了方法','総トークン数','モデル呼出し数','API要求数'],[[INTERFACES[i],CONDITIONS[c],None,None,None] for i,c in order])
 for n,(interface,condition) in enumerate(order,2):
  row=next(r for r in data['study_B']['rows'] if r['interface']==interface and r['condition']==condition)
  for target,source,key in [('C','C','known_total_tokens'),('D','F','model_calls'),('E','G','api_requests')]:
   formula(t2,f'{target}{n}',f'=SUMIFS(\'実験B_実行\'!${source}$2:${source}$5,\'実験B_実行\'!$A$2:$A$5,A{n},\'実験B_実行\'!$B$2:$B$5,B{n})',row[key])
 t2.write('A7','全4実行で成功し、使用量の欠測はなかった。',text);t2.print_area('A1:E7')
 s.write('A1','実験A：4課題の合計',header)
 s.write_row('A2',['方式','総トークン数','成功数','要約採用回数','使用量不明件数'],header)
 for n,(mode,label) in enumerate(MODES.items(),3):
  rows=[r for r in data['study_A']['rows'] if r['checkpoint_policy']==mode];s.write(f'A{n}',label,text)
  formula(s,f'B{n}',f'=SUMIFS(\'実験A_実行\'!$C$2:$C$13,\'実験A_実行\'!$B$2:$B$13,A{n})',sum(r['known_total_tokens'] for r in rows))
  formula(s,f'C{n}',f'=COUNTIFS(\'実験A_実行\'!$B$2:$B$13,A{n},\'実験A_実行\'!$H$2:$H$13,1)',sum(int(r['success']) for r in rows))
  formula(s,f'D{n}',f'=SUMIFS(\'実験A_実行\'!$I$2:$I$13,\'実験A_実行\'!$B$2:$B$13,A{n})',sum(r['checkpoint_installations'] for r in rows))
  formula(s,f'E{n}',f'=SUMIFS(\'実験A_実行\'!$J$2:$J$13,\'実験A_実行\'!$B$2:$B$13,A{n})',sum(r['unknown_usage_calls'] for r in rows))
 s.write('A8','実験B：同じ写真課題の2条件',header)
 s.write_row('A9',['API条件','通常継続','終了制御','削減率','通常継続の成功数','終了制御の成功数','使用量不明件数'],header);s.set_row(8,34)
 for n,(interface,label) in enumerate(INTERFACES.items(),10):
  rows={r['condition']:r for r in data['study_B']['rows'] if r['interface']==interface};s.write(f'A{n}',label,text)
  for target,condition in [('B','ordinary'),('C','evidence_stop')]:
   formula(s,f'{target}{n}',f'=SUMIFS(\'実験B_実行\'!$C$2:$C$5,\'実験B_実行\'!$A$2:$A$5,A{n},\'実験B_実行\'!$B$2:$B$5,{target}$9)',rows[condition]['known_total_tokens'])
  ordinary=rows['ordinary']['known_total_tokens'];stop=rows['evidence_stop']['known_total_tokens']
  formula(s,f'D{n}',f'=(B{n}-C{n})/B{n}',(ordinary-stop)/ordinary,percent)
  for target,source,condition in [('E','B','ordinary'),('F','C','evidence_stop')]:
   formula(s,f'{target}{n}',f'=COUNTIFS(\'実験B_実行\'!$A$2:$A$5,A{n},\'実験B_実行\'!$B$2:$B$5,{source}$9,\'実験B_実行\'!$H$2:$H$5,1)',int(rows[condition]['official_success']))
  formula(s,f'G{n}',f'=SUMIFS(\'実験B_実行\'!$I$2:$I$5,\'実験B_実行\'!$A$2:$A$5,A{n})',sum(r['unknown_usage_calls'] for r in rows.values()))
 s.write('A15','実験A：4課題合計の方式間比較',header)
 s.write_row('A16',['対象方式','基準方式','差分トークン数','差分率'],header)
 for n,target,base in [(17,1,0),(18,2,0),(19,2,1)]:
  labels=list(MODES.values());s.write_row(n-1,0,[labels[target],labels[base]],text)
  formula(s,f'C{n}',f'=B{target+3}-B{base+3}',mode_totals[target]-mode_totals[base])
  formula(s,f'D{n}',f'=C{n}/B{base+3}',(mode_totals[target]-mode_totals[base])/mode_totals[base],percent)
 s.write('A21','差分＝対象方式−基準方式。負の値は削減を表す。実験AとBの削減率は合算しない。',text);s.print_area('A1:G21')
 info.set_column('A:A',115,text)
 lines=[
  '編集方法：実験A_実行と実験B_実行の元データを編集すると、表1・表2と集計式が更新される。',
  '表1・表2と元データは編集可能なExcelのネイティブ表。結果グラフと画像は含まない。',
  '専用は要約専用のモデル呼出しを表す。方式名は本稿で比較する条件の名称である。',
  '専用1回方式：要約専用の呼出しで候補を作る。要約機会は最大1回。',
  '専用反復方式：要約専用の呼出しを繰り返す。前の採用要約と新たな古い履歴をまとめる。要約機会は最大3回。',
  '行動併記方式：行動と要約候補を同じモデル応答で生成する。要約専用の追加呼出しはなく、要約機会は最大3回。',
  '要約機会と採用回数は異なる。不採用の場合も要約機会を1回使ったと数える。',
  '実験Bの介入は終了制御、API実行記録を検査する処理は完了判定と呼ぶ。',
  '総トークン数は要約専用の生成を含む全モデル呼出しの入力と出力の合計。キャッシュされた入力も含む。',
  '総トークン数は論理トークンの指標であり、金銭課金や時間を直接表さない。',
  '成功は実行終了後の公式評価器による。実験Aの全12実行と実験Bの全4実行で成功、使用量欠測なし。',
  '実験AとBは独立した既知課題の比較であり、組合せ効果や一般的な品質保証は評価していない。',
  '実験Bでは13データベースのハッシュが一致したが、要求・応答全文の厳密な先頭一致は成立しなかった。',
  '元データは同梱のresults_data.json。新しい実験値は追加していない。',
 ]
 for i,line in enumerate(lines):info.write(i,0,line,text)
 info.print_area(0,0,len(lines)-1,0);t1.activate();wb.close()
 return formulas,raw_values

def read_cells(z,path,strings):
 root=ET.fromstring(z.read(path));cells={};forms={}
 for c in root.findall('.//s:sheetData/s:row/s:c',NS):
  value=c.find('s:v',NS);f=c.find('s:f',NS)
  if value is None:continue
  v=value.text
  if c.attrib.get('t')=='s':v=strings[int(v)]
  elif c.attrib.get('t') not in ['str','inlineStr']:v=float(v)
  cells[c.attrib['r']]=v
  if f is not None:forms[c.attrib['r']]=f.text
 return cells,forms

def validate(path,expected_formulas,raw):
 with zipfile.ZipFile(path) as z:
  assert not any(n.startswith('xl/charts/') or n.startswith('xl/media/') for n in z.namelist())
  strings=[''.join(node.itertext()) for node in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si',NS)]
  count=0
  for i,name in enumerate(SHEETS,1):
   cells,forms=read_cells(z,f'xl/worksheets/sheet{i}.xml',strings);count+=len(forms)
   for (sheet,cell),(expr,value) in expected_formulas.items():
    if name==sheet:
     assert forms[cell]==expr.lstrip('=')
     assert abs(cells[cell]-value)<1e-9,(name,cell,cells[cell],value)
   if name in raw:
    for rowno,row in enumerate(raw[name],2):
     for col,value in enumerate(row):assert cells[f'{chr(ord("A")+col)}{rowno}']==value
  assert count==57==len(expected_formulas)
  tables=[]
  for filename in sorted(n for n in z.namelist() if re.fullmatch(r'xl/tables/table[0-9]+\.xml',n)):
   table=ET.fromstring(z.read(filename));tables.append({'name':table.attrib['name'],'ref':table.attrib['ref']})
  assert len(tables)==4
 return {'native_tables':4,'native_charts':0,'embedded_images':0,'formula_count':count,'all_16_run_values_from_source':True,'all_formula_caches_checked':True,'sheets':SHEETS,'tables':tables}

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--data',type=Path,required=True);ap.add_argument('--output-dir',type=Path,required=True);args=ap.parse_args()
 data=json.loads(args.data.read_text());assert len(data['study_A']['rows'])==12 and len(data['study_B']['rows'])==4 and data['studies_pooled'] is False
 out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False);xlsx=out/'results_tables.xlsx';formulas,raw=make_workbook(data,xlsx);validation=validate(xlsx,formulas,raw)
 record={'version':'v17','data_sha256':sha(args.data),'workbook_sha256':sha(xlsx),'script_sha256':sha(__file__),'xlsxwriter_version':xlsxwriter.__version__,'workbook_validation':validation,'result_graphs_included':False,'independent_studies_not_pooled':True,'method_names':list(MODES.values()),'termination_condition_names':list(CONDITIONS.values()),'comparison_rate_note':'A difference rate=(target−baseline)/baseline; B reduction rate=(ordinary−control)/ordinary.','native_Microsoft_Excel_render_verified':False,'model_API_eval_calls':0,'outputs':{'results_tables.xlsx':sha(xlsx)}}
 (out/'excel_tables_manifest.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n');print(json.dumps(record,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
