"""TheSNMC RustDB content transforms applied during decay stages."""

from __future__ import annotations

import gzip
import json
import csv
from pathlib import Path
import zipfile


def summarize_log(text: str, max_words: int = 12) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + " ...[summary]"


def compress_image_marker(payload: str) -> str:
    """
    Placeholder image compression.
    For the MVP we model image data as a text marker.
    """
    if payload.startswith("compressed("):
        return payload
    return f"compressed({payload})"


def summarize_text_file(path: str, max_words: int = 80) -> str:
    source = Path(path)
    text = source.read_text(encoding="utf-8", errors="ignore")
    words = text.split()
    summary = " ".join(words[:max_words])
    if len(words) > max_words:
        summary += " ...[summary]"
    target = source.with_suffix(source.suffix + ".summary.txt")
    target.write_text(summary, encoding="utf-8")
    return str(target)


def compress_image_file(path: str, quality: int = 45) -> str:
    source = Path(path)
    target = source.with_suffix(".compressed.jpg")
    try:
        from PIL import Image
    except Exception:
        # Pillow not installed; return original path so decay still progresses.
        return str(source)
    with Image.open(source) as img:
        rgb = img.convert("RGB")
        rgb.save(target, format="JPEG", optimize=True, quality=quality)
    return str(target)


def compress_image_file_aggressive(path: str, quality: int = 20, max_side: int = 768) -> str:
    source = Path(path)
    target = source.with_suffix(".cold.jpg")
    try:
        from PIL import Image
    except Exception:
        return str(source)
    with Image.open(source) as img:
        rgb = img.convert("RGB")
        rgb.thumbnail((max_side, max_side))
        rgb.save(target, format="JPEG", optimize=True, quality=quality)
    return str(target)


def compress_binary_file(path: str) -> str:
    source = Path(path)
    target = source.with_suffix(source.suffix + ".gz")
    with source.open("rb") as src, gzip.open(target, "wb", compresslevel=6) as gz:
        gz.write(src.read())
    return str(target)


def metadata_only_file(path: str) -> str:
    source = Path(path)
    meta = {
        "name": source.name,
        "size_bytes": source.stat().st_size if source.exists() else 0,
        "suffix": source.suffix.lower(),
    }
    target = source.with_suffix(source.suffix + ".meta.json")
    target.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return str(target)


def summarize_spreadsheet_file(path: str, max_rows: int = 10) -> str:
    source = Path(path)
    target = source.with_suffix(source.suffix + ".summary.txt")
    suffix = source.suffix.lower()
    lines: list[str] = [f"name={source.name}", f"suffix={suffix}"]
    try:
        if suffix == ".csv":
            with source.open("r", encoding="utf-8", errors="ignore", newline="") as f:
                reader = csv.reader(f)
                for idx, row in enumerate(reader):
                    if idx >= max_rows:
                        break
                    lines.append(",".join(row))
        elif suffix in {".xlsx", ".xlsm"}:
            # xlsx is zip+xml; this extracts a small text snapshot without extra dependencies.
            with zipfile.ZipFile(source, "r") as zf:
                sheet_names = [n for n in zf.namelist() if n.startswith("xl/worksheets/sheet")]
                lines.append(f"sheet_count={len(sheet_names)}")
                if sheet_names:
                    data = zf.read(sheet_names[0]).decode("utf-8", errors="ignore")
                    lines.append(data[:1500])
        else:
            lines.append("unsupported_spreadsheet_format")
    except Exception as exc:
        lines.append(f"summary_error={type(exc).__name__}")
    target.write_text("\n".join(lines), encoding="utf-8")
    return str(target)


def summarize_document_file(path: str) -> str:
    source = Path(path)
    target = source.with_suffix(source.suffix + ".summary.txt")
    suffix = source.suffix.lower()
    lines = [f"name={source.name}", f"suffix={suffix}", f"size_bytes={source.stat().st_size if source.exists() else 0}"]
    try:
        if suffix == ".pdf":
            lines.append("pdf_summary=metadata_only (install pypdf for rich text extraction)")
        elif suffix == ".docx":
            with zipfile.ZipFile(source, "r") as zf:
                xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
                lines.append(xml[:2000])
        elif suffix in {".txt", ".md", ".log", ".json"}:
            lines.append(source.read_text(encoding="utf-8", errors="ignore")[:2000])
        else:
            lines.append("document_summary=metadata_only")
    except Exception as exc:
        lines.append(f"summary_error={type(exc).__name__}")
    target.write_text("\n".join(lines), encoding="utf-8")
    return str(target)

