"""Read the report model evaluated by Typst, including all imported modules."""
import json
from pathlib import Path
import subprocess


class ReportError(ValueError):
    pass


def load_model(source):
    source = Path(source).resolve()
    if not source.is_file():
        raise ReportError(f"Typst source not found: {source}")
    try:
        result = subprocess.run(
            ["typst", "query", "--root", str(source.parent), str(source),
             "<report-data>", "--field", "value", "--one"],
            text=True, capture_output=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReportError(f"Cannot run typst query: {exc}") from exc
    if result.returncode or "unknown font family" in result.stderr:
        raise ReportError(result.stderr.strip() or "Typst query failed")
    if result.stderr.strip():
        print(result.stderr.strip(), file=__import__('sys').stderr)
    try:
        model = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ReportError("Typst returned invalid JSON") from exc
    if not isinstance(model, dict) or model.get("schema") != 1:
        raise ReportError("Expected report-data schema 1. Adapt legacy Typst to the modular template first.")
    for key in ("config", "info", "title", "blocks"):
        if key not in model:
            raise ReportError(f"Missing model field: {key}")
    return model


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def reference_id(node):
    return node["target"].removeprefix("<").removesuffix(">")


def reference_text(block, short=True):
    number = block["number"]
    kind = block["kind"]
    if kind == "figure":
        return ("рис. " if short else "рисунок ") + number
    if kind == "table":
        return ("табл. " if short else "таблица ") + number
    if kind == "equation":
        return f"({number})"
    if kind == "source":
        return f"[{number}]"
    return number


def asset_path(root, relative):
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ReportError(f"Image must be inside the project: {relative}")
    if not path.is_file():
        raise ReportError(f"Image not found: {relative}")
    return path
