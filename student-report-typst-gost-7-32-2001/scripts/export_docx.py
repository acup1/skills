#!/usr/bin/env python3
"""Export this skill's modular Typst source to editable Word (not PDF-to-DOCX)."""
import argparse
import os
from pathlib import Path
import sys
import tempfile

from report_model import ReportError, asset_path, load_model, reference_id, reference_text

try:
    from docx import Document
    from docx.image.image import Image as DocxImage
    from docx.enum.style import WD_STYLE_TYPE
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Mm, Pt, RGBColor
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
except ImportError:
    sys.exit("DOCX requires python-docx: python3 -m pip install -r scripts/requirements-docx.txt")


def element(tag, **attributes):
    node = OxmlElement(tag)
    for key, value in attributes.items():
        node.set(qn(key.replace('_', ':')), str(value))
    return node


def math_nodes(value):
    """Convert supported Typst math trees to native Office Math, failing on loss."""
    if value is None:
        return []
    if isinstance(value, str):
        value = {"func": "text", "text": value}
    if not isinstance(value, dict):
        raise ReportError(f"Unsupported math value: {value!r}")
    kind = value.get("func")
    if kind in ("equation", "lr"):
        return math_nodes(value["body"])
    if kind == "sequence":
        return [node for child in value["children"] for node in math_nodes(child)]
    if kind in ("text", "symbol", "space"):
        run = element("m:r")
        text = element("m:t")
        text.set(qn("xml:space"), "preserve")
        text.text = " " if kind == "space" else value["text"]
        run.append(text)
        return [run]
    if kind == "frac":
        frac = element("m:f")
        for tag, key in (("m:num", "num"), ("m:den", "denom")):
            child = element(tag); child.extend(math_nodes(value[key])); frac.append(child)
        return [frac]
    if kind == "attach":
        if any(value.get(k) is not None for k in ("tl", "tr", "bl", "br")):
            raise ReportError("Prescripts/side attachments are not supported in DOCX")
        top, bottom = value.get("t"), value.get("b")
        if top is None and bottom is None:
            return math_nodes(value["base"])
        node = element("m:sSubSup" if top is not None and bottom is not None else "m:sSup" if top is not None else "m:sSub")
        for tag, body in (("m:e", value["base"]), ("m:sub", bottom), ("m:sup", top)):
            if body is not None:
                child = element(tag); child.extend(math_nodes(body)); node.append(child)
        return [node]
    if kind == "root":
        node = element("m:rad")
        props = element("m:radPr")
        props.append(element("m:degHide", m_val="0" if value.get("index") is not None else "1"))
        node.append(props)
        for tag, body in (("m:deg", value.get("index")), ("m:e", value["radicand"])):
            child = element(tag); child.extend(math_nodes(body)); node.append(child)
        return [node]
    if kind in ("mat", "vec"):
        if value.get("augment") is not None:
            raise ReportError("Augmented matrices need an explicit DOCX implementation")
        rows = value["rows"] if kind == "mat" else [[v] for v in value["children"]]
        matrix = element("m:m")
        for row in rows:
            mr = element("m:mr")
            for cell in row:
                e = element("m:e"); e.extend(math_nodes(cell)); mr.append(e)
            matrix.append(mr)
        delim = value.get("delim", "(")
        if delim is None:
            return [matrix]
        pairs = {"(": ("(", ")"), "[": ("[", "]"), "{": ("{", "}"), "|": ("|", "|"), "||": ("‖", "‖")}
        if isinstance(delim, list) and len(delim) == 2:
            left, right = delim
        elif delim in pairs:
            left, right = pairs[delim]
        else:
            raise ReportError(f"Unsupported matrix delimiters: {delim}")
        d = element("m:d"); props = element("m:dPr")
        props.append(element("m:begChr", m_val=left)); props.append(element("m:endChr", m_val=right))
        d.append(props); e = element("m:e"); e.append(matrix); d.append(e)
        return [d]
    raise ReportError(f"Unsupported Typst math element '{kind}'; simplify it or extend math_nodes; no content was discarded")


