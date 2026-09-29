#!/usr/bin/env python3
"""Create a modular report without replacing any existing file."""
import argparse
from datetime import date
from pathlib import Path
import shutil


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("destination", type=Path)
    ap.add_argument("--title", choices=("lab", "mai-course", "generic"))
    ap.add_argument("--profile", choices=("student-lab", "student-course", "gost-2001-strict"), default="student-lab")
    args = ap.parse_args()
    target = args.destination.resolve()
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        ap.error("Destination must be absent or empty; existing reports are never overwritten")
    template = Path(__file__).resolve().parents[1] / "templates"
    shutil.copytree(template, target, dirs_exist_ok=True)
    (target / "images").mkdir(exist_ok=True)
    if args.title:
        (target / "titles/selected.typ").write_text(f'#let title-variant = "{args.title}"\n', encoding="utf-8")
    path = target / "settings/config.typ"
    config = path.read_text(encoding="utf-8").replace('profile: "student-lab"', f'profile: "{args.profile}"')
    if args.profile == "student-course":
        config = config.replace("right: 10", "right: 15").replace("heading-bold: false", "heading-bold: true")
        config = config.replace("heading-uppercase: false", "heading-uppercase: true")
        config = config.replace('equation-numbering: "continuous"', 'equation-numbering: "section"')
        config = config.replace("contents: false", "contents: true")
        for name, var, title in [("01-introduction", "introduction", "ВВЕДЕНИЕ"), ("03-conclusion", "conclusion", "ЗАКЛЮЧЕНИЕ")]:
            (target / f"chapters/{name}.typ").write_text(
                '#import "../settings/blocks.typ": *\n'
                f'#let {var} = (structural([{title}]),)\n', encoding="utf-8")
        (target / "chapters/02-main.typ").write_text(
            '#import "../settings/blocks.typ": *\n#import "../tables/results.typ": results\n'
            '#let main-part = (section([Теоретическая часть]),\n'
            '  section([Практическая часть]), ..results)\n', encoding="utf-8")
    elif args.profile == "gost-2001-strict":
        config = config.replace("short-refs: true", "short-refs: false")
        config = config.replace("heading-bold: true", "heading-bold: false")
    path.write_text(config, encoding="utf-8")
    meta = target / "settings/metadata.typ"
    text = meta.read_text(encoding="utf-8").replace('year: ""', f'year: "{date.today().year}"')
    if args.title == "mai-course" or args.profile == "student-course":
        text = text.replace('work-kind: "Лабораторная работа"', 'work-kind: "Курсовая работа"')
    if args.title == "generic":
        for value in ("Федеральное государственное автономное образовательное учреждение высшего образования",
                      "Московский авиационный институт", "(национальный исследовательский университет)", "Москва"):
            text = text.replace(f'"{value}"', '""')
    meta.write_text(text, encoding="utf-8")
    print(f"Created {target}")
    if not args.title:
        print("Title pending: ask the user (lab / mai-course / generic), then edit titles/selected.typ")


if __name__ == "__main__":
    main()
