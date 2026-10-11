"""Tests for skills/wiki/scripts/wiki.py — run: python3 -m pytest -q skills/wiki/tests"""
import hashlib
import http.client
import importlib.util
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "wiki.py"
spec = importlib.util.spec_from_file_location("wiki", SCRIPT)
wiki = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wiki)

FILES = {
    "README.md": "# Fixture\n\nIntro with [guide](docs/guide.md), [[alpha]] and FEAT-CORE-001.\n",
    "docs/guide.md": "---\ntitle: The Guide\n---\n# Ignored\n\nBack to [home](../README.md#top). REQ-X1-002.\n"
                     "\n```\n[not a link](beta/beta.md)\n```\n",
    "docs/view.html": "<html><head><title>View &amp; Play</title></head><body>hi</body></html>",
    "notes/deep/report.html": "<html><body>no title</body></html>",
    "alpha/alpha.md": "---\ntitle: alpha\nkind: code\ndeps: [beta, ghost]\n---\n# alpha · code\n\nAlpha owns things.\n",
    "alpha/docs/alpha.req.md": "# alpha · requirements\n\n- REQ-ALPHA-001 must work\n",
    "alpha/inner/notes.md": "Plain first paragraph.\n",
    "alpha/sub/sub.md": "---\nkind: code\n---\n# sub\n\nUp to [alpha](../alpha.md).\n",
    "alpha/sub/docs/sub.brief.md": "# sub · brief\n",
    "beta/beta.md": "---\nkind: lib\ndeps:\n  - alpha\n---\n# beta\n",
    "gamma/gamma.md": "---\ntitle: gamma\n---\n# not a module (no kind)\n",
    "gamma/deep/x.md": "# X\n",
    "notes/README.md": "# Notes\n",
    "notes/deep/more.md": "# More\n",
    "node_modules/x/readme.md": "# skipped\n",
    ".hidden/x.md": "# skipped\n",
    "cache.nosync/x.md": "# skipped\n",
    ".claude/other.md": "# skipped\n",
    ".claude/settings/x.md": "# skipped\n",
    ".claude/skills/s/SKILL.md": "# Skill S\n",
    "graphify-out/graph.json": json.dumps({"nodes": [
        {"id": "n1", "source_file": "docs/guide.md", "community": 3},
        {"id": "n2", "source_file": "alpha/alpha.md", "community": 3}],
        "community_labels": {"3": "Guides"}}),
}


@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / "fixture"
    for rel, text in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    (root / "big.html").write_bytes(b"x" * (wiki.MAX_FILE + 1))
    return root


@pytest.fixture()
def built(repo, tmp_path):
    w = wiki.build(repo, tmp_path / "data")
    return w, {i["id"]: i for i in w["items"]}


def test_item_extraction(built):
    w, items = built
    assert set(items) == {"README.md", "docs/guide.md", "docs/view.html", "notes/deep/report.html", "alpha/alpha.md",
                          "alpha/docs/alpha.req.md", "alpha/inner/notes.md", "beta/beta.md", "gamma/gamma.md",
                          ".claude/skills/s/SKILL.md", "alpha/sub/sub.md", "alpha/sub/docs/sub.brief.md",
                          "gamma/deep/x.md", "notes/README.md", "notes/deep/more.md"}
    assert items["docs/guide.md"]["title"] == "The Guide"
    assert items["README.md"]["title"] == "Fixture"
    assert items["alpha/inner/notes.md"]["title"] == "notes.md"
    assert items["docs/view.html"]["title"] == "View & Play"
    assert items["notes/deep/report.html"]["kind"] == "exhibit"  # any .html is an exhibit
    assert items["alpha/alpha.md"]["kind"] == items["beta/beta.md"]["kind"] == "module"
    assert items["gamma/gamma.md"]["kind"] == "page"
    assert items["alpha/inner/notes.md"]["summary"] == "Plain first paragraph."
    assert items["README.md"]["summary"].startswith("Intro with guide, alpha and")
    assert items["README.md"]["ids"] == ["FEAT-CORE-001"]
    assert items["alpha/docs/alpha.req.md"]["ids"] == ["REQ-ALPHA-001"]


def test_grouping(built):
    _, items = built
    group = {k: v["group"] for k, v in items.items()}
    assert group["alpha/alpha.md"] == group["alpha/docs/alpha.req.md"] == group["alpha/inner/notes.md"] == "alpha"
    assert group["beta/beta.md"] == "beta"
    assert group["alpha/sub/sub.md"] == group["alpha/sub/docs/sub.brief.md"] == "sub"  # nearest module wins
    assert group["docs/guide.md"] == "Guides"  # graphify cluster beats folder
    assert group["docs/view.html"] == "docs"
    assert group["README.md"] == "root"
    assert group[".claude/skills/s/SKILL.md"] == ".claude"


