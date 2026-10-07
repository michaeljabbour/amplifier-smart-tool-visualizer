"""The live view: a small local web server that shows the graph and follows its change log.

Started only when asked (`knowledge serve`). Binds to 127.0.0.1. While agents ingest, relate
or supersede in another process, the page picks up each change within a couple of seconds
and flashes what is new. Standard library only.
"""

from __future__ import annotations

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import lib
from .errors import classify
from .render import render_html
from .store import graph_path


def make_server(graph=None, *, host: str = "127.0.0.1", port: int = 0, as_of: str | None = None,
                max_nodes: int = 1500) -> ThreadingHTTPServer:
    path = str(graph_path(graph))
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep stderr quiet; the CLI prints the address
            return

        def _send(self, status: int, body: bytes, kind: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, value, status: int = 200) -> None:
            self._send(status, json.dumps(value, ensure_ascii=False).encode(), "application/json")

        def do_GET(self):  # noqa: N802 - http.server API
            url = urllib.parse.urlparse(self.path)
            q = {k: v[-1] for k, v in urllib.parse.parse_qs(url.query).items()}
            try:
                with lock:
                    if url.path in ("/", "/index.html"):
                        data = lib.graph_data(path, as_of=as_of, concept=q.get("concept"),
                                              max_nodes=max_nodes)
                        self._send(200, render_html(data, live=True).encode(), "text/html; charset=utf-8")
                    elif url.path == "/api/graph":
                        self._json(lib.graph_data(path, as_of=as_of, concept=q.get("concept"), max_nodes=max_nodes))
                    elif url.path == "/api/events":
                        self._json(lib.events(path, since=int(q.get("since", 0) or 0), limit=200))
                    else:
                        self._json({"error": "not found"}, 404)
            except Exception as exc:  # noqa: BLE001 - report to the page, keep serving
                self._json({"error": classify(exc).as_dict()}, 500)

    return ThreadingHTTPServer((host, port), Handler)
