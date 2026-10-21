"""Mechanical checks and review images, not a claim of human visual review."""
import argparse
import hashlib
import json
from pathlib import Path
import pymupdf


def inspect(folder, images=None):
    manifest=json.loads((folder/'build_manifest.json').read_text())
    layout=json.loads((folder/'layout_checks.json').read_text())
    slides=json.loads((folder/'slides.json').read_text())
    pdf=folder/'AI_harness_progress_20261022.pdf'
    errors=[]
    with pymupdf.open(pdf) as doc:
        if len(doc)!=manifest['pages'] or layout['pages']!=len(doc):errors.append('page count')
        for i,page in enumerate(doc,1):
            if abs(page.rect.width-960)>1 or abs(page.rect.height-540)>1:errors.append(f'size:{i}')
            text=page.get_text()
            if i==1 and slides[0].get('cover'):
                expected=slides[0]['title'].replace('<br>','')
                if ''.join(text.split())!=''.join(expected.split()):errors.append('title-only-cover')
            elif len(text)<30:
                errors.append(f'text:{i}')
            if '\ufffd' in text:errors.append(f'text:{i}')
            for b in page.get_text('dict')['blocks']:
                if b['type']!=0:continue
                for line in b['lines']:
                    for span in line['spans']:
                        if not page.rect.contains(pymupdf.Rect(span['bbox'])):errors.append(f'outside:{i}')
            if images:
                images.mkdir(parents=True,exist_ok=True)
                page.get_pixmap(matrix=pymupdf.Matrix(1.3,1.3)).save(images/f'slide_{i:02d}.png')
    errors += layout['errors']
    report=dict(pages=manifest['pages'],errors=errors,method='Chrome element bounds + PDF text and page bounds',
        visual_review_claim=False,pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest())
    (folder/'automated_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    if errors:raise ValueError(errors)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',type=Path,required=True);p.add_argument('--images',type=Path)
    a=p.parse_args();print(json.dumps(inspect(a.folder,a.images)))
