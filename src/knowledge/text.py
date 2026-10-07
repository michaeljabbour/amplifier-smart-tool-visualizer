"""Reading material and cutting it into chunks. Deterministic, standard library only.

The chunker is the one from the original notebook pipeline: a recursive splitter that
tries paragraph, line, then word breaks, 1500 characters with 150 of overlap.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path

CHUNK_SIZE = 1500
CHUNK_OVERLAP = 150
TEXT_SUFFIXES = {
    ".md", ".markdown", ".txt", ".rst", ".org", ".html", ".htm", ".json", ".jsonl", ".csv",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb", ".c", ".h", ".cpp",
    ".cs", ".swift", ".kt", ".sql", ".yaml", ".yml", ".toml", ".tex", ".pdf",
}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".tox",
             ".mypy_cache", ".pytest_cache", ".ruff_cache", ".next", "target", ".obsidian"}
MAX_FILE_BYTES = 2_000_000


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def node_key(label: str) -> str:
    """The identity of a concept: lowercase, single spaces, no surrounding punctuation."""
    key = re.sub(r"\s+", " ", str(label)).strip().lower()
    return key.strip(" .,;:!?\"'`()[]{}<>*_#")


def split_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into pieces of at most `size` characters, breaking at the largest unit that fits."""
    text = text.strip()
    if not text:
        return []
    if size <= 0:
        raise ValueError("Chunk size must be a positive number of characters.")
    overlap = max(0, min(overlap, size // 2))
    pieces = _split(text, ["\n\n", "\n", ". ", " ", ""], size)
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if current and len(current) + len(piece) > size:
            chunks.append(current.strip())
            tail = current[-overlap:] if overlap else ""
            # start the overlap at a word boundary so no chunk opens mid-word
            if " " in tail:
                tail = tail[tail.index(" ") + 1:]
            current = tail
        current += piece
    if current.strip():
        chunks.append(current.strip())
    return [c for c in chunks if c]


def _split(text: str, separators: list[str], size: int) -> list[str]:
    if len(text) <= size:
        return [text]
    sep = separators[0]
    if sep == "":
        return [text[i:i + size] for i in range(0, len(text), size)]
    parts = text.split(sep)
    out: list[str] = []
    for i, part in enumerate(parts):
        piece = part + (sep if i < len(parts) - 1 else "")
        if len(piece) > size:
            out.extend(_split(piece, separators[1:], size))
        elif piece:
            out.append(piece)
    return out


def strip_html(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|tr|section|article)>", "\n", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    raw = re.sub(r"[ \t]+", " ", raw)
    return re.sub(r"\n\s*\n+", "\n\n", raw).strip()


def transcript_text(raw: str) -> str:
    """Pull the spoken text out of an agent session log (one JSON event per line).

    Understands the common shapes: {role, content}, {message: {role, content}}, content as a
    string or as a list of {type: text, text}. Lines that are not messages are skipped.
    """
    out: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = event.get("message") if isinstance(event.get("message"), dict) else event
        role = msg.get("role") or event.get("type") or ""
        content = msg.get("content", msg.get("text"))
        text = _content_text(content)
        if text and role in ("user", "assistant", "system", "human", "ai", ""):
            out.append(f"{role or 'note'}: {text}" if role else text)
    return "\n\n".join(out)


def _content_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") in (None, "text", "output_text", "input_text"):
                parts.append(str(block.get("text", "")))
        return "\n".join(p for p in parts if p).strip()
    return ""


def read_file(path: Path) -> str:
    """The text of one file, converted by kind. PDFs need the optional pypdf package."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader  # optional
        except ImportError:
            from .errors import SETUP, ToolError

            raise ToolError("missing_prerequisite", f"{path} is a PDF and pypdf is not installed.",
                            hint="Install the [pdf] extra (pypdf), or turn the PDF into text first.",
                            exit_code=SETUP) from None
        return "\n\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages)
    raw = path.read_text(encoding="utf-8", errors="replace")
    if suffix in (".html", ".htm"):
        return strip_html(raw)
    if suffix == ".jsonl":
        spoken = transcript_text(raw)
        return spoken or raw
    return raw


def load_documents(target: str | Path) -> list[dict]:
    """Read a file or a folder into documents: [{uri, title, text}].

    Folders are walked in sorted order, skipping hidden folders, build output and
    anything that is not text. This is a convenience; the library's ingest takes text.
    """
    path = Path(target).expanduser()
    if not path.exists():
        raise FileNotFoundError(2, "No such file or folder", str(path))
    files = [path] if path.is_file() else sorted(_walk(path))
    docs = []
    for f in files:
        try:
            if f.stat().st_size > MAX_FILE_BYTES:
                continue
            text = read_file(f)
        except UnicodeDecodeError:
            continue
        if text.strip():
            docs.append({"uri": str(f.resolve()), "title": f.name, "text": text})
    return docs


def _walk(root: Path):
    for p in root.iterdir():
        if p.name.startswith(".") or p.name in SKIP_DIRS:
            continue
        if p.is_dir() and not p.is_symlink():
            yield from _walk(p)
        elif p.is_file() and p.suffix.lower() in TEXT_SUFFIXES:
            yield p


def fetch_url(url: str, timeout: float = 30.0) -> dict:
    """Fetch one web page and return it as a document. Only called when the caller allows it."""
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "knowledge-smart-tool/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - caller opted in
        raw = resp.read(MAX_FILE_BYTES).decode(resp.headers.get_content_charset() or "utf-8", "replace")
    title = re.search(r"(?is)<title>(.*?)</title>", raw)
    return {"uri": url, "title": html.unescape(title.group(1)).strip() if title else url,
            "text": strip_html(raw)}


# --- words, for the co-occurrence method --------------------------------------------------

STOPWORDS = set("""
a about above after again against all almost also am among an and any are aren't as at be because
been before being below between both but by can can't cannot could couldn't did didn't do does
doesn't doing don't down during each either else even ever every few for from further get gets
got had hadn't has hasn't have haven't having he he'd he'll he's her here here's hers herself him
himself his how how's however i i'd i'll i'm i've if in into is isn't it it's its itself just
let's like may me might more most much must mustn't my myself near need neither no nor not now of
off often on once one only or other ought our ours ourselves out over own per perhaps quite rather
really same shan't she she'd she'll she's should shouldn't since so some such than that that's the
their theirs them themselves then there there's these they they'd they'll they're they've this
those though through thus to too toward under until up upon us use used using very via was wasn't
we we'd we'll we're we've well were weren't what what's when when's where where's whether which
while who who's whom whose why why's will with within without won't would wouldn't yet you you'd
you'll you're you've your yours yourself yourselves etc eg ie vs also yes
""".split())

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9'\-]*[A-Za-z0-9]|[A-Za-z]")


def lemma(word: str) -> str:
    """A light, predictable stem: lowercase and drop common plural endings."""
    w = word.lower().strip("'-")
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith("sses"):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is", "ous")):
        return w[:-1]
    return w


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+|\n{2,}|\n(?=[-*#\d])", text) if s.strip()]


def content_words(sentence: str) -> list[str]:
    words = []
    for match in _WORD.finditer(sentence):
        w = match.group(0)
        low = w.lower()
        if low in STOPWORDS or len(low) < 3 or low.isdigit():
            continue
        words.append(lemma(w))
    return words
