"""Integration checks use synthetic data in disposable projects, never user reports."""
from datetime import date
import importlib.util
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from zipfile import ZipFile
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from report_model import ReportError, load_model
from preflight import check_model, check_docx


def run(*args):
    return subprocess.run([str(a) for a in args], text=True, capture_output=True, timeout=120)


def write_png(path):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    raw = b"".join(b"\0" + b"\xff\xff\xff" * 400 for _ in range(100))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 400, 100, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


@unittest.skipUnless(shutil.which("typst"), "Typst is required for integration checks")
class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="report tests ")
        self.base = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def project(self, title="lab", profile="student-lab"):
        path = self.base / title
        result = run(sys.executable, ROOT / "scripts/init_project.py", path, "--title", title, "--profile", profile)
        self.assertEqual(result.returncode, 0, result.stderr)
        meta = path / "settings/metadata.typ"
        text = meta.read_text()
        changes = {'discipline: ""': 'discipline: "Проверка шаблона"', 'group: ""': 'group: "ТЕСТ-01"',
                   'students: ()': 'students: ("Иванов И. И.",)', 'teacher: ""': 'teacher: "Петров П. П."',
                   'university: ""': 'university: "Учебный вуз"', 'city: ""': 'city: "Москва"'}
        for old, new in changes.items(): text = text.replace(old, new)
        meta.write_text(text)
        (path / "chapters/01-introduction.typ").write_text('''#import "../settings/blocks.typ": *
#let introduction = (structural([ВВЕДЕНИЕ], new-page: true), para[Синтетическая проверка экспорта. Источник: @src-test.])
''')
        (path / "chapters/02-main.typ").write_text('''#import "../settings/blocks.typ": *
#import "../tables/results.typ": results
#let main-part = (
 section([Первая глава]), section([Подраздел], level: 2),
 para[Формулы @eq-first и @eq-second проверяют экспорт.],
 formula($a_1^2 = frac(b,c) + root(3,x)$, id: "eq-first"),
 section([Следующий подраздел], level: 2),
 formula($H = mat(delim: "[", 1,2;3,4)$, id: "eq-second"),
 section([Вторая глава]),
 formula($x = vec(1,2)$, id: "eq-third"),
 para[Изображение показано на @fig-test, данные — в @tab-test.],
 screenshot("images/проверка.png", [Синтетический рисунок], id: "fig-test", width: 0.7),
 ..results,
 numbered-list(([Первый пункт], [Второй пункт])),
 bullet-list(([Маркер один], [Маркер два])),
)
''')
        (path / "tables/results.typ").write_text('''#import "../settings/blocks.typ": *
#let results = (result-table([Синтетические данные], ([№], [Результат]), (([1], [Да]), ([2], [Нет])), id: "tab-test"),)
''')
        (path / "chapters/03-conclusion.typ").write_text('''#import "../settings/blocks.typ": *
#let conclusion = (structural([ЗАКЛЮЧЕНИЕ]), para[Это проверочный документ, не эксперимент.])
''')
        (path / "bibliography/sources.typ").write_text('''#import "../settings/blocks.typ": *
#let sources = (source("src-test", [Проверочный источник.]),)
''')
        write_png(path / "images/проверка.png")
        return path

    def test_structure_pending_title_and_no_overwrite(self):
        path = self.base / "pending"
        result = run(sys.executable, ROOT / "scripts/init_project.py", path)
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("images", "tables", "titles", "settings", "chapters", "bibliography"):
            self.assertTrue((path / name).is_dir())
        with self.assertRaises(ReportError): load_model(path / "report.typ")
        original = (path / "report.typ").read_bytes()
        result = run(sys.executable, ROOT / "scripts/init_project.py", path, "--title", "lab")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((path / "report.typ").read_bytes(), original)

    def test_all_titles_compile_and_models_validate(self):
        for title, profile in (("lab", "student-lab"), ("mai-course", "student-course"), ("generic", "gost-2001-strict")):
            with self.subTest(title=title):
                path = self.project(title, profile)
                result = run("typst", "compile", path / "report.typ", path / "report.pdf")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("unknown font", result.stderr)
                model = load_model(path / "report.typ")
                self.assertEqual(model["info"]["year"], str(date.today().year))
                self.assertEqual(model["title"], title)
                self.assertEqual(check_model(model, path)[0], [])

    @unittest.skipUnless(shutil.which("pdftotext"), "Poppler is required to measure rendered line positions")
    def test_body_line_pitch_is_equal_inside_and_between_paragraphs(self):
        path = self.project()
        (path / "report.typ").write_text('''#import "settings/config.typ": config
#import "settings/metadata.typ": info
#import "settings/blocks.typ": *
#import "settings/render.typ": render-report
#render-report(config, info, "lab", (
 para[Alpha #linebreak() Bravo],
 para[Charlie],
 para[Delta @fig-test.],
 screenshot("images/проверка.png", [Синтетический рисунок], id: "fig-test"),
))
''')
        result = run("typst", "compile", path / "report.typ", path / "report.pdf")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = run("pdftotext", "-bbox", path / "report.pdf", path / "positions.xml")
        self.assertEqual(result.returncode, 0, result.stderr)
        positions = {w.text: float(w.get("yMin")) for w in ET.parse(path / "positions.xml").iter("{http://www.w3.org/1999/xhtml}word")}
        for first, second in (("Alpha", "Bravo"), ("Bravo", "Charlie"), ("Charlie", "Delta")):
            self.assertAlmostEqual(positions[second] - positions[first], 21, places=3)

    @unittest.skipUnless(shutil.which("pdftotext") and importlib.util.find_spec("docx"), "Poppler and python-docx are required")
    def test_body_hyphenation_is_disabled_in_pdf_and_word(self):
        path = self.project()
        word = "администрирование"
        (path / "chapters/03-conclusion.typ").write_text(
            '#import "../settings/blocks.typ": *\n#let conclusion = (para[' + " ".join([word] * 30) + '],)\n')
        result = run("typst", "compile", path / "report.typ", path / "report.pdf")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = run("pdftotext", "-layout", path / "report.pdf", "-")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count(word), 30)
        self.assertNotIn("\u00ad", result.stdout)
        result = run(sys.executable, ROOT / "scripts/export_docx.py", path / "report.typ")
        self.assertEqual(result.returncode, 0, result.stderr)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        attr = "{" + ns["w"] + "}val"
        with ZipFile(path / "report.docx") as archive:
            settings = ET.fromstring(archive.read("word/settings.xml"))
            styles = ET.fromstring(archive.read("word/styles.xml"))
        self.assertEqual(settings.find("w:autoHyphenation", ns).get(attr), "false")
        normal = styles.find('w:style[@w:styleId="Normal"]', ns)
        self.assertEqual(normal.find("w:pPr/w:suppressAutoHyphens", ns).get(attr), "true")
        spacing = normal.find("w:pPr/w:spacing", ns)
        for key in ("before", "after"):
            self.assertEqual(spacing.get("{" + ns["w"] + "}" + key), "0")
        self.assertEqual(check_docx(path / "report.docx", load_model(path / "report.typ"))[0], [])

    @unittest.skipUnless(importlib.util.find_spec("docx"), "python-docx is required")
    def test_heading_levels_remain_semantic_and_follow_profile(self):
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        attr = "{" + ns["w"] + "}val"
        for title, profile, bold in (("lab", "student-lab", True), ("generic", "gost-2001-strict", False)):
            with self.subTest(profile=profile):
                path = self.project(title, profile)
                chapter = path / "chapters/02-main.typ"
                chapter.write_text(chapter.read_text().replace(
                    'section([Подраздел], level: 2),',
                    'section([Подраздел], level: 2), section([Именованный пункт], level: 3),'))
                model = load_model(path / "report.typ")
                self.assertEqual(model["config"]["heading-bold"], bold)
                result = run(sys.executable, ROOT / "scripts/export_docx.py", path / "report.typ")
                self.assertEqual(result.returncode, 0, result.stderr)
                with ZipFile(path / "report.docx") as archive:
                    styles = ET.fromstring(archive.read("word/styles.xml"))
                    document = ET.fromstring(archive.read("word/document.xml"))
                for level in (1, 2, 3):
                    style_id = f"Heading{level}"
                    style = styles.find(f'w:style[@w:styleId="{style_id}"]', ns)
                    self.assertIsNotNone(style)
                    self.assertEqual(style.find("w:pPr/w:outlineLvl", ns).get(attr), str(level - 1))
                    bold_node = style.find("w:rPr/w:b", ns)
                    self.assertEqual(bold_node is not None and bold_node.get(attr) != "0", bold)
                    self.assertIsNotNone(style.find("w:pPr/w:keepNext", ns))
                    self.assertIsNotNone(style.find("w:pPr/w:keepLines", ns))
                    paragraphs = [p for p in document.findall(".//w:p", ns)
                                  if p.find(f'w:pPr/w:pStyle[@w:val="{style_id}"]', ns) is not None]
                    self.assertTrue(paragraphs)
                    self.assertFalse(any(p.findall('.//w:b[@w:val="0"]', ns) for p in paragraphs))

    @unittest.skipUnless(importlib.util.find_spec("docx"), "python-docx is required")
    def test_crop_uses_original_media_and_preserves_visible_aspect_ratio(self):
        path = self.project()
        original = (path / "images/проверка.png").read_bytes()
        chapter = path / "chapters/02-main.typ"
        chapter.write_text(chapter.read_text().replace('id: "fig-test", width: 0.7)',
            'id: "fig-test", width: 0.7, max-height: 20, '
            'crop: crop-px((100, 10, 200, 80), source: (400, 100)))'))
        result = run("typst", "compile", path / "report.typ", path / "report.pdf")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = run(sys.executable, ROOT / "scripts/export_docx.py", path / "report.typ")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((path / "images/проверка.png").read_bytes(), original)
        with ZipFile(path / "report.docx") as archive:
            media = [archive.read(n) for n in archive.namelist() if n.startswith("word/media/")]
            self.assertIn(original, media)
            xml = ET.fromstring(archive.read("word/document.xml"))
        ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main",
              "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"}
        crop = xml.find(".//a:srcRect", ns)
        self.assertEqual(crop.attrib, {"l": "25000", "t": "10000", "r": "25000", "b": "10000"})
        size = xml.find(".//wp:extent", ns)
        width, height = int(size.get("cx")), int(size.get("cy"))
        self.assertAlmostEqual(width / height, 2.5, places=5)
        self.assertLessEqual(height, 20 * 36000)
        self.assertAlmostEqual(height / 36000, 20, places=4)

    def test_crop_outside_source_is_rejected(self):
        path = self.project()
        chapter = path / "chapters/02-main.typ"
        chapter.write_text(chapter.read_text().replace('id: "fig-test", width: 0.7)',
            'id: "fig-test", width: 0.7, '
            'crop: crop-px((390, 0, 20, 50), source: (400, 100)))'))
        with self.assertRaises(ReportError):
            load_model(path / "report.typ")

    @unittest.skipUnless(shutil.which("pdftotext") and importlib.util.find_spec("docx"), "Poppler and python-docx are required")
    def test_heading_numbers_and_profile_page_breaks_in_both_formats(self):
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        for title, profile in (("lab", "student-lab"), ("mai-course", "student-course")):
            with self.subTest(profile=profile):
                path = self.project(title, profile)
                (path / "report.typ").write_text('''#import "settings/config.typ": config
#import "settings/metadata.typ": info
#import "settings/blocks.typ": *
#import "settings/render.typ": render-report
#import "titles/selected.typ": title-variant
#render-report(config, info, title-variant, (
 structural([ВВЕДЕНИЕ]), para[INTROTEXT],
 section([Глава один]), para[ALPHATEXT],
 section([Подраздел], level: 2), para[BRAVOTEXT],
 section([Пункт], level: 3), para[CHARLIETEXT],
 section([Другой подраздел], level: 2), para[DELTATEXT],
 section([Глава два]), para[ECHOTEXT],
 structural([ЗАКЛЮЧЕНИЕ]), para[FOXTROTTEXT],
))
''')
                model = load_model(path / "report.typ")
                heads = [b for b in model["blocks"] if b["kind"] == "heading"]
                self.assertEqual([h["number"] for h in heads], ["", "1.", "1.1.", "1.1.1.", "1.2.", "2.", ""])
                expected_breaks = [True, True, False, False, False, profile == "student-course", True]
                self.assertEqual([h["new-page"] for h in heads], expected_breaks)
                result = run("typst", "compile", path / "report.typ", path / "report.pdf")
                self.assertEqual(result.returncode, 0, result.stderr)
                result = run("pdftotext", "-layout", path / "report.pdf", "-")
                self.assertEqual(result.returncode, 0, result.stderr)
                pages = result.stdout.split("\f")
                location = {marker: next(i for i, text in enumerate(pages) if marker in text)
                            for marker in ("INTROTEXT", "ALPHATEXT", "BRAVOTEXT", "CHARLIETEXT", "DELTATEXT", "ECHOTEXT", "FOXTROTTEXT")}
                self.assertEqual(location["ALPHATEXT"], location["INTROTEXT"] + 1)
                for marker in ("BRAVOTEXT", "CHARLIETEXT", "DELTATEXT"):
                    self.assertEqual(location[marker], location["ALPHATEXT"])
                self.assertEqual(location["ECHOTEXT"], location["ALPHATEXT"] + int(profile == "student-course"))
                self.assertEqual(location["FOXTROTTEXT"], location["ECHOTEXT"] + 1)
                self.assertIn("1.1. Подраздел", " ".join(result.stdout.split()))
                self.assertIn("1.1.1. Пункт", " ".join(result.stdout.split()))
                result = run(sys.executable, ROOT / "scripts/export_docx.py", path / "report.typ")
                self.assertEqual(result.returncode, 0, result.stderr)
                with ZipFile(path / "report.docx") as archive:
                    doc = ET.fromstring(archive.read("word/document.xml"))
                paragraphs = [p for p in doc.findall(".//w:p", ns)
                              if (style := p.find("w:pPr/w:pStyle", ns)) is not None
                              and style.get("{" + ns["w"] + "}val") in ("Heading1", "Heading2", "Heading3")]
                self.assertEqual(len(paragraphs), len(heads))
                for paragraph, head, expected in zip(paragraphs, heads, expected_breaks):
                    node = paragraph.find("w:pPr/w:pageBreakBefore", ns)
                    actual = node is not None and node.get("{" + ns["w"] + "}val") not in ("0", "false", "off")
                    self.assertEqual(actual, expected)
                    if head["number"]:
                        text = "".join(t.text or "" for t in paragraph.findall(".//w:t", ns))
                        self.assertTrue(text.startswith(head["number"] + " "), text)

    def test_section_equations_reset_only_at_chapter(self):
        path = self.project("mai-course", "student-course")
        model = load_model(path / "report.typ")
        self.assertEqual([b["number"] for b in model["blocks"] if b["kind"] == "equation"], ["1.1", "1.2", "2.1"])

    def test_reference_must_precede_figure(self):
        path = self.project()
        p = path / "chapters/02-main.typ"
        p.write_text(p.read_text().replace("Изображение показано на @fig-test, данные — в @tab-test.", "Данные — в @tab-test."))
        errors, _ = check_model(load_model(path / "report.typ"), path)
        self.assertTrue(any("reference in prose before" in e for e in errors), errors)

    def test_missing_image_is_a_build_error(self):
        path = self.project()
        (path / "images/проверка.png").unlink()
        with self.assertRaises(ReportError): load_model(path / "report.typ")

    @unittest.skipUnless(importlib.util.find_spec("docx"), "python-docx is required")
    def test_docx_preserves_editable_content(self):
        path = self.project("mai-course", "student-course")
        result = run(sys.executable, ROOT / "scripts/export_docx.py", path / "report.typ")
        self.assertEqual(result.returncode, 0, result.stderr)
        model = load_model(path / "report.typ")
        self.assertEqual(check_docx(path / "report.docx", model)[0], [])
        with ZipFile(path / "report.docx") as archive:
            xml = ET.fromstring(archive.read("word/document.xml"))
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main", "m": "http://schemas.openxmlformats.org/officeDocument/2006/math"}
            for tag in ("m:f", "m:m", "m:rad", "m:sSubSup", "w:numPr", "w:hyperlink", "w:bookmarkStart"):
                self.assertIsNotNone(xml.find(".//" + tag, ns), tag)
            text = "".join(e.text or "" for e in xml.findall(".//w:t", ns))
            for actual in ("(1.1)", "(1.2)", "(2.1)", "Да", "Нет", "рис.\u00a01", "табл.\u00a01", "Синтетический рисунок"):
                self.assertIn(actual, text)
            self.assertTrue(any(n.startswith("word/media/") for n in archive.namelist()))
            # Consecutive requested page breaks coalesce, and runs inherit bold heading styles.
            self.assertFalse(xml.findall('.//w:br[@w:type="page"]', ns))
            headings = [p for p in xml.findall('.//w:p', ns) if p.find('w:pPr/w:pStyle[@w:val="Heading1"]', ns) is not None]
            self.assertTrue(headings)
            self.assertFalse(any(p.findall('.//w:b[@w:val="0"]', ns) for p in headings))

    @unittest.skipUnless(importlib.util.find_spec("docx"), "python-docx is required")
    def test_unsupported_content_does_not_replace_output(self):
        path = self.project()
        output = path / "report.docx"; output.write_bytes(b"original file")
        p = path / "chapters/03-conclusion.typ"
        p.write_text(p.read_text().replace("para[Это проверочный документ, не эксперимент.]", "para[#box[Неподдерживаемая вёрстка]]"))
        result = run(sys.executable, ROOT / "scripts/export_docx.py", path / "report.typ")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unsupported Typst inline", result.stderr)
        self.assertEqual(output.read_bytes(), b"original file")

    def test_page_cap_requires_rendered_artifact(self):
        path = self.project()
        result = run(sys.executable, ROOT / "scripts/preflight.py", path / "report.typ", "--max-pages", "5")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Cannot verify page limit", result.stdout)


if __name__ == "__main__":
    unittest.main()
