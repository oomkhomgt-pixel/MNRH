"""Every text-mode file read/write must name its encoding.

Without ``encoding=`` Python uses the OS locale's code page. On Thai-locale
Windows that is cp874, so the HTML report (declared UTF-8) would be garbled,
or fail to write, as soon as it contains a Thai case alias or a character
outside cp874. This is a static check because the default encoding cannot be
switched from inside a running interpreter.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = sorted((ROOT / "corridor_engine").glob("*.py")) + [ROOT / "CorridorFinder" / "CorridorFinder.py"]


def _text_io_without_encoding(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name not in ("open", "read_text", "write_text"):
            continue
        if any(kw.arg == "encoding" for kw in node.keywords):
            continue
        if name == "open":
            mode = node.args[1] if len(node.args) > 1 else next((kw.value for kw in node.keywords if kw.arg == "mode"), None)
            if isinstance(mode, ast.Constant) and "b" in mode.value:
                continue
        yield f"{path.name}:{node.lineno}"


def test_text_file_io_names_its_encoding():
    offenders = [loc for path in SOURCES for loc in _text_io_without_encoding(path)]
    assert not offenders, "text-mode file I/O without encoding=: " + ", ".join(offenders)