class Exporter:
    def __init__(self, model, root):
        self.model, self.root = model, root
        self.cfg, self.info = model["config"], model["info"]
        self.doc = Document()
        self.pending_break = False
        self.targets = {b["id"]: b for b in model["blocks"] if b.get("id")}
        self.bookmarks = {key: (i, f"sr_{i}") for i, key in enumerate(self.targets, 1)}
        self.width = 210 - self.cfg["margins"]["left"] - self.cfg["margins"]["right"]
        self.setup()

    def setup(self):
        sec = self.doc.sections[0]
        sec.page_width, sec.page_height = Mm(210), Mm(297)
        for side, value in self.cfg["margins"].items():
            setattr(sec, side + "_margin", Mm(value))
        sec.footer_distance = Mm(10)
        sec.different_first_page_header_footer = True
        if "TOC Heading" not in self.doc.styles:
            self.doc.styles.add_style("TOC Heading", WD_STYLE_TYPE.PARAGRAPH)
        for name in ("Normal", "Caption", "Heading 1", "Heading 2", "Heading 3", "TOC Heading"):
            style = self.doc.styles[name]
            style.font.name = self.cfg["font"]
            style.font.size = Pt(self.cfg["font-size"])
            style.font.color.rgb = RGBColor(0, 0, 0)
            style.font.bold = bool(self.cfg["heading-bold"]) if name.startswith("Heading") or name == "TOC Heading" else False
            style.font.italic = False
            rp = style.element.get_or_add_rPr()
            fonts = rp.find(qn("w:rFonts"))
            for attr in tuple(fonts.attrib):
                if "theme" in attr.lower(): del fonts.attrib[attr]
            for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
                fonts.set(qn("w:" + attr), self.cfg["font"])
            rp.append(element("w:lang", w_val="ru-RU"))
            pf = style.paragraph_format
            pf.line_spacing = self.cfg["line-spacing"]
            pf.space_before = Pt(0)
            pf.space_after = Pt(self.cfg.get("paragraph-spacing", 0) if name == "Normal" else 0)
            props = style.element.get_or_add_pPr()
            props.append(element("w:suppressAutoHyphens", w_val="true" if name.startswith("Heading") or name == "TOC Heading" or not self.cfg.get("hyphenate", False) else "false"))
            pf.first_line_indent = Mm(self.cfg["first-indent"] if name == "Normal" else 0)
            pf.widow_control = True
            if name.startswith("Heading") or name == "TOC Heading":
                level = int(name[-1]) if name.startswith("Heading") else 1
                pf.keep_with_next = True
                pf.keep_together = True
                pf.space_before = Pt(self.cfg.get("heading-space-before", [12, 9, 6])[level - 1])
                pf.space_after = Pt(self.cfg.get("heading-space-after", [6, 6, 3])[level - 1])
                props = style.element.get_or_add_pPr()
                outline = props.find(qn("w:outlineLvl"))
                if outline is None:
                    outline = element("w:outlineLvl"); props.append(outline)
                outline.set(qn("w:val"), str(level - 1 if name.startswith("Heading") else 9))
        p = sec.footer.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Mm(0)
        self.field(p, "PAGE", "2")
        settings = self.doc.settings.element
        settings.append(element("w:updateFields", w_val="true"))
        settings.append(element("w:autoHyphenation", w_val="true" if self.cfg.get("hyphenate", False) else "false"))
        mathpr = settings.find(qn("m:mathPr"))
        if mathpr is None:
            mathpr = element("m:mathPr"); settings.append(mathpr)
        old = mathpr.find(qn("m:mathFont"))
        if old is not None:
            mathpr.remove(old)
        mathpr.insert(0, element("m:mathFont", m_val=self.cfg["math-font"]))
        self.doc.core_properties.title = self.info["topic"]
        self.doc.core_properties.author = "; ".join(self.info["students"])

    @staticmethod
    def field(paragraph, code, cached=""):
        paragraph.add_run()._r.append(element("w:fldChar", w_fldCharType="begin"))
        instruction = element("w:instrText"); instruction.text = " " + code + " "
        instruction.set(qn("xml:space"), "preserve")
        paragraph.add_run()._r.append(instruction)
        paragraph.add_run()._r.append(element("w:fldChar", w_fldCharType="separate"))
        paragraph.add_run(cached)
        paragraph.add_run()._r.append(element("w:fldChar", w_fldCharType="end"))

    def paragraph(self, body=None, align=WD_ALIGN_PARAGRAPH.JUSTIFY, indent=True, style=None):
        p = self.doc.add_paragraph(style=style)
        if self.pending_break:
            p.paragraph_format.page_break_before = True
            self.pending_break = False
        p.alignment = align
        if not indent:
            p.paragraph_format.first_line_indent = Mm(0)
        if body is not None:
            self.inline(p, body)
        return p

    def append_math(self, paragraph, value):
        node = element("m:oMath")
        node.extend(math_nodes(value))
        for run in node.iter(qn("m:r")):
            props = element("w:rPr")
            props.append(element("w:rFonts", w_ascii=self.cfg["math-font"], w_hAnsi=self.cfg["math-font"], w_cs=self.cfg["math-font"]))
            props.append(element("w:sz", w_val=round(self.cfg["font-size"] * 2)))
            run.insert(0, props)
        paragraph._p.append(node)

    def inline(self, p, value, bold=None, italic=None):
        if value is None:
            return
        if isinstance(value, str):
            r = p.add_run(value); r.bold, r.italic = bold, italic
            return
        if not isinstance(value, dict):
            raise ReportError(f"Unsupported inline value: {value!r}")
        kind = value.get("func")
        if kind == "sequence":
            for child in value["children"]:
                self.inline(p, child, bold, italic)
        elif kind in ("text", "symbol", "space", "raw"):
            if kind == "raw" and value.get("block"):
                raise ReportError("Use paragraph blocks for text; block code requires a dedicated exporter")
            self.inline(p, " " if kind == "space" else value["text"], bold, italic)
        elif kind == "strong":
            self.inline(p, value["body"], not bold, italic)
        elif kind == "emph":
            self.inline(p, value["body"], bold, not italic)
        elif kind == "linebreak":
            p.add_run().add_break(WD_BREAK.LINE)
        elif kind == "equation":
            self.append_math(p, value)
        elif kind == "ref":
            key = reference_id(value)
            if key not in self.targets:
                raise ReportError(f"Unknown reference: {key}")
            if set(value) - {"func", "target"}:
                raise ReportError("Custom ref supplements/forms are not supported; use plain @id")
            text = reference_text(self.targets[key], self.cfg["short-refs"])
            self.hyperlink(p, text, anchor=self.bookmarks[key][1])
        elif kind == "link":
            destination = value["dest"]
            if not isinstance(destination, str) or destination.startswith("<"):
                raise ReportError("Use @id for internal references")
            self.hyperlink(p, value["body"], url=destination)
        elif kind in ("sub", "super", "underline", "strike"):
            before = len(p.runs)
            self.inline(p, value["body"], bold, italic)
            for run in p.runs[before:]:
                if kind == "sub": run.font.subscript = True
                elif kind == "super": run.font.superscript = True
                elif kind == "underline": run.underline = True
                else: run.font.strike = True
        else:
            raise ReportError(f"Unsupported Typst inline element '{kind}'; use explicit report blocks (see references/docx.md)")

    def hyperlink(self, p, body, anchor=None, url=None):
        # Build runs with the same inline renderer, then move them into the link.
        start = len(p._p)
        self.inline(p, body)
        runs = list(p._p)[start:]
        link = element("w:hyperlink")
        if anchor:
            link.set(qn("w:anchor"), anchor)
        if url:
            link.set(qn("r:id"), p.part.relate_to(url, RT.HYPERLINK, is_external=True))
        for run in runs:
            link.append(run)
        p._p.append(link)

    def bookmark(self, p, block):
        if not block.get("id"):
            return
        number, name = self.bookmarks[block["id"]]
        p._p.append(element("w:bookmarkStart", w_id=number, w_name=name))
        p._p.append(element("w:bookmarkEnd", w_id=number))

    def title(self):
        info = self.info
        center, right = WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.RIGHT
        organization = [info[k] for k in ("ministry", "organization", "university", "university-detail", "department") if info[k]]
        for line in organization:
            p = self.paragraph(line, center, False)
            if self.model["title"] == "mai-course" and self.cfg["profile"] != "gost-2001-strict" and line in (info["university"], info["university-detail"]):
                for run in p.runs: run.bold = True
        work = [info["work-kind"], "по дисциплине", f'«{info["discipline"]}»']
        if info["topic"]: work.append(f'на тему: «{info["topic"]}»')
        if info["variant"]: work.append(f'{info["variant"]} вариант')
        p = self.paragraph("\n".join(work), center, False)
        p.paragraph_format.space_before = Mm({"mai-course": 50, "generic": 35, "lab": 24}[self.model["title"]])
        p.paragraph_format.keep_together = True
        people = [info["student-label"]]
        for student in info["students"]:
            prefix = f'Студент группы {info["group"]} ' if self.model["title"] == "mai-course" and info["group"] else ""
            people.append(prefix + student)
        if self.model["title"] != "mai-course" and info["group"]:
            people.append("Группа " + info["group"])
        people += ["", info["teacher-label"], " ".join(x for x in (info["teacher-position"], info["teacher"]) if x)]
        p = self.paragraph("\n".join(people), right, False)
        p.paragraph_format.space_before = Mm(24 if self.model["title"] == "generic" else 30)
        p.paragraph_format.keep_together = True
        p = self.paragraph(info["city"] + "\n" + str(info["year"]), center, False)
        p.paragraph_format.space_before = Mm(12)
        p.paragraph_format.keep_together = True
        self.pending_break = True

    def list_numbering(self, ordered):
        numbering = self.doc.part.numbering_part.element
        abstract_id = max([int(n.get(qn("w:abstractNumId"))) for n in numbering.findall(qn("w:abstractNum"))] + [-1]) + 1
        num_id = max([int(n.get(qn("w:numId"))) for n in numbering.findall(qn("w:num"))] + [0]) + 1
        abstract = element("w:abstractNum", w_abstractNumId=abstract_id)
        lvl = element("w:lvl", w_ilvl=0)
        lvl.append(element("w:start", w_val=1))
        lvl.append(element("w:numFmt", w_val="decimal" if ordered else "bullet"))
        lvl.append(element("w:lvlText", w_val="%1." if ordered else "–"))
        abstract.append(lvl); numbering.append(abstract)
        num = element("w:num", w_numId=num_id); num.append(element("w:abstractNumId", w_val=abstract_id)); numbering.append(num)
        return num_id

    def add_report_picture(self, paragraph, path, block):
        """Use original media plus native DrawingML crop; preserve visible aspect ratio."""
        img = DocxImage.from_file(str(path))
        crop = block.get("crop") or {"left": 0, "top": 0, "right": 0, "bottom": 0}
        left, top, right, bottom = [crop[k] for k in ("left", "top", "right", "bottom")]
        if (any(v < 0 or v >= 1 for v in (left, top, right, bottom))
                or left + right >= 1 or top + bottom >= 1):
            raise ReportError("Crop margins must leave a nonempty image")
        ratio = img.px_width * (1 - left - right) / (img.px_height * (1 - top - bottom))
        limit = block.get("max-height")
        if limit is None:
            limit = self.cfg.get("figure-max-height", 80)
        if limit <= 0 or not 0 < block["width"] <= 1:
            raise ReportError("Image size limits must be positive; width must be in (0, 1]")
        width = min(self.width * block["width"], limit * ratio)
        height = width / ratio
        shape = paragraph.add_run().add_picture(str(path), width=Mm(width), height=Mm(height))
        if block.get("crop") is not None:
            rect = element("a:srcRect")
            for key, value in zip(("l", "t", "r", "b"), (left, top, right, bottom)):
                rect.set(key, str(round(value * 100000)))
            fill = shape._inline.graphic.graphicData.pic.blipFill
            fill.insert(1, rect)
        return shape

    def render(self):
        self.title()
        if self.cfg["contents"]:
            self.paragraph("СОДЕРЖАНИЕ", WD_ALIGN_PARAGRAPH.CENTER, False, style="TOC Heading")
            p = self.paragraph(indent=False)
            self.field(p, f'TOC \\o "1-{self.cfg["contents-depth"]}" \\h \\z \\u')
            self.pending_break = True
        for block in self.model["blocks"]:
            kind = block["kind"]
            if kind == "paragraph":
                self.paragraph(block["body"])
            elif kind == "heading":
                p = self.paragraph(indent=False, style=f'Heading {block["level"]}')
                p.paragraph_format.page_break_before = bool(block["new-page"] or p.paragraph_format.page_break_before)
                p.paragraph_format.keep_with_next = True
                p.paragraph_format.keep_together = True
                upper = block["structural"] or (block["level"] == 1 and self.cfg["heading-uppercase"])
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER if upper else WD_ALIGN_PARAGRAPH.LEFT
                if block["number"]: p.add_run(block["number"] + " ")
                self.inline(p, block["body"])
                if upper:
                    for run in p.runs: run.text = run.text.upper()
                self.bookmark(p, block)
            elif kind == "figure":
                path = asset_path(self.root, block["path"])
                if path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
                    raise ReportError(f"DOCX images must be PNG/JPEG; convert explicitly: {path.name}")
                p = self.paragraph(align=WD_ALIGN_PARAGRAPH.CENTER, indent=False)
                p.paragraph_format.keep_with_next = True
                self.add_report_picture(p, path, block)
                p = self.paragraph(align=WD_ALIGN_PARAGRAPH.CENTER, indent=False, style="Caption")
                p.add_run(f'Рисунок {block["number"]} – '); self.inline(p, block["caption"])
                p.paragraph_format.keep_together = True
                p.paragraph_format.space_after = Pt(6)
                self.bookmark(p, block)
            elif kind == "table":
                p = self.paragraph(align=WD_ALIGN_PARAGRAPH.LEFT, indent=False, style="Caption")
                p.add_run(f'Таблица {block["number"]} – '); self.inline(p, block["caption"])
                p.paragraph_format.keep_with_next = True; self.bookmark(p, block)
                rows = [block["headers"]] + block["rows"]
                widths = block["widths"] or [1] * len(rows[0])
                table = self.doc.add_table(rows=0, cols=len(widths)); table.autofit = False
                table.style = "Table Grid"
                for column, width in zip(table.columns, widths):
                    column.width = Mm(self.width * width / sum(widths))
                borders = element("w:tblBorders")
                for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
                    borders.append(element("w:" + edge, w_val="single", w_sz=4, w_color="000000"))
                table._tbl.tblPr.append(borders)
                for i, row in enumerate(rows):
                    cells = table.add_row().cells
                    trpr = table.rows[-1]._tr.get_or_add_trPr()
                    trpr.append(element("w:cantSplit"))
                    if i == 0: trpr.append(element("w:tblHeader", w_val="true"))
                    for cell, body, width in zip(cells, row, widths):
                        cell.width = Mm(self.width * width / sum(widths))
                        p = cell.paragraphs[0]
                        p.paragraph_format.first_line_indent = Mm(0)
                        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                        self.inline(p, body)
            elif kind == "equation":
                p = self.paragraph(indent=False, align=WD_ALIGN_PARAGRAPH.LEFT)
                p.paragraph_format.tab_stops.add_tab_stop(Mm(self.width / 2), WD_TAB_ALIGNMENT.CENTER)
                p.paragraph_format.tab_stops.add_tab_stop(Mm(self.width), WD_TAB_ALIGNMENT.RIGHT)
                p.add_run("\t")
                self.append_math(p, block["body"])
                p.add_run("\t(" + block["number"] + ")")
                p.paragraph_format.space_before = p.paragraph_format.space_after = Pt(6)
                self.bookmark(p, block)
            elif kind == "list":
                num_id = self.list_numbering(block["ordered"])
                for body in block["items"]:
                    p = self.paragraph(body, indent=False)
                    pf = p.paragraph_format
                    pf.left_indent = Mm(self.cfg["first-indent"] + 6)
                    pf.first_line_indent = Mm(-6)
                    props = element("w:numPr"); props.append(element("w:ilvl", w_val=0)); props.append(element("w:numId", w_val=num_id))
                    p._p.get_or_add_pPr().append(props)
            elif kind == "source":
                p = self.paragraph(indent=False, align=WD_ALIGN_PARAGRAPH.LEFT)
                p.add_run(block["number"] + ". "); self.inline(p, block["body"]); self.bookmark(p, block)
            elif kind == "pagebreak":
                self.pending_break = True
            else:
                raise ReportError(f"Unsupported block: {kind}")
        return self.doc


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path)
    ap.add_argument("output", type=Path, nargs="?")
    args = ap.parse_args()
    source = args.source.resolve()
    output = (args.output or source.with_suffix(".docx")).resolve()
    if output.suffix.lower() != ".docx":
        ap.error("Output filename must end in .docx")
    temp = None
    try:
        model = load_model(source)
        doc = Exporter(model, source.parent).render()
        output.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(suffix=".docx", dir=output.parent)
        os.close(fd)
        doc.save(temp)
        os.replace(temp, output)
        print(f"Created {output}")
        if model["config"]["contents"]:
            print("TOC is a Word field: update all fields in Word/LibreOffice before checking pagination.")
        print("Check Word pagination separately from Typst PDF; both use the same source content.")
    except (ReportError, OSError, ValueError) as exc:
        ap.exit(1, f"DOCX ERROR: {exc}\n")
    finally:
        if temp and Path(temp).exists(): Path(temp).unlink()


if __name__ == "__main__":
    main()
