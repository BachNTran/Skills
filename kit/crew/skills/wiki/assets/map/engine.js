// wiki map — the canvas engine behind the Systems and Code views. One <canvas>, an infinite plane with
// pan/zoom/inertia, one level frame at a time; drilling zooms into a block and swaps its child level in
// place (the child layout is mapped into the block's rect, so nothing jumps). No DOM text, no fetches:
// levels come in through show(), peeks through on.peek(). Repo strings reach the canvas only via fillText.
import { layoutLevel, visibleKinds, LABEL_MAX, LABELS_ALWAYS } from './layout.js';
import { PALETTE, drawNode, drawGhost, drawEdge, edgeLook, drawLabel, labelRect, chip, nodeLook, shapePath,
  roundRect, rgba, isLight, fontOf, textW, ellipsize } from './draw.js';

const DRILL_MS = 420, SWAP = 0.6, GLIDE_MS = 300, JUMP_MS = 320, CALM_MS = 120, HOVER_MS = 150, COOL_MS = 500;
const PEEK_MIN = 240, PEEK_MAX = 6, HIT_PX = 6, MARGIN = { l: 40, r: 40, t: 64, b: 40 };
// one shape for every level on every screen: layers flow left to right and wrap at a fixed aspect, so a
// level lays out the same each time it is opened (spatial memory holds); the camera fits it to the screen
const LAYOUT_DIR = 'LR', LAYOUT_ASPECT = 1.75;
const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
const lerp = (a, b, t) => a + (b - a) * t;
const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const TOKEN_KEYS = ['bg', 's1', 's2', 's3', 'ink', 'soft', 'muted', 'line', 'faint', 'mint', 'lime', 'sand', 'rose'];
const FALLBACK = { bg: '#0b0f0d', s1: '#111815', s2: '#16201b', s3: '#1c2a23', ink: '#f0f5f1', soft: '#d3ddd6', muted: '#8da295',
  line: 'rgba(141,162,149,0.2)', faint: 'rgba(141,162,149,0.16)', mint: '#5eead4', lime: '#a3e635', sand: '#d9c78a', rose: '#fb9a85' };
const FRAME_FIRST = new Set(['group', 'dir', 'bucket']);

/** Bézier point and tangent. */
function bez(p0, p1, p2, p3, t) {
  const u = 1 - t;
  return [u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
    u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]];
}

/** Camera tween with a fixed point: the zoom feels like moving towards/away from one spot. */
function zoomLerp(a, b, e, W, H) {
  const k = Math.exp(lerp(Math.log(a.k), Math.log(b.k), e));
  const ca = [a.x + W / 2 / a.k, a.y + H / 2 / a.k], cb = [b.x + W / 2 / b.k, b.y + H / 2 / b.k];
  const d = 1 / b.k - 1 / a.k;
  const u = Math.abs(Math.log(b.k / a.k)) > 1e-3 ? (1 / k - 1 / a.k) / d : e;
  return { k, x: lerp(ca[0], cb[0], u) - W / 2 / k, y: lerp(ca[1], cb[1], u) - H / 2 / k };
}

/**
 * Mount the map canvas in `host` and return its API (show a level, drill, select, fit, zoom, state(), rects()).
 * Each level is laid out for the canvas's shape: a long chain of layers wraps into bands, and small levels take
 * whichever direction (left-right or top-down) fits the screen better.
 * tokens(): theme colours; calm(): true for reduced motion; on: event handlers; now(): clock in ms (tests).
 */
