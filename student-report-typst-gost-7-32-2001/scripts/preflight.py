#!/usr/bin/env python3
"""Validate evaluated modular report data and optional PDF/DOCX artifacts."""
import argparse
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from zipfile import ZipFile, BadZipFile

from report_model import ReportError, asset_path, load_model, reference_id, walk

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
      "m": "http://schemas.openxmlformats.org/officeDocument/2006/math"}


def pdf_pages(path):
    if not path.is_file():
        raise ReportError(f"PDF not found: {path}")
    try:
        run = subprocess.run(["pdfinfo", str(path)], text=True, capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReportError(f"Cannot count PDF pages (install Poppler/pdfinfo): {exc}") from exc
    match = re.search(r"^Pages:\s+(\d+)\s*$", run.stdout, re.M)
    if run.returncode or not match:
        raise ReportError(f"pdfinfo failed: {run.stderr.strip()}")
    return int(match.group(1))


def check_model(model, root):
    errors, notes = [], []
    info, cfg, blocks = model["info"], model["config"], model["blocks"]
    for key in ("university", "work-kind", "discipline", "students", "group", "teacher", "city", "year"):
        if not info.get(key): errors.append(f"Missing title field: {key}")
    names = list(info.get("students", [])) + [info.get("teacher", "")]
    for name in filter(None, names):
        if not re.fullmatch(r"[А-ЯЁA-Z][А-Яа-яЁёA-Za-z’'–-]+(?: [А-ЯЁA-Z]\.){2}", name):
            notes.append(f"Check surname and spaced initials: {name}")
    if not any(b["kind"] == "paragraph" for b in blocks):
        errors.append("Report contains no body paragraphs; fill the scaffold")
    ids = {b["id"]: b for b in blocks if b.get("id")}
    seen_refs, cited_sources = set(), []
    for i, block in enumerate(blocks, 1):
        kind, key = block["kind"], block.get("id")
        if kind in ("figure", "table") and (not key or key not in seen_refs):
            errors.append(f"Block {i} ({kind}) needs an @id reference in prose before it appears")
        if kind == "figure":
            try: asset_path(root, block["path"])
            except ReportError as exc: errors.append(str(exc))
        # Captions/cells do not count as introductory prose.
        for node in walk(block):
            if node.get("func") == "ref":
                target = reference_id(node)
                if target not in ids:
                    errors.append(f"Unknown reference: {target}")
                if kind in ("paragraph", "list"):
                    seen_refs.add(target)
                    if target in ids and ids[target]["kind"] == "source" and target not in cited_sources:
                        cited_sources.append(target)
            if node.get("func") == "raw" and node.get("block"):
                notes.append(f"Block {i}: check that a terminal listing does not replace a supplied screenshot")
            if node.get("func") == "text" and re.search(r"\b(?:TODO|PLACEHOLDER|lorem ipsum)\b|ЗАПОЛНИТЬ", node.get("text", ""), re.I):
                errors.append(f"Unfinished placeholder in block {i}")
    source_ids = [b["id"] for b in blocks if b["kind"] == "source"]
    if source_ids != cited_sources:
        errors.append("Bibliography must contain only cited sources in order of first citation")
    if cfg["profile"] == "gost-2001-strict" and (cfg["short-refs"] or cfg["heading-bold"]):
        errors.append("Strict profile conflicts with abbreviated references/bold headings")
    notes.append(f'Profile: {cfg["profile"]}; title: {model["title"]}; font: {cfg["font"]} {cfg["font-size"]} pt')
    notes.append("Visual review still required: title fits one page, images legible, captions attached, no clipping")
    return errors, notes


def check_docx(path, model):
    errors, notes = [], []
    try:
        with ZipFile(path) as archive:
            bad = archive.testzip()
            if bad: raise ReportError(f"Corrupt ZIP member: {bad}")
            document = ET.fromstring(archive.read("word/document.xml"))
            styles = ET.fromstring(archive.read("word/styles.xml"))
            section = document.find(".//w:sectPr", NS)
            if section is None: raise ReportError("DOCX section settings are missing")
            if section.find("w:titlePg", NS) is None: errors.append("DOCX title page does not hide the first footer")
            size = section.find("w:pgSz", NS)
            for attr, mm in (("w", 210), ("h", 297)):
                if size is None or abs(int(size.get(f'{{{NS["w"]}}}{attr}', 0)) - mm / 25.4 * 1440) > 2:
                    errors.append("DOCX page is not A4")
            margins = section.find("w:pgMar", NS)
            for side, mm in model["config"]["margins"].items():
                if margins is None or abs(int(margins.get(f'{{{NS["w"]}}}{side}', 0)) - mm / 25.4 * 1440) > 2:
                    errors.append(f"DOCX margin differs from Typst config: {side}")
            for style in styles.findall("w:style", NS):
                style_id = style.get(f'{{{NS["w"]}}}styleId')
                if style_id in ("Normal", "Caption", "Heading1", "Heading2", "Heading3"):
                    fonts = style.find("w:rPr/w:rFonts", NS)
                    size_node = style.find("w:rPr/w:sz", NS)
                    if fonts is None or fonts.get(f'{{{NS["w"]}}}ascii') != model["config"]["font"] or any("theme" in k.lower() for k in fonts.attrib):
                        errors.append(f"DOCX font/theme mismatch in {style_id}")
                    if size_node is None or int(size_node.get(f'{{{NS["w"]}}}val', 0)) != model["config"]["font-size"] * 2:
                        errors.append(f"DOCX font size mismatch in {style_id}")
            normal = next((s for s in styles.findall("w:style", NS) if s.get(f'{{{NS["w"]}}}styleId') == "Normal"), None)
            if normal is None: raise ReportError("Normal style is missing")
            font = normal.find("w:rPr/w:rFonts", NS)
            fontsize = normal.find("w:rPr/w:sz", NS)
            spacing = normal.find("w:pPr/w:spacing", NS)
            if font is None or font.get(f'{{{NS["w"]}}}ascii') != model["config"]["font"]:
                errors.append("DOCX font differs from config")
            if fontsize is None or int(fontsize.get(f'{{{NS["w"]}}}val', 0)) != model["config"]["font-size"] * 2:
                errors.append("DOCX font size differs from config")
            if spacing is None or int(spacing.get(f'{{{NS["w"]}}}line', 0)) != round(model["config"]["line-spacing"] * 240):
                errors.append("DOCX line spacing differs from config")
            for attr, value in (("before", 0), ("after", model["config"].get("paragraph-spacing", 0))):
                if spacing is None or int(spacing.get(f'{{{NS["w"]}}}{attr}', -1)) != round(value * 20):
                    errors.append(f"DOCX paragraph {attr} spacing differs from config")
            settings = ET.fromstring(archive.read("word/settings.xml"))
            hyphenation = settings.find("w:autoHyphenation", NS)
            expected_hyphenation = bool(model["config"].get("hyphenate", False))
            if hyphenation is None or (hyphenation.get(f'{{{NS["w"]}}}val') not in ("0", "false", "off")) != expected_hyphenation:
                errors.append("DOCX automatic hyphenation differs from config")
            suppression = normal.find("w:pPr/w:suppressAutoHyphens", NS)
            if suppression is None or (suppression.get(f'{{{NS["w"]}}}val') not in ("0", "false", "off")) == expected_hyphenation:
                errors.append("DOCX paragraph hyphenation differs from config")
            expected_tables = sum(b["kind"] == "table" for b in model["blocks"])
            if len(document.findall(".//w:tbl", NS)) != expected_tables:
                errors.append("DOCX editable table count differs from source")
            expected_images = sum(b["kind"] == "figure" for b in model["blocks"])
            if len(document.findall(".//w:drawing", NS)) != expected_images:
                errors.append("DOCX image count differs from source")
            expected_math = sum(b["kind"] == "equation" for b in model["blocks"])
            if len(document.findall(".//m:oMath", NS)) < expected_math:
                errors.append("DOCX native equations are missing")
            footers = [archive.read(n) for n in archive.namelist() if re.fullmatch(r"word/footer\d+\.xml", n)]
            if not any(b"PAGE" in f for f in footers): errors.append("DOCX page-number field is missing")
            notes.append("DOCX XML: styles, geometry, editable tables, images and native equations checked")
            if model["config"]["contents"]: notes.append("Refresh the Word TOC field before validating final page numbers")
    except (OSError, BadZipFile, KeyError, ET.ParseError, ReportError, ValueError) as exc:
        errors.append(f"DOCX check failed: {exc}")
    return errors, notes


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("typ", type=Path)
    ap.add_argument("pdf", type=Path, nargs="?")
    ap.add_argument("--docx", type=Path)
    ap.add_argument("--docx-pdf", type=Path, help="PDF rendered from Word/LibreOffice for a separate page-count check")
    ap.add_argument("--max-pages", type=int)
    args = ap.parse_args()
    if args.max_pages is not None and args.max_pages < 1: ap.error("--max-pages must be positive")
    try:
        model = load_model(args.typ)
        errors, notes = check_model(model, args.typ.resolve().parent)
        if args.docx:
            more_errors, more_notes = check_docx(args.docx, model)
            errors += more_errors; notes += more_notes
        for label, path in (("Typst PDF", args.pdf), ("DOCX-rendered PDF", args.docx_pdf)):
            if path:
                try:
                    pages = pdf_pages(path); notes.append(f"{label}: {pages} pages")
                    if args.max_pages is not None and pages > args.max_pages:
                        errors.append(f"{label} exceeds page limit: {pages} > {args.max_pages}")
                except ReportError as exc: errors.append(str(exc))
        if args.max_pages and not (args.pdf or args.docx_pdf):
            errors.append("Cannot verify page limit without a rendered PDF")
        if args.max_pages and args.docx and not args.docx_pdf:
            errors.append("DOCX page cap is unverified: provide --docx-pdf after rendering it in an office app")
    except ReportError as exc:
        errors, notes = [str(exc)], []
    for note in notes: print("NOTE:", note)
    for error in errors: print("ERROR:", error)
    print("FAILED" if errors else "AUTOMATED CHECKS PASSED (visual review still required)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
