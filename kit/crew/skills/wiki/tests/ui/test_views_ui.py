"""End-to-end Systems/Code views in a headless browser (spec §11.1 steps 1-12).

Needs playwright + the chromium build ui_util knows, the canvas engine (assets/map/engine.js) and wikimap;
skips cleanly while any of them is missing. The example (and the poly fixture for step 12) is served from a
tmp copy by wiki.make_server on a thread. `test=1` in the hash exposes the engine as #map.__engine."""
import importlib.util
import json
import re
import shutil
import sys
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlparse

import pytest

UI = Path(__file__).resolve().parent
WK = UI.parents[1]
EXAMPLE = WK.parents[3] / "example" / "weather-station"
POLY = WK / "tests" / "fixtures" / "poly"
pytest.importorskip("playwright.sync_api")
sys.path.insert(0, str(UI))
ui_util = pytest.importorskip("ui_util")
if not (WK / "assets" / "map" / "engine.js").is_file():
    pytest.skip("assets/map/engine.js not there yet (WP5)", allow_module_level=True)
_spec = importlib.util.spec_from_file_location("wiki_views_ui", WK / "scripts" / "wiki.py")
wiki = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wiki)
if wiki.load_map_lib() is None:
    pytest.skip("wikimap.open_map not available yet (WP3)", allow_module_level=True)

GUARD = """addEventListener('securitypolicyviolation', (e) => (window.__csp ||= []).push(`${e.violatedDirective} ${e.blockedURI}`));"""


