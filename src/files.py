from __future__ import annotations

import io
import json
import mimetypes
import re
from dataclasses import dataclass
from typing import Iterable, Optional

TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml", ".toml", ".csv", ".html", ".css", ".sql", ".sh", ".xml"}
MAX_CONTEXT_CHARS = 18_000


@dataclass(frozen=True)
class GeneratedFile:
    filename: str
    content: str
    language: str


def sanitize_filename(value: str, fallback: str = "download.txt") -> str:
    value = value.strip().replace("\\", "/").split("/")[-1]
    value = re.sub(r"[^A-Za-z0-9._-]", "_", value)
    return value[:120] or fallback


def guessed_mime(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def extract_text(filename: str, raw: bytes) -> str:
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            return "\n".join(page.extract_text() or "" for page in reader.pages)[:MAX_CONTEXT_CHARS]
        except Exception:
            return "[PDF text could not be extracted.]"
    if suffix in TEXT_SUFFIXES or not suffix:
        return raw.decode("utf-8", errors="replace")[:MAX_CONTEXT_CHARS]
    return "[Binary file: not included in model context.]"


def extract_generated_files(response: str) -> list[GeneratedFile]:
    """Recognize FILE: name markers directly above fenced code blocks."""
    pattern = re.compile(
        r"(?:^|\n)\s*(?:FILE|File)\s*:\s*([^\n]+)\n```([\w+-]*)\n(.*?)```",
        re.DOTALL,
    )
    files: list[GeneratedFile] = []
    for match in pattern.finditer(response):
        filename = sanitize_filename(match.group(1).strip())
        content = match.group(3).rstrip("\n")
        if content and len(content) <= 1_000_000:
            files.append(GeneratedFile(filename, content, match.group(2) or "text"))
    return files[:10]


def render_context(files: Iterable[tuple[str, str]]) -> str:
    chunks: list[str] = []
    remaining = MAX_CONTEXT_CHARS
    for filename, text in files:
        if remaining <= 0:
            break
        body = text[:remaining]
        chunks.append(f"--- {sanitize_filename(filename)} ---\n{body}")
        remaining -= len(body)
    return "\n\n".join(chunks)


def json_download(data: object) -> bytes:
    return json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
