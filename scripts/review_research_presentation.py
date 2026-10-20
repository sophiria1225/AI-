"""Verify generated slide text/data and render previews for visual inspection."""
import argparse
import hashlib
import json
import re
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw
from pptx import Presentation

ROOT = Path(__file__).resolve().parents[1]


def normalized(value):
    return re.sub(r"\s+", "", value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview-dir", type=Path, required=True)
    args = parser.parse_args()
    folder = ROOT/"materials/20261020"
    deck = json.loads((folder/"slides.json").read_text())
    data = json.loads((folder/"data_sources.json").read_text())
    pdf = pymupdf.open(folder/"AI_harness_research_20261020.pdf")
    pptx = Presentation(folder/"AI_harness_research_20261020.pptx")
    assert len(deck) == len(pdf) == len(pptx.slides) == 29
    checks, overlaps = [], []
    for name, expected in data["source_sha256"].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == expected, name
    for i,(spec,page,slide) in enumerate(zip(deck,pdf,pptx.slides),1):
        pdf_text = normalized(page.get_text())
        pptx_text = normalized("".join(sh.text for sh in slide.shapes if sh.has_text_frame))
        elements = [e for e in spec["elements"] if e["kind"] == "text"]
        missing_pdf = [e["text"] for e in elements if normalized(e["text"]) not in pdf_text]
        missing_pptx = [e["text"] for e in elements if normalized(e["text"]) not in pptx_text]
        assert not missing_pdf, (i,"PDF text missing",missing_pdf)
        assert not missing_pptx, (i,"PPTX text missing",missing_pptx)
        # Detect overlapping actual line boxes, not the intentionally large text frames.
        for j,a in enumerate(elements):
            ah = len(a["rendered_lines"])*a["size"]*a.get("leading",1.32)
            for b in elements[j+1:]:
                bh = len(b["rendered_lines"])*b["size"]*b.get("leading",1.32)
                dx=min(a["x"]+a["w"],b["x"]+b["w"])-max(a["x"],b["x"])
                dy=min(a["y"]+ah,b["y"]+bh)-max(a["y"],b["y"])
                if dx>1 and dy>1:
                    overlaps.append({"page":i,"a":a["text"],"b":b["text"],"overlap":[dx,dy]})
        checks.append({"page":i,"native_text_boxes":len(elements),"pdf_text_present":True,
                       "pptx_text_present":True,"pdf_images":len(page.get_images())})
    assert not overlaps, overlaps
    # Exact values in the public aggregate, CSV, chart input and visible appendix.
    assert sum(r["total_tokens"] for r in data["P3"]) == 1113881
    assert sum(r["calls"] for r in data["P3"]) == 105
    m = data["P4"]["measurements"]
    assert m["input_tokens"]+m["output_tokens"] == m["known_total_tokens"] == 586166
    assert 0 <= m["cached_input_tokens"] <= m["input_tokens"]
    assert m["evaluation"]["resolved"] is False and m["artifact_bytes"] == 0
    all_text = normalized("".join(p.get_text() for p in pdf))
    for value in (283176,275008,280166,275531,583040,3126,586166):
        assert f"{value:,}" in all_text, value
    args.preview_dir.mkdir(parents=True,exist_ok=True)
    for start in range(0,len(pdf),9):
        sheet=Image.new("RGB",(1200,735),"#D8E0E8")
        draw=ImageDraw.Draw(sheet)
        for k,page in enumerate(pdf[start:start+9]):
            pix=page.get_pixmap(matrix=pymupdf.Matrix(.4,.4),alpha=False)
            im=Image.frombytes("RGB",(pix.width,pix.height),pix.samples)
            x=(k%3)*400+8;y=(k//3)*245+20
            sheet.paste(im,(x,y));draw.text((x,y-16),str(start+k+1),fill="black")
        sheet.save(args.preview_dir/f"contact_{start+1:02d}.png")
    for i,page in enumerate(pdf,1):
        page.get_pixmap(matrix=pymupdf.Matrix(1.25,1.25),alpha=False).save(args.preview_dir/f"slide_{i:02d}.png")
    for page_number, name in [(5,"architecture_implemented"), (6,"architecture_planned")]:
        pdf[page_number].get_pixmap(matrix=pymupdf.Matrix(1.5,1.5),alpha=False).save(folder/"figures"/f"{name}.png")
        single = pymupdf.open()
        single.insert_pdf(pdf,from_page=page_number,to_page=page_number)
        single.save(folder/"figures"/f"{name}.pdf")
        single.close()
    result = {
        "pages":len(pdf),"checks":checks,"source_hashes_match":True,
        "exact_numeric_checks_passed":True,"missing_text":[],"text_overlaps":overlaps,
        "pdf_rendered_pages":len(pdf),
        "native_powerpoint_rendered":False,
        "limitations":["PowerPoint text, geometry and package were verified; no native PowerPoint rendering was performed.",
                       "PDF previews still require visual review. This script does not certify aesthetic quality."],
        "artifact_sha256":{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in folder.glob("AI_harness_research_20261020.*")},
    }
    (folder/"review.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"pages":len(pdf),"sources":"match","text":"present","overlap_count":len(overlaps)}))


if __name__=="__main__":
    main()
