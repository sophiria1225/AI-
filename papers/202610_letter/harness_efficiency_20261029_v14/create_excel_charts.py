#!/usr/bin/env python3
"""Build editable Excel charts and export those same charts through LibreOffice.

Requires XlsxWriter, PyMuPDF and CairoSVG. The Excel workbook contains native
OOXML charts backed by cell formulas, not raster chart images. The exported
manuscript figures are crops of this workbook's LibreOffice PDF output.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, subprocess, tempfile, zipfile
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET
import xlsxwriter
import pymupdf
import cairosvg

BLUE='#4C78A8'; ORANGE='#F28E2B'; FONT='Hiragino Sans'
W_MM=65; H_MM=58
FIXED=datetime(2026,10,29)
MODES={'single_checkpoint':'Single','rolling_separate':'Separate','rolling_inline':'Inline'}
TASKS={'34d9492_1':'写真操作','3c13f5a_1':'精算','60d0b5b_1':'返金','6104387_1':'CSV処理'}
INTERFACES={'documented':'文書必須','named':'名前参照'}
CONDITIONS={'ordinary':'通常継続','evidence_stop':'完了判定'}
NS={'c':'http://schemas.openxmlformats.org/drawingml/2006/chart','a':'http://schemas.openxmlformats.org/drawingml/2006/main','s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def make_workbook(data,path):
 wb=xlsxwriter.Workbook(path)
 wb.set_properties({'title':'LLMエージェントの実験結果と編集可能なグラフ','author':'','created':FIXED,'comments':'Closed study A/B aggregates; independent studies, not pooled.'})
 wb.set_calc_mode('auto')
 header=wb.add_format({'font_name':FONT,'font_size':11,'bold':True,'bg_color':'#EAF0F7','border':1,'text_wrap':True})
 text=wb.add_format({'font_name':FONT,'font_size':11})
 integer=wb.add_format({'font_name':FONT,'font_size':11,'num_format':'#,##0'})
 decimal=wb.add_format({'font_name':FONT,'font_size':11,'num_format':'0.000'})
 percent=wb.add_format({'font_name':FONT,'font_size':11,'num_format':'0.00%'})
 chart_sheets=[]
 for name in ['図2_実験A','図3_実験B']:
  ws=wb.add_worksheet(name);ws.hide_gridlines(2);ws.set_tab_color(BLUE if not chart_sheets else ORANGE)
  ws.set_margins(.25,.25,.25,.25);ws.set_header('');ws.set_footer('');ws.set_paper(9)
  ws.set_column('A:N',5);ws.set_default_row(15);ws.print_area('A1:N31');ws.set_print_scale(100);ws.set_zoom(100)
  chart_sheets.append(ws)
 a=wb.add_worksheet('実験A_結果');b=wb.add_worksheet('実験B_結果');s=wb.add_worksheet('集計');info=wb.add_worksheet('説明')
 headers_a=['課題','方式','総トークン数','入力トークン数','出力トークン数','モデル呼出し数','API要求数','成功','要約採用回数','使用量不明件数']
 headers_b=['API条件','終了方法','総トークン数','入力トークン数','出力トークン数','モデル呼出し数','API要求数','成功','使用量不明件数']
 for ws,heads in [(a,headers_a),(b,headers_b)]:
  ws.freeze_panes(1,2);ws.hide_gridlines(2);ws.write_row(0,0,heads,header);ws.set_row(0,34);ws.set_column(0,1,16,text);ws.set_column(2,len(heads)-1,18,integer);ws.autofilter(0,0,12 if ws is a else 4,len(heads)-1);ws.set_landscape();ws.fit_to_pages(1,1)
 for i,row in enumerate(data['study_A']['rows'],1):
  a.write_row(i,0,[TASKS[row['task_id']],MODES[row['checkpoint_policy']],row['known_total_tokens'],row['input_tokens'],row['output_tokens'],row['model_calls'],row['api_requests'],int(row['success']),row['checkpoint_installations'],row['unknown_usage_calls']])
 for i,row in enumerate(data['study_B']['rows'],1):
  b.write_row(i,0,[INTERFACES[row['interface']],CONDITIONS[row['condition']],row['known_total_tokens'],row['input_tokens'],row['output_tokens'],row['model_calls'],row['api_requests'],int(row['official_success']),row['unknown_usage_calls']])
 a.print_area('A1:J13');b.print_area('A1:I5')
 s.hide_gridlines(2);s.set_column('A:A',16,text);s.set_column('B:G',20,integer);s.set_landscape();s.fit_to_pages(1,1);s.print_area('A1:G16')
 s.write('A1','実験A：4課題の合計と内訳',header)
 s.write_row('A2',['方式','その他3課題','CSV処理','合計','成功数','その他3課題','CSV処理'],header)
 a_values=[]
 for r,(mode,label) in enumerate(MODES.items(),2):
  rows=[q for q in data['study_A']['rows'] if q['checkpoint_policy']==mode]
  csv=sum(q['known_total_tokens'] for q in rows if q['task_id']=='6104387_1');other=sum(q['known_total_tokens'] for q in rows if q['task_id']!='6104387_1')
  n=r+1;s.write(r,0,label,text)
  s.write_formula(r,1,f'=SUMIFS(\'実験A_結果\'!$C$2:$C$13,\'実験A_結果\'!$B$2:$B$13,A{n},\'実験A_結果\'!$A$2:$A$13,"<>CSV処理")',integer,other)
  s.write_formula(r,2,f'=SUMIFS(\'実験A_結果\'!$C$2:$C$13,\'実験A_結果\'!$B$2:$B$13,A{n},\'実験A_結果\'!$A$2:$A$13,"CSV処理")',integer,csv)
  s.write_formula(r,3,f'=SUM(B{n}:C{n})',integer,other+csv)
  s.write_formula(r,4,f'=COUNTIFS(\'実験A_結果\'!$B$2:$B$13,A{n},\'実験A_結果\'!$H$2:$H$13,1)',integer,4)
  s.write_formula(r,5,f'=B{n}/1000',decimal,other/1000);s.write_formula(r,6,f'=C{n}/1000',decimal,csv/1000)
  a_values.append([other,csv])
 s.write('A7','B〜D列：トークン、F〜G列：千トークン',text)
 s.write('A9','実験B：同じ写真課題の2条件',header)
 s.write_row('A10',['API条件','通常継続','完了判定','削減率','グラフの注記','通常継続','完了判定'],header)
 b_values=[]
 for r,(interface,label) in enumerate(INTERFACES.items(),10):
  rows={q['condition']:q for q in data['study_B']['rows'] if q['interface']==interface};ordinary=rows['ordinary']['known_total_tokens'];stop=rows['evidence_stop']['known_total_tokens'];pct=(ordinary-stop)/ordinary;n=r+1
  s.write(r,0,label,text)
  for col,key,value in [(1,'通常継続',ordinary),(2,'完了判定',stop)]:
   s.write_formula(r,col,f'=SUMIFS(\'実験B_結果\'!$C$2:$C$5,\'実験B_結果\'!$A$2:$A$5,A{n},\'実験B_結果\'!$B$2:$B$5,"{key}")',integer,value)
  s.write_formula(r,3,f'=(B{n}-C{n})/B{n}',percent,pct)
  s.write_formula(r,4,f'=TEXT(D{n},"0.00%")&"減"',text,f'{pct*100:.2f}%減')
  s.write_formula(r,5,f'=B{n}/1000',decimal,ordinary/1000);s.write_formula(r,6,f'=C{n}/1000',decimal,stop/1000)
  b_values.append([ordinary,stop])
 s.write('A14','B〜C列：トークン、F〜G列：千トークン',text)
 s.write('A15','実験AとBは別々に評価する。両者の削減率を合算しない。',text)
 info.set_column('A:A',100,text);info.hide_gridlines(2)
 for i,line in enumerate(['編集方法：結果表を編集すると、集計式と棒の高さが更新される。','グラフはExcelのネイティブグラフであり、色・軸・凡例・ラベルを編集できる。','図3の削減率注記は編集可能な文字ラベル。値変更時は集計D/E列の値に合わせてラベルも編集する。','削減率注記を文字ラベルとしたのは、LibreOfficeで同じグラフを書き出すための互換対応。','図2／図3シートは原稿への出力用。グラフに図番号や長い説明は含めない。','総トークン数は入力と出力の合計。要約生成を含む全モデル呼出しを集計する。','キャッシュされた入力も含む論理トークン数であり、金銭課金や時間ではない。','成功は実行終了後の公式評価器による。全12実行／全4実行で成功、使用量欠測なし。','実験AとBは独立した既知課題の比較であり、組合せ効果や一般的な品質保証は評価していない。','実験Bでは13データベースのハッシュが一致したが、要求・応答全文の厳密な先頭一致は成立しなかった。','元データ：同梱のresults_data.json。新しい実験値は追加していない。']):info.write(i,0,line,text)
 info.print_area('A1:A11');info.set_landscape();info.fit_to_pages(1,1)
 font={'name':FONT,'size':16,'color':'#222222'}
 def base_chart(stacked,max_value,major):
  c=wb.add_chart({'type':'column',**({'subtype':'stacked'} if stacked else {})})
  c.set_size({'width':130/25.4*96,'height':116/25.4*96})
  c.set_chartarea({'border':{'none':True},'fill':{'color':'#FFFFFF'}})
  c.set_plotarea({'border':{'none':True},'fill':{'color':'#FFFFFF'},'layout':{'x':.235,'y':.19,'width':.725,'height':.65}})
  c.set_legend({'position':'top','font':font,'border':{'none':True}})
  c.set_x_axis({'num_font':font,'line':{'color':'#555555','width':1},'major_tick_mark':'none','minor_tick_mark':'none'})
  c.set_y_axis({'name':'総トークン数（千トークン）','name_font':font,'num_font':font,'min':0,'max':max_value,'major_unit':major,'major_gridlines':{'visible':True,'line':{'color':'#DDDDDD','width':.8}},'line':{'none':True},'num_format':'0','major_tick_mark':'none','minor_tick_mark':'none'})
  c.set_title({'none':True});return c
 c=base_chart(True,1000,200)
 for j,(col,color,name) in enumerate([('F',BLUE,'その他3課題'),('G',ORANGE,'CSV処理')]):
  c.add_series({'name':"='集計'!$"+col+'$2','name_data':[name],'categories':"='集計'!$A$3:$A$5",'categories_data':list(MODES.values()),'values':"='集計'!$"+col+'$3:$'+col+'$5','values_data':[v[j]/1000 for v in a_values],'fill':{'color':color},'border':{'none':True},'gap':55})
 chart_sheets[0].insert_chart('A1',c,{'x_offset':0,'y_offset':0});chart_sheets[0].activate()
 c=base_chart(False,180,50)
 for j,(col,color,name) in enumerate([('F',BLUE,'通常継続'),('G',ORANGE,'完了判定')]):
  opts={'name':"='集計'!$"+col+'$10','name_data':[name],'categories':"='集計'!$A$11:$A$12",'categories_data':list(INTERFACES.values()),'values':"='集計'!$"+col+'$11:$'+col+'$12','values_data':[v[j]/1000 for v in b_values],'fill':{'color':color},'border':{'none':True},'gap':70,'overlap':-15}
  if j==0:opts['data_labels']={'value':True,'position':'outside_end','font':font,'custom':[{'value':f'{(v[0]-v[1])/v[0]*100:.2f}%減','font':font} for n,v in zip([11,12],b_values)]}
  c.add_series(opts)
 chart_sheets[1].insert_chart('A1',c,{'x_offset':0,'y_offset':0})
 wb.close()
 return a_values,b_values

def export_pdf(workbook,out,soffice):
 with tempfile.TemporaryDirectory(prefix='excel_chart_export_') as tmp:
  t=Path(tmp);env=os.environ.copy();dirs=[Path('/System/Library/Fonts'),Path('/System/Library/Fonts/Supplemental'),Path('/Library/Fonts'),soffice.parent.parent/'Resources/fonts/truetype']
  config='<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig>'+''.join('<dir>'+escape(str(d))+'</dir>' for d in dirs)+'<cachedir>'+escape(str(t/'cache'))+'</cachedir>'
  for name in ['Arial','Calibri','Yu Gothic','MS PGothic','ＭＳ Ｐゴシック']:config+='<alias><family>'+escape(name)+'</family><prefer><family>Hiragino Sans</family></prefer></alias>'
  config+='</fontconfig>';(t/'fonts.conf').write_text(config);env.update(FONTCONFIG_FILE=str(t/'fonts.conf'),FONTCONFIG_PATH=str(t))
  filter='pdf:calc_pdf_Export:'+json.dumps({'PageRange':{'type':'string','value':'1-2'}},separators=(',',':'))
  cmd=[str(soffice),'-env:UserInstallation='+(t/'profile').as_uri(),'--headless','--nologo','--nodefault','--nofirststartwizard','--norestore','--convert-to',filter,'--outdir',str(out),str(workbook)]
  run=subprocess.run(cmd,capture_output=True,text=True,timeout=120,env=env);run.check_returncode()
  pdf=out/(workbook.stem+'.pdf');assert pdf.is_file(),run.stdout+run.stderr
 return pdf,run.stdout+run.stderr

def chart_metadata(path):
 with zipfile.ZipFile(path) as z:
  names=sorted(n for n in z.namelist() if re.fullmatch(r'xl/charts/chart[0-9]+\.xml',n));assert len(names)==2
  rows=[]
  for name in names:
   root=ET.fromstring(z.read(name));axis=root.find('.//c:valAx',NS)
   colors=['#'+q.attrib['val'] for q in root.findall('.//c:barChart/c:ser/c:spPr/a:solidFill/a:srgbClr',NS)]
   title=''.join(t.text or '' for t in axis.findall('.//c:title//a:t',NS))
   minimum=axis.find('c:scaling/c:min',NS)
   rows.append({'colors':colors,'y_axis_label':title,'y_axis_origin':None if minimum is None else float(minimum.attrib['val'])})
  return rows

def crop_charts(pdf,out,metadata):
 source=pymupdf.open(pdf);assert len(source)==2
 records={}
 for i,stem in enumerate(['result_summary','result_termination']):
  page=source[i];white=[q['rect'] for q in page.get_drawings() if q.get('fill')==(1.,1.,1.)]
  crop=max(white,key=lambda r:r.get_area());target=pymupdf.Rect(0,0,W_MM/25.4*72,H_MM/25.4*72)
  doc=pymupdf.open();dest=doc.new_page(width=target.width,height=target.height);dest.show_pdf_page(target,source,i,clip=crop,keep_proportion=True)
  doc.set_metadata({'title':stem,'creator':'create_excel_charts.py','producer':'LibreOffice Calc native Excel chart export; PyMuPDF crop','creationDate':'D:20261029000000Z','modDate':'D:20261029000000Z'})
  path=out/(stem+'.pdf');path.write_bytes(doc.tobytes(garbage=4,deflate=True,no_new_id=True));doc.close()
  doc=pymupdf.open(path);p=doc[0];spans=[s for b in p.get_text('dict')['blocks'] if 'lines' in b for l in b['lines'] for s in l['spans'] if s['text'].strip()];minimum=min(s['size'] for s in spans)
  assert minimum>=7,(stem,minimum)
  visible=''.join(s['text'] for s in spans)
  assert all(p.rect.contains(pymupdf.Rect(s['bbox'])) for s in spans),(stem,'clipped text')
  p.get_pixmap(dpi=500,alpha=False).save(out/(stem+'.png'))
  svg=p.get_svg_image(text_as_path=True);(out/(stem+'.svg')).write_text(svg)
  eps=cairosvg.svg2eps(bytestring=svg.encode());eps=re.sub(rb'^%%CreationDate:.*$',b'%%CreationDate: Thu Oct 29 00:00:00 2026',eps,flags=re.MULTILINE);(out/(stem+'.eps')).write_bytes(eps)
  records[stem]={'source_pdf_page':i+1,'source_crop_points':list(crop),'source_crop_mm':[crop.width/72*25.4,crop.height/72*25.4],'width_mm':W_MM,'height_mm':H_MM,'uniform_scale':min(target.width/crop.width,target.height/crop.height),'minimum_font_pt':minimum,'exported_text':visible,**metadata[i],'outputs':{f'{stem}.{e}':sha(out/f'{stem}.{e}') for e in ['pdf','png','svg','eps']}}
  doc.close()
 source.close();return records

def validate_workbook(path,a_values,b_values):
 with zipfile.ZipFile(path) as z:
  charts=[n for n in z.namelist() if re.fullmatch(r'xl/charts/chart[0-9]+\.xml',n)];assert len(charts)==2
  assert not any(n.startswith('xl/media/') for n in z.namelist())
  records=[]
  for name,expected in zip(sorted(charts),[a_values,b_values]):
   root=ET.fromstring(z.read(name));series=root.findall('.//c:barChart/c:ser',NS);assert len(series)==2
   vals=[]
   for s in series:
    formula=s.find('c:val/c:numRef/c:f',NS).text
    values=[float(v.text) for v in s.findall('c:val/c:numRef/c:numCache/c:pt/c:v',NS)];vals.append(values)
    assert formula.startswith("'集計'!")
   assert vals==[[r[j]/1000 for r in expected] for j in [0,1]]
   colors=[q.attrib['val'] for q in root.findall('.//c:barChart/c:ser/c:spPr/a:solidFill/a:srgbClr',NS)];assert colors==[BLUE[1:],ORANGE[1:]]
   assert root.find('.//c:valAx/c:scaling/c:min',NS).attrib['val']=='0'
   records.append({'chart_xml':name,'native_bar_series':2,'series_values_thousand_tokens':vals,'colors':colors,'zero_origin':True})
  formulas=sum(len(ET.fromstring(z.read(n)).findall('.//s:f',NS)) for n in z.namelist() if re.fullmatch(r'xl/worksheets/sheet[0-9]+\.xml',n))
  assert formulas==30,formulas
 return {'native_charts':2,'embedded_raster_images':0,'formula_count':formulas,'all_16_run_values_from_source':True,'charts':records}

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 mode=ap.add_mutually_exclusive_group(required=True);mode.add_argument('--data',type=Path,help='Build the workbook from the frozen JSON results.');mode.add_argument('--workbook',type=Path,help='Re-export an edited workbook; keep chart worksheets first.')
 ap.add_argument('--output-dir',type=Path,required=True);ap.add_argument('--soffice',type=Path,required=True);args=ap.parse_args()
 out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False);figs=out/'figures';figs.mkdir()
 xlsx=out/'results_charts.xlsx'
 if args.data:
  data=json.loads(args.data.read_text());assert len(data['study_A']['rows'])==12 and len(data['study_B']['rows'])==4 and data['studies_pooled'] is False
  a,b=make_workbook(data,xlsx);validation=validate_workbook(xlsx,a,b)
 else:
  shutil.copyfile(args.workbook,xlsx);validation={'mode':'export_edited_workbook','frozen_data_equality_checked':False}
 metadata=chart_metadata(xlsx)
 pdf,log=export_pdf(xlsx,out,args.soffice.resolve());pdf.rename(figs/'excel_charts_source.pdf');pdf=figs/'excel_charts_source.pdf'
 figures=crop_charts(pdf,figs,metadata)
 if args.data:
  assert all('総トークン数' in v['exported_text'] and '千トークン' in v['exported_text'] for v in figures.values())
  normalized=figures['result_termination']['exported_text'].replace(' ','');assert '30.15%減' in normalized and '26.00%減' in normalized
 record={'version':'v14','data_sha256':sha(args.data) if args.data else None,'workbook_sha256':sha(xlsx),'script_sha256':sha(Path(__file__)),'source_pdf_sha256':sha(pdf),'renderer':subprocess.check_output([str(args.soffice),'--version'],text=True).strip(),'native_Microsoft_Excel_render_verified':False,'export_method':'Native chart XML -> LibreOffice Calc PDF -> vector crop, no independently redrawn plot','independent_studies_not_pooled':True,'workbook_validation':validation,'reduction_label_behavior':'Native editable text labels, calculated when building the workbook; after editing data, update these labels to match the formulas in the aggregate sheet.','figures':figures,'model_API_eval_calls':0}
 (out/'excel_charts_manifest.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n');(out/'excel_export.log').write_text(log)
 print(json.dumps({'workbook':str(xlsx),'figures':figures},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
