from __future__ import annotations

from pathlib import Path
import re


def basic_metadata(filename: str, raw: bytes) -> dict[str, str | int]:
    suffix = Path(filename).suffix.lower()
    return {
        "filename": filename,
        "type": suffix.lstrip(".").upper(),
        "size_bytes": len(raw),
        "size_mb": round(len(raw) / (1024 * 1024), 2),
    }


def validate_upload(filename: str, raw: bytes, max_mb: int = 50) -> None:
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".docx", ".txt"}:
        raise ValueError("Supported files: PDF, DOCX and TXT.")
    if not raw:
        raise ValueError("The uploaded file is empty.")
    if len(raw) > max_mb * 1024 * 1024:
        raise ValueError(f"File exceeds the {max_mb} MB application limit.")