def test_links(built):
    _, items = built
    assert items["README.md"]["links"] == ["alpha/alpha.md", "docs/guide.md"]
    assert items["docs/guide.md"]["links"] == ["README.md"]  # fenced code is not prose
    assert items["alpha/alpha.md"]["links"] == ["beta/beta.md"] and items["alpha/alpha.md"]["deps"] == ["beta"]
    assert items["beta/beta.md"]["links"] == ["alpha/alpha.md"]  # block-style YAML list


def test_link_kinds(built):
    w, items = built
    edges = {frozenset((e["source"], e["target"])): e["kind"] for e in w["links"]}
    assert len(edges) == len(w["links"])  # undirected, no duplicates
    assert set(e["kind"] for e in w["links"]) == {"tree", "ref"}
    tree = {k for k, v in edges.items() if v == "tree"}
    pair = lambda a, b: frozenset((a, b))
    # module hub-and-spoke: the module links to every page of its own group, not to nested modules' pages
    assert pair("alpha/alpha.md", "alpha/docs/alpha.req.md") in tree
    assert pair("alpha/alpha.md", "alpha/inner/notes.md") in tree
    assert pair("alpha/sub/sub.md", "alpha/sub/docs/sub.brief.md") in tree
    assert pair("alpha/alpha.md", "alpha/sub/docs/sub.brief.md") not in edges
    # module -> nearest enclosing module; here a content link covers the same pair, and ref wins
    assert edges[pair("alpha/sub/sub.md", "alpha/alpha.md")] == "ref"
    assert edges[pair("alpha/alpha.md", "beta/beta.md")] == "ref"  # deps (mutual) collapse to one ref edge
    # non-module groups: top-level README/index, else the shortest-path page, is the hub
    assert pair("notes/README.md", "notes/deep/more.md") in tree
    assert pair("notes/README.md", "notes/deep/report.html") in tree
    assert pair("gamma/gamma.md", "gamma/deep/x.md") in tree
    refs = {k for k, v in edges.items() if v == "ref"}
    assert refs == {pair(a, b) for a, it in items.items() for b in it["links"]}  # every content link, as ref
    assert not any(len(k) == 1 for k in edges)  # no self-loops


def test_group_hub():
    assert wiki.group_hub(["d/a.md", "d/README.md", "d/x/index.md"]) == "d/README.md"
    assert wiki.group_hub(["d/b.md", "d/aa.md", "d/x/README.md"]) == "d/b.md"  # README not top-level
    assert wiki.group_hub(["d/x.html", "d/y/z.md"]) == "d/y/z.md"  # pages beat exhibits
    assert wiki.group_hub(["d/x.html"]) == "d/x.html"


def test_hashing_and_no_bodies(built, repo, tmp_path):
    w, items = built
    raw = (repo / "README.md").read_bytes()
    assert items["README.md"]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert items["README.md"]["bytes"] == len(raw)
    on_disk = (tmp_path / "data" / "wiki.json").read_text()
    assert json.loads(on_disk)["items"] == w["items"]
    assert "Intro with [guide]" not in on_disk  # bodies are served on demand, never embedded


def test_feedback_append_and_resolve(built, repo, tmp_path):
    _, items = built
    data = tmp_path / "data"
    with pytest.raises(ValueError):
        wiki.add_feedback(data, items, {"item": "README.md", "kind": "rant", "text": "x"})
    with pytest.raises(ValueError):
        wiki.add_feedback(data, items, {"item": "../etc/passwd", "kind": "idea", "text": "x"})
    with pytest.raises(ValueError):
        wiki.add_feedback(data, items, {"item": "README.md", "kind": "idea", "text": "x" * 4001})
    a = wiki.add_feedback(data, items, {"item": "README.md", "kind": "wrong", "text": "typo\nhere", "quote": "Intro"})
    b = wiki.add_feedback(data, items, {"item": "docs/view.html", "kind": "answer", "text": "option B"})
    assert a["id"].startswith("F-") and a["status"] == "open" and a["sha256"] == items["README.md"]["sha256"]
    first = (data / "feedback.jsonl").read_text().splitlines()
    wiki.resolve(data, a["id"], "fixed the typo")
    lines = (data / "feedback.jsonl").read_text().splitlines()
    assert lines[:2] == first and len(lines) == 3  # append-only
    folded = {r["id"]: r for r in wiki.load_feedback(data)}
    assert folded[a["id"]]["status"] == "resolved" and folded[a["id"]]["note"] == "fixed the typo"
    assert folded[b["id"]]["status"] == "open"
    with pytest.raises(KeyError):
        wiki.resolve(data, "F-nope", "x")
    out = subprocess.run([sys.executable, str(SCRIPT), "feedback", str(repo), "--data-dir", str(data)],
                         capture_output=True, text=True, check=True).stdout.splitlines()
    assert out == [f"{b['id']}  answer  docs/view.html@{b['sha256'][:12]}  option B"]


