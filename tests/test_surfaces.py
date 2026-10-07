"""The surfaces: manifest, help, CLI conventions, exports, the view and MCP."""

import json
import re
try:
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib
import xml.dom.minidom

import knowledge as kg
from knowledge import help as h
from knowledge.mcp_server import handle
from conftest import ROOT, run_cli


def test_manifest_matches_package_version():
    m = kg.manifest()
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert m["version"] == pyproject["project"]["version"] == kg.__version__
    assert m["name"] == "knowledge" and m["smart_tool_format"] == 1
    assert set(m) >= {"description", "use_cases", "platforms", "requires", "body"}
    assert all(r["install"].startswith("https://") for r in m["requires"])
    assert sorted(h.model_backed()) == ["ask", "ingest", "questions", "reconcile", "report"]


def test_skill_shape_and_size():
    skill = h.skill()
    assert skill.startswith('<skill_content name="knowledge">') and skill.endswith("</skill_content>")
    assert "Skill directory:" in skill and "## Capabilities" in skill
    assert len(skill.splitlines()) < 500
    for name in h.CAPABILITIES:
        assert f"`{name}`" in skill
        cs = h.capability_skill(name)
        assert "## Arguments" in cs and "## When it fails" in cs and f"**Kind:** {h.CAPABILITIES[name]['kind']}" in cs


def test_every_capability_has_help_from_the_cli():
    for name in h.CAPABILITIES:
        full = run_cli(name, "--help")
        short = run_cli(name, "-h")
        assert full.returncode == 0 and "## Arguments" in full.stdout, name
        assert short.returncode == 0 and "usage:" in short.stdout, name


def test_json_envelope_and_exit_codes(graph):
    ok = run_cli("relate", "a", "supports", "b", "--graph", graph, "--json")
    doc = json.loads(ok.stdout)
    assert ok.returncode == 0 and doc["ok"] is True and doc["command"] == "relate"
    missing = run_cli("show", "nothing-here", "--graph", graph, "--json")
    doc = json.loads(missing.stdout)
    assert missing.returncode == 1 and doc["ok"] is False and doc["error"]["code"] == "concept_not_found"
    usage = run_cli("no-such-verb")
    assert usage.returncode == 2
    model = run_cli("ask", "q", "--graph", graph, "--json", env={"KNOWLEDGE_HOST": "none"})
    assert model.returncode == 3 and json.loads(model.stdout)["error"]["code"] == "provider_not_configured"


def test_stdin_closed_never_hangs(graph):
    r = run_cli("add", "-", "--graph", graph, stdin="")
    assert r.returncode == 1  # nothing to add, said loudly


def test_graph_flag_before_the_command(graph):
    run_cli("relate", "a", "supports", "b", "--graph", graph)
    r = run_cli("--graph", graph, "stats", "--json")
    assert json.loads(r.stdout)["result"]["edges"] == 1


def test_exports(example_graph, tmp_path):
    for fmt in ("json", "cytoscape", "graphml", "csv", "canvas", "obsidian"):
        r = kg.export(example_graph, fmt, str(tmp_path / f"out-{fmt}"))
        assert r["format"] == fmt
    assert json.loads((tmp_path / "out-json").read_text())["format"] == "knowledge-graph/1"
    assert json.loads((tmp_path / "out-cytoscape").read_text())["elements"]["nodes"]
    xml.dom.minidom.parse(str(tmp_path / "out-graphml"))
    canvas = json.loads((tmp_path / "out-canvas").read_text())
    assert canvas["nodes"] and {"id", "x", "y", "width", "height", "type"} <= set(canvas["nodes"][0])
    assert (tmp_path / "out-csv").read_text().startswith("node_1,node_2,edge")
    vault = tmp_path / "out-obsidian"
    note = (vault / "Concepts" / "delegation reduces perceived agency.md").read_text()
    assert "[[experiment 14]]" in note and "*supports*" in note
    assert (vault / "Gaps.md").exists() and (vault / "Topics map.canvas").exists()


def test_view_is_self_contained(example_graph, tmp_path):
    r = kg.visualize(example_graph, str(tmp_path / "v.html"))
    html = (tmp_path / "v.html").read_text()
    assert r["nodes"] > 50 and "Content-Security-Policy" in html and "connect-src 'none'" in html
    assert not re.search(r"""(src|href)=["']https?://""", html)
    data = json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S).group(1))
    assert data["format"] == "knowledge-graph/1" and data["gaps"] is not None
    hostile = kg.relate(example_graph, "</script><script>alert(1)</script>", "is", "bad")
    assert hostile
    html = kg.visualize(example_graph, str(tmp_path / "v2.html")) and (tmp_path / "v2.html").read_text()
    assert "</script><script>alert(1)" not in html


def test_live_server_serves_graph_and_events(example_graph):
    import threading
    import urllib.request

    from knowledge.serve import make_server

    server = make_server(example_graph)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        page = urllib.request.urlopen(base + "/").read().decode()
        assert "const LIVE = true" in page and "connect-src 'self'" in page
        last = json.loads(urllib.request.urlopen(base + "/api/graph").read())["last_event"]
        kg.relate(example_graph, "new idea", "supports", "delegation", agent="watcher")
        ev = json.loads(urllib.request.urlopen(f"{base}/api/events?since={last}").read())["events"]
        assert any(e["kind"] == "edge_added" and e["agent"] == "watcher" for e in ev)
    finally:
        server.shutdown()


def test_mcp_lists_and_calls_tools(example_graph):
    init = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["serverInfo"]["name"] == "knowledge"
    tools = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
    assert {t["name"] for t in tools} >= {"knowledge_search", "knowledge_relate", "knowledge_ask"}
    call = handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
        "name": "knowledge_ask", "arguments": {"graph": example_graph, "question": "delegation"}}})
    body = json.loads(call["result"]["content"][0]["text"])
    assert "task" in body and body["context"]["citations"]
    err = handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
        "name": "knowledge_show", "arguments": {"graph": example_graph, "concept": "zzzz"}}})
    assert err["result"]["isError"]
    assert handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_doctor_runs_without_credentials():
    r = kg.doctor()
    assert r["ready"]["deterministic"] and any(c["id"] == "model" for c in r["checks"])


def test_shipped_contract_copies_match():
    root = ROOT
    pkg = root / "src" / "knowledge" / "docs"
    assert (root / "contracts" / "graph.v1.md").read_text() == (pkg / "graph-format.md").read_text()
    assert (root / "contracts" / "cli.v1.md").read_text() == (pkg / "cli-contract.md").read_text()


def test_ingest_help_states_both_kinds():
    text = kg.capability_skill("ingest")
    assert "--method agent run with no model" in text
