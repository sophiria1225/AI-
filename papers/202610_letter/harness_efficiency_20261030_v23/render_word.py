#!/usr/bin/env python3
"""Render the official-template Word manuscript with an installed LibreOffice.

Requires pymupdf. Choose a new output directory; previous proofs are preserved.
On macOS --mac-font-fallback supplies the explicit local proof font mapping.
It never changes font declarations in the DOCX.
"""
import argparse,hashlib,json,os,subprocess,tempfile
from pathlib import Path
from xml.sax.saxutils import escape
import pymupdf

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--soffice',type=Path,required=True)
 ap.add_argument('--docx',type=Path,default=Path(__file__).parent/'manuscript.docx')
 ap.add_argument('--outdir',type=Path,required=True)
 ap.add_argument('--mac-font-fallback',action='store_true')
 a=ap.parse_args();source=a.docx.resolve();out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=True)
 pdf=out/(source.stem+'.pdf')
 if pdf.exists():raise FileExistsError('Choose a new output directory to preserve earlier proof.')
 with tempfile.TemporaryDirectory(prefix='ieice_word_render_') as t:
  temp=Path(t);env=os.environ.copy()
  if a.mac_font_fallback:
   fontdirs=[Path('/System/Library/Fonts'),Path('/System/Library/Fonts/Supplemental'),Path('/Library/Fonts'),a.soffice.resolve().parent.parent/'Resources/fonts/truetype']
   aliases={n:'Hiragino Mincho ProN' for n in ['ＭＳ 明朝','ＭＳ明朝','MS Mincho','ＭＳ Ｐ明朝','MS PMincho']}
   aliases.update({n:'Hiragino Sans' for n in ['ＭＳ ゴシック','ＭＳゴシック','MS Gothic','ＭＳ Ｐゴシック','MS PGothic']})
   aliases.update({'serif':'Times New Roman','sans-serif':'Arial'})
   conf='<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig>'
   conf+=''.join('<dir>'+escape(str(d))+'</dir>' for d in fontdirs)
   conf+='<cachedir>'+escape(str(temp/'fontcache'))+'</cachedir>'
   conf+=''.join('<alias><family>'+escape(k)+'</family><prefer><family>'+escape(v)+'</family></prefer></alias>' for k,v in aliases.items())+'</fontconfig>'
   config=temp/'fonts.conf';config.write_text(conf)
   env.update(FONTCONFIG_FILE=str(config),FONTCONFIG_PATH=str(temp))
  cmd=[str(a.soffice.resolve()),'-env:UserInstallation='+(temp/'profile').as_uri(),'--headless','--nologo','--nodefault','--nofirststartwizard','--norestore','--convert-to','pdf:writer_pdf_Export','--outdir',str(out),str(source)]
  run=subprocess.run(cmd,capture_output=True,text=True,timeout=120,env=env)
  (out/'conversion.log').write_text(run.stdout+run.stderr);run.check_returncode()
 if not pdf.is_file():raise RuntimeError('PDF not produced')
 doc=pymupdf.open(pdf);fonts={};pages=[]
 for i,page in enumerate(doc,1):
  for xref,ext,kind,name,*_ in page.get_fonts(full=True):
   fonts[name]={'type':kind,'embedded':bool(doc.extract_font(xref)[3])}
  png=out/f'page_{i:02d}.png';page.get_pixmap(dpi=150,alpha=False).save(png)
  pages.append({'page':i,'width_points':page.rect.width,'height_points':page.rect.height,'png_sha256':sha(png)})
 receipt={'source_docx':source.name,'source_sha256':sha(source),'pdf':pdf.name,'pdf_sha256':sha(pdf),'renderer':subprocess.check_output([str(a.soffice.resolve()),'--version'],text=True).strip(),'mac_font_fallback':a.mac_font_fallback,'docx_fonts_modified':False,'microsoft_word_pagination_equivalence_verified':False,'pages':pages,'fonts':fonts,'visual_review_complete':False}
 (out/'render_validation.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'pdf':str(pdf),'pages':len(doc),'sha256':sha(pdf)}))
if __name__=='__main__':main()