def site(tmp_path_factory, src: Path, name: str):
    if not src.is_dir():
        pytest.skip(f"missing {src}")
    base = tmp_path_factory.mktemp(name)
    root = base / src.name
    shutil.copytree(src, root, symlinks=True, ignore=shutil.ignore_patterns(".wiki", ".wikimap", "__pycache__"))
    srv = wiki.make_server(root, base / "data", port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    urllib.request.urlopen(f"{url}/api/map", timeout=120).read()  # build once, before any page waits on it
    return srv, url


@pytest.fixture(scope="module")
def example(tmp_path_factory):
    srv, url = site(tmp_path_factory, EXAMPLE, "ex")
    yield url
    srv.shutdown()
    srv.server_close()


@pytest.fixture(scope="module")
def poly(tmp_path_factory):
    srv, url = site(tmp_path_factory, POLY, "poly")
    yield url
    srv.shutdown()
    srv.server_close()


@pytest.fixture(scope="module")
def browser():
    with ui_util.browser() as b:
        yield b


@pytest.fixture()
def new_page(browser):
    """new_page(**context options) -> page; on teardown: no console errors, page errors or CSP violations."""
    made = []

    def make(viewport=(1280, 800), **opts):
        size = {"width": viewport[0], "height": viewport[1]}
        if hasattr(browser, "new_context"):
            ctx = browser.new_context(viewport=size, **opts)
            page = ctx.new_page()
        else:  # ui_util handed a context
            ctx, page = None, browser.new_page()
            page.set_viewport_size(size)
            if opts:
                page.emulate_media(**opts)
        errors = []
        page.on("console", lambda m: errors.append(f"console {m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.add_init_script(GUARD)
        made.append((page, ctx, errors))
        return page

    yield make
    problems = []
    for page, ctx, errors in made:
        try:
            problems += [f"csp: {v}" for v in page.evaluate("() => window.__csp || []")]
        except Exception:
            pass
        problems += errors
        (ctx or page).close()
    assert not problems, problems


def hash_of(page) -> dict:
    return dict(parse_qsl(urlparse(page.url).fragment))


def wait_hash(page, key, value, timeout=3000):
    page.wait_for_function("([k, v]) => (new URLSearchParams(location.hash.slice(1)).get(k) || '') === v",
                           arg=[key, value], timeout=timeout)


def go(page, base, **h):
    frag = "&".join(f"{k}={quote(v, safe='')}" for k, v in {**h, "test": "1"}.items())
    page.goto(f"{base}/#{frag}")
    page.wait_for_function("() => document.querySelectorAll('#map-a11y button').length > 0 && !!document.querySelector('#map').__engine",
                           timeout=15000)
    settle(page)


def settle(page, timeout=3000):
    page.wait_for_function("() => { const e = document.querySelector('#map').__engine; return e && !e.state().animating; }",
                           timeout=timeout)


def engine(page, expr):
    return page.evaluate(f"() => {{ const e = document.querySelector('#map').__engine; return {expr}; }}")


def a11y_names(page):
    return page.eval_on_selector_all("#map-a11y button", "bs => bs.map(b => b.textContent)")


def press_on(page, node_id, key="Enter"):
    b = page.locator(f'#map-a11y button[data-id="{node_id}"]')
    b.focus()
    b.press(key)


def api(base, path):
    with urllib.request.urlopen(base + path, timeout=30) as r:
        return json.loads(r.read())


# 1
def test_systems_root(example, new_page):
    page = new_page()
    go(page, example, view="systems")
    assert page.is_visible('#views [data-view="systems"]') and page.is_visible('#views [data-view="code"]')
    assert page.inner_text("#map-crumbs").strip() == "weather-station"
    assert {"firmware", "backend", "dashboard", "protocol", "deploy", "host"} <= set(a11y_names(page))
    lit = page.evaluate("""() => {
      const c = document.querySelector('#map canvas'), g = c.getContext('2d');
      const bg = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim();
      const ref = [1, 3, 5].map((i) => parseInt(bg.slice(i, i + 2), 16));
      const d = g.getImageData(0, 0, c.width, c.height).data;
      let n = 0;
      for (let i = 0; i < d.length; i += 4 * 7) if (Math.max(...ref.map((v, k) => Math.abs(d[i + k] - v))) > 24) n++;
      return n;
    }""")
    assert lit > 200  # the canvas is not blank


# 2
def test_drill_and_escape(example, new_page):
    page = new_page()
    go(page, example, view="systems")
    press_on(page, "firmware")
    wait_hash(page, "at", "firmware", timeout=1000)
    assert page.locator("#map-crumbs .crumb").count() == 2
    assert {"sensing", "storage", "comms", "ports", "adapters", "targets"} <= set(a11y_names(page))
    settle(page)
    page.keyboard.press("Escape")
    wait_hash(page, "at", "")
    assert page.locator("#map-crumbs .crumb").count() == 1


# 3
def test_zoom_through(example, new_page):
    page = new_page()
    go(page, example, view="systems", at="firmware")
    r = engine(page, "e.rects()['firmware/sensing']")
    box = page.locator("#map").bounding_box()
    x, y = box["x"] + r["x"] + r["w"] / 2, box["y"] + r["y"] + r["h"] / 2
    page.mouse.move(x, y)
    for _ in range(60):
        if hash_of(page).get("at") == "firmware/sensing":
            break
        page.mouse.wheel(0, -160)
        page.wait_for_timeout(60)
    wait_hash(page, "at", "firmware/sensing", timeout=2000)
    settle(page)
    # the world point under the cursor stays put across the frame swap (engine contract; checked to 2 px by WP5)


# 4
def test_handoff_to_code(example, new_page):
    page = new_page()
    go(page, example, view="systems", at="firmware")
    press_on(page, "firmware/comms")
    wait_hash(page, "view", "code")
    wait_hash(page, "at", "firmware/comms")
    assert page.locator("#map-crumbs .lens-glyph").count() == 1
    page.wait_for_function("() => document.querySelector('#map-status').textContent.includes('Code lens')", timeout=2000)


def open_batmon(page, example):
    go(page, example, view="systems", at="firmware/sensing", sel="firmware/sensing/battery_monitor")
    page.wait_for_selector("#map-panel:not([hidden]) .mp-title", timeout=5000)


# 5
def test_icd_button(example, new_page):
    page = new_page()
    open_batmon(page, example)
    icd = page.locator("#map-panel .mp-icd")
    (icd if icd.count() else page.locator("#map-panel .mp-docs button", has_text="ICD")).first.click()
    page.wait_for_function("() => (new URLSearchParams(location.hash.slice(1)).get('item') || '').endsWith('battery_monitor.icd.md')")
    wait_hash(page, "view", "read")
    page.wait_for_function("""() => [...document.querySelectorAll('#r-body h1, #r-body h2, #r-body h3, #r-body h4')]
      .some((h) => { const r = h.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; })""", timeout=3000)


# 6
def test_req_chip_flashes_the_line(example, new_page):
    page = new_page()
    open_batmon(page, example)
    chip = page.locator("#map-panel .mp-reqs button", has_text="REQ-BATMON-002")
    if not chip.count():  # module panels may list no REQs: the bound source file does
        go(page, example, view="code", at="firmware/sensing/battery_monitor/src",
           sel="firmware/sensing/battery_monitor/src/brownout.cpp")
        chip = page.locator("#map-panel .mp-reqs button", has_text="REQ-BATMON-002")
        chip.wait_for(timeout=5000)
    chip.first.click()
    page.wait_for_function("() => (new URLSearchParams(location.hash.slice(1)).get('item') || '').endsWith('battery_monitor.req.md')")
    flash = page.wait_for_selector("#r-body .flash", timeout=1500)
    assert "REQ-BATMON-002" in flash.inner_text()


# 7
def test_search_source_and_back(example, new_page):
    page = new_page()
    go(page, example, view="code", at="firmware")
    page.fill("#map-q", "encode_reading")
    page.press("#map-q", "Enter")
    page.wait_for_function("() => (new URLSearchParams(location.hash.slice(1)).get('sel') || '').endsWith('uplink.cpp#comms::encode_reading')",
                           timeout=8000)
    settle(page)
    at = hash_of(page)["at"]
    page.keyboard.press("s")
    wait_hash(page, "view", "read")
    h = hash_of(page)
    assert h["src"].endswith("firmware/comms/src/uplink.cpp") and re.fullmatch(r"\d+(-\d+)?", h["line"])
    hit = page.wait_for_selector("ol.src li.hit")
    assert page.evaluate("(li) => { const r = li.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; }", hit)
    page.click(".src-head button")
    wait_hash(page, "view", "code")
    wait_hash(page, "at", at)


# 8
def test_trace_lights_lifted_edge(example, new_page):
    hits = api(example, "/api/map/search?q=sample&limit=50")
    sid = next(h["id"] for h in hits if h["id"].endswith("BatteryMonitor::sample"))
    page = new_page()
    go(page, example, view="systems", at="firmware", sel=sid)
    page.wait_for_selector("#map-panel:not([hidden]) .mp-act", timeout=5000)
    page.locator("#map-panel .mp-act button", has_text="Trace ↓").click()
    page.wait_for_function("""() => { const e = document.querySelector('#map').__engine;
      return Object.entries(e.state().edges || {}).some(([id, v]) => v.lit && id.startsWith('firmware/sensing>') && id.includes('firmware/ports')); }""",
                           timeout=5000)


# 9
def test_lens_toggle_keeps_positions(example, new_page):
    page = new_page()
    go(page, example, view="systems", at="firmware")
    before = engine(page, "e.rects()")
    page.focus("#map")
    page.keyboard.press("l")
    wait_hash(page, "view", "code")
    page.wait_for_timeout(400)
    settle(page)
    after = engine(page, "e.rects()")
    shared = [i for i in before if i in after and not i.startswith("ghost:")]
    assert shared
    for i in shared:
        assert abs(before[i]["x"] - after[i]["x"]) <= 2 and abs(before[i]["y"] - after[i]["y"]) <= 2, i


# 10
def test_reduced_motion(example, new_page):
    page = new_page(reduced_motion="reduce")
    go(page, example, view="systems")
    ms = page.evaluate("""async () => {
      const b = document.querySelector('#map-a11y button[data-id="firmware"]');
      b.focus();
      await new Promise((ok) => setTimeout(ok, 50));
      const t0 = performance.now();
      b.click();
      while (new URLSearchParams(location.hash.slice(1)).get('at') !== 'firmware' && performance.now() - t0 < 3000)
        await new Promise((ok) => setTimeout(ok, 4));
      return performance.now() - t0;
    }""")
    assert ms < 200
    page.wait_for_timeout(300)
    engine(page, "e.state()")  # resets the frame counter
    page.wait_for_timeout(1000)
    assert engine(page, "e.state().frames") == 0


# 11
def test_light_theme_and_phone(example, new_page):
    page = new_page(color_scheme="light")
    go(page, example, view="systems")
    rgb = page.evaluate("() => getComputedStyle(document.body).backgroundColor")
    r, g, b = (int(v) for v in re.findall(r"\d+", rgb)[:3])
    assert 0.2126 * r + 0.7152 * g + 0.0722 * b > 200
    page.set_viewport_size({"width": 390, "height": 800})
    page.wait_for_timeout(250)
    assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth && document.body.scrollWidth <= innerWidth")
    for v in ("read", "graph2d", "graph3d", "systems", "code"):
        bb = page.locator(f'#views [data-view="{v}"]').bounding_box()
        assert bb and bb["x"] >= 0 and bb["x"] + bb["width"] <= 390 and bb["width"] >= 24, v


# 12
def test_hostile_docstring_is_text(poly, new_page):
    lv = api(poly, "/api/map/level?lens=code&at=" + quote("svc/pkg/src/evil.py", safe=""))
    syms = [n for n in lv["nodes"] if n.get("type") == "symbol"]
    target = next((n for n in syms if "alert" in (n.get("brief") or "")), syms[0] if syms else None)
    at, sel = ("svc/pkg/src/evil.py", target["id"]) if target else ("svc/pkg/src", "svc/pkg/src/evil.py")
    page = new_page()
    go(page, poly, view="code", at=at, sel=sel)
    page.wait_for_selector("#map-panel:not([hidden]) .mp-title", timeout=5000)
    panel = page.locator("#map-panel")
    page.wait_for_function("() => document.querySelector('#map-panel').textContent.includes('alert(1)')", timeout=5000)
    assert panel.locator("script").count() == 0
    assert page.locator("img[onerror]").count() == 0 and panel.locator("img").count() == 0
