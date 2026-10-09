#!/usr/bin/env python3
"""Record short, silent demo videos of the examples for the product page.

Each scene drives a view the way a first-time visitor would (a visible cursor, real clicks),
records it in headless Chromium, and converts it to H.264 MP4 with ffmpeg. Writes, per scene:
  docs/images/<scene>-demo.mp4 and docs/images/<scene>-poster.png
plus docs/images/trailer.mp4 (a cut of every scene) and its poster.
Needs Playwright with Chromium, and ffmpeg on PATH. Run scripts/build-examples.py first.

    python3 scripts/record-demos.py [scene ...]
"""

from __future__ import annotations

import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
ASSETS = ROOT / "site" / "assets"
OUT = ROOT / "docs" / "images"
GRAPHS = ROOT / ".work" / "graphs"
W, H = 1440, 900
HOLD = 4200
STEP = 1800

CURSOR = """
window.addEventListener('DOMContentLoaded', () => {
  const c = document.createElement('div');
  c.style.cssText = 'position:fixed;z-index:99999;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;' +
    'background:rgba(47,111,222,.35);border:2px solid rgba(47,111,222,.9);pointer-events:none;transition:transform .12s;left:-40px;top:-40px';
  document.body.appendChild(c);
  addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
  addEventListener('mousedown', () => { c.style.transform = 'scale(.6)'; }, true);
  addEventListener('mouseup', () => { c.style.transform = 'scale(1)'; }, true);
});
"""


def hold(page, ms=HOLD):
    page.wait_for_timeout(ms)


def glide(page, x, y, steps=24):
    page.mouse.move(x, y, steps=steps)


def click_at(page, x, y, shift=False):
    glide(page, x, y)
    page.wait_for_timeout(250)
    if shift:
        page.keyboard.down("Shift")
    page.mouse.click(x, y)
    if shift:
        page.keyboard.up("Shift")


