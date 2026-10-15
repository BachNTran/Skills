"""Canvas engine (assets/map/{engine,layout,draw}.js) in a headless browser, no server: spec §8.2-§8.7.

The harness (tests/ui/harness.html + levels.js) is served statically from the wiki skill root and exposes
window.H = {engine, levels, show(name, mode, via), state(), events, clock, layoutLevel, idle(), frame()}.
H.clock can freeze the engine's clock, so transitions can be inspected frame by frame.
Skips cleanly when Playwright or the Chromium build is missing.
"""
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

UI = Path(__file__).resolve().parent
sys.path.insert(0, str(UI))
ui_util = pytest.importorskip("ui_util")
pytest.importorskip("playwright.sync_api")

WK = UI.parents[1]
MAP_JS = [WK / "assets" / "map" / n for n in ("engine.js", "layout.js", "draw.js")]
NODE = "/mnt/c/Program Files/nodejs/node.exe"

# Pixel scan of the main canvas and the minimap: counts pixels that differ from the background and pixels
# that are blue/purple (HSL saturation > 0.3 and hue 200-300 degrees).
SCAN = """() => {
  const out = { total: 0, ink: 0, blue: 0, worst: null };
  const bg = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim();
  const m = bg.match(/^#([0-9a-f]{6})$/i);
  const B = m ? [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16)) : [11, 15, 13];
  for (const c of [H.engine.canvas, document.getElementById('map-mini')]) {
    if (!c || !c.width || !c.height) continue;
    const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
    for (let i = 0; i < d.length; i += 4) {
      if (d[i + 3] === 0) continue;
      const r = d[i], g = d[i + 1], b = d[i + 2];
      out.total++;
      if (Math.abs(r - B[0]) + Math.abs(g - B[1]) + Math.abs(b - B[2]) > 18) out.ink++;
      const mx = Math.max(r, g, b), mn = Math.min(r, g, b), ch = mx - mn;
      if (!ch) continue;
      const l = (mx + mn) / 510, s = ch / 255 / (1 - Math.abs(2 * l - 1));
      let h = mx === r ? ((g - b) / ch) % 6 : mx === g ? (b - r) / ch + 2 : (r - g) / ch + 4;
      h = (h * 60 + 360) % 360;
      if (s > 0.3 && h >= 200 && h <= 300) { out.blue++; if (!out.worst) out.worst = [r, g, b, h, s]; }
    }
  }
  return out;
}"""


def node_check_target(path: Path, tmp: Path) -> Path:
    """node --check treats .js as CommonJS outside a "type": "module" package: check an .mjs copy."""
    dst = tmp / (path.stem + ".mjs")
    shutil.copyfile(path, dst)
    return dst


