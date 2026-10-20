"""Render one slide description into editable PPTX shapes and a matching PDF.

This is a reporting utility. It is not imported by the experimental runtime.
Coordinates and font sizes use points on a 960 x 540 canvas.
"""
import json
import math
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE, MSO_CONNECTOR
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Pt
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

WIDTH, HEIGHT = 960, 540
FONT = "ResearchJP"


def color(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i+2], 16)/255 for i in (0, 2, 4))


def wrap(text, width, size):
    """CJK-aware hard wrapping, saved as identical line breaks in both formats."""
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        line = ""
        for char in paragraph:
            if line and pdfmetrics.stringWidth(line+char, FONT, size) > width:
                lines.append(line.rstrip())
                line = char.lstrip()
            else:
                line += char
        lines.append(line)
    return lines


def render(slides, output, font_path, font_name="Arial Unicode MS", *,
           stem="AI_harness_research_20261020",
           title="AIハーネス研究 中間報告 2026-10-20"):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont(FONT, str(font_path)))
    errors = []
    for i, spec in enumerate(slides, 1):
        for item in spec["elements"]:
            if item["kind"] != "text":
                continue
            lines = wrap(item["text"], item["w"], item["size"])
            needed = len(lines)*item["size"]*item.get("leading", 1.32)
            if needed > item["h"]+.1:
                errors.append(f"Slide {i}: {needed:.1f}>{item['h']}: {item['text'][:100]}")
    if errors:
        raise ValueError("\n".join(errors))
    prs = Presentation()
    prs.slide_width, prs.slide_height = Pt(WIDTH), Pt(HEIGHT)
    prs.core_properties.title = title
    prs.core_properties.subject = "目的・アーキテクチャ・実験・考察・今後の検証"
    prs.core_properties.author = "AIハーネス研究"
    prs.core_properties.keywords = "開発観察;総トークン;オーケストレーション;未検証の仮説"
    pdf = canvas.Canvas(str(output/(stem + ".pdf")),
                        pagesize=(WIDTH, HEIGHT), invariant=1)
    pdf.setTitle(prs.core_properties.title)
    pdf.setAuthor(prs.core_properties.author)
    measurements = []

    def pdf_color(value, stroke=False):
        if stroke:
            pdf.setStrokeColorRGB(*color(value))
        else:
            pdf.setFillColorRGB(*color(value))

    def shape_fill(shape, fill, stroke, dashed=False):
        if fill:
            shape.fill.solid()
            shape.fill.fore_color.rgb = RGBColor.from_string(fill.lstrip("#"))
        else:
            shape.fill.background()
        if stroke:
            shape.line.color.rgb = RGBColor.from_string(stroke.lstrip("#"))
            shape.line.width = Pt(1.2)
            if dashed:
                shape.line.dash_style = MSO_LINE_DASH_STYLE.DASH
        else:
            shape.line.fill.background()

    for i, spec in enumerate(slides, 1):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        bg = spec.get("background", "#F5F7FA")
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = RGBColor.from_string(bg[1:])
        pdf_color(bg)
        pdf.rect(0, 0, WIDTH, HEIGHT, fill=1, stroke=0)
        notes = [spec["title"], spec.get("notes", "")]
        for item in spec["elements"]:
            kind = item["kind"]
            x, y = item["x"], item["y"]
            if kind == "text":
                w, h, size = item["w"], item["h"], item["size"]
                lines = wrap(item["text"], w, size)
                leading = size * item.get("leading", 1.32)
                needed = len(lines)*leading
                if needed > h+0.1:
                    raise ValueError(f"Slide {i} text exceeds height: {needed:.1f}>{h}: {item['text'][:60]}")
                if not (0 <= x and x+w <= WIDTH+0.1 and 0 <= y and y+h <= HEIGHT+0.1):
                    raise ValueError(f"Slide {i} text outside canvas: {item}")
                item["rendered_lines"] = lines
                box = slide.shapes.add_textbox(Pt(x), Pt(y), Pt(w), Pt(h))
                tf = box.text_frame
                tf.word_wrap = False
                tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
                tf.clear()
                for n, line in enumerate(lines):
                    p = tf.paragraphs[0] if n == 0 else tf.add_paragraph()
                    p.space_before = p.space_after = Pt(0)
                    p.line_spacing = Pt(leading)
                    run = p.add_run()
                    run.text = line
                    run.font.name = font_name
                    run.font.size = Pt(size)
                    run.font.bold = item.get("bold", False)
                    run.font.color.rgb = RGBColor.from_string(item["color"][1:])
                    for tag in ("a:ea", "a:cs"):
                        node = OxmlElement(tag)
                        node.set("typeface", font_name)
                        run._r.get_or_add_rPr().append(node)
                    if item.get("url"):
                        run.hyperlink.address = item["url"]
                pdf_color(item["color"])
                pdf.setFont(FONT, size)
                # Use the embedded font's ascent, not a guessed line-box top.
                ascent = pdfmetrics.getAscent(FONT)*size/1000
                for n, line in enumerate(lines):
                    pdf.drawString(x, HEIGHT-y-ascent-n*leading, line)
                if item.get("url"):
                    pdf.linkURL(item["url"], (x, HEIGHT-y-h, x+w, HEIGHT-y), relative=0)
                measurements.append({"slide": i, "text": item["text"][:80],
                                     "lines": len(lines), "used_height": needed, "box_height": h})
            elif kind == "box":
                w, h = item["w"], item["h"]
                shape = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.RECTANGLE, Pt(x), Pt(y), Pt(w), Pt(h))
                shape_fill(shape, item.get("fill"), item.get("stroke"), item.get("dashed"))
                pdf.saveState()
                if item.get("fill"):
                    pdf_color(item["fill"])
                if item.get("stroke"):
                    pdf_color(item["stroke"], True)
                pdf.setLineWidth(1.2)
                if item.get("dashed"):
                    pdf.setDash(6, 4)
                pdf.rect(x, HEIGHT-y-h, w, h, fill=bool(item.get("fill")),
                         stroke=bool(item.get("stroke")))
                pdf.restoreState()
            elif kind == "line":
                x2, y2 = item["x2"], item["y2"]
                c = item.get("color", "#617084")
                connector = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                                                       Pt(x), Pt(y), Pt(x2), Pt(y2))
                connector.line.color.rgb = RGBColor.from_string(c[1:])
                connector.line.width = Pt(item.get("width", 1.8))
                if item.get("dashed"):
                    connector.line.dash_style = MSO_LINE_DASH_STYLE.DASH
                pdf.saveState()
                pdf_color(c, True)
                pdf.setLineWidth(item.get("width", 1.8))
                if item.get("dashed"):
                    pdf.setDash(6, 4)
                pdf.line(x, HEIGHT-y, x2, HEIGHT-y2)
                if item.get("arrow", True):
                    tail = OxmlElement("a:tailEnd")
                    tail.set("type", "triangle")
                    connector._element.spPr.get_or_add_ln().append(tail)
                    a = math.atan2(y2-y, x2-x)
                    p = pdf.beginPath()
                    p.moveTo(x2, HEIGHT-y2)
                    for angle in (a+2.65, a-2.65):
                        p.lineTo(x2+8*math.cos(angle), HEIGHT-(y2+8*math.sin(angle)))
                    p.close()
                    pdf_color(c)
                    pdf.drawPath(p, stroke=0, fill=1)
                pdf.restoreState()
            elif kind == "image":
                path = output/item["path"]
                slide.shapes.add_picture(str(path), Pt(x), Pt(y), Pt(item["w"]), Pt(item["h"]))
                pdf.drawImage(str(path), x, HEIGHT-y-item["h"], item["w"], item["h"], mask="auto")
            else:
                raise ValueError(kind)
        slide.notes_slide.notes_text_frame.text = "\n\n".join(filter(None, notes))
        pdf.showPage()
    pdf.save()
    prs.save(output/(stem + ".pptx"))
    (output/"slides.json").write_text(json.dumps(slides, ensure_ascii=False, indent=2)+"\n")
    (output/"layout_checks.json").write_text(json.dumps({
        "pages": len(slides), "text_boxes": len(measurements), "overflow": [],
        "font_name": font_name, "font_path_for_build": str(font_path), "boxes": measurements,
        "note": "Text bounds checked in the shared layout. Native PowerPoint rendering can vary by installed font."
    }, ensure_ascii=False, indent=2)+"\n")