def click_el(page, locator):
    locator.scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    box = locator.bounding_box()
    click_at(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def node(page, concept, shift=False):
    xy = page.evaluate(f"window.knowledgeView.screen({json.dumps(concept)})")
    if not xy:
        raise RuntimeError(f"{concept} is not in the view")
    click_at(page, xy[0], xy[1], shift=shift)


def open_view(page, url):
    page.goto(url)
    page.wait_for_timeout(2600)
    glide(page, W / 2, H / 2, steps=10)


# --- choosing what to show, from the real graph ---------------------------------------------------

def picks() -> dict:
    """Targets for each scene, chosen from the built graphs (so the demos follow the real data)."""
    from collections import deque

    import knowledge as kg

    amp = kg.graph_data(str(GRAPHS / "amplifier.db"), passages=0)
    typed = [e for e in amp["edges"] if not e["valid_to"]]
    adj: dict[str, set] = {}
    for e in typed:
        adj.setdefault(e["source"], set()).add(e["target"])
        adj.setdefault(e["target"], set()).add(e["source"])
    support = {"supports", "confirms", "validates"}
    contra = {"contradicts", "replaces", "constrains", "conflicts_with", "undermines"}
    score: dict[str, int] = {}
    for e in typed:
        if e["relation"] in support | contra:
            score[e["target"]] = score.get(e["target"], 0) + (2 if e["relation"] in contra else 1)
    # the evidence scene shows a stated principle or claim that another source contradicts
    types = {n["id"]: n["type"] for n in amp["nodes"]}
    contested = {e["target"] for e in typed if e["relation"] == "contradicts"
                 and types.get(e["target"]) in ("principle", "claim")}
    pool = contested or set(score) or set(adj)
    claim = max(pool, key=lambda n: (len(adj.get(n, ())), n))

    def dist(a, b):
        seen, q = {a: 0}, deque([a])
        while q:
            v = q.popleft()
            if v == b:
                return seen[v]
            for w in adj.get(v, ()):
                if w not in seen:
                    seen[w] = seen[v] + 1
                    q.append(w)
        return None

    comm = {n["id"]: n["community"] for n in amp["nodes"]}
    top = sorted(amp["nodes"], key=lambda n: -n.get("strength", 0))[:40]
    best, best_d = None, 0
    for i, a in enumerate(top):
        for b in top[i + 1:]:
            if comm.get(a["id"]) == comm.get(b["id"]):
                continue
            d = dist(a["id"], b["id"])
            if d and 3 <= d <= 6 and d > best_d:
                best, best_d = (a["id"], b["id"]), d
    hist = kg.graph_data(str(GRAPHS / "amplifier-history.db"), passages=0)
    closed: dict[str, int] = {}
    for e in hist["edges"]:
        if e["valid_to"]:
            for end in (e["source"], e["target"]):
                closed[end] = closed.get(end, 0) + 1
    history = max(closed, key=lambda n: (closed[n], n)) if closed else hist["nodes"][0]["id"]
    return {"claim": claim, "path": best or (top[0]["id"], top[1]["id"]), "history": history}


PICKS: dict = {}


def pick(key):
    if not PICKS:
        PICKS.update(picks())
    return PICKS[key]


# --- scenes ------------------------------------------------------------------------------------

def scene_gaps(page):
    open_view(page, (ASSETS / "amplifier.html").as_uri())
    hold(page, 2200)
    click_el(page, page.locator(".gap").first)
    hold(page)
    click_el(page, page.locator("#detail .link").first)
    hold(page)
    click_at(page, 330, 820)  # empty canvas: clear
    hold(page, 1200)


def scene_evidence(page):
    open_view(page, (ASSETS / "amplifier.html").as_uri())
    node(page, pick("claim"))
    hold(page, 5600)
    page.locator("#right").hover()
    page.mouse.wheel(0, 420)
    hold(page)
    page.mouse.wheel(0, 420)
    hold(page)


def scene_path(page):
    a, b = pick("path")
    open_view(page, (ASSETS / "amplifier.html").as_uri())
    node(page, a)
    hold(page, 2400)
    node(page, b, shift=True)
    hold(page, 7000)


def scene_time(page):
    open_view(page, (ASSETS / "amplifier-history.html").as_uri())
    hold(page, 1800)
    click_el(page, page.locator("#play"))
    hold(page, 11500)
    click_el(page, page.locator("#showClosed"))
    hold(page, 1600)
    node(page, pick("history"))
    hold(page, 6000)


def scene_words(page):
    open_view(page, (ASSETS / "this-repo.html").as_uri())
    hold(page, 2400)
    click_el(page, page.locator("#search"))
    page.keyboard.type("graph", delay=120)
    page.keyboard.press("Enter")
    hold(page)
    page.keyboard.press("Escape")
    rows = page.locator("#topics .row")
    for i in (1, 2):
        click_el(page, rows.nth(i))
        hold(page, 1300)
    for i in (1, 2):
        click_el(page, rows.nth(i))
    hold(page, 2500)


def scene_agent(page):
    """A terminal replay of real commands and their real output (captured now, from the built graphs)."""
    env = {**os.environ, "KNOWLEDGE_HOME": str(ROOT / ".work" / "home")}
    lab = str(GRAPHS / "amplifier.db")
    a, b = pick("path")

    def run(*args):
        r = subprocess.run([sys.executable, str(ROOT / "bin" / "knowledge.py"), *args], capture_output=True, text=True,
                           env=env, timeout=60)
        return json.loads(r.stdout)["result"]

    gaps = run("gaps", "--graph", lab, "--top", "1", "--json")["gaps"][0]
    path = run("path", a, b, "--graph", lab, "--k", "1", "--json")["paths"][0]
    con = run("contradictions", "--graph", lab, "--json")
    question = "how do hooks and orchestrators relate"
    ctx = run("context", question, "--graph", lab, "--budget", "900", "--json")
    blocks = [
        ("knowledge gaps --graph amplifier", [
            f"topics: {gaps['topics'][0]}", f"   <->  {gaps['topics'][1]}",
            f"score: {gaps['score']}   observed {gaps['observed_weight']}, expected {gaps['expected_weight']}",
            f"bridge candidates: {', '.join(gaps['bridge_candidates'][0][:2])}  +  {', '.join(gaps['bridge_candidates'][1][:2])}"]),
        (f'knowledge path "{a}" "{b}"', [
            " -> ".join(path["nodes"])] + [
            f"  {s['from']} --{s['relations'][0]['relation'] if s['relations'] else 'shares a passage with'}--> {s['to']}"
            for s in path["steps"]]),
        ("knowledge contradictions --graph amplifier", [
            f"explicit: {e['source']} --{e['relation']}--> {e['target']}" for e in con["explicit"][:2]] + [
            f"candidate: {c['a']['source']} {c['a']['relation']} / {c['b']['relation']} {c['b']['target']}  ({c['why']})"
            for c in con["candidates"][:1]]),
        (f'knowledge context "{question}"', [line[:150] for line in ctx["text"].splitlines()[:5]]),
    ]
    body = "".join(f'<div class="cmd" data-cmd="{html.escape(cmd)}"></div><pre class="out">{html.escape(chr(10).join(lines))}</pre>'
                   for cmd, lines in blocks)
    page.set_content(f"""<!doctype html><meta charset=utf-8><style>
      body{{margin:0;background:#15171a;color:#e8eaed;font:17px/1.5 ui-monospace,Menlo,monospace;padding:40px 56px}}
      .bar{{color:#9aa0a6;font-size:14px;margin-bottom:22px}} .cmd{{color:#8ab4f8;min-height:26px}} .cmd:before{{content:'$ ';color:#9aa0a6}}
      .out{{margin:6px 0 22px;color:#c8ccd0;white-space:pre-wrap;opacity:0;transition:opacity .4s}} .out.on{{opacity:1}}
    </style><div class=bar>Inside an agent: deterministic commands, no model, no key. Real output from the graph of Amplifier's own docs.</div>{body}""")
    for i in range(len(blocks)):
        cmd = page.locator(".cmd").nth(i)
        text = cmd.get_attribute("data-cmd")
        for k in range(1, len(text) + 1):
            cmd.evaluate(f"(el) => el.textContent = {json.dumps(text[:k])}")
            page.wait_for_timeout(28)
        page.wait_for_timeout(350)
        page.locator(".out").nth(i).evaluate("(el) => el.classList.add('on')")
        hold(page, 3200)
    hold(page, 1500)


def first(page, selector):
    """The first visible element matching selector, or None."""
    loc = page.locator(selector)
    for i in range(min(loc.count(), 40)):
        if loc.nth(i).is_visible():
            return loc.nth(i)
    return None


def scene_developers(page):
    """Python's typing PEPs: the question opens a timeline; a replaced plan shows what replaced it."""
    open_view(page, (ASSETS / "python-typing.html").as_uri())
    hold(page, 5600)
    bar = first(page, "#vpanel rect.bar.closed")
    if bar:
        click_el(page, bar)
        hold(page, 5600)
    bar = first(page, "#vpanel rect.bar:not(.closed)")
    if bar:
        click_el(page, bar)
    hold(page, 4200)


def scene_scientists(page):
    """arXiv abstracts: the question opens an argument -- the claim, and the quotes against and for it."""
    open_view(page, (ASSETS / "scaling-laws.html").as_uri())
    hold(page, 5600)
    quote = first(page, "#vpanel details.qd > summary")
    if quote:
        click_el(page, quote)
        hold(page, 4800)
    name = first(page, "#vpanel [data-node]")
    if name:
        click_el(page, name)
    hold(page, 4200)


def scene_work(page):
    """Federal AI policy: the question opens a timeline of what applies now; replaced requirements stay, hollow."""
    open_view(page, (ASSETS / "federal-ai-policy.html").as_uri())
    hold(page, 5600)
    bar = first(page, "#vpanel rect.bar.closed")
    if bar:
        click_el(page, bar)
        hold(page, 5200)
    bar = first(page, "#vpanel rect.bar:not(.closed)")
    if bar:
        click_el(page, bar)
    hold(page, 4200)


def scene_forms(page):
    """Six forms of the same graph: the question picks one, the tabs show the rest."""
    open_view(page, (ASSETS / "python-typing.html").as_uri())
    hold(page, 2600)
    for view in ("map", "timeline", "argument", "steps", "matrix", "rhythm"):
        click_el(page, page.locator(f"#tab-{view}"))
        hold(page, 3400)


def scene_matrix(page):
    """Gaps as a matrix: topics against topics, links observed against expected, gap cells outlined."""
    open_view(page, (ASSETS / "amplifier.html").as_uri())
    hold(page, 1600)
    click_el(page, page.locator("#tab-matrix"))
    hold(page, 3600)
    cell = first(page, "#vpanel td.mc.gap")
    if cell:
        click_el(page, cell)
    hold(page, 5200)


def scene_asks(page):
    """A vague question gets a question back, not a guess; the answer opens the view."""
    env = {**os.environ, "KNOWLEDGE_HOME": str(ROOT / ".work" / "home")}
    graph = str(GRAPHS / "scaling-laws.db")
    vague = next(q["question"] for q in json.loads((ROOT / "examples" / "scaling-laws" / "questions.json").read_text())
                 if q["expect_lens"] == "ask")

    def run(*args):
        r = subprocess.run([sys.executable, str(ROOT / "bin" / "knowledge.py"), *args, "--graph", graph],
                           capture_output=True, text=True, env=env, timeout=60)
        return r

    asked = run("visualize", "--for", vague, "--out", str(Path(tempfile.gettempdir()) / "asks.html"), "--json")
    doc = json.loads(asked.stdout)["result"]
    choice = doc["choices"][0]
    answer = run("visualize", "--lens", choice["lens"], *(["--concept", choice["concept"]] if choice["concept"] else []),
                 *(["--to", choice["to"]] if choice["to"] else []), "--out", str(Path(tempfile.gettempdir()) / "asks.html"))
    opened_line = next((ln for ln in answer.stderr.splitlines() if ln.startswith("Opens on")), "")
    blocks = [
        (f'knowledge visualize --for "{vague}" --graph scaling-laws', [doc["question"]] +
         [f"  - {c['label']}" for c in doc["choices"][:5]] + ["(exit 1: ask the person; do not pick for them)"]),
        (choice["command"].replace(f'"{graph}"', "scaling-laws").replace(" --open", ""), [opened_line]),
    ]
    body = "".join(f'<div class="cmd" data-cmd="{html.escape(cmd)}"></div>'
                   f'<pre class="out">{html.escape(chr(10).join(lines))}</pre>' for cmd, lines in blocks)
    style = ("body{margin:0;background:#15171a;color:#e8eaed;font:18px/1.55 ui-monospace,Menlo,monospace;padding:48px 60px}"
             ".bar{color:#9aa0a6;font-size:15px;margin-bottom:26px} .cmd{color:#8ab4f8;min-height:28px}"
             ".cmd:before{content:'$ ';color:#9aa0a6}"
             ".out{margin:8px 0 26px;color:#c8ccd0;white-space:pre-wrap;opacity:0;transition:opacity .4s} .out.on{opacity:1}")
    page.set_content(f"<!doctype html><meta charset=utf-8><style>{style}</style><div class=bar>A vague question gets a question "
                     f"back, with the command for each answer. Real output.</div>{body}")
    for i in range(len(blocks)):
        cmd = page.locator(".cmd").nth(i)
        text = cmd.get_attribute("data-cmd")
        for k in range(1, len(text) + 1):
            cmd.evaluate(f"(el) => el.textContent = {json.dumps(text[:k])}")
            page.wait_for_timeout(26)
        page.wait_for_timeout(350)
        page.locator(".out").nth(i).evaluate("(el) => el.classList.add('on')")
        hold(page, 5200)
    hold(page, 1200)


SCENES = {"developers": scene_developers, "scientists": scene_scientists, "work": scene_work, "forms": scene_forms,
          "matrix": scene_matrix, "asks": scene_asks,
          "gaps": scene_gaps, "evidence": scene_evidence, "path": scene_path, "time": scene_time,
          "words": scene_words, "agent": scene_agent}  # live is recorded by scripts/record-live.py
TRAILER = [("developers", 2.6, 10), ("scientists", 2.6, 9), ("work", 2.6, 9), ("forms", 2.4, 19), ("asks", 0.5, 9),
           ("live", 6, 11), ("agent", 0.5, 7)]


def record(name: str, tmp: Path) -> Path:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=str(tmp),
                                  record_video_size={"width": W, "height": H}, bypass_csp=True)
        ctx.add_init_script(CURSOR)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        SCENES[name](page)
        page.screenshot(path=str(OUT / f"{name}-poster.png"))
        video = Path(page.video.path())
        ctx.close()
        browser.close()
    if errors:
        raise RuntimeError(f"{name}: page errors {errors}")
    mp4 = OUT / f"{name}-demo.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-ss", "0.6", "-c:v", "libx264", "-pix_fmt",
                    "yuv420p", "-crf", "26", "-preset", "slow", "-movflags", "+faststart", "-an", str(mp4)], check=True)
    return mp4


def trailer(tmp: Path) -> None:
    parts = []
    for i, (name, start, length) in enumerate(TRAILER):
        src = OUT / f"{name}-demo.mp4"
        if not src.exists():
            continue
        part = tmp / f"part{i}.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start), "-t", str(length), "-i", str(src),
                        "-vf", "fade=t=in:st=0:d=0.4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "26", "-an",
                        str(part)], check=True)
        parts.append(part)
    listing = tmp / "parts.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in parts))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy",
                    "-movflags", "+faststart", str(OUT / "trailer.mp4")], check=True)
    shutil.copy2(OUT / "developers-poster.png", OUT / "trailer-poster.png")


def main() -> None:
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is needed on PATH.")
    if not (ASSETS / "amplifier.html").exists():
        sys.exit("Run scripts/build-examples.py first.")
    OUT.mkdir(parents=True, exist_ok=True)
    names = sys.argv[1:] or list(SCENES)
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        for name in names:
            mp4 = record(name, tmp / name)
            print(f"{name}: {mp4} ({mp4.stat().st_size // 1024} KB)")
        trailer(tmp)
        print(f"trailer: {OUT / 'trailer.mp4'}")


if __name__ == "__main__":
    main()