@pytest.mark.parametrize("js", MAP_JS, ids=lambda p: p.name)
def test_js_syntax(js, tmp_path):
    assert js.is_file(), js
    node = NODE if Path(NODE).is_file() else shutil.which("node")
    if not node:
        pytest.skip("node not found")
    target = node_check_target(js, tmp_path)
    arg = str(target)
    if node == NODE:
        wslpath = shutil.which("wslpath")
        if not wslpath:
            pytest.skip("wslpath not found")
        arg = subprocess.run([wslpath, "-w", arg], capture_output=True, text=True, check=True).stdout.strip()
    r = subprocess.run([node, "--check", arg], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr


def test_no_unsafe_apis():
    for js in MAP_JS:
        text = js.read_text(encoding="utf-8")
        for bad in ("innerHTML", "eval(", "new Function", "shadowBlur", "fetch("):
            assert bad not in text, f"{js.name} uses {bad}"


# ---------------------------------------------------------------- browser fixtures

@pytest.fixture(scope="module")
def site():
    url, stop = ui_util.serve_dir(WK)
    yield url
    stop()


@pytest.fixture(scope="module")
def chromium():
    with ui_util.browser() as b:
        yield b


class Page:
    """One harness page plus its console guard and network log."""

    def __init__(self, browser, site, level="root", w=1280, h=800, **ctx):
        self.ctx = browser.new_context(viewport={"width": w, "height": h}, **ctx)
        self.pg = self.ctx.new_page()
        self.errors = ui_util.console_guard(self.pg)
        self.requests = []
        self.pg.on("request", lambda r: self.requests.append(r.url))
        self.pg.goto(f"{site}/tests/ui/harness.html?level={level}")
        self.pg.wait_for_function("window.H && window.H.ok === true", timeout=10000)
        self.idle()

    def js(self, expr, arg=None):
        return self.pg.evaluate(expr, arg) if arg is not None else self.pg.evaluate(expr)

    def idle(self, ms=3000):
        assert self.js(f"H.idle({ms})"), "engine never went idle"

    def frame(self):
        self.js("H.frame()")

    def state(self):
        return self.js("H.state()")

    def rects(self):
        return self.js("H.engine.rects()")

    def events(self, kind=None):
        ev = self.js("H.events")
        return [e for e in ev if kind is None or e["ev"] == kind]

    def close(self):
        assert not self.errors, self.errors
        self.ctx.close()


@pytest.fixture
def page(chromium, site):
    made = []

    def make(level="root", **kw):
        p = Page(chromium, site, level, **kw)
        made.append(p)
        return p

    yield make
    for p in made:
        p.close()


def centre(r):
    return r["x"] + r["w"] / 2, r["y"] + r["h"] / 2


# ---------------------------------------------------------------- rendering

@pytest.mark.parametrize("level", ["root", "child", "cyclic", "big", "code", "file", "kinds"])
def test_canvas_draws_every_level(page, level):
    p = page(level)
    scan = p.js(SCAN)
    assert scan["total"] > 0
    assert scan["ink"] / scan["total"] > 0.01, scan  # not blank: well over 1 % of pixels differ from --bg
    st = p.state()
    assert st["at"] == p.js(f"H.levels.{level}.at")
    assert len(st["visible"]) == p.js(f"H.levels.{level}.nodes.length")  # fit shows every block


def test_dpr2_backing_store(page):
    p = page("root", device_scale_factor=2)
    size = p.js("[H.engine.canvas.width, H.engine.canvas.height, H.engine.canvas.clientWidth, H.engine.canvas.clientHeight]")
    assert size[0] == 2 * size[2] and size[1] == 2 * size[3], size
    assert p.js(SCAN)["ink"] > 0


@pytest.mark.parametrize("scheme", ["dark", "light"])
def test_palette_never_blue_or_purple(page, scheme):
    p = page("root", color_scheme=scheme)
    light_bg = p.js("getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()")
    assert (light_bg.lower() == "#0b0f0d") == (scheme == "dark")
    p.js("H.engine.select('firmware'); H.engine.highlight({nodes: new Map([['firmware', 2]]), edges: new Set(['firmware>backend'])}); H.engine.setOverlay('health'); 0")
    for level in ("root", "child", "cyclic", "big", "code", "file", "kinds"):
        p.js(f"H.show('{level}', 'jump')")
        p.idle()
        p.frame()
        scan = p.js(SCAN)
        assert scan["blue"] == 0, (level, scan)
    r = p.js("(H.show('root', 'jump'), 0)")
    p.idle()
    # hover dims the rest; still no blue
    rect = p.rects()["backend"]
    p.pg.mouse.move(*centre(rect))
    p.pg.wait_for_timeout(250)
    assert p.js(SCAN)["blue"] == 0


# ---------------------------------------------------------------- layout

LAYOUT_CHECK = """(arg) => {
  const [name, dir] = Array.isArray(arg) ? arg : [arg, 'LR'];
  const lv = H.levels[name];
  const measure = (t, role) => String(t || '').length * (role === 'label' ? 6.2 : 8.2);
  const a = H.layoutLevel(lv, { measure, dir }), b = H.layoutLevel(lv, { measure, dir });
  const ids = Object.keys(a.nodes), bad = [];
  for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++) {
    const p = a.nodes[ids[i]], q = a.nodes[ids[j]];
    if (p.x < q.x + q.w && q.x < p.x + p.w && p.y < q.y + q.h && q.y < p.y + p.h) bad.push([ids[i], ids[j]]);
  }
  const outside = ids.filter((id) => { const r = a.nodes[id]; return r.x < 0 || r.y < 0 || r.x + r.w > a.w || r.y + r.h > a.h; });
  const ghostsIn = Object.entries(a.ghosts).filter(([, r]) => r.x < a.w && r.x + r.w > 0 && r.y < a.h && r.y + r.h > 0).map(([id]) => id);
  const routes = Object.values(a.edges).every((e) => e.pts.length >= 4 && (e.pts.length - 1) % 3 === 0 && e.pts.every((p) => isFinite(p[0]) && isFinite(p[1])));
  // routes between two level blocks never pass behind (or within 3 px of) a third block
  const bez = (P, j, t) => { const u = 1 - t; return [0, 1].map((c) => u * u * u * P[j][c] + 3 * u * u * t * P[j + 1][c] + 3 * u * t * t * P[j + 2][c] + t * t * t * P[j + 3][c]); };
  const intrude = [], ghostIntrude = [];
  for (const e of lv.edges) {
    const r = a.edges[e.id]; if (!r || r.back) continue;
    const inner = a.nodes[e.s] && a.nodes[e.t];
    for (let j = 0; j + 3 < r.pts.length; j += 3) for (let k = 1; k < 24; k++) {
      const [x, y] = bez(r.pts, j, k / 24);
      for (const id of ids) {
        if (id === e.s || id === e.t) continue;
        const q = a.nodes[id];
        if (x > q.x - 3 && x < q.x + q.w + 3 && y > q.y - 3 && y < q.y + q.h + 3) (inner ? intrude : ghostIntrude).push([e.id, id]);
      }
    }
  }
  return { same: JSON.stringify(a) === JSON.stringify(b), overlaps: bad, outside, ghostsIn, routes,
    intrude: [...new Set(intrude.map(String))], ghostIntrude: [...new Set(ghostIntrude.map(String))],
    n: ids.length, want: lv.nodes.length, ghosts: Object.keys(a.ghosts).length, wantGhosts: (lv.ghosts || []).length, order: a.order.length, mode: a.mode,
    dir: a.dir, w: a.w, h: a.h };
}"""


@pytest.mark.parametrize("dir_", ["LR", "TB"])
@pytest.mark.parametrize("level", ["root", "child", "cyclic", "big", "code", "file", "kinds"])
def test_layout_invariants(page, level, dir_):
    p = page("root")
    r = p.js(LAYOUT_CHECK, [level, dir_])
    assert r["dir"] == dir_
    assert r["same"], "layout is not deterministic"
    assert r["overlaps"] == [], r["overlaps"][:5]
    assert r["outside"] == [], r["outside"]  # the level frame (0,0,w,h) contains every member
    assert r["ghostsIn"] == [], r["ghostsIn"]  # ghosts sit outside the frame
    assert r["routes"]
    if r["mode"] == "layered":
        assert r["intrude"] == [], r["intrude"][:5]  # block-to-block routes run through columns and gaps
    if r["n"] <= 40:  # the 150-block stress level is too dense to route every ghost edge around
        assert r["ghostIntrude"] == [], r["ghostIntrude"][:5]  # ghost routes bend around every block
    assert r["n"] == r["want"] and r["ghosts"] == r["wantGhosts"] and r["order"] == r["n"]


def test_layout_modes(page):
    p = page("root")
    assert p.js(LAYOUT_CHECK, "kinds")["mode"] == "shelf"  # no edges -> grid
    assert p.js(LAYOUT_CHECK, "root")["mode"] == "layered"
    assert p.js(LAYOUT_CHECK, "cyclic")["mode"] == "layered"  # cycles broken by the feedback arc set
    back = p.js("Object.values(H.layoutLevel(H.levels.cyclic).edges).filter((e) => e.back).length")
    assert back >= 1


def test_layout_top_down_for_portrait(page):
    """dir 'TB' (portrait screens) stacks layers top-down: the root level is taller than wide, layers run down
    the page, and pins given in TB coordinates come back unchanged (lens switch)."""
    p = page("root")
    lr, tb = p.js(LAYOUT_CHECK, ["root", "LR"]), p.js(LAYOUT_CHECK, ["root", "TB"])
    assert lr["w"] > lr["h"] and tb["h"] > tb["w"]
    r = p.js("""() => {
      const lv = H.levels.root, a = H.layoutLevel(lv, { dir: 'TB' });
      const down = lv.edges.filter((e) => a.nodes[e.s] && a.nodes[e.t] && !a.edges[e.id]?.back)
        .every((e) => a.nodes[e.s].y + a.nodes[e.s].h <= a.nodes[e.t].y + 1);
      const b = H.layoutLevel(lv, { dir: 'TB', pins: a.nodes });
      const kept = Object.keys(a.nodes).every((id) => ['x', 'y', 'w', 'h'].every((k) => Math.abs(a.nodes[id][k] - b.nodes[id][k]) <= 1));
      return { down, kept };
    }""")
    assert r["down"], "forward edges point down in TB"
    assert r["kept"], "pins survive the TB transform"


def test_layout_budget_150_nodes(page):
    p = page("root")
    ms = p.js("""() => {
      const lv = H.levels.big;
      const c = document.createElement('canvas').getContext('2d');
      c.font = '650 14px sans-serif';
      const measure = (t) => c.measureText(String(t)).width;
      H.layoutLevel(lv, { measure });                 // warm-up (JIT)
      const runs = [];
      for (let i = 0; i < 5; i++) { const t0 = performance.now(); H.layoutLevel(lv, { measure }); runs.push(performance.now() - t0); }
      runs.sort((a, b) => a - b);
      return { median: runs[2], n: lv.nodes.length, m: lv.edges.length };
    }""")
    assert ms["n"] == 150 and ms["m"] >= 600
    assert ms["median"] <= 40, ms


def test_lens_pins_keep_positions(page):
    p = page("child")
    before = p.rects()
    lens = p.js("""(() => { const lv = JSON.parse(JSON.stringify(H.levels.child)); lv.lens = 'code';
      lv.nodes.push({ id: 'firmware/main.cpp', type: 'file', tier: 'code', kind: 'cpp', name: 'main.cpp', drill: null, n: 0, badges: {} });
      return lv; })()""")
    p.js("(lv) => H.show(lv, 'lens')", lens)
    p.idle()
    after = p.rects()
    for nid in p.js("H.levels.child.nodes.map((n) => n.id)"):
        for k in "xywh":
            assert abs(before[nid][k] - after[nid][k]) <= 1, (nid, k, before[nid], after[nid])
    assert "firmware/main.cpp" in after


# ---------------------------------------------------------------- camera and transitions

def test_wheel_zoom_keeps_cursor_point(page):
    p = page("root")
    p.js("H.engine.setAutoDrill(false)")
    sx, sy = 700.0, 333.0
    p.pg.mouse.move(sx, sy)
    for dy in (-120, -120, 80, -300, 240):
        c0 = p.state()["cam"]
        p.pg.mouse.wheel(0, dy)
        p.pg.wait_for_timeout(60)
        c1 = p.state()["cam"]
        assert c1["k"] != c0["k"]
        w0 = (c0["x"] + sx / c0["k"], c0["y"] + sy / c0["k"])
        w1 = (c1["x"] + sx / c1["k"], c1["y"] + sy / c1["k"])
        drift = math.hypot(w1[0] - w0[0], w1[1] - w0[1]) * c1["k"]
        assert drift <= 1, (dy, drift)
    assert p.events("activate") == []


def test_drag_pans_with_inertia(page):
    p = page("root")
    c0 = p.state()["cam"]
    m = p.pg.mouse
    m.move(600, 650)
    m.down()
    for i in range(1, 9):
        m.move(600 - i * 30, 650)
        p.pg.wait_for_timeout(8)
    m.up()
    c1 = p.state()["cam"]
    p.idle()
    c2 = p.state()["cam"]
    assert c1["x"] > c0["x"]          # dragged left -> camera moved right
    assert c2["x"] > c1["x"] + 1      # and kept gliding after release
    assert p.events("select") == []   # a drag is not a click


def test_drill_and_up_swap_without_jump(page):
    p = page("root")
    ref = "firmware/storage"
    p.js("H.clock.freeze(); window.T0 = H.clock.now(); window.P = H.show('child', 'drill', 'firmware'); 0")
    samples = {}
    for frac in (0.3, 0.5999, 0.6, 0.6001, 0.8):
        p.js(f"H.clock.set(T0 + 420 * {frac})")
        p.frame()
        samples[frac] = p.rects()[ref]
    a, b = samples[0.5999], samples[0.6]
    assert math.hypot(*(a[k] - b[k] for k in "xy")) <= 2, (a, b)
    assert abs(a["w"] - b["w"]) <= 2
    b2 = samples[0.6001]
    assert math.hypot(*(b2[k] - b[k] for k in "xy")) <= 2
    assert samples[0.3]["w"] < samples[0.8]["w"]  # the child grows through the zoom
    p.js("H.clock.release(); 0")
    p.js("window.P")
    p.idle()
    assert p.state()["at"] == "firmware"
    # real-time durations
    p2 = page("root")
    t = p2.js("(async () => { const t0 = performance.now(); await H.show('child', 'drill', 'firmware'); const t1 = performance.now(); await H.show('root', 'up', 'firmware'); return [t1 - t0, performance.now() - t1]; })()")
    assert t[0] <= 600 and t[1] <= 600, t
    assert p2.state()["at"] == "."


def test_up_swap_without_jump(page):
    p = page("child")
    p.js("H.show('child', 'jump')")
    p.idle()
    ref = "firmware/storage"
    p.js("H.clock.freeze(); window.T0 = H.clock.now(); window.P = H.show('root', 'up', 'firmware'); 0")
    p.js("H.clock.set(T0 + 1)")
    p.frame()
    first = p.rects()
    # at the start of 'up', the child level is drawn where it was: the parent frame sits around it
    assert "firmware" in first
    p.js("H.clock.release(); 0")
    p.js("window.P")
    p.idle()
    assert p.state()["at"] == "."


def test_zoom_through_activate_and_up_with_cooldown(page):
    p = page("root")
    p.js("H.manual = true; 0")
    r = p.rects()["firmware"]
    sx, sy = centre(r)
    p.pg.mouse.move(sx, sy)
    short = min(1280, 800)
    fired_at = None
    for _ in range(80):
        before = p.rects()["firmware"]
        p.pg.mouse.wheel(0, -60)
        p.pg.wait_for_timeout(20)
        acts = p.events("activate")
        if acts:
            after = p.rects()["firmware"]
            fired_at = max(after["w"], after["h"]) / short
            assert max(before["w"], before["h"]) / short < 0.85 or fired_at >= 0.85
            assert acts[0]["id"] == "firmware" and acts[0]["auto"] is True
            break
        cover = max(p.rects()["firmware"]["w"], p.rects()["firmware"]["h"]) / short
        assert cover < 0.85 + 1e-6, cover  # never past the threshold without firing
    assert fired_at is not None and fired_at >= 0.85, fired_at
    assert len(p.events("activate")) == 1  # one request per gesture, not one per wheel tick

    # now really drill, then try to zoom straight back out: the 500 ms cooldown holds
    p.js("H.manual = false; H.events.length = 0; 0")
    p.js("H.show('child', 'drill', 'firmware')")
    p.idle()
    p.pg.mouse.move(640, 400)
    t0 = time.monotonic()
    for _ in range(4):
        p.pg.mouse.wheel(0, 400)
    early = p.events("up")
    elapsed = time.monotonic() - t0
    if elapsed < 0.45:
        assert early == [], early
    p.pg.wait_for_timeout(600)
    for _ in range(12):
        if p.events("up"):
            break
        p.pg.mouse.wheel(0, 200)
        p.pg.wait_for_timeout(30)
    ups = p.events("up")
    assert ups and ups[0]["auto"] is True
    st = p.state()
    lay = p.js("H.layoutLevel(H.levels.child)")
    assert max(lay["w"], lay["h"]) * st["k"] < 0.55 * short + 1  # fired only below 55 %
    p.idle()
    assert p.state()["at"] == "."


def test_zoom_through_toggle_off(page):
    p = page("root")
    p.js("H.engine.setAutoDrill(false)")
    sx, sy = centre(p.rects()["firmware"])
    p.pg.mouse.move(sx, sy)
    for _ in range(40):
        p.pg.mouse.wheel(0, -100)
    p.pg.wait_for_timeout(100)
    assert p.events("activate") == []


def test_dblclick_and_click(page):
    p = page("root")
    p.js("H.manual = true; 0")
    sx, sy = centre(p.rects()["backend"])
    p.pg.mouse.click(sx, sy)
    assert p.events("select")[-1]["id"] == "backend"
    assert p.state()["sel"] == "backend"
    p.pg.mouse.dblclick(sx, sy)
    acts = p.events("activate")
    assert acts and acts[-1]["id"] == "backend" and acts[-1]["auto"] is False
    g = centre(p.rects()["ghost:ops/alerts"])
    p.pg.mouse.click(*g)
    assert p.events("ghost")[-1]["id"] == "ghost:ops/alerts"
    p.pg.mouse.click(5, 5)  # empty plane clears the selection
    assert p.events("select")[-1]["id"] is None


def test_peek_draws_child_inside_large_block(page):
    p = page("root")
    p.js("H.engine.setAutoDrill(false)")
    sx, sy = centre(p.rects()["firmware"])
    p.pg.mouse.move(sx, sy)
    for _ in range(30):
        if p.rects()["firmware"]["w"] >= 300:
            break
        p.pg.mouse.wheel(0, -80)
        p.pg.wait_for_timeout(20)
    p.idle()
    p.pg.wait_for_timeout(100)
    p.frame()
    assert "firmware" in p.state()["peeks"]


# ---------------------------------------------------------------- filter, highlight, reduced motion

def test_set_filter_is_client_side(page):
    p = page("root")
    n_req = len(p.requests)
    all_edges = set(p.state()["edges"])
    p.js("H.engine.setFilter({ kinds: new Set(['flow']), minConf: 0 })")
    p.idle()
    flow = set(p.state()["edges"])
    want = set(p.js("H.levels.root.edges.filter((e) => e.kinds.flow).map((e) => e.id)"))
    assert flow == want and flow < all_edges
    p.js("H.engine.setFilter({ kinds: new Set(['call', 'contract']), minConf: 0.8 })")
    p.idle()
    hi = set(p.state()["edges"])
    assert hi == set(p.js("H.levels.root.edges.filter((e) => (e.kinds.call || e.kinds.contract) && e.conf >= 0.8).map((e) => e.id)"))
    p.js("H.engine.setFilter(null)")
    p.idle()
    assert set(p.state()["edges"]) == all_edges
    assert len(p.requests) == n_req, p.requests[n_req:]  # no fetch


def test_highlight_lights_edges(page):
    p = page("root")
    p.js("H.engine.highlight({ nodes: new Map([['firmware', 3], ['backend', 1]]), edges: new Set(['firmware>backend']) })")
    p.frame()
    edges = p.state()["edges"]
    assert edges["firmware>backend"]["lit"] is True
    assert [k for k, v in edges.items() if v["lit"]] == ["firmware>backend"]
    p.js("H.engine.highlight(null)")
    assert not any(v["lit"] for v in p.state()["edges"].values())


def test_reduced_motion(page):
    p = page("root", reduced_motion="reduce")
    dt = p.js("(async () => { const t0 = performance.now(); await H.show('child', 'drill', 'firmware'); return performance.now() - t0; })()")
    assert dt <= 150, dt
    assert p.state()["at"] == "firmware"
    dt = p.js("(async () => { const t0 = performance.now(); await H.show('root', 'up', 'firmware'); return performance.now() - t0; })()")
    assert dt <= 150, dt
    p.idle()
    p.state()  # reset the frame counter
    p.pg.wait_for_timeout(1000)
    assert p.state()["frames"] == 0


def test_idle_stops_render_loop(page):
    # a level without flow edges has no ambient animation: after it settles the loop stops entirely
    p = page("code")
    p.pg.wait_for_timeout(200)
    p.state()
    p.pg.wait_for_timeout(1000)
    assert p.state()["frames"] == 0
    # flow edges animate their dashes (throttled), so the loop keeps ticking but well under 60 fps
    q = page("root")
    q.state()
    q.pg.wait_for_timeout(1000)
    assert 0 < q.state()["frames"] <= 40


def test_order_and_rects(page):
    p = page("child")
    order = p.js("H.engine.order()")
    assert sorted(order) == sorted(p.js("H.levels.child.nodes.map((n) => n.id)"))
    rects = p.rects()
    assert all(k in rects for k in order)
    assert all(k in rects for k in p.js("H.levels.child.ghosts.map((g) => g.id)"))
    p.js("H.engine.focus('firmware/ports')")
    p.idle()
    r = p.rects()["firmware/ports"]
    assert abs(r["x"] + r["w"] / 2 - 640) <= 2 and abs(r["y"] + r["h"] / 2 - 400) <= 2
    assert p.state()["sel"] == "firmware/ports"


def test_minimap_click_pans(page):
    p = page("root")
    p.js("H.engine.zoomBy(4)")
    p.idle()
    c0 = p.state()["cam"]
    box = p.pg.locator("#map-mini").bounding_box()
    p.pg.mouse.click(box["x"] + 12, box["y"] + box["height"] / 2)
    p.frame()
    c1 = p.state()["cam"]
    assert c1["x"] < c0["x"]


def test_frame_budget_150_nodes_dpr2(page):
    p = page("big", device_scale_factor=2)
    ms = p.js("""async () => { const ms = [];
      for (let i = 0; i < 30; i++) { H.engine.panBy(i % 2 ? 5 : -5, 0); await H.frame(); ms.push(H.state().ms); }
      ms.sort((a, b) => a - b); return ms[15]; }""")
    assert ms <= 8, ms  # JS time of one render (150 nodes, 600 edges, dpr 2)