@pytest.fixture()
def server(repo, tmp_path):
    srv = wiki.make_server(repo, tmp_path / "data", port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def call(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse()
    out = r.status, dict(r.getheaders()), r.read()
    c.close()
    return out


def test_server_reads(server):
    status, _, body = call(server, "GET", "/api/wiki")
    w = json.loads(body)
    assert status == 200 and len(w["items"]) == 15 and {e["kind"] for e in w["links"]} == {"tree", "ref"}
    status, _, body = call(server, "GET", "/api/item?id=README.md")
    assert status == 200 and body.startswith(b"# Fixture")
    status, headers, _ = call(server, "GET", "/exhibit?id=docs/view.html")
    assert status == 200 and headers["Content-Security-Policy"] == "sandbox allow-scripts"
    assert call(server, "GET", "/exhibit?id=README.md")[0] == 404  # pages are not exhibits
    status, headers, body = call(server, "GET", "/")
    assert status == 200 and b"<html" in body and "Content-Security-Policy" in headers


@pytest.mark.parametrize("path", ["/api/item?id=../../etc/passwd", "/api/item?id=/etc/passwd",
                                  "/api/item?id=docs/../../fixture/README.md", "/exhibit?id=../x.html",
                                  "/assets/../scripts/wiki.py", "/assets/%2e%2e/scripts/wiki.py", "/etc/passwd"])
def test_server_rejects_traversal(server, path):
    assert call(server, "GET", path)[0] in (403, 404)


def test_server_feedback(server):
    post = lambda body, ctype="application/json": call(server, "POST", "/api/feedback", body,
                                                       {"Content-Type": ctype})
    ok = json.dumps({"item": "README.md", "sha256": "abc", "kind": "answer", "text": "yes", "quote": "Intro"})
    status, _, body = post(ok)
    rec = json.loads(body)
    assert status == 201 and rec["kind"] == "answer" and rec["status"] == "open"
    assert post(json.dumps({"item": "README.md", "kind": "nope", "text": "x"}))[0] == 400
    assert post(json.dumps({"item": "missing.md", "kind": "idea", "text": "x"}))[0] == 400
    assert post(json.dumps({"item": "README.md", "kind": "idea", "text": ""}))[0] == 400
    assert post(ok, "text/plain")[0] == 415  # sandboxed exhibits cannot send JSON cross-origin
    big = json.dumps({"item": "README.md", "kind": "idea", "text": "x" * (wiki.MAX_BODY + 10)})
    assert post(big)[0] == 413
    status, _, body = call(server, "GET", "/api/feedback")
    assert status == 200 and [r["id"] for r in json.loads(body)] == [rec["id"]]


def test_server_rejects_methods_and_hosts(server):
    assert call(server, "PUT", "/api/feedback", b"{}")[0] == 405
    assert call(server, "DELETE", "/api/wiki")[0] == 405
    assert call(server, "POST", "/api/wiki", b"{}", {"Content-Type": "application/json"})[0] == 404
    assert call(server, "GET", "/api/wiki", headers={"Host": "evil.example:7790"})[0] == 403
    assert "Access-Control-Allow-Origin" not in call(server, "GET", "/api/wiki")[1]


SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><title>Flow</title><script>alert(1)</script></svg>'


@pytest.fixture()
def figs(repo, tmp_path):
    (repo / "docs/flow.svg").write_text(SVG)
    (repo / "docs/pic.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (repo / "docs/notes.txt").write_text("secret")
    (tmp_path / "outside.png").write_bytes(b"\x89PNG")
    srv = wiki.make_server(repo, tmp_path / "data", port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def test_svg_is_figure_item(repo, tmp_path):
    (repo / "docs/flow.svg").write_text(SVG)
    it = {i["id"]: i for i in wiki.build(repo, tmp_path / "data")["items"]}["docs/flow.svg"]
    assert it["kind"] == "figure" and it["title"] == "Flow"


def test_svg_served_sandboxed(figs):
    status, headers, body = call(figs, "GET", "/figure?id=docs/flow.svg")
    csp = headers["Content-Security-Policy"]
    assert status == 200 and headers["Content-Type"] == "image/svg+xml" and body.startswith(b"<svg")
    assert csp.startswith("sandbox") and "default-src 'none'" in csp and "script-src" not in csp
    assert call(figs, "GET", "/figure?id=README.md")[0] == 404  # only figures
    assert call(figs, "GET", "/exhibit?id=docs/flow.svg")[0] == 404  # not an exhibit


def test_inline_images(figs):
    status, headers, body = call(figs, "GET", "/img?path=docs/pic.png")
    assert status == 200 and headers["Content-Type"] == "image/png" and body.startswith(b"\x89PNG")
    assert call(figs, "GET", "/img?path=docs/flow.svg")[0] == 200
    assert "sandbox" in call(figs, "GET", "/img?path=docs/flow.svg")[1]["Content-Security-Policy"]


@pytest.mark.parametrize("path", ["../outside.png", "docs/../../outside.png", "%2e%2e/outside.png", "/etc/passwd",
                                  "docs/notes.txt", "README.md", "docs/missing.png", "", "docs"])
def test_inline_image_refused(figs, path):
    assert call(figs, "GET", "/img?path=" + path)[0] == 404
