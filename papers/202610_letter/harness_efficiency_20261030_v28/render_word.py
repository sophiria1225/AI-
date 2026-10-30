#!/usr/bin/env python3
"""Render the Word manuscript with explicit non-hanging punctuation in LibreOffice.

LibreOffice 26.8 imports DOCX overflowPunct=0 as hanging punctuation. This export
uses a temporary flat ODF intermediate and changes only style:punctuation-wrap
from hanging to simple. All text, fonts, dimensions, sections, images and tables
in that intermediate are otherwise retained. The DOCX source is never rewritten.
"""
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile
from lxml import etree as E
import argparse,hashlib,json,os,re,subprocess,tempfile,unicodedata
import pymupdf

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def norm(text):return re.sub(r'[\s\u200b\u200c\u200d\ufeff]+','',unicodedata.normalize('NFKC',text))
def source_text(path):
    W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    M='{http://schemas.openxmlformats.org/officeDocument/2006/math}'
    with ZipFile(path) as z:root=E.fromstring(z.read('word/document.xml'))
    def walk(el):
        if el.tag in (W+'t',M+'t'):return el.text or ''
        if el.tag==M+'nary':
            ch=el.find(M+'naryPr/'+M+'chr')
            lead=ch.get(M+'val') if ch is not None else '∫'
            return lead+''.join(walk(c) for c in el if c.tag!=M+'naryPr')
        return ''.join(walk(c) for c in el)
    return walk(root.find(W+'body'))
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--soffice',type=Path,required=True)
    ap.add_argument('--docx',type=Path,required=True)
    ap.add_argument('--outdir',type=Path,required=True)
    a=ap.parse_args();source=a.docx.resolve();out=a.outdir.resolve();out.mkdir(parents=True,exist_ok=True)
    pdf=out/(source.stem+'.pdf')
    if pdf.exists():raise FileExistsError(pdf)
    digest=sha(source)
    logs=[]
    with tempfile.TemporaryDirectory(prefix='ieice_word_punctuation_') as temp:
        temp=Path(temp);initial=temp/'initial';corrected=temp/'corrected';initial.mkdir();corrected.mkdir()
        env=os.environ.copy()
        fontdirs=[Path('/System/Library/Fonts'),Path('/System/Library/Fonts/Supplemental'),Path('/Library/Fonts'),a.soffice.resolve().parent.parent/'Resources/fonts/truetype']
        aliases={n:'Hiragino Mincho ProN' for n in ['ＭＳ 明朝','ＭＳ明朝','MS Mincho','ＭＳ Ｐ明朝','MS PMincho']}
        aliases.update({n:'Hiragino Sans' for n in ['ＭＳ ゴシック','ＭＳゴシック','MS Gothic','ＭＳ Ｐゴシック','MS PGothic']})
        aliases.update({'serif':'Times New Roman','sans-serif':'Arial'})
        conf='<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig>'
        conf+=''.join('<dir>'+escape(str(d))+'</dir>' for d in fontdirs)
        conf+='<cachedir>'+escape(str(temp/'fontcache'))+'</cachedir>'
        conf+=''.join('<alias><family>'+escape(k)+'</family><prefer><family>'+escape(v)+'</family></prefer></alias>' for k,v in aliases.items())+'</fontconfig>'
        fc=temp/'fonts.conf';fc.write_text(conf);env.update(FONTCONFIG_FILE=str(fc),FONTCONFIG_PATH=str(temp))
        base=[str(a.soffice.resolve()),'-env:UserInstallation='+(temp/'profile').as_uri(),'--headless','--nologo','--nodefault','--nofirststartwizard','--norestore']
        def run(args):
            result=subprocess.run(base+args,capture_output=True,text=True,timeout=120,env=env)
            logs.append(result.stdout+result.stderr);result.check_returncode()
        run(['--convert-to','fodt:OpenDocument Text Flat XML','--outdir',str(initial),str(source)])
        fodt=initial/(source.stem+'.fodt');tree=E.fromstring(fodt.read_bytes());before_text=''.join(tree.itertext())
        S='{urn:oasis:names:tc:opendocument:xmlns:style:1.0}'
        changed=0
        for el in tree.iter(S+'paragraph-properties'):
            if el.get(S+'punctuation-wrap')=='hanging':
                el.set(S+'punctuation-wrap','simple');changed+=1
        assert ''.join(tree.itertext())==before_text
        assert changed>0,'Expected LibreOffice hanging punctuation styles'
        corrected_fodt=corrected/fodt.name
        corrected_fodt.write_bytes(E.tostring(tree,encoding='UTF-8',xml_declaration=True))
        run(['--convert-to','pdf:writer_pdf_Export','--outdir',str(out),str(corrected_fodt)])
    assert sha(source)==digest
    (out/'conversion.log').write_text('\n'.join(logs))
    doc=pymupdf.open(pdf);pages=[];body=[];fonts={}
    for i,page in enumerate(doc,1):
        png=out/f'page_{i:02d}.png';page.get_pixmap(dpi=150,alpha=False).save(png)
        for xref,ext,kind,name,*_ in page.get_fonts(full=True):fonts[name]={'type':kind,'embedded':bool(doc.extract_font(xref)[3])}
        text=''
        for block in page.get_text('dict')['blocks']:
            if block['type']!=0:continue
            for line in block['lines']:
                # Official template body area, excluding running header and page number.
                if line['bbox'][1]>70 and line['bbox'][3]<657:
                    text+=''.join(span['text'] for span in line['spans'])
        body.append(text)
        pages.append({'page':i,'width_points':page.rect.width,'height_points':page.rect.height,'png_sha256':sha(png),'text_characters':len(norm(text))})
    expected=norm(source_text(source));actual=norm(''.join(body))
    match=expected==actual
    (out/'docx_text_normalized.txt').write_text(expected)
    (out/'pdf_text_normalized.txt').write_text(actual)
    receipt={'source_docx':str(source),'source_sha256':digest,'source_unmodified':True,'pdf':str(pdf),'pdf_sha256':sha(pdf),'renderer':subprocess.check_output([str(a.soffice.resolve()),'--version'],text=True).strip(),'renderer_intermediate':'Flat ODF; only style:punctuation-wrap hanging->simple changed','punctuation_styles_corrected':changed,'mac_font_fallback':True,'docx_fonts_modified':False,'native_Microsoft_Word_pagination_verified':False,'total_pages':len(doc),'body_and_references_pages':len(doc)-1,'English_abstract_only_last_page':norm(body[-1]).startswith('AbstractWeindependently') and 'Keywords:' in norm(body[-1]),'DOCX_PDF_text_including_punctuation_equal':match,'normalization':'NFKC, remove whitespace and zero-width formatting; emit OMML n-ary operator; exclude PDF headers/footers','normalized_character_count':len(expected),'pages':pages,'fonts':fonts,'visual_review_complete':False}
    (out/'render_validation.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:receipt[k] for k in ['pdf','total_pages','DOCX_PDF_text_including_punctuation_equal','normalized_character_count','punctuation_styles_corrected']}))
    if not match:
        from difflib import SequenceMatcher
        for tag,i,j,k,l in SequenceMatcher(None,expected,actual,autojunk=False).get_opcodes():
            if tag!='equal':print(tag,repr(expected[i:j]),repr(actual[k:l]))
        raise SystemExit('PDF text mismatch')
if __name__=='__main__':main()
