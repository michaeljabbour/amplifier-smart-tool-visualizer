#!/usr/bin/env python3
"""Record the live view while real agents write to a graph, then speed the recording up.

Starts `knowledge serve` on GRAPH, records the page in headless Chromium until STOP_FILE exists
(or the time limit passes), then writes docs/images/live-demo.mp4 sped up to about TARGET seconds,
with a poster. Development only; needs Playwright with Chromium, and ffmpeg.

    python3 scripts/record-live.py .work/graphs/amplifier-live.db .work/live.stop
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "docs" / "images"
W, H = 1440, 900
TARGET = 45.0
LIMIT = 60 * 45


def main() -> None:
    from playwright.sync_api import sync_playwright

    from knowledge.serve import make_server

    graph, stop = sys.argv[1], Path(sys.argv[2])
    stop.unlink(missing_ok=True)
    server = make_server(graph, max_nodes=600)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"recording {url}", flush=True)
    with tempfile.TemporaryDirectory() as t, sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=t,
                                  record_video_size={"width": W, "height": H})
        page = ctx.new_page()
        page.goto(url)
        start = time.time()
        last_fit = 0.0
        while not stop.exists() and time.time() - start < LIMIT:
            page.wait_for_timeout(1000)
            if time.time() - last_fit > 20:  # keep the growing graph in frame
                page.evaluate("window.knowledgeView && window.knowledgeView.fit()")
                last_fit = time.time()
        page.wait_for_timeout(3000)
        page.evaluate("window.knowledgeView && window.knowledgeView.fit()")
        page.wait_for_timeout(4000)
        page.screenshot(path=str(OUT / "live-poster.png"))
        video = Path(page.video.path())
        ctx.close()
        browser.close()
        elapsed = time.time() - start
        speed = max(1.0, elapsed / TARGET)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-vf", f"setpts=PTS/{speed:.3f}",
                        "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "26", "-movflags", "+faststart",
                        "-an", str(OUT / "live-demo.mp4")], check=True)
    server.shutdown()
    print(f"recorded {elapsed:.0f}s, sped up {speed:.1f}x -> {OUT / 'live-demo.mp4'}", flush=True)


if __name__ == "__main__":
    main()
