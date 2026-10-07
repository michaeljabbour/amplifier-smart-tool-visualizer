"""The interactive view: one self-contained HTML file with the graph embedded as JSON.

No outside requests: a strict content security policy, no fonts, scripts or styles from
elsewhere. Opened from disk it is a snapshot; served by `serve` it follows the change log.
"""

from __future__ import annotations

import json
from html import escape
from importlib.resources import files

CSP_FILE = ("default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; "
            "connect-src 'none'; base-uri 'none'; form-action 'none'")
CSP_LIVE = CSP_FILE.replace("connect-src 'none'", "connect-src 'self'")


def _template() -> str:
    return files("knowledge").joinpath("resources/viewer.html").read_text(encoding="utf-8")


def embed_json(data: dict) -> str:
    """JSON that is safe inside a <script> element."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return text.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029").replace("<!--", "<\\!--")


def render_html(data: dict, *, title: str | None = None, live: bool = False) -> str:
    page = _template()
    return (page.replace("__CSP__", CSP_LIVE if live else CSP_FILE)
            .replace("__TITLE__", escape(title or f"Knowledge: {data.get('graph', '')}"))
            .replace("__LIVE__", "true" if live else "false")
            .replace("__DATA__", embed_json(data)))