export function createEngine({ host, tokens, calm = () => false, on = {}, now } = {}) {
  const clock = typeof now === 'function' ? now : () => performance.now();
  const emit = (name, ...a) => (typeof on[name] === 'function' ? on[name](...a) : undefined);
  const canvas = document.createElement('canvas');
  canvas.className = 'map-canvas';
  Object.assign(canvas.style, { display: 'block', width: '100%', height: '100%', touchAction: 'none', outline: 'none', userSelect: 'none' });
  host.appendChild(canvas);
  const ctx = canvas.getContext('2d');
  let W = 0, H = 0, dpr = 1, destroyed = false;
  let T = { ...FALLBACK }, light = false, pal = PALETTE.dark;
  const fam = (getComputedStyle(host).fontFamily || '').trim() || 'ui-sans-serif, system-ui, sans-serif';
  const readTokens = () => {
    let t = {};
    try { t = (typeof tokens === 'function' ? tokens() : tokens) || {}; } catch { t = {}; }
    T = {};
    for (const k of TOKEN_KEYS) T[k] = (t[k] && String(t[k]).trim()) || FALLBACK[k];
    light = isLight(T.bg); pal = light ? PALETTE.light : PALETTE.dark;
  };
  readTokens();
  const isCalm = () => { try { return !!calm(); } catch { return false; } };
  const measure = (text, role) => textW(ctx, String(text ?? ''), role === 'label' ? fontOf(500, 11, fam) : role === 'small' ? fontOf(500, 10.5, fam) : fontOf(650, 14, fam));

  // ---------------------------------------------------------------- state
  let cur = null;          // current frame
  let tr = null;           // running transition
  let camTw = null;        // camera tween {from, to, t0, dur}
  let inertia = null;      // {vx, vy} px/ms
  let filter = null, filterKey = 'all';
  let sel = null, autoDrill = true, overlay = 'none', lit = null;
  let hover = null, hoverSet = null, hoverMix = 0, hoverT = 0;
  let roots = [];
  let frames = 0, renderMs = 0, lastT = clock(), flowOff = 0, moving = false, lastMove = 0, atFit = true;
  let coolUntil = 0, pendingAuto = 0, viewTimer = 0, ambientTimer = 0, raf = 0;
  const pulses = new Map();
  const peeks = new Map();   // id → {st, level, frame, fk}
  const layCache = new Map();
  let mini = null;

  // ---------------------------------------------------------------- frames
  function layoutFor(level, pins) {
    const dir = LAYOUT_DIR, aspect = LAYOUT_ASPECT;
    const key = `${level.rev || ''}|${level.lens || ''}|${level.at}|${filterKey}|${pins ? 'p' + Object.keys(pins).length : ''}|${dir}|${aspect}`;
    const lay = !pins && layCache.get(key);
    if (lay && (lay.src === level || (level.rev && lay.n === (level.nodes || []).length && lay.e === (level.edges || []).length))) return lay.lay;
    const out = layoutLevel(level, { measure, pins, filter, dir, aspect });
    if (!pins) {
      layCache.set(key, { lay: out, src: level, n: (level.nodes || []).length, e: (level.edges || []).length });
      if (layCache.size > 48) layCache.delete(layCache.keys().next().value);
    }
    return out;
  }

  function makeFrame(level, pins = null) {
    const lay = layoutFor(level, pins);
    const f = { level, lay, at: level.at, S: 1, O: [0, 0], cam: { x: 0, y: 0, k: 1 }, fitK: 1,
      nodes: new Map((level.nodes || []).map((n) => [n.id, n])), ghosts: new Map((level.ghosts || []).map((g) => [g.id, g])),
      edges: new Map((level.edges || []).map((e) => [e.id, e])), routes: new Map(), vis: [], nb: new Map(), draw: [] };
    for (const [id, r] of Object.entries(lay.edges)) {
      const e = f.edges.get(id);
      if (!e) continue;
      const vk = visibleKinds(e, filter);
      f.routes.set(id, route(r.pts, r.lab));
      f.vis.push({ e, vk, look: edgeLook(e, vk, T), route: f.routes.get(id) });
      for (const [a, b] of [[e.s, e.t], [e.t, e.s]]) (f.nb.get(a) || f.nb.set(a, new Set()).get(a)).add(b);
    }
    f.vis.sort((a, b) => (a.look.key < b.look.key ? -1 : a.look.key > b.look.key ? 1 : 0));
    f.draw = (level.nodes || []).map((n) => n.id).sort((a, b) => (FRAME_FIRST.has(f.nodes.get(b).type) - FRAME_FIRST.has(f.nodes.get(a).type)) || (a < b ? -1 : 1));
    buildHit(f);
    f.fitK = fitCam(f).k;
    return f;
  }
  function relook(f) { if (f) for (const v of f.vis) v.look = edgeLook(v.e, v.vk, T); }

  function route(pts, lab) {
    const path = new Path2D();
    path.moveTo(pts[0][0], pts[0][1]);
    const samples = [pts[0]], segs = [];
    for (let i = 1; i + 2 < pts.length; i += 3) {
      path.bezierCurveTo(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], pts[i + 2][0], pts[i + 2][1]);
      let len = 0, prev = pts[i - 1];
      for (let s = 1; s <= 12; s++) { const p = bez(pts[i - 1], pts[i], pts[i + 1], pts[i + 2], s / 12); len += Math.hypot(p[0] - prev[0], p[1] - prev[1]); samples.push(p); prev = p; }
      const mid = bez(pts[i - 1], pts[i], pts[i + 1], pts[i + 2], 0.5);
      segs.push({ len, mid });
    }
    const n = pts.length - 1, end = pts[n];
    let c = pts[n - 1];
    if (Math.hypot(end[0] - c[0], end[1] - c[1]) < 0.5) c = pts[Math.max(0, n - 2)];
    const dl = Math.hypot(end[0] - c[0], end[1] - c[1]) || 1;
    const cum = [0];
    for (let i = 1; i < samples.length; i++) cum.push(cum[i - 1] + Math.hypot(samples[i][0] - samples[i - 1][0], samples[i][1] - samples[i - 1][1]));
    // the layout names the segment in a column gap (labels there never sit on a block); else the longest
    const best = (lab >= 0 && segs[lab]) || segs.reduce((a, b) => (b.len > a.len ? b : a), segs[0] || { len: 0, mid: pts[0] });
    return { path, samples, cum, segs, best, end, dir: [(end[0] - c[0]) / dl, (end[1] - c[1]) / dl] };
  }

  function buildHit(f) {
    const cell = 120, grid = new Map();
    const put = (x0, y0, x1, y1, item) => {
      for (let gx = Math.floor(x0 / cell); gx <= Math.floor(x1 / cell); gx++)
        for (let gy = Math.floor(y0 / cell); gy <= Math.floor(y1 / cell); gy++) {
          const key = gx + ',' + gy;
          (grid.get(key) || grid.set(key, []).get(key)).push(item);
        }
    };
    f.draw.forEach((id, i) => { const r = f.lay.nodes[id]; put(r.x, r.y, r.x + r.w, r.y + r.h, { type: 'node', id, z: 1000 + i }); });
    for (const [id, r] of Object.entries(f.lay.ghosts)) put(r.x, r.y, r.x + r.w, r.y + r.h, { type: 'ghost', id, z: 5000 });
    for (const v of f.vis) {
      const s = v.route.samples;
      for (let i = 1; i < s.length; i++) {
        put(Math.min(s[i - 1][0], s[i][0]), Math.min(s[i - 1][1], s[i][1]), Math.max(s[i - 1][0], s[i][0]), Math.max(s[i - 1][1], s[i][1]), { type: 'edge', id: v.e.id, a: s[i - 1], b: s[i], z: 0 });
      }
    }
    f.grid = { cell, grid };
  }

  function hitAt(sx, sy) {
    const f = cur;
    if (!f || tr) return null;
    const k = f.cam.k, wx = f.cam.x + sx / k, wy = f.cam.y + sy / k;
    const items = f.grid.grid.get(Math.floor(wx / f.grid.cell) + ',' + Math.floor(wy / f.grid.cell)) || [];
    let best = null, bestD = HIT_PX / k;
    for (const it of items) {
      if (it.type === 'edge') {
        const [ax, ay] = it.a, [bx, by] = it.b, dx = bx - ax, dy = by - ay;
        const t = clamp(((wx - ax) * dx + (wy - ay) * dy) / (dx * dx + dy * dy || 1), 0, 1);
        const d = Math.hypot(wx - (ax + dx * t), wy - (ay + dy * t));
        if (d < bestD && (!best || best.type === 'edge')) { bestD = d; best = { type: 'edge', id: it.id }; }
      } else {
        const r = it.type === 'node' ? f.lay.nodes[it.id] : f.lay.ghosts[it.id];
        if (wx >= r.x && wx <= r.x + r.w && wy >= r.y && wy <= r.y + r.h && (!best || best.type === 'edge' || it.z > best.z)) best = { type: it.type, id: it.id, z: it.z };
      }
    }
    return best ? { type: best.type, id: best.id } : null;
  }

  // ---------------------------------------------------------------- camera
  function boundsOf(lay) {
    let x0 = 0, y0 = 0, x1 = lay.w, y1 = lay.h;
    for (const r of Object.values(lay.ghosts)) { x0 = Math.min(x0, r.x); y0 = Math.min(y0, r.y); x1 = Math.max(x1, r.x + r.w); y1 = Math.max(y1, r.y + r.h); }
    return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
  }
  const bounds = (f) => boundsOf(f.lay);
  function fitRect(b, margin = 0, cap = 1.6) {
    const aw = Math.max(40, W - MARGIN.l - MARGIN.r), ah = Math.max(40, H - MARGIN.t - MARGIN.b);
    const bw = b.w * (1 + 2 * margin), bh = b.h * (1 + 2 * margin);
    const k = Math.min(aw / bw, ah / bh, cap);
    const cx = MARGIN.l + aw / 2, cy = MARGIN.t + ah / 2;
    return { k, x: b.x + b.w / 2 - cx / k, y: b.y + b.h / 2 - cy / k };
  }
  const fitCam = (f) => fitRect(bounds(f));
  const X = (cam) => ({ k: cam.k, tx: -cam.x * cam.k, ty: -cam.y * cam.k });
  const kLimits = (f) => [f.fitK * 0.05, f.fitK * 40];
  const busy = () => !!tr && tr.type !== 'glide';

  function touched() { moving = true; lastMove = clock(); atFit = false; invalidate(); }
  function zoomAt(f, sx, sy, user) {
    if (!cur || busy()) return;
    const c = cur.cam, [lo, hi] = kLimits(cur);
    const k2 = clamp(c.k * f, lo, hi);
    const wx = c.x + sx / c.k, wy = c.y + sy / c.k;
    c.k = k2; c.x = wx - sx / k2; c.y = wy - sy / k2;
    camTw = null;
    touched();
    if (user) zoomThrough(f, sx, sy);
  }
  function pan(dx, dy) { if (!cur || busy()) return; cur.cam.x -= dx / cur.cam.k; cur.cam.y -= dy / cur.cam.k; camTw = null; touched(); }
  function tweenCam(to, dur = 300) {
    if (!cur) return;
    if (isCalm() || dur <= 0) { cur.cam = { ...to }; touched(); return; }
    camTw = { from: { ...cur.cam }, to: { ...to }, t0: clock(), dur };
    invalidate();
  }

  function zoomThrough(f, sx, sy) {
    const t = clock();
    if (!autoDrill || busy() || t < coolUntil || (pendingAuto && t - pendingAuto < 1500)) return;
    const short = Math.min(W, H);
    if (f > 1) {
      const h = hitAt(sx, sy);
      if (!h || h.type !== 'node') return;
      const n = cur.nodes.get(h.id), r = screenRect(cur, h.id);
      if (n && n.drill && Math.max(r.w, r.h) >= 0.85 * short) { pendingAuto = t; emit('activate', h.id, { auto: true }); }
    } else if (f < 1 && !isRoot(cur)) {
      const k = cur.cam.k;
      if (Math.max(cur.lay.w * k, cur.lay.h * k) < 0.55 * short) { pendingAuto = t; emit('up', { auto: true }); }
    }
  }
  const isRoot = (f) => !f || f.at === '.' || f.at === '' || f.at == null || (Array.isArray(f.level.crumbs) && f.level.crumbs.length === 1);

  function screenRect(f, id, Xf = X(f.cam)) {
    const r = posOf(f, id) || f.lay.ghosts[id];
    if (!r) return null;
    return { x: r.x * Xf.k + Xf.tx, y: r.y * Xf.k + Xf.ty, w: r.w * Xf.k, h: r.h * Xf.k };
  }
  function posOf(f, id) {
    const r = f.lay.nodes[id];
    if (!r) return null;
    if (tr && tr.type === 'glide' && f === tr.neu && tr.from[id]) {
      const e = tr.e ?? 0, a = tr.from[id];
      return { x: lerp(a.x, r.x, e), y: lerp(a.y, r.y, e), w: lerp(a.w, r.w, e), h: lerp(a.h, r.h, e) };
    }
    return r;
  }

  // ---------------------------------------------------------------- show / transitions
  function show(level, opts = {}) {
    if (destroyed || !level) return Promise.resolve();
    finish(true);
    pendingAuto = 0;
    if (level.at !== cur?.at) { hover = null; hoverSet = null; }
    if (level.at === '.' || level.at === '') roots = (level.nodes || []).map((n) => n.id);
    const mode = opts.mode || 'jump', via = opts.via ?? null;
    if (cur && cur.level.rev !== level.rev) peeks.clear();
    return new Promise((resolve) => {
      const calmNow = isCalm();
      if (!cur || !W) {
        cur = makeFrame(level); cur.cam = fitCam(cur); atFit = true; settle(resolve); return;
      }
      const t0 = clock();
      if ((mode === 'refresh' || mode === 'lens') && level.at === cur.at) {
        const old = cur, neu = makeFrame(level, mode === 'lens' ? old.lay.nodes : null);
        // a lens switch keeps the camera, so blocks shared by both lenses stay exactly where they were
        neu.S = old.S; neu.O = old.O; neu.cam = atFit && mode === 'refresh' ? fitCam(neu) : { ...old.cam };
        cur = neu;
        if (calmNow) { settle(resolve); return; }
        tr = { type: 'glide', t0, dur: GLIDE_MS, old, neu, from: { ...old.lay.nodes }, resolve, e: 0, cam0: { ...old.cam }, cam1: { ...neu.cam } };
        invalidate(); return;
      }
      if (mode === 'drill' && via && cur.lay.nodes[via]) {
        const P = cur, B = P.lay.nodes[via], C = makeFrame(level);
        const s = 0.92 * Math.min(B.w / C.lay.w, B.h / C.lay.h);
        const o = [B.x + (B.w - C.lay.w * s) / 2, B.y + (B.h - C.lay.h * s) / 2];
        C.S = P.S * s; C.O = [P.O[0] + o[0] * P.S, P.O[1] + o[1] * P.S];
        const camC = fitCam(C);
        if (calmNow) { C.cam = camC; tr = { type: 'fade', t0, dur: CALM_MS, old: P, neu: C, resolve }; cur = C; invalidate(); return; }
        const pk = peeks.get(via), pa = pk && pk.st === 'ok' ? peekAlpha(screenRect(P, via)) : 0;
        tr = { type: 'drill', t0, dur: DRILL_MS, P, C, via, s, o, cam0: { ...P.cam }, camB: fitRect(B, 0.08, Infinity), camC, pa, resolve, swapped: false };
        invalidate(); return;
      }
      if (mode === 'up' && via) {
        const C = cur, P = makeFrame(level), B = P.lay.nodes[via];
        if (B) {
          const s = 0.92 * Math.min(B.w / C.lay.w, B.h / C.lay.h);
          const o = [B.x + (B.w - C.lay.w * s) / 2, B.y + (B.h - C.lay.h * s) / 2];
          P.S = C.S / s; P.O = [C.O[0] - o[0] * P.S, C.O[1] - o[1] * P.S];
          const camP = fitCam(P);
          if (calmNow) { P.cam = camP; tr = { type: 'fade', t0, dur: CALM_MS, old: C, neu: P, resolve }; cur = P; invalidate(); return; }
          P.cam = { k: C.cam.k / s, x: o[0] + C.cam.x * s, y: o[1] + C.cam.y * s };
          peeks.set(via, { st: 'ok', level: C.level, frame: C, fk: filterKey });
          tr = { type: 'up', t0, dur: DRILL_MS, P, C, via, s, o, cam0: { ...P.cam }, camP, pa: 0.6, resolve };
          cur = P; invalidate(); return;
        }
      }
      const neu = makeFrame(level);
      neu.cam = fitCam(neu);
      tr = { type: calmNow ? 'fade' : 'jump', t0, dur: calmNow ? CALM_MS : JUMP_MS, old: cur, neu, resolve };
      cur = neu; invalidate();
    });
  }

  function settle(resolve) {
    coolUntil = clock() + COOL_MS;
    invalidate();
    if (resolve) resolve();
    queueView(0);
  }
  /** Snap the running transition to its end. */
  function finish(silent) {
    if (!tr) return;
    const t = tr;
    tr = null;
    if (t.type === 'drill') { t.C.cam = { ...t.camC }; cur = t.C; atFit = true; }
    else if (t.type === 'up') { t.P.cam = { ...t.camP }; cur = t.P; atFit = true; }
    else if (t.type === 'jump' || t.type === 'fade') { cur = t.neu; atFit = true; }
    else if (t.type === 'glide') cur = t.neu;
    settle(t.resolve);
    if (!silent) invalidate();
  }

  function step(t, dt) {
    let active = false;
    if (tr) {
      const p = clamp((t - tr.t0) / tr.dur, 0, 1);
      if (tr.type === 'drill') {
        if (p < SWAP) { tr.P.cam = zoomLerp(tr.cam0, tr.camB, ease(p / SWAP), W, H); tr.e = ease(p / SWAP); cur = tr.P; }
        else {
          if (!tr.swapped) {
            const b = tr.camB;
            tr.camS = { k: b.k * tr.s, x: (b.x - tr.o[0]) / tr.s, y: (b.y - tr.o[1]) / tr.s };
            tr.swapped = true; tr.e = 1;
          }
          tr.e2 = ease((p - SWAP) / (1 - SWAP));
          tr.C.cam = zoomLerp(tr.camS, tr.camC, tr.e2, W, H);
          cur = tr.C;
        }
      } else if (tr.type === 'up') {
        tr.e = ease(p); tr.P.cam = zoomLerp(tr.cam0, tr.camP, tr.e, W, H);
      } else if (tr.type === 'jump') {
        tr.e = ease(p); tr.neu.cam = zoomLerp({ ...fitCam(tr.neu), k: fitCam(tr.neu).k * 0.94 }, fitCam(tr.neu), tr.e, W, H);
      } else if (tr.type === 'glide') {
        tr.e = ease(p); tr.neu.cam = zoomLerp(tr.cam0, tr.cam1, tr.e, W, H);
      } else tr.e = p;
      moving = tr.type !== 'fade' && tr.type !== 'glide';
      if (p >= 1) finish(false);
      else active = true;
    }
    if (camTw && cur) {
      const p = clamp((t - camTw.t0) / camTw.dur, 0, 1);
      cur.cam = zoomLerp(camTw.from, camTw.to, ease(p), W, H);
      moving = true; lastMove = t;
      if (p >= 1) { camTw = null; queueView(); } else active = true;
    }
    if (inertia && cur) {
      if (isCalm()) inertia = null;
      else {
        cur.cam.x -= (inertia.vx * dt) / cur.cam.k; cur.cam.y -= (inertia.vy * dt) / cur.cam.k; // keeps the drag's direction
        const d = Math.pow(0.92, dt / 16);
        inertia.vx *= d; inertia.vy *= d;
        moving = true; lastMove = t;
        if (Math.hypot(inertia.vx, inertia.vy) < 0.01) { inertia = null; queueView(); } else active = true;
      }
    }
    const want = hoverSet ? 1 : 0;
    if (hoverMix !== want) {
      hoverMix = isCalm() ? want : clamp(hoverMix + (want ? 1 : -1) * (dt / HOVER_MS), 0, 1);
      if (hoverMix !== want) active = true;
    }
    for (const [id, t0] of pulses) { if (t - t0 > (isCalm() ? 600 : 1000)) pulses.delete(id); else active = true; }
    if (moving && t - lastMove > 90 && !tr && !camTw && !inertia) moving = false;
    if (moving) active = true;
    return active;
  }

  // ---------------------------------------------------------------- render loop
  let ambientRaf = false; // the pending frame only advances the flow dashes
  function invalidate() { schedule(); }
  function schedule(ambient = false) {
    if (destroyed) return;
    if (raf) { if (!ambient) ambientRaf = false; return; }
    if (document.hidden || W === 0) { if (tr) finish(true); return; }
    ambientRaf = ambient;
    raf = requestAnimationFrame(tick);
  }
  function ambientWanted() {
    if (isCalm() || !cur || tr) return false;
    if (lit && lit.edges.size) return true; // trace particles
    let n = 0;
    for (const v of cur.vis) if (v.look.flow) n++;
    return n > 0 && n <= 120;
  }
  function tick() {
    raf = 0;
    if (destroyed) return;
    frames++;
    const t = clock(), dt = clamp(t - lastT, 0, 64);
    lastT = t;
    flowOff += dt * 0.03;
    const active = step(t, dt);
    const r0 = performance.now();
    render(t);
    renderMs = performance.now() - r0;
    if (active) schedule();
    else if (ambientWanted()) {
      if (!ambientTimer) ambientTimer = setTimeout(() => { ambientTimer = 0; schedule(true); }, 33);
    }
  }

  function render(t) {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.globalAlpha = 1;
    ctx.fillStyle = T.bg; ctx.fillRect(0, 0, W, H);
    if (!cur) return;
    grid(cur);
    if (!tr || tr.type === 'glide') frame(cur, X(cur.cam), {});
    else if (tr.type === 'drill') {
      if (!tr.swapped) {
        const e = tr.e || 0, XP = X(tr.P.cam);
        frame(tr.P, XP, { sib: 1 - e, via: tr.via, viaBody: 1 - e, viaText: 1 - e * 1.6, box: 1 - e, peeks: true });
        const Xc = { k: tr.s * XP.k, tx: tr.o[0] * XP.k + XP.tx, ty: tr.o[1] * XP.k + XP.ty };
        // B's outline becomes the child's level frame
        const B = tr.P.lay.nodes[tr.via], Cb = { x: (B.x - tr.o[0]) / tr.s, y: (B.y - tr.o[1]) / tr.s, w: B.w / tr.s, h: B.h / tr.s };
        const morph = { x: lerp(Cb.x, 0, e), y: lerp(Cb.y, 0, e), w: lerp(Cb.w, tr.C.lay.w, e), h: lerp(Cb.h, tr.C.lay.h, e) };
        frameBox(tr.C, Xc, e, e, morph);
        frame(tr.C, Xc, { alpha: lerp(tr.pa, 1, e), ghosts: 0, box: 0, labels: e > 0.5, child: true });
      } else frame(tr.C, X(tr.C.cam), { ghosts: tr.e2 });
    } else if (tr.type === 'up') {
      const e = tr.e || 0, XP = X(tr.P.cam);
      frame(tr.P, XP, { sib: e, via: tr.via, viaBody: e, viaText: e, box: e, peeks: true });
      const Xc = { k: tr.s * XP.k, tx: tr.o[0] * XP.k + XP.tx, ty: tr.o[1] * XP.k + XP.ty };
      const B = tr.P.lay.nodes[tr.via], Cb = { x: (B.x - tr.o[0]) / tr.s, y: (B.y - tr.o[1]) / tr.s, w: B.w / tr.s, h: B.h / tr.s };
      const morph = { x: lerp(0, Cb.x, e), y: lerp(0, Cb.y, e), w: lerp(tr.C.lay.w, Cb.w, e), h: lerp(tr.C.lay.h, Cb.h, e) };
      frameBox(tr.C, Xc, 1 - e, 1 - e, morph);
      frame(tr.C, Xc, { alpha: lerp(1, tr.pa * 0.6, e), ghosts: clamp(1 - e * 2.5, 0, 1), box: 0, labels: e < 0.5, child: true });
    } else {
      const e = tr.e || 0;
      frame(tr.old, X(tr.old.cam), { alpha: 1 - e });
      frame(tr.neu, X(tr.neu.cam), { alpha: e });
    }
    drawMini();
  }

  // dot grid on the absolute plane (continuous across drills: A = O + c·S)
  function grid(f) {
    const kA = f.cam.k / f.S, xA = f.O[0] + f.cam.x * f.S, yA = f.O[1] + f.cam.y * f.S;
    let g = 32;
    while (g * kA < 18) g *= 4;
    while (g * kA >= 72) g /= 4;
    const layer = (gs, a, r) => {
      if (a <= 0.01) return;
      const sp = gs * kA, x0 = Math.ceil(xA / gs) * gs, y0 = Math.ceil(yA / gs) * gs;
      ctx.beginPath();
      for (let x = (x0 - xA) * kA; x < W; x += sp) for (let y = (y0 - yA) * kA; y < H; y += sp) ctx.rect(Math.round(x * dpr) / dpr - r / 2, Math.round(y * dpr) / dpr - r / 2, r, r);
      ctx.fillStyle = rgba(T.muted, a); ctx.fill();
    };
    const fine = clamp((g * kA - 18) / 30, 0, 1);
    layer(g, (light ? 0.2 : 0.13) * fine, 1);
    layer(g * 4, light ? 0.3 : 0.2, 1.4);
  }

  function frameBox(f, Xf, alpha, wm, r = null) {
    if (alpha <= 0.01) return;
    const b = r || { x: 0, y: 0, w: f.lay.w, h: f.lay.h };
    const x = b.x * Xf.k + Xf.tx, y = b.y * Xf.k + Xf.ty, w = b.w * Xf.k, h = b.h * Xf.k;
    if (w < 4) return;
    const rad = clamp(14 * Xf.k, 4, 22);
    ctx.globalAlpha = alpha;
    ctx.beginPath(); roundRect(ctx, x, y, w, h, rad);
    const gr = ctx.createLinearGradient(0, y, 0, y + h);
    gr.addColorStop(0, rgba(T.s1, light ? 0.75 : 0.62)); gr.addColorStop(1, rgba(T.s1, light ? 0.45 : 0.32));
    ctx.fillStyle = gr; ctx.fill();
    ctx.strokeStyle = rgba(T.muted, light ? 0.3 : 0.24); ctx.lineWidth = 1; ctx.stroke();
    const crumbs = f.level.crumbs;
    const name = (Array.isArray(crumbs) && crumbs.length && crumbs[crumbs.length - 1].name) || f.level.name || f.at || '';
    if (!r) f.title = null;
    if (wm > 0.01 && w > 120) {
      const fs = clamp(16 * Xf.k, 11, 26), pad = clamp(20 * Xf.k, 10, 28);
      ctx.globalAlpha = alpha * wm;
      const nf = fontOf(700, fs, fam);
      ctx.font = nf; ctx.fillStyle = rgba(T.ink, 0.62); ctx.textBaseline = 'middle'; ctx.textAlign = 'left';
      const s = ellipsize(ctx, name, nf, w - pad * 2);
      ctx.fillText(s, Math.round(x + pad), Math.round(y + pad + fs * 0.5));
      const lens = f.level.lens ? (f.level.lens === 'code' ? 'code' : 'systems') : '';
      if (lens) {
        const lf = fontOf(600, fs * 0.58, fam);
        ctx.font = lf; ctx.fillStyle = rgba(T.muted, 0.9);
        ctx.fillText(lens.toUpperCase().split('').join(' '), Math.round(x + pad + textW(ctx, s, nf) + fs * 0.6), Math.round(y + pad + fs * 0.55));
      }
      if (!r) { // the level title: edge labels and chips must not land on it
        const lw = lens ? fs * 0.6 + textW(ctx, lens.toUpperCase().split('').join('\u200a'), fontOf(600, fs * 0.58, fam)) : 0;
        f.title = { x: x + pad - 4, y: y + pad - 3, w: textW(ctx, s, nf) + lw + 8, h: fs + 6 };
      }
    }
    ctx.globalAlpha = 1;
  }

  /** Open area boxes (the root of the Systems lens): a soft boundary, its title on top. Screen-space titles are
   *  kept in f.areaTitles so edge labels avoid them and a click on one opens the area. */
  function areaBoxes(f, Xf, alpha) {
    f.areaTitles = [];
    const areas = f.lay.areas;
    if (!areas || alpha <= 0.01) return;
    const k = Xf.k;
    for (const id of Object.keys(areas).sort()) {
      const b = areas[id];
      const x = b.x * k + Xf.tx, y = b.y * k + Xf.ty, w = b.w * k, h = b.h * k;
      if (w < 6 || x > W || y > H || x + w < 0 || y + h < 0) continue;
      const tint = tintOf(id), rad = clamp(18 * k, 5, 26);
      ctx.globalAlpha = alpha;
      ctx.beginPath(); roundRect(ctx, x, y, w, h, rad);
      ctx.fillStyle = rgba(tint, light ? 0.06 : 0.05); ctx.fill();
      ctx.setLineDash([Math.max(3, 7 * k), Math.max(2, 5 * k)]);
      ctx.strokeStyle = rgba(tint, light ? 0.55 : 0.45); ctx.lineWidth = Math.max(1, 1.5 * Math.min(1, k * 1.4)); ctx.stroke();
      ctx.setLineDash([]);
      const fs = clamp(18 * k, 10, 28), pad = clamp(22 * k, 8, 30);
      if (w > 90 && fs >= 10) {
        const nf = fontOf(700, fs, fam);
        ctx.font = nf; ctx.fillStyle = rgba(tint, 0.95); ctx.textBaseline = 'middle'; ctx.textAlign = 'left';
        const s = ellipsize(ctx, b.title || id, nf, w - pad * 2);
        const ty = y + pad + fs * 0.5;
        ctx.fillText(s, Math.round(x + pad), Math.round(ty));
        const sub = fontOf(600, fs * 0.5, fam);
        ctx.font = sub; ctx.fillStyle = rgba(T.muted, 0.9);
        const tw = textW(ctx, s, nf);
        if (tw + fs * 3.6 < w - pad * 2) ctx.fillText('A R E A', Math.round(x + pad + tw + fs * 0.6), Math.round(ty + fs * 0.05));
        f.areaTitles.push({ id, x: x + pad - 4, y: y + pad - 4, w: tw + fs * 4, h: fs + 8 });
      }
    }
    ctx.globalAlpha = 1;
  }
  function areaAt(sx, sy) {
    for (const t of cur?.areaTitles || []) if (sx >= t.x && sx <= t.x + t.w && sy >= t.y && sy <= t.y + t.h) return t.id;
    return null;
  }

  function lodOf(sw) { return sw < 10 ? 0 : sw < 60 ? 1 : sw < 140 ? 2 : sw < 260 ? 3 : 4; }
  function peekAlpha(r) {
    if (!r) return 0;
    if (isCalm()) return 0.6;
    const short = Math.min(W, H), m = Math.max(r.w, r.h);
    return 0.35 + 0.45 * clamp((m - PEEK_MIN) / Math.max(1, 0.85 * short - PEEK_MIN), 0, 1);
  }
  const tintOf = (id) => {
    const top = String(id).split('#')[0].split('/')[0];
    let i = roots.indexOf(top);
    if (i < 0) { i = 0; for (const c of top) i = (i * 31 + c.charCodeAt(0)) >>> 0; }
    return pal[i % pal.length];
  };

  function dimOf(f, id) {
    if (!hoverSet || f !== cur || hoverMix <= 0) return 1;
    return hoverSet.has(id) ? 1 : lerp(1, 0.25, hoverMix);
  }

  /** Draw one level frame with the world→screen transform Xf. */
  function frame(f, Xf, o) {
    const alpha = o.alpha ?? 1, sib = o.sib ?? 1, ghostsA = (o.ghosts ?? 1) * alpha;
    if (alpha <= 0.003) return;
    const k = Xf.k, main = f === cur && !o.child;
    if (!o.peek) frameBox(f, Xf, (o.box ?? 1) * alpha, (o.box ?? 1));
    if (!o.peek) areaBoxes(f, Xf, alpha * sib);
    const calmNow = isCalm();
    // ---- edges (world transform, batched by style)
    const glide = tr && tr.type === 'glide' && f === tr.neu ? tr : null;
    const edgeA = glide ? glide.e * glide.e : 1;
    ctx.setTransform(dpr * k, 0, 0, dpr * k, dpr * Xf.tx, dpr * Xf.ty);
    const flowOn = !calmNow && !o.peek && f.vis.length <= 600 && f.vis.filter((v) => v.look.flow).length <= 120;
    const heads = !moving || o.peek;
    const vp = { x0: -Xf.tx / k - 40 / k, y0: -Xf.ty / k - 40 / k, x1: (W - Xf.tx) / k + 40 / k, y1: (H - Xf.ty) / k + 40 / k };
    if (glide && glide.old) drawEdgesOf(glide.old, 1 - glide.e, false, heads, flowOn, vp);
    drawEdgesOf(f, alpha * sib * edgeA, o.peek, heads, flowOn, vp, o.peek ? 0.75 : 1);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    // particles on traced edges
    if (lit && !o.peek && main && lit.edges.size) particles(f, Xf, alpha);
    // ---- nodes
    const peekList = [];
    for (const id of f.draw) {
      const n = f.nodes.get(id), r0 = posOf(f, id);
      if (!r0) continue;
      const r = { x: r0.x * k + Xf.tx, y: r0.y * k + Xf.ty, w: r0.w * k, h: r0.h * k };
      if (r.x > W + 20 || r.y > H + 20 || r.x + r.w < -20 || r.y + r.h < -20) continue;
      const isVia = id === o.via;
      let a = alpha * (isVia ? (o.viaBody ?? 1) : sib) * dimOf(f, id);
      if (glide && !glide.from[id]) a *= glide.e;
      if (o.peek) a *= 0.95;
      const lod = lodOf(r.w);
      const st = { T, fam, dpr, light, tint: tintOf(id), alpha: a, k: k, sel: main && sel === id, hov: main && hover && hover.id === id,
        lit: !!(lit && lit.nodes.has(id)), health: overlay === 'health', stale: n.badges && n.badges.stale > 0, moving, peek: !!o.peek };
      const canPeek = !o.peek && !isVia && n.drill && r.w >= PEEK_MIN && lod >= 3 && !r0.strip; // a base strip: no preview
      if (canPeek) peekList.push({ id, n, r, st, lod, a });
      else {
        if (isVia) { drawNode(ctx, n, r, { ...st, only: 'body' }, lod); drawNode(ctx, n, r, { ...st, alpha: alpha * clamp(o.viaText ?? 1, 0, 1), only: 'text' }, lod); }
        else drawNode(ctx, n, r, st, lod);
        if (st.lit && lod >= 2) litChip(id, r);
      }
    }
    // peeks: the child layout drawn inside the block (largest first, at most PEEK_MAX)
    peekList.sort((a, b) => b.r.w * b.r.h - a.r.w * a.r.h);
    peekList.forEach((p, i) => {
      const pk = i < PEEK_MAX && o.peeks !== false ? wantPeek(p.id) : null;
      const pf = pk && pk.st === 'ok' ? pk.frame : null;
      drawNode(ctx, p.n, p.r, { ...p.st, only: 'body', peeking: !!pf }, p.lod);
      if (pf) {
        const r0 = f.lay.nodes[p.id];
        const s = 0.92 * Math.min(r0.w / pf.lay.w, r0.h / pf.lay.h);
        const ox = r0.x + (r0.w - pf.lay.w * s) / 2, oy = r0.y + (r0.h - pf.lay.h * s) / 2;
        const Xp = { k: s * k, tx: ox * k + Xf.tx, ty: oy * k + Xf.ty };
        ctx.save(); ctx.beginPath(); shapePath(ctx, nodeLook(p.n).shape, p.r.x + 1, p.r.y + 1, p.r.w - 2, p.r.h - 2, 10); ctx.clip();
        frame(pf, Xp, { alpha: p.a * peekAlpha(p.r), ghosts: 0, box: 0, labels: p.r.w >= 560, peek: true, peeks: false });
        ctx.restore();
      }
      drawNode(ctx, p.n, p.r, { ...p.st, only: 'text', peeking: !!pf }, p.lod);
      if (p.st.lit) litChip(p.id, p.r);
    });
    // ---- labels and chips (screen space, greedy by weight, skipped on collision)
    if (o.labels !== false && (!o.peek || o.labels === true) && k > 0.32) labels(f, Xf, alpha * sib * edgeA);
    // ---- ghosts
    if (ghostsA > 0.01 && !o.peek) {
      for (const [id, g0] of Object.entries(f.lay.ghosts)) {
        const g = f.ghosts.get(id);
        const r = { x: g0.x * k + Xf.tx, y: g0.y * k + Xf.ty, w: g0.w * k, h: g0.h * k, side: g0.side, pos: g0.pos };
        if (r.x > W || r.y > H || r.x + r.w < 0 || r.y + r.h < 0) continue;
        drawGhost(ctx, g, r, { T, fam, dpr, k, crumbs: f.level.crumbs, alpha: ghostsA * sib * dimOf(f, id), hov: main && hover && hover.id === id, sel: main && sel === id, lit: !!(lit && lit.nodes.has(id)) }, lodOf(r.w));
      }
    }
    if (main) for (const [id, t0] of pulses) pulseRing(f, Xf, id, t0);
  }

  function drawEdgesOf(f, a, peek, heads, flowOn, vp, wmul = 1) {
    if (a <= 0.003) return;
    const k = ctx.getTransform().a / dpr;
    // dense levels: quieter, thinner lines so the blocks stay readable (hover and trace bring them back)
    const dens = f.vis.length > 36 ? clamp(Math.sqrt(36 / f.vis.length), 0.32, 1) : 1;
    if (dens < 1) wmul *= 0.55 + 0.45 * dens;
    for (const v of f.vis) {
      const s = v.route.samples, e = v.e;
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (let i = 0; i < s.length; i += 3) { const p = s[i]; if (p[0] < x0) x0 = p[0]; if (p[0] > x1) x1 = p[0]; if (p[1] < y0) y0 = p[1]; if (p[1] > y1) y1 = p[1]; }
      if (x1 < vp.x0 || x0 > vp.x1 || y1 < vp.y0 || y0 > vp.y1) continue;
      let ea = a;
      const isLit = !!(lit && lit.edges.has(e.id));
      if (f === cur && hoverSet && hoverMix > 0 && !isLit) { // a traced edge stays lit while hovering elsewhere
        const on = hover && (hover.type === 'edge' ? hover.id === e.id : (e.s === hover.id || e.t === hover.id));
        ea *= on ? 1 : lerp(1, 0.2, hoverMix);
      }
      if (dens < 1 && !isLit && !(hover && f === cur && (hover.id === e.id || e.s === hover.id || e.t === hover.id))) ea *= dens;
      const look = wmul !== 1 ? { ...v.look, width: v.look.width * wmul } : v.look;
      drawEdge(ctx, v.route, look, k, T, { alpha: ea, lit: isLit, flowOn: flowOn && !peek, flowOff: flowOff / k, heads });
    }
  }

  function labels(f, Xf, a) {
    if (a <= 0.02) return;
    const k = Xf.k, fs = clamp(11 * Math.sqrt(k), 9.5, 13);
    const placed = [];
    // a busy level labels only what is in focus: the hovered edge or block, and the selected block's edges
    const busy = f.vis.length > LABELS_ALWAYS && f === cur;
    const focus = (e) => (sel && (e.s === sel || e.t === sel)) || (hover && (hover.type === 'edge' ? hover.id === e.id : (e.s === hover.id || e.t === hover.id)));
    const cand = f.vis.filter((v) => (!busy || focus(v.e)) && ((v.look.label && v.e.labels && v.e.labels.length) || v.look.chip)).sort((p, q) => (q.e.n || 0) - (p.e.n || 0) || (p.e.id < q.e.id ? -1 : 1));
    const blocks = [];
    for (const id of f.draw) { const r = f.lay.nodes[id]; blocks.push({ x: r.x * k + Xf.tx, y: r.y * k + Xf.ty, w: r.w * k, h: r.h * k }); }
    if (f.title) blocks.push(f.title);
    for (const t of f.areaTitles || []) blocks.push(t);
    const hit = (r) => placed.some((p) => r.x < p.x + p.w + 4 && r.x + r.w + 4 > p.x && r.y < p.y + p.h + 3 && r.y + r.h + 3 > p.y)
      || blocks.some((p) => r.x < p.x + p.w && r.x + r.w > p.x && r.y < p.y + p.h && r.y + r.h > p.y);
    for (const v of cand) {
      const seg = v.route.best, mx = seg.mid[0] * k + Xf.tx, my = seg.mid[1] * k + Xf.ty;
      if (mx < -50 || my < -50 || mx > W + 50 || my > H + 50) continue;
      let ea = a;
      if (hoverSet && hoverMix > 0 && f === cur) { const on = hover && (hover.type === 'edge' ? hover.id === v.e.id : (v.e.s === hover.id || v.e.t === hover.id)); ea *= on ? 1 : lerp(1, 0.15, hoverMix); }
      const isLit = !!(lit && lit.edges.has(v.e.id));
      const segPx = seg.len * k;
      if (v.look.label && v.e.labels && v.e.labels.length && segPx > 64) {
        // one line when it fits, else wrapped to two lines (the layout reserves LABEL_MAX per column gap)
        // several labels lifted onto one edge: the first one plus a count; the tooltip lists them all
        const txt = v.e.labels.length > 1 ? `${v.e.labels[0]}  +${v.e.labels.length - 1} more` : v.e.labels[0];
        const lr = labelRect(ctx, txt, fam, fs, Math.min(LABEL_MAX * (fs / 11), segPx - 16 - fs * 1.3));
        const r = { x: mx - lr.w / 2, y: my - lr.h / 2, w: lr.w, h: lr.h };
        if (lr.lines.length && lr.lines[0] && segPx > lr.w + 16 && !hit(r)) {
          placed.push(drawLabel(ctx, lr, mx, my, v.look, T, fam, fs, ea, isLit, dpr));
          if (v.look.chip) placed.push(chip(ctx, v.look.chip, r.x + r.w + 4, my, v.look.color, T, fam, fs * 0.9));
          continue;
        }
      }
      if (v.look.chip && segPx > 34) {
        const size = fs * 0.9, f2 = fontOf(650, size, fam), cw = textW(ctx, v.look.chip, f2) + size * 1.1;
        const r = { x: mx - cw / 2, y: my - size * 0.83, w: cw, h: size * 1.65 };
        if (!hit(r)) { ctx.globalAlpha = ea; placed.push(chip(ctx, v.look.chip, mx, my, v.e.state === 'undeclared' ? T.rose : v.look.color, T, fam, size, 'center')); ctx.globalAlpha = 1; }
      }
    }
  }

  function litChip(id, r) {
    const c = lit.nodes.get(id);
    if (!(c > 1)) return;
    chip(ctx, String(c), r.x + r.w - 6, r.y + 2, T.lime, T, fam, 10, 'center');
  }

  function particles(f, Xf, a) {
    const t = clock() / 1000, k = Xf.k;
    let count = 0;
    ctx.fillStyle = rgba(T.lime, a);
    ctx.beginPath();
    for (const v of f.vis) {
      if (!lit.edges.has(v.e.id) || count >= 200) continue;
      const { samples: s, cum } = v.route, L = cum[cum.length - 1];
      if (L * k < 30) continue;
      const per = Math.min(3, Math.max(1, Math.round((L * k) / 160)));
      for (let j = 0; j < per && count < 200; j++, count++) {
        const d = (((t * 70) / k / L + j / per) % 1) * L;
        let i = 1;
        while (i < cum.length - 1 && cum[i] < d) i++;
        const u = (d - cum[i - 1]) / ((cum[i] - cum[i - 1]) || 1);
        const x = lerp(s[i - 1][0], s[i][0], u) * k + Xf.tx, y = lerp(s[i - 1][1], s[i][1], u) * k + Xf.ty;
        ctx.moveTo(x + 2.4, y); ctx.arc(x, y, 2.4, 0, Math.PI * 2);
      }
    }
    ctx.fill();
  }

  function pulseRing(f, Xf, id, t0) {
    const r = screenRect(f, id, Xf);
    if (!r) return;
    const c = isCalm(), p = clamp((clock() - t0) / (c ? 600 : 1000), 0, 1);
    for (const off of c ? [0] : [0, 0.35]) {
      const q = c ? 0.5 : clamp((p - off) / 0.65, 0, 1);
      if (q <= 0 || q >= 1) continue;
      const g = 4 + q * 22;
      ctx.globalAlpha = (1 - q) * 0.9;
      ctx.beginPath(); roundRect(ctx, r.x - g, r.y - g, r.w + 2 * g, r.h + 2 * g, 12 + g * 0.5);
      ctx.strokeStyle = T.lime; ctx.lineWidth = 2; ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  // ---------------------------------------------------------------- peeks
  function wantPeek(id) {
    let pk = peeks.get(id);
    if (pk && pk.st === 'ok' && pk.fk !== filterKey) { pk.frame = makeFrame(pk.level); pk.fk = filterKey; }
    if (pk) return pk;
    if (typeof on.peek !== 'function') return null;
    if ([...peeks.values()].filter((p) => p.st === 'wait').length >= PEEK_MAX) return null;
    pk = { st: 'wait' };
    peeks.set(id, pk);
    Promise.resolve().then(() => emit('peek', id)).then((level) => {
      if (destroyed || peeks.get(id) !== pk) return;
      if (level && Array.isArray(level.nodes) && level.nodes.length) { pk.level = level; pk.frame = makeFrame(level); pk.fk = filterKey; pk.st = 'ok'; }
      else pk.st = 'none';
      invalidate();
    }, () => { pk.st = 'none'; });
    return pk;
  }

  // ---------------------------------------------------------------- minimap
  function drawMini() {
    if (!mini || !cur) return;
    const el = mini.el, cw = el.clientWidth || el.width, ch = el.clientHeight || el.height;
    if (!cw || !ch) return;
    if (el.width !== Math.round(cw * dpr) || el.height !== Math.round(ch * dpr)) { el.width = Math.round(cw * dpr); el.height = Math.round(ch * dpr); }
    const m = mini.ctx, f = cur, b = bounds(f), pad = 8;
    const s = Math.min((cw - 2 * pad) / b.w, (ch - 2 * pad) / b.h);
    const ox = (cw - b.w * s) / 2 - b.x * s, oy = (ch - b.h * s) / 2 - b.y * s;
    mini.map = { s, ox, oy };
    m.setTransform(dpr, 0, 0, dpr, 0, 0);
    m.clearRect(0, 0, cw, ch);
    m.beginPath(); roundRect(m, 0.5, 0.5, cw - 1, ch - 1, 8); m.fillStyle = rgba(T.s1, 0.92); m.fill(); m.strokeStyle = rgba(T.muted, 0.25); m.lineWidth = 1; m.stroke();
    m.beginPath(); roundRect(m, ox, oy, f.lay.w * s, f.lay.h * s, 3); m.strokeStyle = rgba(T.muted, 0.22); m.stroke();
    m.beginPath();
    for (const v of f.vis) { const r = v.route.samples; m.moveTo(r[0][0] * s + ox, r[0][1] * s + oy); m.lineTo(r[r.length - 1][0] * s + ox, r[r.length - 1][1] * s + oy); }
    m.strokeStyle = rgba(T.mint, 0.22); m.stroke();
    for (const id of f.draw) {
      const r = f.lay.nodes[id];
      m.fillStyle = rgba(tintOf(id), sel === id ? 0.95 : 0.5);
      m.fillRect(r.x * s + ox, r.y * s + oy, Math.max(1.5, r.w * s), Math.max(1.5, r.h * s));
    }
    m.fillStyle = rgba(T.muted, 0.45);
    for (const r of Object.values(f.lay.ghosts)) m.fillRect(r.x * s + ox, r.y * s + oy, Math.max(1.5, r.w * s), Math.max(1.5, r.h * s));
    const c = f.cam, vx = c.x * s + ox, vy = c.y * s + oy, vw = (W / c.k) * s, vh = (H / c.k) * s;
    m.beginPath(); m.rect(vx, vy, vw, vh); m.fillStyle = rgba(T.mint, 0.08); m.fill(); m.strokeStyle = rgba(T.mint, 0.85); m.lineWidth = 1.2; m.stroke();
  }
  function attachMini(el) {
    if (mini && mini.el === el) return;
    detachMini();
    const c2 = el.getContext('2d');
    if (!c2) return;
    const move = (ev) => {
      if (!mini || !mini.map || !cur || busy()) return;
      const rc = el.getBoundingClientRect(), { s, ox, oy } = mini.map;
      const wx = (ev.clientX - rc.left - ox) / s, wy = (ev.clientY - rc.top - oy) / s;
      cur.cam.x = wx - W / 2 / cur.cam.k; cur.cam.y = wy - H / 2 / cur.cam.k;
      camTw = null; inertia = null; touched(); queueView();
    };
    const down = (ev) => { ev.preventDefault(); el.setPointerCapture?.(ev.pointerId); mini.drag = true; move(ev); };
    const mv = (ev) => { if (mini && mini.drag) move(ev); };
    const up = () => { if (mini) mini.drag = false; };
    el.addEventListener('pointerdown', down); el.addEventListener('pointermove', mv);
    el.addEventListener('pointerup', up); el.addEventListener('pointercancel', up);
    mini = { el, ctx: c2, off: () => { el.removeEventListener('pointerdown', down); el.removeEventListener('pointermove', mv); el.removeEventListener('pointerup', up); el.removeEventListener('pointercancel', up); } };
    invalidate();
  }
  function detachMini() { if (mini) { mini.off(); mini = null; } }

  // ---------------------------------------------------------------- input
  const ptrs = new Map();
  let drag = null, pinch = null, hoverPt = null, hoverRaf = 0;
  const local = (ev) => { const r = canvas.getBoundingClientRect(); return [ev.clientX - r.left, ev.clientY - r.top]; };
  function onDown(ev) {
    if (ev.pointerType === 'mouse' && ev.button !== 0) return;
    const [x, y] = local(ev);
    ptrs.set(ev.pointerId, { x, y });
    inertia = null; camTw = null;
    if (ptrs.size === 1) drag = { id: ev.pointerId, x0: x, y0: y, x, y, moved: false, hist: [{ t: clock(), x, y }] };
    else if (ptrs.size === 2) {
      const [a, b] = [...ptrs.values()];
      pinch = { d: Math.hypot(a.x - b.x, a.y - b.y) || 1, mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2 };
      drag = null;
      for (const id of ptrs.keys()) canvas.setPointerCapture?.(id);
    }
  }
  function onMove(ev) {
    const [x, y] = local(ev);
    if (ptrs.has(ev.pointerId)) {
      ptrs.set(ev.pointerId, { x, y });
      if (pinch && ptrs.size >= 2) {
        const [a, b] = [...ptrs.values()];
        const d = Math.hypot(a.x - b.x, a.y - b.y) || 1, mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
        pan(mx - pinch.mx, my - pinch.my);
        const f = d / pinch.d;
        zoomAt(f, mx, my, true);
        pinch = { d, mx, my };
        return;
      }
      if (drag && drag.id === ev.pointerId) {
        if (!drag.moved && Math.hypot(x - drag.x0, y - drag.y0) > 4) { drag.moved = true; canvas.setPointerCapture?.(ev.pointerId); setHover(null, null); }
        if (drag.moved) {
          pan(x - drag.x, y - drag.y);
          drag.hist.push({ t: clock(), x, y });
          if (drag.hist.length > 8) drag.hist.shift();
        }
        drag.x = x; drag.y = y;
        return;
      }
    }
    hoverPt = [x, y];
    if (!hoverRaf) hoverRaf = requestAnimationFrame(() => { hoverRaf = 0; if (hoverPt) { const h = hitAt(hoverPt[0], hoverPt[1]); setHover(h, h ? { x: hoverPt[0], y: hoverPt[1] } : null); } });
  }
  function endPtr(ev, cancelled) {
    if (!ptrs.has(ev.pointerId)) return;
    ptrs.delete(ev.pointerId);
    if (pinch) { if (ptrs.size < 2) pinch = null; drag = null; queueView(); return; }
    if (!drag || drag.id !== ev.pointerId) return;
    const d = drag;
    drag = null;
    if (!d.moved) { if (!cancelled) click(d.x0, d.y0); return; }
    const t = clock(), h = d.hist.filter((p) => t - p.t < 100);
    if (!isCalm() && h.length >= 2 && !cancelled) {
      const a = h[0], b = h[h.length - 1], dt = Math.max(8, b.t - a.t);
      const vx = (b.x - a.x) / dt, vy = (b.y - a.y) / dt;
      if (Math.hypot(vx, vy) > 0.05) { inertia = { vx, vy }; invalidate(); return; }
    }
    queueView();
  }
  function click(x, y) {
    const h = hitAt(x, y);
    if (h && h.type === 'ghost') { const g = cur.ghosts.get(h.id); if (g) emit('ghost', g); return; }
    if (!h || h.type === 'edge') { const a = areaAt(x, y); if (a) { emit('area', a); return; } } // an area's title opens it
    const id = h && h.type === 'node' ? h.id : null;
    sel = id; invalidate();
    emit('select', id);
  }
  function onDbl(ev) {
    ev.preventDefault();
    const [x, y] = local(ev);
    const h = hitAt(x, y);
    if (h && h.type === 'node') emit('activate', h.id, { auto: false });
  }
  function onWheel(ev) {
    ev.preventDefault();
    if (!cur || busy()) return;
    const mul = ev.deltaMode === 1 ? 16 : ev.deltaMode === 2 ? 800 : 1;
    const dx = ev.deltaX * mul, dy = ev.deltaY * mul;
    const [sx, sy] = local(ev);
    inertia = null;
    if (!ev.ctrlKey && (dx !== 0 || !Number.isInteger(dy))) { pan(-dx, -dy); queueView(); return; }
    zoomAt(Math.exp(-dy * 0.0015 * (ev.ctrlKey ? 4 : 1)), sx, sy, true);
    queueView();
  }
  function setHover(h, pt) {
    const same = (h && hover && h.type === hover.type && h.id === hover.id) || (!h && !hover);
    hover = h;
    if (!same) {
      if (h && h.type !== 'edge') { hoverSet = new Set([h.id, ...(cur.nb.get(h.id) || [])]); }
      else if (h && h.type === 'edge') { const e = cur.edges.get(h.id); hoverSet = new Set(e ? [e.s, e.t] : []); }
      else hoverSet = null;
      canvas.style.cursor = h ? 'pointer' : '';
      invalidate();
    }
    if (!same || h) emit('hover', h, pt);
  }
  const prevent = (ev) => ev.preventDefault();
  const onLeave = () => { hoverPt = null; if (hover) setHover(null, null); };
  canvas.addEventListener('pointerdown', onDown);
  canvas.addEventListener('pointermove', onMove);
  canvas.addEventListener('pointerup', (ev) => endPtr(ev, false));
  canvas.addEventListener('pointercancel', (ev) => endPtr(ev, true));
  canvas.addEventListener('lostpointercapture', (ev) => endPtr(ev, true));
  canvas.addEventListener('pointerleave', onLeave);
  canvas.addEventListener('dblclick', onDbl);
  canvas.addEventListener('wheel', onWheel, { passive: false });
  canvas.addEventListener('contextmenu', prevent);
  canvas.addEventListener('gesturestart', prevent);

  // ---------------------------------------------------------------- environment
  function resize() {
    const w = host.clientWidth, h = host.clientHeight, d = window.devicePixelRatio || 1;
    if (w === W && h === H && d === dpr) return;
    const centre = cur ? [cur.cam.x + W / 2 / cur.cam.k, cur.cam.y + H / 2 / cur.cam.k] : null;
    W = w; H = h; dpr = d;
    canvas.width = Math.max(1, Math.round(W * dpr)); canvas.height = Math.max(1, Math.round(H * dpr));
    if (cur) {
      cur.fitK = fitCam(cur).k;
      if (atFit || !centre || !isFinite(centre[0])) cur.cam = fitCam(cur);
      else { cur.cam.x = centre[0] - W / 2 / cur.cam.k; cur.cam.y = centre[1] - H / 2 / cur.cam.k; }
    }
    watchDpr();
    invalidate();
  }
  let dprMq = null;
  const onDpr = () => resize();
  function watchDpr() {
    if (dprMq && dprMq.d === dpr) return;
    if (dprMq) dprMq.mq.removeEventListener('change', onDpr);
    const mq = matchMedia(`(resolution: ${dpr}dppx)`);
    mq.addEventListener('change', onDpr);
    dprMq = { mq, d: dpr };
  }
  const ro = typeof ResizeObserver === 'function' ? new ResizeObserver(() => resize()) : null;
  ro?.observe(host);
  const schemeMq = matchMedia('(prefers-color-scheme: dark)');
  const onScheme = () => { readTokens(); relook(cur); if (tr) { relook(tr.old); relook(tr.neu); relook(tr.P); relook(tr.C); } for (const p of peeks.values()) relook(p.frame); invalidate(); };
  schemeMq.addEventListener('change', onScheme);
  const onVis = () => { if (!document.hidden) { lastT = clock(); invalidate(); } };
  document.addEventListener('visibilitychange', onVis);
  resize();

  function queueView(delay = 160) {
    clearTimeout(viewTimer);
    viewTimer = setTimeout(() => {
      viewTimer = 0;
      if (!cur || destroyed) return;
      if (tr || camTw || inertia) { queueView(delay); return; }
      emit('view', { at: cur.at, k: cur.cam.k, fit: cur.fitK, visible: visibleIds() });
    }, delay);
  }
  function visibleIds() {
    if (!cur) return [];
    const Xf = X(cur.cam), out = [];
    for (const id of cur.draw) { const r = screenRect(cur, id, Xf); if (r && r.x < W && r.y < H && r.x + r.w > 0 && r.y + r.h > 0) out.push(id); }
    return out;
  }

  // ---------------------------------------------------------------- API
  const api = {
    show,
    setFilter(fl) {
      filter = fl ? { kinds: fl.kinds instanceof Set ? new Set(fl.kinds) : new Set(fl.kinds || []), minConf: +fl.minConf || 0, base: fl.base !== false } : null;
      filterKey = filter ? [...filter.kinds].sort().join(',') + '@' + filter.minConf + (filter.base === false ? '-b' : '') : 'all';
      if (cur && !busy()) { finish(true); return show(cur.level, { mode: 'lens' }); }
      return Promise.resolve();
    },
    select(id) { sel = id || null; invalidate(); },
    focus(id) {
      sel = id || null;
      if (!cur || !id || !cur.lay.nodes[id] || busy()) { invalidate(); return; }
      const r = cur.lay.nodes[id], c = cur.cam;
      tweenCam({ k: c.k, x: r.x + r.w / 2 - W / 2 / c.k, y: r.y + r.h / 2 - H / 2 / c.k }, 300);
      atFit = false; queueView(320);
    },
    highlight(h) {
      lit = h && (h.nodes || h.edges) ? { nodes: h.nodes instanceof Map ? h.nodes : new Map(Object.entries(h.nodes || {})), edges: h.edges instanceof Set ? h.edges : new Set(h.edges || []) } : null;
      invalidate();
    },
    setAutoDrill(b) { autoDrill = !!b; },
    setOverlay(o) { overlay = o === 'health' ? 'health' : 'none'; invalidate(); },
    setRoots(ids) { roots = Array.isArray(ids) ? ids.slice() : []; invalidate(); },
    fit(animate = true) { if (!cur || busy()) return; tweenCam(fitCam(cur), animate ? 320 : 0); atFit = true; queueView(340); },
    zoomBy(f, sx = W / 2, sy = H / 2) {
      if (!cur || busy() || !(f > 0)) return;
      const c = cur.cam, [lo, hi] = kLimits(cur), k2 = clamp(c.k * f, lo, hi);
      const wx = c.x + sx / c.k, wy = c.y + sy / c.k;
      tweenCam({ k: k2, x: wx - sx / k2, y: wy - sy / k2 }, 200); atFit = false; queueView(220);
    },
    panBy(dx, dy) { pan(dx, dy); queueView(); },
    pulse(id) { if (id) { pulses.set(id, clock()); invalidate(); } },
    rects() {
      const out = {};
      if (!cur) return out;
      if (tr && tr.type === 'drill' && !tr.swapped) {
        const XP = X(tr.P.cam), Xc = { k: tr.s * XP.k, tx: tr.o[0] * XP.k + XP.tx, ty: tr.o[1] * XP.k + XP.ty };
        for (const id of Object.keys(tr.C.lay.nodes)) out[id] = screenRect(tr.C, id, Xc);
      }
      const Xf = X(cur.cam);
      for (const id of Object.keys(cur.lay.nodes)) out[id] = screenRect(cur, id, Xf);
      for (const [id, g] of Object.entries(cur.lay.ghosts)) out[id] = { x: g.x * Xf.k + Xf.tx, y: g.y * Xf.k + Xf.ty, w: g.w * Xf.k, h: g.h * Xf.k };
      return out;
    },
    order() { return cur ? cur.lay.order.slice() : []; },
    state() {
      const f = frames;
      frames = 0;
      const edges = {};
      if (cur) for (const v of cur.vis) edges[v.e.id] = { lit: !!(lit && lit.edges.has(v.e.id)) };
      return { at: cur ? cur.at : null, k: cur ? cur.cam.k : 1, fit: cur ? cur.fitK : 1,
        animating: !!(tr || camTw || inertia || moving || pulses.size || (raf && !ambientRaf)), frames: f, visible: visibleIds(), edges,
        cam: cur ? { ...cur.cam } : null, mode: tr ? tr.type : null, sel, autoDrill, overlay, lens: cur ? cur.level.lens || null : null,
        layout: cur ? cur.lay.mode : null, frame: cur ? { w: cur.lay.w, h: cur.lay.h, dir: cur.lay.dir || 'LR' } : null, ms: Math.round(renderMs * 100) / 100, peeks: [...peeks.entries()].filter(([, p]) => p.st === 'ok').map(([id]) => id) };
    },
    minimap(el) { if (el) attachMini(el); else detachMini(); },
    resize,
    destroy() {
      destroyed = true;
      if (raf) cancelAnimationFrame(raf);
      if (hoverRaf) cancelAnimationFrame(hoverRaf);
      clearTimeout(viewTimer); clearTimeout(ambientTimer);
      ro?.disconnect();
      schemeMq.removeEventListener('change', onScheme);
      if (dprMq) dprMq.mq.removeEventListener('change', onDpr);
      document.removeEventListener('visibilitychange', onVis);
      detachMini();
      canvas.remove();
      tr = null; cur = null;
    },
    canvas,
  };
  return api;
}
