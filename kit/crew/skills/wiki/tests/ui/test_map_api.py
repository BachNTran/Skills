"""wiki.py's map side: /api/map*, /api/source, the "map" flag, parameter checks and CLI dispatch.

Two halves. Server mechanics run against a stub map library (no dependency on wikimap's progress);
the route payloads run against the real wikimap on the example and the poly fixture, and skip until
wikimap.open_map exists."""
import http.client
import importlib.util
import json
import os
import shutil
import sys
import threading
import types
from pathlib import Path
from urllib.parse import quote

import pytest

WK = Path(__file__).resolve().parents[2]
SCRIPT = WK / "scripts" / "wiki.py"
EXAMPLE = WK.parents[3] / "example" / "weather-station"
POLY = WK / "tests" / "fixtures" / "poly"
_spec = importlib.util.spec_from_file_location("wiki_map_api", SCRIPT)
wiki = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wiki)
ROUTES = ["/api/map", "/api/map/level?lens=systems&at=.", "/api/map/node?id=x", "/api/map/trace?id=x",
          "/api/map/search?q=x", "/api/source?path=a.py"]


def call(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse()
    out = r.status, dict(r.getheaders()), r.read()
    c.close()
    return out


def get_json(port, path):
    status, _, body = call(port, "GET", path)
    assert status == 200, (path, status, body[:200])
    return json.loads(body)


def serve(root, data):
    srv = wiki.make_server(root, data, port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.fixture()
def tiny(tmp_path):
    root = tmp_path / "tiny"
    (root / "src").mkdir(parents=True)
    (root / "guide.md").write_text("# Guide\n")
    (root / "src" / "a.py").write_bytes(b"def a():\n    return '\xff'\n")  # not UTF-8: decoded with replacement
    (root / "src" / "nul.py").write_bytes(b"x = 1\n\0\0\0")
    return root


# ---------- stub map library ----------

class StubMap:
    def __init__(self, root):
        self.root, self.calls, self.refreshes, self.fail = root, [], 0, False
        self.files = {"src/a.py": {"rec": {"skip": None}}, "src/bin.py": {"rec": {"skip": "binary"}},
                      "src/nul.py": {"rec": {"skip": None}}}

    def refresh(self):
        self.refreshes += 1
        return False

    def index(self):
        return {"v": 1, "rev": "r1", "nodes": [{"id": ".", "parent": None}]}

    def level(self, lens, at):
        self.calls.append(("level", lens, at))
        if self.fail:
            raise RuntimeError("boom")
        return {"v": 1, "lens": lens, "at": at, "nodes": [], "edges": [], "ghosts": []} if at == "." else None

    def node(self, nid):
        return {"node": {"id": nid}} if nid == "src/a.py" else None

    def trace(self, nid, way="both", depth=2):
        self.calls.append(("trace", nid, way, depth))
        return {"root": nid, "nodes": {}, "edges": []}

    def search(self, q, limit=30):
        self.calls.append(("search", q, limit))
        return [{"id": "src/a.py", "name": q}]

    def source_path(self, rel):
        return self.root / rel if rel in ("src/a.py", "src/nul.py") else None


@pytest.fixture()
def stub(tiny, tmp_path, monkeypatch):
    opened = []

    def open_map(root, data=None, *, exact=False):
        opened.append((Path(root), Path(data) if data else None, exact))
        return StubMap(Path(root))

    monkeypatch.setattr(wiki, "_import_wikimap", lambda: types.SimpleNamespace(open_map=open_map))
    srv = serve(tiny, tmp_path / "data")
    yield srv.server_address[1], srv, opened
    srv.shutdown()
    srv.server_close()


def test_map_flag_false_when_the_import_fails(tiny, tmp_path, monkeypatch):
    def broken():
        raise ImportError("no wikimap here")

    monkeypatch.setattr(wiki, "_import_wikimap", broken)
    srv = serve(tiny, tmp_path / "data")
    port = srv.server_address[1]
    try:
        assert get_json(port, "/api/wiki")["map"] is False
        for path in ROUTES:
            status, headers, body = call(port, "GET", path)
            assert status == 404 and json.loads(body) == {"error": "map not available"}, path
        assert get_json(port, "/api/feedback") == []  # the rest of the wiki is untouched
    finally:
        srv.shutdown()
        srv.server_close()


def test_namespace_package_is_not_a_map(tiny, tmp_path, monkeypatch):
    monkeypatch.setattr(wiki, "_import_wikimap", lambda: types.SimpleNamespace())  # imports, but no open_map
    assert wiki.load_map_lib() is None


def test_map_built_lazily_once_and_refresh_throttled(stub, tmp_path, monkeypatch):
    port, srv, opened = stub
    assert get_json(port, "/api/wiki")["map"] is True
    assert opened == [] and srv.state["map"] is None  # nothing built until a map route is asked
    get_json(port, "/api/map")
    get_json(port, "/api/map")
    get_json(port, "/api/map/level?lens=code&at=.")
    assert opened == [(srv.state["map"].root, tmp_path / "data", True)]
    assert srv.state["map"].refreshes == 0  # within 2 s of the build
    monkeypatch.setattr(wiki, "MAP_REFRESH_S", 0.0)
    get_json(port, "/api/map")
    get_json(port, "/api/map/level?lens=code&at=.")  # only /api/map refreshes
    assert srv.state["map"].refreshes == 1


@pytest.mark.parametrize("path", [
    "/api/map/level?at=.", "/api/map/level?lens=graph&at=.", "/api/map/level?lens=SYSTEMS&at=.",
    "/api/map/level?lens=systems&at=" + "a" * 1025,
    "/api/map/node", "/api/map/node?id=", "/api/map/node?id=" + "x" * 1025,
    "/api/map/trace", "/api/map/trace?id=a&dir=up", "/api/map/trace?id=a&depth=0", "/api/map/trace?id=a&depth=5",
    "/api/map/trace?id=a&depth=x", "/api/map/trace?id=a&depth=-1", "/api/map/trace?id=a&depth=2.5", "/api/map/trace?id=a&depth=%202",
    "/api/map/search", "/api/map/search?q=", "/api/map/search?q=" + "q" * 201, "/api/map/search?q=a&limit=0",
    "/api/map/search?q=a&limit=101", "/api/map/search?q=a&limit=ten",
    "/api/source", "/api/source?path=", "/api/source?path=" + "p" * 1025,
])
def test_bad_params_400(stub, path):
    port, srv, opened = stub
    status, headers, body = call(port, "GET", path)
    assert status == 400 and "error" in json.loads(body) and headers["Content-Type"] == "application/json"
    assert opened == []  # checked before the map is built


def test_params_reach_the_map(stub):
    port, srv, _ = stub
    assert get_json(port, "/api/map/trace?id=src/a.py")["root"] == "src/a.py"
    get_json(port, "/api/map/trace?id=b&dir=in&depth=4")
    get_json(port, "/api/map/search?q=dec%20ode")
    get_json(port, "/api/map/search?q=x&limit=100")
    get_json(port, "/api/map/level?lens=systems")  # at defaults to the root
    assert srv.state["map"].calls == [("trace", "src/a.py", "both", 2), ("trace", "b", "in", 4),
                                      ("search", "dec ode", 30), ("search", "x", 100), ("level", "systems", ".")]
    assert get_json(port, "/api/map/node?id=src/a.py") == {"node": {"id": "src/a.py"}}


def test_unknown_ids_404(stub):
    port, *_ = stub
    for path in ("/api/map/level?lens=systems&at=nope", "/api/map/node?id=nope", "/api/map/nope"):
        status, _, body = call(port, "GET", path)
        assert status == 404, path


def test_source_served_inert(stub):
    port, *_ = stub
    status, headers, body = call(port, "GET", "/api/source?path=src/a.py")
    assert status == 200 and body.decode("utf-8") == "def a():\n    return '�'\n"
    assert headers["Content-Type"] == "text/plain; charset=utf-8"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Content-Security-Policy"] == "sandbox; default-src 'none'"
    assert "Access-Control-Allow-Origin" not in headers


@pytest.mark.parametrize("path,code", [("src/bin.py", 415), ("src/nul.py", 415), ("src/missing.py", 404),
                                       ("guide.md", 404), ("../tiny/src/a.py", 404)])
def test_source_refusals(stub, path, code):
    port, *_ = stub
    assert call(port, "GET", "/api/source?path=" + path)[0] == code


def test_map_failure_is_500_and_the_wiki_survives(stub):
    port, srv, _ = stub
    get_json(port, "/api/map")
    srv.state["map"].fail = True
    status, _, body = call(port, "GET", "/api/map/level?lens=systems&at=.")
    assert status == 500 and "boom" not in body.decode()  # no internals in the answer
    assert get_json(port, "/api/wiki")["map"] is True


def test_guard_methods_and_cors_on_new_routes(stub):
    port, *_ = stub
    for path in ROUTES:
        assert call(port, "GET", path, headers={"Host": "evil.example:7790"})[0] == 403, path
        assert call(port, "PUT", path, b"{}")[0] == 405, path
        assert call(port, "DELETE", path)[0] == 405, path
        assert call(port, "POST", path, b"{}", {"Content-Type": "application/json"})[0] == 404, path
        assert "Access-Control-Allow-Origin" not in call(port, "GET", path)[1], path


# ---------- CLI dispatch ----------

def test_cli_dispatches_map_commands(monkeypatch, capsys):
    seen = []
    fake = types.ModuleType("wikimap.cli")
    fake.main = lambda argv: seen.append(list(argv)) or 7
    monkeypatch.setitem(sys.modules, "wikimap.cli", fake)
    for cmd in wiki.MAP_CMDS:
        assert wiki.main([cmd, "repo", "--data-dir", "d"]) == 7
    assert seen == [[c, "repo", "--data-dir", "d"] for c in wiki.MAP_CMDS]
    assert set(wiki.MAP_CMDS) == {"map", "check", "sync", "pending", "ack", "show", "trace", "install-hooks"}


def test_cli_without_wikimap(monkeypatch, capsys, tmp_path):
    monkeypatch.setitem(sys.modules, "wikimap.cli", None)  # import of wikimap.cli now raises ImportError
    assert wiki.main(["sync", "--hook"]) == 0 and wiki.main(["pending", "--hook"]) == 0
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""  # a hook stays silent
    assert wiki.main(["check", str(tmp_path)]) == 3
    assert capsys.readouterr().err.startswith("E:ERROR     (root)  map not available")
    (tmp_path / "a.md").write_text("# A\n")
    assert wiki.main(["build", str(tmp_path), "--data-dir", str(tmp_path / "d")]) == 0  # wiki commands unchanged
    assert capsys.readouterr().out.startswith("wiki: ")


def test_no_subprocess_and_lazy_server_imports():
    src = SCRIPT.read_text()
    assert "subprocess" not in src and "webbrowser.open(url)" in src
    head = src[: src.index("def make_server")]
    assert "http.server" not in head  # map and hook commands do not pay for the server


# ---------- real wikimap: route payloads ----------

def real_lib():
    lib = wiki.load_map_lib()
    if lib is None:
        pytest.skip("wikimap.open_map not available yet (WP3)")
    return lib


def copy_repo(src: Path, dst: Path) -> Path:
    if not src.is_dir():
        pytest.skip(f"missing {src}")
    shutil.copytree(src, dst, symlinks=True, ignore=shutil.ignore_patterns(".wiki", ".wikimap", "__pycache__"))
    return dst


@pytest.fixture(scope="module")
def example_port(tmp_path_factory):
    real_lib()
    base = tmp_path_factory.mktemp("example")
    srv = serve(copy_repo(EXAMPLE, base / "weather-station"), base / "data")
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


@pytest.fixture(scope="module")
def poly_port(tmp_path_factory):
    real_lib()
    base = tmp_path_factory.mktemp("poly")
    root = copy_repo(POLY, base / "poly")
    src = root / "svc" / "pkg" / "src"
    (src / "huge.py").write_text("x = 1\n" * 200_000)  # > 1 MB
    (src / "bin.py").write_bytes(b"x = 1\n" + b"\0" * 64)
    (base / "outside.py").write_text("SECRET = 1\n")
    (root / ".env").write_text("API_KEY=DOTENV_SECRET\n")
    try:
        os.symlink(base / "outside.py", src / "link.py")
        os.symlink(root / ".env", src / "env_link.yaml")  # in-root link into a skipped dot-file
    except OSError:
        pass
    srv = serve(root, base / "data")
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


NODE_KEYS = {"id", "type", "tier", "kind", "name", "drill", "n", "item", "badges"}
EDGE_KEYS = {"id", "s", "t", "kinds", "n", "conf", "hist", "labels", "dash", "state", "x", "prov", "samples"}


def test_example_routes(example_port):
    port = example_port
    assert get_json(port, "/api/wiki")["map"] is True
    idx = get_json(port, "/api/map")
    assert {"v", "rev", "repo", "modgate", "built", "root", "nodes", "counts", "stats"} <= set(idx)
    assert idx["modgate"] is True and idx["root"] == "."
    by = {n["id"]: n for n in idx["nodes"]}
    assert {"id", "parent", "type", "tier", "kind", "name", "n", "drill", "item", "badges"} <= set(by["."])
    assert by["firmware/comms"]["drill"]["systems"] == "code"
    assert not any("#" in i for i in by)  # no symbols in the index

    lv = get_json(port, "/api/map/level?lens=systems&at=.")
    assert {"v", "rev", "lens", "at", "crumbs", "nodes", "ghosts", "edges", "overflow"} <= set(lv)
    assert {n["name"] for n in lv["nodes"]} >= {"firmware", "backend", "dashboard", "protocol", "deploy", "host"}
    assert all(NODE_KEYS <= set(n) for n in lv["nodes"]) and all(EDGE_KEYS <= set(e) for e in lv["edges"])
    assert all(e["id"] == f'{e["s"]}>{e["t"]}' for e in lv["edges"])
    fw = get_json(port, "/api/map/level?lens=systems&at=firmware")
    assert [c["id"] for c in fw["crumbs"]] == [".", "firmware"]
    assert any(g["id"] == "ghost:backend/ingest" for g in fw["ghosts"])
    assert get_json(port, "/api/map/level?lens=code&at=firmware/storage")["lens"] == "code"
    assert call(port, "GET", "/api/map/level?lens=systems&at=firmware/comms")[0] == 404  # a Systems leaf
    assert call(port, "GET", "/api/map/level?lens=systems&at=no/such")[0] == 404

    hits = get_json(port, "/api/map/search?q=decode")
    assert hits and {"id", "name", "type", "kind", "path", "at", "lens"} <= set(hits[0])
    assert hits[0]["id"].endswith("decode.py#decode")
    sym = quote(hits[0]["id"], safe="")  # a symbol id holds "#"
    node = get_json(port, "/api/map/node?id=" + sym)
    assert node["node"]["id"] == hits[0]["id"]
    assert {"node", "chain", "docs", "callers", "callees", "impls", "implements", "reqs", "tests", "findings"} <= set(node)
    assert node["chain"][0]["id"] == "."
    tr = get_json(port, "/api/map/trace?id=" + sym + "&dir=out&depth=2")
    assert {"root", "nodes", "edges"} <= set(tr) and tr["root"] == hits[0]["id"]

    rel = hits[0]["id"].split("#")[0]
    status, headers, body = call(port, "GET", "/api/source?path=" + rel)
    assert status == 200 and b"def decode" in body and headers["Content-Security-Policy"] == "sandbox; default-src 'none'"


def test_poly_routes(poly_port):
    port = poly_port
    idx = get_json(port, "/api/map")
    assert idx["modgate"] is True
    lv = get_json(port, "/api/map/level?lens=code&at=.")
    assert lv["lens"] == "code" and lv["nodes"]
    assert not any("hidden" in n["id"] or n["id"].startswith("vendor/thirdparty/") for n in idx["nodes"] if n["type"] == "file")
    assert get_json(port, "/api/map/search?q=Engine")


@pytest.mark.parametrize("path,code", [
    ("../x", 404), ("/etc/passwd", 404), ("%2e%2e%2fpoly.md", 404), ("%2Fetc%2Fpasswd", 404),
    ("svc/svc.md", 404),               # a doc, not an indexed code file
    ("svc/pkg/src/link.py", 404),      # a symlink out of the root
    ("svc/pkg/src/env_link.yaml", 404),  # a symlink to the skipped .env
    ("svc/pkg/src/huge.py", 404),      # over 1 MB
    ("svc/pkg/src/bin.py", 415),       # binary
    (".hidden/ignored.py", 404), ("vendor/thirdparty/lib.c", 404),
])
def test_source_rejections_on_fixture(poly_port, path, code):
    assert call(poly_port, "GET", "/api/source?path=" + path)[0] == code


def test_source_ok_on_fixture(poly_port):
    status, _, body = call(poly_port, "GET", "/api/source?path=svc/pkg/src/evil.py")
    assert status == 200 and b"<script>" in body  # served as inert text
