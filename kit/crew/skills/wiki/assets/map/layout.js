// wiki map — level layout. Pure and deterministic: the same level, filter and pins always give the same
// geometry. Coordinates are world units (1 unit = 1 CSS px at zoom 1). The level frame is the box
// (0, 0, w, h); every level node sits inside it, ghosts sit outside it.
// Edge routes are cubic Béziers: pts = [p0, c1, c2, p1, c1, c2, p2, …] (3·segments + 1 points).

export const PAD = { x: 44, top: 76, bottom: 44 };
export const LABEL_MAX = 168;    // widest edge label line, world px at zoom 1
export const LABELS_ALWAYS = 12; // a level with more visible edges shows labels on hover and selection only

/** How many of a level's edges pass the filter. */
export function visibleEdges(level, filter) {
  return (level.edges || []).filter((e) => e.s !== e.t && Object.keys(visibleKinds(e, filter)).length).length;
}
const GAP_Y = 24;          // min vertical gap between blocks in one layer
const GAP_DUMMY = 14;      // gap next to a long-edge waypoint (the route runs through it)
const GHOST_GAP = 52;      // frame → ghost column
const BAND_GAP = 72;
const LANES = 6, RUNS = 8;   // distinct lanes beside columns / runs along a gap before edges share them       // estimate of the gap between wrapped bands (the real one grows with the edges in it)
const TYPE_ORDER = ['root', 'module', 'group', 'own', 'actor', 'dir', 'bucket', 'file', 'symbol'];
const SYS = new Set(['root', 'module', 'group', 'own']);
const BANDED = new Set(['class', 'struct', 'interface']);

const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
const byStr = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
const defMeasure = (text, role) => String(text || '').length * (role === 'label' ? 6.2 : role === 'small' ? 6 : 8.2);

/** Kinds of edge e that pass filter ({kinds:Set, minConf}); {} when it is hidden. */
export function visibleKinds(e, filter) {
  const out = {};
  if (!e || !e.kinds) return out;
  if (filter && typeof filter.minConf === 'number' && (e.conf ?? 1) < filter.minConf) return out;
  if (filter && filter.base === false && e.base) return out; // edges to shared base blocks: on demand
  for (const k of Object.keys(e.kinds)) if (!filter || !filter.kinds || filter.kinds.has(k)) out[k] = e.kinds[k];
  return out;
}

/** Room the header badges take (findings dot, coverage ring, status pip, crit chip), so names are not cut. */
function badgeW(n) {
  const b = n.badges || {};
  return (b.findings > 0 ? 22 : 0) + (b.cov ? 18 : 0) + (b.status || b.state ? 10 : 0) + (b.crit ? 26 : 0);
}

/** Block size in world units (§8.3). */
export function nodeSize(n, measure = defMeasure) {
  if (n.box) return { w: n.box.w, h: n.box.h }; // an open area box: sized by its own layout
  const m = measure(n.name || n.id, 'name');
  const cont = n.drill ? clamp(Math.sqrt(n.n || 0) / 2, 1, 2) : 1;
  if (n.type === 'actor') return { w: clamp(56 + m * 1.15, 150, 300), h: 56 }; // room for the whole name when zoomed out
  if (SYS.has(n.type)) return { w: Math.round(clamp(32 + m, 168, 320) * cont), h: Math.round(92 * cont) };
  if (n.type === 'dir' || n.type === 'bucket') return { w: Math.round(clamp(40 + m + badgeW(n), 160, 280) * cont), h: Math.round(72 * cont) };
  if (n.type === 'file') return { w: clamp(48 + m, 150, 260), h: 56 };
  if (n.type === 'symbol') return { w: clamp(62 + m + badgeW(n), 120, 300), h: BANDED.has(n.kind) ? 46 : 34 }; // + kind letter chip; long Class::method names
  return { w: clamp(32 + m, 168, 320), h: 92 };
}

/** A ghost's location below what the crumbs already show: its path's parents minus the shared prefix. */
export function ghostParents(g, crumbs) {
  const parts = String(g.path || '').split(' › ').filter(Boolean).slice(0, -1);
  const here = (Array.isArray(crumbs) ? crumbs : []).slice(1).map((c) => c && c.name);
  let i = 0;
  while (i < parts.length && i < here.length && parts[i] === here[i]) i++;
  return parts.slice(i);
}

export function ghostSize(g, measure = defMeasure, crumbs = null) {
  const parent = ghostParents(g, crumbs).join(' › ');
  const sub = parent ? measure('› ' + parent, 'small') * 1.2 + 16 : 0; // room for the location even at low zoom (text has a min size)
  return { w: Math.round(clamp(34 + measure(g.name || g.peer || g.id, 'name') * 0.86 + sub, 110, 220)), h: 30 };
}

// ---------------------------------------------------------------- Sugiyama pieces

/** Eades–Lin–Smyth greedy feedback arc set: a vertex order; edges running backwards in it are back edges. */
function greedyOrder(ids, edges) {
  // edges: [a, b, weight]; heavier edges (declared flows) are kept forward in preference to code edges
  const n = ids.length, outs = ids.map(() => []), ins = ids.map(() => []);
  for (const [a, b, w = 1] of edges) { outs[a].push([b, w]); ins[b].push([a, w]); }
  const outd = outs.map((l) => l.reduce((s, x) => s + x[1], 0)), ind = ins.map((l) => l.reduce((s, x) => s + x[1], 0));
  const gone = new Uint8Array(n), s1 = [], s2 = [], fed = new Float64Array(n); // fed: weight in from the placed front
  let left = n;
  const drop = (v, front) => { gone[v] = 1; left--; for (const [w, x] of outs[v]) { ind[w] -= x; if (front) fed[w] += x; } for (const [w, x] of ins[v]) outd[w] -= x; };
  while (left > 0) {
    let moved = true;
    while (moved) {
      moved = false;
      for (let v = 0; v < n; v++) if (!gone[v] && outd[v] <= 1e-9) { s2.push(v); drop(v, false); moved = true; }
      for (let v = 0; v < n; v++) if (!gone[v] && ind[v] <= 1e-9) { s1.push(v); drop(v, true); moved = true; }
    }
    if (left === 0) break;
    // a cycle: the vertex with the most out-weight surplus, then the one the placed part feeds most (the flow
    // enters the cycle there, so the cut falls on the edge closing it), then the first
    let best = -1, bd = -Infinity, bf = -Infinity;
    for (let v = 0; v < n; v++) {
      if (gone[v]) continue;
      const d = outd[v] - ind[v];
      if (d > bd + 1e-9 || (Math.abs(d - bd) <= 1e-9 && fed[v] > bf + 1e-9)) { bd = d; bf = fed[v]; best = v; }
    }
    s1.push(best); drop(best, true);
  }
  return s1.concat(s2.reverse());
}

/** How often an edge's flow happens, from the rate part of its label (`what · how · rate`): the hot path
 *  (per bar, per fill, every 60 s) weighs most, so cycles break on the rarer read-back or request edge. */
export function rateWeight(e) {
  const l = (e.labels || []).join(' · ').toLowerCase();
  if (/per (bar|fill|tick|sample|message|event|frame|second)|next open|every |\/s\b|engine loop/.test(l)) return 4;
  if (/on demand|on open|per start|per build|manual|dev\b|per ci/.test(l)) return 1;
  return 2;
}

/** Back edges of the drawn flow: a weighted greedy feedback arc set (Eades-Lin-Smyth) over the solid flows,
 *  so the feedback edge (portfolio state back to risk) and the read-back edges go backwards, not a pipeline step. */
function flowBack(nodesIn, pairs, solid, inner) {
  const edges = [];
  pairs.forEach(([a, b], k) => { if (solid[k] && a !== b) edges.push([a, b, rateWeight(inner[k])]); });
  const ord = greedyOrder(nodesIn.map((n) => n.id), edges), pos = new Array(nodesIn.length);
  ord.forEach((v, i) => { pos[v] = i; });
  const back = new Set();
  pairs.forEach(([a, b], k) => { if (solid[k] && a !== b && pos[a] > pos[b]) back.add(k); });
  return back;
}

/** A topological order of the forward solid flows (Kahn, smallest index first): the layering order. */
function flowOrder(core, pairs, solid, back) {
  const inCore = new Set(core), indeg = new Map(core.map((v) => [v, 0])), out = new Map(core.map((v) => [v, []]));
  pairs.forEach(([a, b], k) => { if (solid[k] && !back.has(k) && a !== b && inCore.has(a) && inCore.has(b)) { out.get(a).push(b); indeg.set(b, indeg.get(b) + 1); } });
  const ready = core.filter((v) => indeg.get(v) === 0).sort((a, b) => a - b), ord = [];
  while (ready.length) {
    const v = ready.shift();
    ord.push(v);
    for (const w of out.get(v)) { indeg.set(w, indeg.get(w) - 1); if (indeg.get(w) === 0) { ready.push(w); ready.sort((a, b) => a - b); } }
  }
  return ord;
}

function countCross(layers, down) {
  let total = 0;
  for (let L = 0; L + 1 < layers.length; L++) {
    const pairs = [];
    const pos = new Map(layers[L + 1].map((v, i) => [v, i]));
    layers[L].forEach((u, i) => { for (const v of down[u]) pairs.push(i * 65536 + pos.get(v)); });
    pairs.sort((a, b) => a - b);
    const seq = pairs.map((p) => p & 65535);
    total += inversions(seq);
  }
  return total;
}
function inversions(a) { // merge-sort inversion count
  if (a.length < 2) return 0;
  const tmp = new Array(a.length);
  let inv = 0;
  for (let w = 1; w < a.length; w *= 2) {
    for (let lo = 0; lo < a.length; lo += 2 * w) {
      const mid = Math.min(lo + w, a.length), hi = Math.min(lo + 2 * w, a.length);
      let i = lo, j = mid, k = lo;
      while (i < mid && j < hi) { if (a[i] <= a[j]) tmp[k++] = a[i++]; else { inv += mid - i; tmp[k++] = a[j++]; } }
      while (i < mid) tmp[k++] = a[i++];
      while (j < hi) tmp[k++] = a[j++];
    }
    for (let i = 0; i < a.length; i++) a[i] = tmp[i];
  }
  return inv;
}

/** Crossings between the edges of u and v (u left of v) towards one neighbouring layer. */
function pairCross(nu, nv, pos) {
  let c = 0;
  for (const a of nu) { const pa = pos[a]; for (const b of nv) if (pos[b] < pa) c++; }
  return c;
}

/**
 * Priority placement of one layer (keeps the order, min gaps): weighted least squares towards each block's
 * wish, solved exactly by pool-adjacent-violators. High-priority blocks (long-edge waypoints, busy nodes)
 * weigh more, so they get closest to where they want to be. Returns top y per block.
 */
function placeLayer(hs, gaps, want, prio) {
  const n = hs.length, off = new Float64Array(n), out = new Array(n), st = [];
  for (let i = 1; i < n; i++) off[i] = off[i - 1] + hs[i - 1] + gaps[i - 1];
  for (let i = 0; i < n; i++) {
    let b = { s: prio[i] * (want[i] - hs[i] / 2 - off[i]), w: prio[i], a: i, z: i };
    while (st.length && st[st.length - 1].s / st[st.length - 1].w >= b.s / b.w) {
      const p = st.pop();
      b = { s: p.s + b.s, w: p.w + b.w, a: p.a, z: b.z };
    }
    st.push(b);
  }
  for (const b of st) for (let i = b.a; i <= b.z; i++) out[i] = b.s / b.w + off[i];
  return out;
}

// ---------------------------------------------------------------- routes

/** Horizontal "bump" curves through points (layered routes): every segment leaves and enters level, so it
 *  stays inside the box of its two ends and never swings into a block. */
function bumps(points) {
  const out = [points[0]];
  for (let i = 0; i + 1 < points.length; i++) {
    const a = points[i], b = points[i + 1], h = (b[0] - a[0]) / 2;
    out.push([a[0] + h, a[1]], [b[0] - h, b[1]], b);
  }
  return out.map(([x, y]) => [Math.round(x * 10) / 10, Math.round(y * 10) / 10]);
}

/** Cubic Bézier chain through points; end tangents follow the given unit directions. */
function spline(points, d0, d1) {
  const P = points, m = P.length - 1, out = [P[0]];
  const tan = P.map((p, i) => {
    if (i === 0 || i === m) {
      const q = i === 0 ? P[1] : P[m - 1], dir = i === 0 ? d0 : d1;
      const len = Math.hypot(q[0] - p[0], q[1] - p[1]);
      const s = Math.max(28, len * (m === 1 ? 1.1 : 0.9));
      return [dir[0] * s, dir[1] * s];
    }
    return [(P[i + 1][0] - P[i - 1][0]) / 2, (P[i + 1][1] - P[i - 1][1]) / 2];
  });
  for (let i = 0; i < m; i++) {
    const a = P[i], b = P[i + 1], ta = tan[i], tb = tan[i + 1];
    out.push([a[0] + ta[0] / 3, a[1] + ta[1] / 3], [b[0] - tb[0] / 3, b[1] - tb[1] / 3], b);
  }
  return out.map(([x, y]) => [Math.round(x * 10) / 10, Math.round(y * 10) / 10]);
}

/** Orthogonal polyline → cubic chain with rounded corners. P: the polyline without repeats or collinear
 *  points; seg[j] = index of the cubic for its straight run j (P[j] → P[j + 1]). */
function ortho(points, r = 14) {
  const P = [];
  for (const q of points) {
    const l = P[P.length - 1], k = P[P.length - 2];
    if (l && Math.abs(q[0] - l[0]) < 0.5 && Math.abs(q[1] - l[1]) < 0.5) continue;
    if (k && ((Math.abs(k[0] - l[0]) < 0.5 && Math.abs(l[0] - q[0]) < 0.5) || (Math.abs(k[1] - l[1]) < 0.5 && Math.abs(l[1] - q[1]) < 0.5))) P.pop(); // collinear
    P.push(q);
  }
  const out = [P[0]], seg = [];
  let cur = P[0];
  const line = (q) => { out.push([cur[0] + (q[0] - cur[0]) / 3, cur[1] + (q[1] - cur[1]) / 3], [cur[0] + (2 * (q[0] - cur[0])) / 3, cur[1] + (2 * (q[1] - cur[1])) / 3], q); cur = q; };
  for (let j = 1; j < P.length; j++) {
    const u = P[j - 1], v = P[j], w = P[j + 1];
    seg.push((out.length - 1) / 3);
    if (!w) { line(v); break; }
    const li = Math.hypot(v[0] - u[0], v[1] - u[1]), lo = Math.hypot(w[0] - v[0], w[1] - v[1]);
    const rr = Math.min(r, li / 2, lo / 2);
    const di = [(v[0] - u[0]) / li, (v[1] - u[1]) / li], dout = [(w[0] - v[0]) / lo, (w[1] - v[1]) / lo];
    const p1 = [v[0] - di[0] * rr, v[1] - di[1] * rr], p2 = [v[0] + dout[0] * rr, v[1] + dout[1] * rr];
    line(p1);
    out.push([p1[0] + di[0] * rr * 0.55, p1[1] + di[1] * rr * 0.55], [p2[0] - dout[0] * rr * 0.55, p2[1] - dout[1] * rr * 0.55], p2);
    cur = p2;
  }
  return { pts: out.map(([x, y]) => [Math.round(x * 10) / 10, Math.round(y * 10) / 10]), seg, P };
}

const SIDE_DIR = { r: [1, 0], l: [-1, 0], t: [0, -1], b: [0, 1] };

/** Spread the ends on one side of a rect, ordered by the far end's coordinate. */
function spreadPorts(list, rect) {
  const byKey = new Map();
  for (const p of list) { const k = p.side; (byKey.get(k) || byKey.set(k, []).get(k)).push(p); }
  for (const [side, ps] of byKey) {
    const vert = side === 'l' || side === 'r';
    ps.sort((a, b) => a.far - b.far || byStr(a.key, b.key));
    const span = vert ? rect.h : rect.w, m = ps.length;
    const step = m > 1 ? Math.min(vert ? 14 : 22, (span * 0.62) / (m - 1)) : 0;
    ps.forEach((p, i) => {
      const off = (i - (m - 1) / 2) * step;
      if (side === 'r') p.pt = [rect.x + rect.w, rect.y + rect.h / 2 + off];
      else if (side === 'l') p.pt = [rect.x, rect.y + rect.h / 2 + off];
      else if (side === 't') p.pt = [rect.x + rect.w / 2 + off, rect.y];
      else p.pt = [rect.x + rect.w / 2 + off, rect.y + rect.h];
    });
  }
}

// ---------------------------------------------------------------- main

/**
 * level: {nodes, ghosts, edges, rev, lens, at}. measure(text, role) → width in px (role name|label|small).
 * pins: {id: {x,y,w,h}} positions to keep (lens switch). filter: {kinds:Set, minConf}.
 * aspect: the screen's width/height; a long chain of layers then wraps into bands when that fits it clearly better.
 * → {w, h, mode, nodes:{id:{x,y,w,h,L,o}}, ghosts:{id:{x,y,w,h,side}}, edges:{id:{pts, back}}, order:[ids]}
 */
export function layoutLevel(level, { measure = defMeasure, pins = null, filter = null, dir = 'LR', aspect = 0, labels = null } = {}) {
  const room = labels ?? visibleEdges(level, filter) <= LABELS_ALWAYS;
  if ((level.ghosts || []).length) { // a ghost whose every edge is filtered out has nothing to say here
    const live = new Set();
    for (const e of level.edges || []) if (Object.keys(visibleKinds(e, filter)).length) { live.add(e.s); live.add(e.t); }
    level = { ...level, ghosts: level.ghosts.filter((g) => live.has(g.id)) };
  }
  if (Array.isArray(level.areas) && level.areas.length) return finish(layoutAreas(level, measure, filter, aspect, room), level, filter, measure);
  if (dir !== 'TB') return pins ? layoutCore(level, measure, pins, filter, false, aspect, room) : finish(layoutFlat(level, measure, filter, aspect, room), level, filter, measure);
  // Top-to-bottom (portrait screens): lay out LR on transposed sizes, then transpose back. The frame keeps its
  // padding (title band on top): final = (core.y - S, core.x + S), core = (final.y - S, final.x + S).
  const S = PAD.top - PAD.x;
  const T = (r) => ({ ...r, x: r.y - S, y: r.x + S, w: r.h, h: r.w });
  let cpins = null;
  if (pins) { cpins = {}; for (const [id, r] of Object.entries(pins)) cpins[id] = { x: r.y - S, y: r.x + S, w: r.h, h: r.w }; }
  const c = layoutCore(level, measure, cpins, filter, true, aspect > 0 ? 1 / aspect : 0);
  const nodes = {}, ghosts = {}, edges = {};
  for (const [id, r] of Object.entries(c.nodes)) nodes[id] = T(r);
  const POS = { in: 'top', out: 'bottom', both: 'left' };
  for (const [id, r] of Object.entries(c.ghosts)) ghosts[id] = { ...T(r), pos: POS[r.side] || 'bottom' };
  for (const [id, e] of Object.entries(c.edges)) edges[id] = { ...e, pts: e.pts.map(([x, y]) => [y - S, x + S]) };
  const order = Object.keys(nodes).sort((a, b) => nodes[a].L - nodes[b].L || nodes[a].x - nodes[b].x || nodes[a].y - nodes[b].y || byStr(a, b));
  return { w: Math.max(240, c.h - S), h: Math.max(160, c.w + S), mode: c.mode, dir: 'TB', nodes, ghosts, edges, order };
}

function layoutCore(level, measure, pins, filter, tb, aspect, room = true) {
  let ranked = false; // laid out by its drawn solid flows (then never wrapped into bands)
  const nodesIn = (level.nodes || []).slice().sort((a, b) => byStr(a.id, b.id));
  const ghostsIn = (level.ghosts || []).slice().sort((a, b) => byStr(a.id, b.id));
  const N = nodesIn.length, ix = new Map(nodesIn.map((n, i) => [n.id, i]));
  const gix = new Map(ghostsIn.map((g, i) => [g.id, i]));
  const swap = (z) => (tb ? { w: z.h, h: z.w } : z);
  const size = nodesIn.map((n) => swap(nodeSize(n, measure)));
  const edges = (level.edges || []).filter((e) => Object.keys(visibleKinds(e, filter)).length
    && (ix.has(e.s) || gix.has(e.s)) && (ix.has(e.t) || gix.has(e.t)) && e.s !== e.t)
    .sort((a, b) => byStr(a.id, b.id));
  const inner = edges.filter((e) => ix.has(e.s) && ix.has(e.t));
  // labels longer than LABEL_MAX wrap to two lines, so a column gap never needs more than that
  const labelW = (e) => {
    if (!room) return e.n > 1 ? 24 : 14; // labels show on focus only: no room kept for them
    if (tb) return e.labels && e.labels.length ? 40 : e.n > 1 ? 24 : 0; // TB: the gap is vertical, labels need ~2 lines
    if (!(e.labels && e.labels.length)) return e.n > 1 ? 30 : 0;
    const m = measure(e.labels.join(' · '), 'label');
    return (m > LABEL_MAX ? Math.min(LABEL_MAX, m * 0.55 + 12) : m) + 18;
  };
  const rect = new Array(N);
  let mode, layerOf = new Array(N).fill(0);
  const arcs = []; // back edges, routed as arcs above (or below) the drawing
  let wrap = null;  // bands, when a long chain of layers wraps (see wrapBands)
  const chains = new Map(); // edge id → [vertex refs: {x,y} centre getters]

  const pinned = pins && nodesIn.some((n) => pins[n.id]);
  if (pinned) {
    mode = 'pinned';
    let bx1 = -Infinity, by0 = Infinity, by1 = -Infinity;
    nodesIn.forEach((n, i) => {
      const p = pins[n.id];
      if (p) { rect[i] = { x: p.x, y: p.y, w: p.w, h: p.h }; bx1 = Math.max(bx1, p.x + p.w); by0 = Math.min(by0, p.y); by1 = Math.max(by1, p.y + p.h); }
    });
    let cx = bx1 + 72, cy = by0, colW = 0;
    const colH = Math.max(by1 - by0, 300);
    nodesIn.forEach((n, i) => {
      if (rect[i]) return;
      const s = size[i];
      if (cy > by0 && cy + s.h > by0 + colH) { cx += colW + 48; cy = by0; colW = 0; }
      rect[i] = { x: cx, y: cy, ...s }; cy += s.h + GAP_Y; colW = Math.max(colW, s.w);
    });
    nodesIn.forEach((n, i) => { layerOf[i] = Math.round(rect[i].x / 40); });
  } else {
    const iso = new Set([...Array(N).keys()]);
    for (const e of inner) { iso.delete(ix.get(e.s)); iso.delete(ix.get(e.t)); }
    const core = [...Array(N).keys()].filter((i) => !iso.has(i));
    if (inner.length && inner.length / Math.max(1, N) >= 0.3 && sugiyama(core, iso)) {
      mode = 'layered';
      if (iso.size) { // blocks with no visible edge: tidy rows under the layered drawing
        let bx0 = Infinity, bx1 = -Infinity, by1 = -Infinity;
        for (const i of core) { const r = rect[i]; bx0 = Math.min(bx0, r.x); bx1 = Math.max(bx1, r.x + r.w); by1 = Math.max(by1, r.y + r.h); }
        shelf([...iso], 40, 28, bx0, by1 + 64, Math.max(bx1 - bx0, 640));
      }
    } else {
      mode = 'shelf';
      arcs.length = 0; chains.clear();
      shelf([...Array(N).keys()], inner.length ? 96 : 40, inner.length ? 56 : 32, 0, 0, 0);
    }
  }

  /** Grid of blocks sorted by type then name; maxW > 0 wraps rows at that width, else ceil(sqrt(n·1.6)) columns. */
  function shelf(idx, gx, gy, ox, oy, maxW) {
    const order = idx.slice().sort((a, b) => {
      const ta = TYPE_ORDER.indexOf(nodesIn[a].type), tb = TYPE_ORDER.indexOf(nodesIn[b].type);
      return (ta < 0 ? 99 : ta) - (tb < 0 ? 99 : tb) || byStr(nodesIn[a].name || '', nodesIn[b].name || '') || byStr(nodesIn[a].id, nodesIn[b].id);
    });
    let cols = Math.max(1, Math.ceil(Math.sqrt(order.length * 1.6)));
    if (maxW > 0) {
      const avg = order.reduce((s2, i) => s2 + size[i].w, 0) / Math.max(1, order.length);
      cols = Math.max(1, Math.min(order.length, Math.floor((maxW + gx) / (avg + gx))));
    }
    const cw = [], rh = [];
    order.forEach((i, k) => { const c = k % cols, r = Math.floor(k / cols); cw[c] = Math.max(cw[c] || 0, size[i].w); rh[r] = Math.max(rh[r] || 0, size[i].h); });
    const xs = [ox], ys = [oy];
    for (let c = 1; c < cw.length; c++) xs[c] = xs[c - 1] + cw[c - 1] + gx;
    for (let r = 1; r < rh.length; r++) ys[r] = ys[r - 1] + rh[r - 1] + gy;
    order.forEach((i, k) => {
      const c = k % cols, r = Math.floor(k / cols);
      rect[i] = { x: xs[c], y: ys[r] + (rh[r] - size[i].h) / 2, ...size[i] };
      layerOf[i] = maxW > 0 ? 1e6 + r : c;
    });
  }

  /**
   * Fold layers 0..nL-1 into 2-4 bands of consecutive layers, stacked top to bottom, when that fits `aspect`
   * at least 12% better than one row. Moves Y and fills shiftX in place; null when one row stays.
   */
  function wrapBands(V, Y, nL, colX, colW, layer, shiftX) {
    const lo = new Array(nL).fill(Infinity), hi = new Array(nL).fill(-Infinity);
    V.forEach((v, i) => { if (!v.skip) { lo[v.L] = Math.min(lo[v.L], Y[i]); hi[v.L] = Math.max(hi[v.L], Y[i] + v.h); } });
    const cut = (R) => { const per = Math.ceil(nL / R), out = []; for (let f = 0; f < nL; f += per) out.push([f, Math.min(nL, f + per) - 1]); return out; };
    const ext = ([f, l]) => { let a = Infinity, z = -Infinity; for (let L = f; L <= l; L++) { a = Math.min(a, lo[L]); z = Math.max(z, hi[L]); } return [a, z]; };
    const gapEst = BAND_GAP + (tb ? LABEL_MAX : 0);
    const fit = (bands) => {
      let w = 0, h = gapEst * (bands.length - 1);
      for (const b of bands) { const [a, z] = ext(b); w = Math.max(w, colX[b[1]] + colW[b[1]] - colX[b[0]]); h += z - a; }
      return Math.min(aspect / (w + 2 * PAD.x), 1 / (h + PAD.top + PAD.bottom));
    };
    let bands = null, best = fit(cut(1)) * 1.12;
    for (let R = 2; R <= Math.min(4, Math.ceil(nL / 2)); R++) { const c = cut(R), f = fit(c); if (f > best) { bands = c; best = f; } }
    if (!bands) return null;
    const nb = bands.length, bandL = new Array(nL);
    bands.forEach(([f, l], b) => { for (let L = f; L <= l; L++) bandL[L] = b; });
    const nodeBand = nodesIn.map((n, i) => (V[i].skip ? -1 : bandL[layer[i]]));
    // edges between bands: forward chains and back edges; each takes a lane in the gap(s) it runs through
    const cross = new Map(), back = new Set(), cnt = new Array(nb).fill(0), slot = new Map(), lab = new Array(nb).fill(false);
    const arcRoom = new Array(nb).fill(0);
    for (const e of inner) {
      const si = ix.get(e.s), ti = ix.get(e.t), bs = nodeBand[si], bt = nodeBand[ti];
      const isBack = arcs.some((a) => a.e === e);
      if (bs === bt) {
        if (isBack && bs > 0 && bs < nb - 1) { // a middle band's back edges arc below it, into the gap
          const span = Math.abs(colX[layer[si]] - colX[layer[ti]]) + colW[layer[si]];
          arcRoom[bs] = Math.max(arcRoom[bs], 42 + Math.min(80, 0.06 * span));
        }
        continue;
      }
      const g1 = bt > bs ? bs : bs - 1, g2 = bt > bs ? bt - 1 : bt;
      cross.set(e.id, { bs, bt, g1, g2 });
      if (isBack) back.add(e.id);
      for (const g of new Set([g1, g2])) { slot.set(e.id + '|' + g, cnt[g]++); if (e.labels && e.labels.length) lab[g] = true; }
    }
    for (let i = arcs.length - 1; i >= 0; i--) if (cross.has(arcs[i].e.id)) arcs.splice(i, 1);
    const top = [], bot = [], right = [], gapMid = [];
    let y = 0;
    bands.forEach(([f, l], b) => {
      const [a, z] = ext([f, l]);
      for (let L = f; L <= l; L++) shiftX[L] = -colX[f];
      for (let i = 0; i < V.length; i++) if (!V[i].skip && V[i].L >= f && V[i].L <= l) Y[i] += y - a;
      top[b] = y; bot[b] = y + z - a; right[b] = colX[l] + colW[l] - colX[f];
      if (b < nb - 1) {
        const runs = 24 + 10 * Math.max(0, Math.min(cnt[b], RUNS) - 1) + (lab[b] ? (tb ? LABEL_MAX : 30) : 0);
        gapMid[b] = bot[b] + arcRoom[b] + 24 + runs / 2;
        y = bot[b] + arcRoom[b] + 48 + runs;
      }
    });
    const lane = (L, side, k) => { // x of the free lane beside column L (between columns, else outside the band)
      const b = bandL[L], [f, l] = bands[b];
      const k6 = k % LANES, mid = (gw) => clamp((k6 - (LANES - 1) / 2) * 6, 10 - gw / 2, gw / 2 - 10); // stays in the column gap
      if (side > 0) return L === l ? right[b] + 20 + 8 * k6 : (colX[L] + colW[L] + colX[L + 1]) / 2 + shiftX[L] + mid(colX[L + 1] - colX[L] - colW[L]);
      return L === f ? -20 - 8 * k6 : (colX[L - 1] + colW[L - 1] + colX[L]) / 2 + shiftX[L] + mid(colX[L] - colX[L - 1] - colW[L - 1]);
    };
    return { nb, bandL, nodeBand, cross, back, cnt, slot, gapMid, right, lane, layer, top, bot,
      gutter: Math.max(...right) + 28, lanes: Math.min(LANES, Math.max(0, ...cnt)) };
  }

  /** Sugiyama LR over the core blocks. false (nothing placed) when the layering is too deep to read. */
  function sugiyama(core, iso) {
    const pairs = inner.map((e) => [ix.get(e.s), ix.get(e.t)]);
    // drawn solid flows rank the blocks (the pipeline reads left to right); dashed "uses" and code edges never do
    const solid = inner.map((e) => { const k = visibleKinds(e, filter); return !!k.flow && !e.dash; });
    let ord, dag;
    const succ = nodesIn.map(() => []), pred = nodesIn.map(() => []);
    const layer = new Array(N).fill(0);
    if (solid.some(Boolean)) {
      ranked = true;
      const back = flowBack(nodesIn, pairs, solid, inner);
      ord = flowOrder(core, pairs, solid, back);
      pairs.forEach(([a, b], k) => { if (solid[k] && !back.has(k) && a !== b) { succ[a].push(b); pred[b].push(a); } });
      for (const v of ord) for (const w of succ[v]) layer[w] = Math.max(layer[w], layer[v] + 1);
      dag = pairs.map(([a, b], k) => (solid[k] && !back.has(k) ? [a, b, false] : [b, a, true])); // provisional
      dag.solidBack = back;
    } else {
      const weight = (e) => { const k = visibleKinds(e, filter); return k.flow ? 4 : k.dep ? 2 : k.inherit ? 1.5 : 1; };
      ord = greedyOrder(nodesIn.map((n) => n.id), inner.map((e, i) => [...pairs[i], weight(e)])).filter((v) => !iso.has(v));
      const pos = new Array(N); ord.forEach((v, i) => { pos[v] = i; });
      dag = pairs.map(([a, b]) => (pos[a] < pos[b] ? [a, b, false] : [b, a, true]));
      // longest-path layering in the FAS order (a topological order of the DAG)
      for (const [a, b] of dag) { succ[a].push(b); pred[b].push(a); }
      for (const v of ord) for (const w of succ[v]) layer[w] = Math.max(layer[w], layer[v] + 1);
    }
    // promotion: pull each vertex right next to its nearest successor
    for (let i = ord.length - 1; i >= 0; i--) {
      const v = ord[i];
      if (!succ[v].length) continue;
      const lim = Math.min(...succ[v].map((w) => layer[w])) - 1;
      if (lim > layer[v]) layer[v] = lim;
    }
    // layer width cap
    const cap = Math.ceil(1.5 * Math.sqrt(N));
    for (let L = 0; L <= Math.max(0, ...core.map((v) => layer[v])); L++) {
      let members = core.filter((v) => layer[v] === L);
      while (members.length > cap) {
        const can = members.filter((v) => succ[v].every((w) => layer[w] >= L + 2))
          .sort((a, b) => (succ[a].length + pred[a].length) - (succ[b].length + pred[b].length) || byStr(nodesIn[b].id, nodesIn[a].id));
        if (!can.length) break;
        layer[can[0]] = L + 1;
        members = members.filter((v) => v !== can[0]);
      }
    }
    if (Math.max(0, ...core.map((v) => layer[v])) + 1 > Math.max(12, 2 * cap)) return false;
    if (dag.solidBack) { // a non-ranking edge runs forward through the layers, else as an arc like a back edge
      const back = dag.solidBack;
      dag = pairs.map(([a, b], k) => (solid[k] ? (back.has(k) ? [b, a, true] : [a, b, false])
        : layer[a] < layer[b] ? [a, b, false] : [b, a, true]));
    }
    // vertices: real nodes then waypoints for spans > 1 (back edges are arcs, not waypoints)
    const V = nodesIn.map((n, i) => ({ real: i, L: layer[i], h: size[i].h, key: n.id, skip: iso.has(i) }));
    const down = V.map(() => []), up = V.map(() => []);
    dag.forEach(([a, b, back], k) => {
      const e = inner[k];
      if (back) { arcs.push({ e, s: ix.get(e.s), t: ix.get(e.t) }); return; }
      const chain = [a];
      let prev = a;
      for (let L = layer[a] + 1; L < layer[b]; L++) {
        const d = V.length;
        V.push({ real: -1, L, h: 2, key: `${e.id}~${L}` }); down.push([]); up.push([]);
        down[prev].push(d); up[d].push(prev); chain.push(d); prev = d;
      }
      down[prev].push(b); up[b].push(prev); chain.push(b);
      chains.set(e.id, chain);
    });
    const nL = Math.max(...V.filter((v) => !v.skip).map((v) => v.L)) + 1;
    let layers = Array.from({ length: nL }, () => []);
    V.forEach((v, i) => { if (!v.skip) layers[v.L].push(i); });
    for (const l of layers) l.sort((a, b) => byStr(V[a].key, V[b].key));
    const P = new Float64Array(V.length);
    const setPos = () => { for (const l of layers) l.forEach((v, i) => { P[v] = i; }); };
    setPos();
    let best = layers.map((l) => l.slice()), bestC = countCross(layers, down);
    const bary = (v, nb) => (nb.length ? nb.reduce((s2, w) => s2 + P[w], 0) / nb.length : P[v]);
    const transpose = (l, L) => {
      for (let pass = 0, improved = true; improved && pass < 4; pass++) {
        improved = false;
        for (let i = 0; i + 1 < l.length; i++) {
          const u = l[i], v = l[i + 1];
          let c0 = 0, c1 = 0;
          if (L > 0) { c0 += pairCross(up[u], up[v], P); c1 += pairCross(up[v], up[u], P); }
          if (L + 1 < nL) { c0 += pairCross(down[u], down[v], P); c1 += pairCross(down[v], down[u], P); }
          if (c1 < c0) { l[i] = v; l[i + 1] = u; P[v] = i; P[u] = i + 1; improved = true; }
        }
      }
    };
    const big = V.length > 900;
    for (let sweep = 0; sweep < (big ? 6 : 12) && bestC > 0; sweep++) {
      const downward = sweep % 2 === 0;
      const seq = downward ? [...Array(nL).keys()].slice(1) : [...Array(nL).keys()].reverse().slice(1);
      for (const L of seq) {
        const l = layers[L];
        const bc = new Map(l.map((v) => [v, bary(v, downward ? up[v] : down[v])]));
        l.sort((a, b) => bc.get(a) - bc.get(b) || P[a] - P[b]);
        l.forEach((v, i) => { P[v] = i; });
      }
      if (!big) for (let L = 0; L < nL; L++) transpose(layers[L], L);
      const c = countCross(layers, down);
      if (c < bestC) { bestC = c; best = layers.map((l) => l.slice()); }
    }
    layers = best; setPos();
    // x: columns, gap wide enough for the widest label crossing it
    const colW = layers.map((l) => Math.max(0, ...l.map((v) => (V[v].real >= 0 ? size[V[v].real].w : 0))));
    const gapW = new Array(nL).fill(0);
    for (const e of inner) {
      const ch = chains.get(e.id); if (!ch) continue;
      const lw = labelW(e);
      for (let i = 0; i + 1 < ch.length; i++) gapW[V[ch[i]].L] = Math.max(gapW[V[ch[i]].L], lw);
    }
    const colX = [0];
    for (let L = 1; L < nL; L++) colX[L] = colX[L - 1] + colW[L - 1] + clamp(gapW[L - 1] + 40, 88, LABEL_MAX + 72);
    const shiftX = new Float64Array(nL);
    const cx = (v) => colX[V[v].L] + shiftX[V[v].L] + colW[V[v].L] / 2;
    // y: priority placement, 4 sweeps
    const Y = new Float64Array(V.length);
    for (const l of layers) {
      const tot = l.reduce((s2, v) => s2 + V[v].h, 0) + GAP_Y * Math.max(0, l.length - 1);
      let y = -tot / 2;
      for (const v of l) { Y[v] = y; y += V[v].h + GAP_Y; }
    }
    const gapOf = (l) => l.slice(0, -1).map((v, i) => (V[v].real < 0 || V[l[i + 1]].real < 0 ? GAP_DUMMY : GAP_Y));
    for (let sweep = 0; sweep < 4; sweep++) {
      const downward = sweep % 2 === 0;
      const seq = downward ? [...Array(nL).keys()].slice(1) : [...Array(nL).keys()].reverse().slice(1);
      for (const L of seq) {
        const l = layers[L];
        const hs = l.map((v) => V[v].h);
        const want = l.map((v) => {
          const nb = downward ? up[v] : down[v];
          return nb.length ? nb.reduce((s2, w) => s2 + Y[w] + V[w].h / 2, 0) / nb.length : Y[v] + V[v].h / 2;
        });
        const prio = l.map((v) => (V[v].real < 0 ? 3 : 1 + 0.5 * (up[v].length + down[v].length)));
        const ys = placeLayer(hs, gapOf(l), want, prio);
        l.forEach((v, i) => { Y[v] = ys[i]; });
      }
    }
    if (aspect > 0 && nL >= 3 && !ranked) wrap = wrapBands(V, Y, nL, colX, colW, layer, shiftX); // a drawn pipeline stays one row
    V.forEach((v, i) => {
      if (v.skip) return;
      if (v.real >= 0) { const s2 = size[v.real]; rect[v.real] = { x: cx(i) - s2.w / 2, y: Y[i], w: s2.w, h: s2.h }; layerOf[v.real] = v.L; }
      v.cx = cx(i); v.cy = Y[i] + v.h / 2; v.hw = colW[v.L] / 2;
    });
    for (const [id, ch] of chains) chains.set(id, ch.map((v) => V[v]));
    return true;
  }

  // ---- frame box: nodes (+ back-edge arcs above), padded; then translate so it starts at 0,0
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const r of rect) { x0 = Math.min(x0, r.x); y0 = Math.min(y0, r.y); x1 = Math.max(x1, r.x + r.w); y1 = Math.max(y1, r.y + r.h); }
  if (!N) { x0 = y0 = 0; x1 = 320; y1 = 160; }
  // back edges arc above, or below when blocks stack above both ends
  const stacked = (r, dir) => rect.reduce((c, q) => c + (q !== r && q.x < r.x + r.w && q.x + q.w > r.x && (dir < 0 ? q.y + q.h <= r.y : q.y >= r.y + r.h) ? 1 : 0), 0);
  if (wrap && wrap.cross.size) { x0 -= 8 * wrap.lanes; x1 = Math.max(x1, wrap.gutter + 8 * wrap.lanes); }
  for (const a of arcs) {
    const rs = rect[a.s], rt = rect[a.t];
    const lo = Math.min(rs.x, rt.x), hi = Math.max(rs.x + rs.w, rt.x + rt.w);
    const near = wrap ? rect.filter((r, i) => wrap.nodeBand[i] === wrap.nodeBand[a.s]) : rect; // its own band
    a.side = wrap ? (wrap.nodeBand[a.s] === 0 ? 't' : 'b') : stacked(rs, -1) + stacked(rt, -1) <= stacked(rs, 1) + stacked(rt, 1) ? 't' : 'b';
    const lift = 30 + Math.min(80, 0.06 * (hi - lo));
    if (a.side === 't') {
      let top = Math.min(rs.y, rt.y);
      for (const r of near) if (r.x < hi && r.x + r.w > lo) top = Math.min(top, r.y);
      a.apex = top - lift; y0 = Math.min(y0, a.apex - 8);
    } else {
      let bot = Math.max(rs.y + rs.h, rt.y + rt.h);
      for (const r of near) if (r.x < hi && r.x + r.w > lo) bot = Math.max(bot, r.y + r.h);
      a.apex = bot + lift; y1 = Math.max(y1, a.apex + 8);
    }
  }
  const dx = pinned ? 0 : PAD.x - x0, dy = pinned ? 0 : PAD.top - y0;
  const W = Math.max(pinned ? x1 + PAD.x : x1 - x0 + 2 * PAD.x, 240), H = Math.max(pinned ? y1 + PAD.bottom : y1 - y0 + PAD.top + PAD.bottom, 160);
  for (const r of rect) { r.x = Math.round(r.x + dx); r.y = Math.round(r.y + dy); }
  for (const a of arcs) a.apex += dy;
  for (const ch of chains.values()) for (const v of ch) { v.X = v.cx + dx; v.Y = v.cy + dy; }

  // ---- ghosts: in → left column, out → right column, both → top row; ordered by their peers' barycentre
  const gpeers = ghostsIn.map(() => []);
  for (const e of edges) {
    if (gix.has(e.s) && ix.has(e.t)) gpeers[gix.get(e.s)].push(ix.get(e.t));
    if (gix.has(e.t) && ix.has(e.s)) gpeers[gix.get(e.t)].push(ix.get(e.s));
  }
  const grect = new Array(ghostsIn.length);
  for (const side of ['in', 'out', 'both']) {
    const gs = ghostsIn.map((g, i) => i).filter((i) => (ghostsIn[i].side || 'out') === side || (side === 'out' && !['in', 'both'].includes(ghostsIn[i].side)));
    if (!gs.length) continue;
    const sz = gs.map((i) => swap(ghostSize(ghostsIn[i], measure, level.crumbs)));
    const horiz = side === 'both';
    const want = gs.map((i) => {
      const ps = gpeers[i];
      if (!ps.length) return horiz ? W / 2 : H / 2;
      return ps.reduce((s, p) => s + (horiz ? rect[p].x + rect[p].w / 2 : rect[p].y + rect[p].h / 2), 0) / ps.length;
    });
    const order = gs.map((_, k) => k).sort((a, b) => want[a] - want[b] || byStr(ghostsIn[gs[a]].id, ghostsIn[gs[b]].id));
    const hs = order.map((k) => (horiz ? sz[k].w : sz[k].h));
    const ys = placeLayer(hs, hs.map(() => (horiz ? 16 : 12)), order.map((k) => want[k]), order.map(() => 1));
    order.forEach((k, j) => {
      const s = sz[k], i = gs[k];
      if (side === 'in') grect[i] = { x: -GHOST_GAP - s.w, y: Math.round(ys[j]), ...s, side };
      else if (side === 'out') grect[i] = { x: W + GHOST_GAP, y: Math.round(ys[j]), ...s, side };
      else grect[i] = { x: Math.round(ys[j]), y: -GHOST_GAP + 14 - s.h, ...s, side };
    });
  }

  // ---- ports and routes
  const ends = new Map(); // "n:i" | "g:i" → [port requests]
  const req = (key, rr, side, far, eid, which) => {
    const p = { side, far, key: eid + which, pt: null };
    (ends.get(key) || ends.set(key, { rect: rr, list: [] }).get(key)).list.push(p);
    return p;
  };
  const centre = (r) => [r.x + r.w / 2, r.y + r.h / 2];
  const plans = [];
  for (const e of edges) {
    const si = ix.get(e.s), ti = ix.get(e.t), sg = gix.get(e.s), tg = gix.get(e.t);
    const rs = si !== undefined ? rect[si] : grect[sg], rt = ti !== undefined ? rect[ti] : grect[tg];
    const ks = si !== undefined ? `n:${si}` : `g:${sg}`, kt = ti !== undefined ? `n:${ti}` : `g:${tg}`;
    const [sx, sy] = centre(rs), [tx, ty] = centre(rt);
    const arc = arcs.find((a) => a.e === e), cr = wrap && wrap.cross.get(e.id);
    if (cr && cr.direct === undefined) cr.direct = Math.abs(cr.bt - cr.bs) === 1 && facesGap(si, cr.bt > cr.bs) && facesGap(ti, cr.bt < cr.bs);
    let ss, ts;
    if (arc) { ss = arc.side; ts = arc.side; }
    else if (cr && cr.direct) { ss = cr.bt > cr.bs ? 'b' : 't'; ts = cr.bt > cr.bs ? 't' : 'b'; }
    else if (sg !== undefined || tg !== undefined) {
      const g = grect[sg !== undefined ? sg : tg];
      if (g.side === 'both') {
        ss = sg !== undefined ? 'b' : 't'; ts = tg !== undefined ? 'b' : 't';
        const ni = si !== undefined ? si : ti; // wrapped: leave from the side unless the block looks straight up at the row
        if (wrap && !(wrap.nodeBand[ni] === 0 && facesGap(ni, false))) { if (si !== undefined) ss = 'r'; else ts = 'r'; }
      }
      else if (g.side === 'in') { ss = sg !== undefined ? 'r' : 'l'; ts = tg !== undefined ? 'r' : 'l'; }
      else { ss = sg !== undefined ? 'l' : 'r'; ts = tg !== undefined ? 'l' : 'r'; }
    } else if (mode === 'layered') { ss = 'r'; ts = 'l'; }
    else {
      const ddx = tx - sx, ddy = ty - sy;
      if (Math.abs(ddx) * 0.7 >= Math.abs(ddy) - (rs.h + rt.h) / 2) { ss = ddx >= 0 ? 'r' : 'l'; ts = ddx >= 0 ? 'l' : 'r'; }
      else { ss = ddy >= 0 ? 'b' : 't'; ts = ddy >= 0 ? 't' : 'b'; }
    }
    const ch = chains.get(e.id);
    if (cr && cr.direct) { plans.push({ e, arc, ch, ps: req(ks, rs, ss, tx, e.id, 's'), pt: req(kt, rt, ts, sx, e.id, 't'), ss, ts }); continue; }
    const farS = ch && ch.length > 2 ? (ss === 'r' || ss === 'l' ? ch[1].Y : ch[1].X) : (ss === 'r' || ss === 'l' ? ty : tx);
    const farT = ch && ch.length > 2 ? (ts === 'r' || ts === 'l' ? ch[ch.length - 2].Y : ch[ch.length - 2].X) : (ts === 'r' || ts === 'l' ? sy : sx);
    plans.push({ e, arc, ch, ps: req(ks, rs, ss, farS, e.id, 's'), pt: req(kt, rt, ts, farT, e.id, 't'), ss, ts });
  }
  for (const { rect: rr, list } of ends.values()) spreadPorts(list, rr);
  /** A direct route that crosses a block bends around it (above or below, whichever is nearer). */
  function detour(pts, a, b, d0, d1, e) {
    const skip = new Set([ix.get(e.s), ix.get(e.t)]);
    const way = [];
    for (let iter = 0; iter < 4; iter++) {
      const hit = crossing(pts, skip);
      if (!hit) break;
      const r = rect[hit.i];
      const up = r.y - 18, down = r.y + r.h + 18;
      const y = Math.abs(hit.y - up) <= Math.abs(hit.y - down) ? up : down;
      way.push([r.x + r.w / 2, y]);
      skip.add(hit.i);
      const dir = Math.sign(b[0] - a[0]) || 1;
      way.sort((p, q) => (p[0] - q[0]) * dir);
      pts = spline([a, ...way, b], d0, d1);
    }
    return pts;
  }
  /** Side ports (ghost edges, shelf edges): level bump curves that pass above or below every block in the way. */
  function bumpDetour(a, b, e) {
    const skip = new Set([ix.get(e.s), ix.get(e.t)]);
    const lo = Math.min(a[0], b[0]) + 1, hi = Math.max(a[0], b[0]) - 1, dir = Math.sign(b[0] - a[0]) || 1;
    const way = [];
    let pts = bumps([a, b]);
    for (let iter = 0; iter < 10; iter++) {
      const hit = crossing(pts, skip);
      if (!hit) break;
      const r = rect[hit.i];
      const yOut = hit.y < r.y + r.h / 2 ? r.y - 12 : r.y + r.h + 12;
      for (const x of [r.x - 10, r.x + r.w + 10]) way.push([clamp(x, lo, hi), yOut]);
      skip.add(hit.i);
      way.sort((p, q) => (p[0] - q[0]) * dir || p[1] - q[1]);
      pts = bumps([a, ...way, b]);
    }
    return pts;
  }
  function crossing(pts, skip) {
    let bx0 = Infinity, by0 = Infinity, bx1 = -Infinity, by1 = -Infinity;
    for (const q of pts) { bx0 = Math.min(bx0, q[0]); bx1 = Math.max(bx1, q[0]); by0 = Math.min(by0, q[1]); by1 = Math.max(by1, q[1]); }
    const near = [];
    for (let i = 0; i < rect.length; i++) {
      const r = rect[i];
      if (!skip.has(i) && r.x - 3 < bx1 && r.x + r.w + 3 > bx0 && r.y - 3 < by1 && r.y + r.h + 3 > by0) near.push(i);
    }
    if (!near.length) return null;
    for (let j = 0; j + 3 < pts.length; j += 3) {
      for (let s2 = 1; s2 < 40; s2++) {
        const t = s2 / 40, u = 1 - t;
        const x = u * u * u * pts[j][0] + 3 * u * u * t * pts[j + 1][0] + 3 * u * t * t * pts[j + 2][0] + t * t * t * pts[j + 3][0];
        const y = u * u * u * pts[j][1] + 3 * u * u * t * pts[j + 1][1] + 3 * u * t * t * pts[j + 2][1] + t * t * t * pts[j + 3][1];
        for (const i of near) {
          const r = rect[i];
          if (x > r.x - 3 && x < r.x + r.w + 3 && y > r.y - 3 && y < r.y + r.h + 3) return { i, x, y }; // grazing counts
        }
      }
    }
    return null;
  }

  /** True when nothing of its own band stands between block i and the gap below (down) or above it. */
  function facesGap(i, down) {
    const r = rect[i], b = wrap.nodeBand[i];
    return !rect.some((q, j) => j !== i && wrap.nodeBand[j] === b && q.x < r.x + r.w - 4 && q.x + q.w > r.x + 4
      && (down ? q.y >= r.y + r.h : q.y + q.h <= r.y));
  }
  /** Between bands: straight across the gap when both ends face it, else out of the source's lane, along the gap (and the right gutter past other bands), into the target's lane. */
  function crossRoute(e, a, b) {
    const { g1, g2 } = wrap.cross.get(e.id), si = ix.get(e.s), ti = ix.get(e.t);
    const k1 = wrap.slot.get(e.id + '|' + g1), k2 = wrap.slot.get(e.id + '|' + g2);
    const gy = (g, k) => wrap.gapMid[g] + ((k % RUNS) - (Math.min(wrap.cnt[g], RUNS) - 1) / 2) * 10 + dy;
    // edges sharing a gap put their labels at different points along it: (k + 1) / (n + 1)
    const stagger = (o, lab) => (lab >= 0 && wrap.cnt[g1] > 1 ? splitAt(o.pts, lab, (k1 + 1) / (wrap.cnt[g1] + 1)) : { pts: o.pts, lab });
    if (wrap.cross.get(e.id).direct) {
      const o = ortho([a, [a[0], gy(g1, k1)], [b[0], gy(g1, k1)], b]);
      return stagger(o, o.P.length === 4 ? o.seg[1] : -1);
    }
    const xs = wrap.lane(wrap.layer[si], 1, k1) + dx, xt = wrap.lane(wrap.layer[ti], -1, k2) + dx;
    const P = [a, [xs, a[1]], [xs, gy(g1, k1)]];
    if (g1 !== g2) { const xr = wrap.gutter + 8 * (k1 % LANES) + dx; P.push([xr, gy(g1, k1)], [xr, gy(g2, k2)]); }
    P.push([xt, gy(g2, k2)], [xt, b[1]], b);
    const o = ortho(P);
    let lab = -1, best = -1; // the label sits on the widest run along a gap (not the stubs at either end)
    for (let j = 1; j + 2 < o.P.length; j++) {
      const w = Math.abs(o.P[j + 1][0] - o.P[j][0]);
      if (Math.abs(o.P[j + 1][1] - o.P[j][1]) < 0.5 && w > best) { best = w; lab = o.seg[j]; }
    }
    return stagger(o, lab);
  }
  /** Wrapped bands: a ghost edge that would pass behind a block leaves through the block's lane, runs along
   *  its band's nearer edge and then the outer gutter to the ghost's column. null for a top-row ghost. */
  function ghostRoute(e, a, b, ss, ts) {
    const nodeIsS = ix.has(e.s), i = ix.get(nodeIsS ? e.s : e.t), side = nodeIsS ? ss : ts;
    if (i === undefined || !'lr'.includes(side)) return null;
    const pn = nodeIsS ? a : b, pg = nodeIsS ? b : a, r = rect[i], bd = wrap.nodeBand[i], out = side === 'r';
    const row = (nodeIsS ? ts : ss) === 'b'; // a top-row ghost: up the gutter, then across above the frame
    const xl = wrap.lane(wrap.layer[i], out ? 1 : -1, 0) + dx;
    const t0 = wrap.top[bd] + dy, b0 = wrap.bot[bd] + dy, cy = r.y + r.h / 2;
    const yb = row || cy - t0 <= b0 - cy ? t0 - 14 : b0 + 14;
    const xg = (out ? wrap.gutter + 8 * wrap.lanes + 12 : -32 - 8 * wrap.lanes) + dx;
    const P = row ? [pn, [xl, pn[1]], [xl, yb], [xg, yb], [xg, pg[1] + 16], [pg[0], pg[1] + 16], pg]
      : [pn, [xl, pn[1]], [xl, yb], [xg, yb], [xg, pg[1]], pg];
    return ortho(nodeIsS ? P : P.reverse()).pts;
  }
  /** Split straight cubic c of pts so a piece is centred at fraction f of it; lab names that piece. */
  function splitAt(pts, c, f) {
    const p = pts[3 * c], q = pts[3 * c + 3], at = (t) => [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t];
    const m = f <= 0.5 ? 2 * f : 2 * f - 1, piece = (t0, t1) => [at(t0 + (t1 - t0) / 3), at(t0 + (2 * (t1 - t0)) / 3), at(t1)];
    if (m <= 0.02 || m >= 0.98) return { pts, lab: c };
    const r = (z) => [Math.round(z[0] * 10) / 10, Math.round(z[1] * 10) / 10];
    const out = pts.slice(0, 3 * c + 1).concat([...piece(0, m), ...piece(m, 1)].map(r), pts.slice(3 * c + 4));
    return { pts: out, lab: f <= 0.5 ? c : c + 1 };
  }

  const outEdges = {};
  for (const p of plans) {
    const a = p.ps.pt, b = p.pt.pt;
    let pts;
    if (p.arc) {
      const Yc = (8 * p.arc.apex - a[1] - b[1]) / 6;
      pts = [a, [a[0], Yc], [b[0], Yc], b].map(([x, y]) => [Math.round(x * 10) / 10, Math.round(y * 10) / 10]);
    } else if (wrap && wrap.cross.has(p.e.id)) {
      outEdges[p.e.id] = { ...crossRoute(p.e, a, b), back: wrap.back.has(p.e.id) };
      continue;
    } else if (p.ch && p.ch.length >= 2 && p.ss === 'r' && p.ts === 'l' && b[0] > a[0]) {
      // layered: run level through each column (the block's own row, or the waypoint's free slot) and
      // bend only in the empty gaps between columns, so a route never passes behind a block
      const P = [a], gap = [];
      const add = (q, inGap) => {
        const l = P[P.length - 1];
        if (Math.abs(q[0] - l[0]) < 0.5 && Math.abs(q[1] - l[1]) < 0.5) return;
        if (q[0] < l[0]) q = [l[0], q[1]];
        gap.push(inGap); P.push(q);
      };
      const s0 = p.ch[0], t0 = p.ch[p.ch.length - 1];
      add([Math.max(a[0], s0.X + s0.hw), a[1]], false);
      for (const v of p.ch.slice(1, -1)) { add([v.X - v.hw, v.Y], true); add([v.X + v.hw, v.Y], false); }
      add([Math.min(b[0], t0.X - t0.hw), b[1]], true);
      add(b, false);
      pts = bumps(P);
      let lab = -1, best = -1;
      gap.forEach((g, k) => { const w = P[k + 1][0] - P[k][0]; if (g && w > best) { best = w; lab = k; } });
      outEdges[p.e.id] = lab >= 0 ? { pts, back: false, lab } : { pts, back: false };
      continue;
    } else {
      const mid = p.ch && p.ch.length > 2 ? p.ch.slice(1, -1).map((v) => [v.X, v.Y]) : [];
      const d0 = SIDE_DIR[p.ss], d1 = SIDE_DIR[p.ts].map((d) => -d);
      if (!mid.length && 'lr'.includes(p.ss) && 'lr'.includes(p.ts)) {
        pts = bumpDetour(a, b, p.e);
        if (wrap && crossing(pts, new Set([ix.get(p.e.s), ix.get(p.e.t)]))) pts = ghostRoute(p.e, a, b, p.ss, p.ts) || pts;
      }
      else {
        pts = spline([a, ...mid, b], d0, d1);
        if (!mid.length && rect.length > 1) pts = detour(pts, a, b, d0, d1, p.e); // a ghost edge can cross the only other block
        if (wrap && !mid.length && crossing(pts, new Set([ix.get(p.e.s), ix.get(p.e.t)]))) pts = ghostRoute(p.e, a, b, p.ss, p.ts) || pts;
      }
    }
    outEdges[p.e.id] = { pts, back: !!p.arc };
  }

  const nodes = {}, ghosts = {};
  nodesIn.forEach((n, i) => { nodes[n.id] = { ...rect[i], L: layerOf[i] }; });
  ghostsIn.forEach((g, i) => { ghosts[g.id] = grect[i] || { x: W + GHOST_GAP, y: 0, w: 110, h: 30, side: 'out' }; });
  const order = nodesIn.map((n) => n.id).sort((a, b) => nodes[a].L - nodes[b].L || nodes[a].y - nodes[b].y || nodes[a].x - nodes[b].x || byStr(a, b));
  return { w: Math.round(W), h: Math.round(H), mode, dir: 'LR', nodes, ghosts, edges: outEdges, order };
}

// ---------------------------------------------------------------- open area boxes

const AREA_TITLE = 56;   // the boundary's title band (inside PAD.top), kept free of edges
const CELL = 8;          // router grid, world units
const CLEAR = 6;         // routes keep this far from blocks

/**
 * A level whose nodes carry `area` (the root of the Systems lens): each area is an open box laid out like a
 * level of its own (members flow left to right inside), the boxes and the loose nodes are laid out as one
 * level around them, and every edge joins the real blocks. Edges inside one box keep that box's routes; an
 * edge between boxes is routed on a grid around every block, title band and foreign box.
 * → layoutLevel's result plus areas:{id:{x,y,w,h,title,name}}.
 */
function layoutAreas(level, measure, filter, aspect, room) {
  const nodesIn = (level.nodes || []).slice().sort((a, b) => byStr(a.id, b.id));
  const areasIn = level.areas.slice().sort((a, b) => byStr(a.id, b.id));
  const areaOf = new Map(), byId = new Map(nodesIn.map((n) => [n.id, n]));
  for (const a of areasIn) for (const m of a.members || []) if (byId.has(m)) areaOf.set(m, a.id);
  const edges = (level.edges || []).filter((e) => Object.keys(visibleKinds(e, filter)).length && e.s !== e.t)
    .sort((a, b) => byStr(a.id, b.id));
  // 1. each area on its own
  const sub = new Map();
  for (const a of areasIn) {
    const mem = nodesIn.filter((n) => areaOf.get(n.id) === a.id);
    if (!mem.length) continue;
    const ids = new Set(mem.map((n) => n.id));
    sub.set(a.id, layoutFlat({ nodes: mem, ghosts: [], edges: edges.filter((e) => ids.has(e.s) && ids.has(e.t)) },
      measure, filter, aspect ? Math.max(1, aspect * 0.75) : 0, room));
  }
  // 2. boxes and loose nodes as one level (edges lifted to the boxes, for ordering and gaps only)
  const box = (id) => (areaOf.has(id) ? 'area:' + areaOf.get(id) : id);
  const top = nodesIn.filter((n) => !areaOf.has(n.id));
  for (const a of areasIn) { const l = sub.get(a.id); if (l) top.push({ id: 'area:' + a.id, type: 'group', name: a.title, box: { w: l.w, h: l.h } }); }
  const lifted = new Map();
  for (const e of edges) {
    const s = box(e.s), t = box(e.t);
    if (s === t || !(byId.has(e.s) || e.s.startsWith('ghost:')) || !(byId.has(e.t) || e.t.startsWith('ghost:'))) continue;
    const id = `${s}>${t}`, g = lifted.get(id);
    if (g) { g.n += e.n || 1; continue; }
    lifted.set(id, { id, s, t, kinds: { flow: 1 }, n: e.n || 1, dash: !!e.dash, labels: e.labels && e.labels.length ? [e.labels[0]] : [] });
  }
  const sup = layoutFlat({ nodes: top, ghosts: level.ghosts || [], edges: [...lifted.values()] },
    measure, { kinds: new Set(['flow']), minConf: 0 }, aspect, room);
  // 3. compose
  const nodes = {}, areas = {}, outEdges = {};
  for (const a of areasIn) {
    const l = sub.get(a.id), r = sup.nodes['area:' + a.id];
    if (!l || !r) continue;
    areas[a.id] = { x: r.x, y: r.y, w: r.w, h: r.h, title: a.title, name: a.name || a.title, L: r.L };
    for (const [id, q] of Object.entries(l.nodes)) nodes[id] = { ...q, x: q.x + r.x, y: q.y + r.y, L: r.L };
    for (const [id, q] of Object.entries(l.edges)) outEdges[id] = { ...q, pts: q.pts.map(([x, y]) => [x + r.x, y + r.y]) };
  }
  for (const n of nodesIn) if (!areaOf.has(n.id) && sup.nodes[n.id]) nodes[n.id] = sup.nodes[n.id];
  const ghosts = sup.ghosts;
  for (const e of edges) { // loose ↔ loose (and ghosts): the outer layout's own route
    if (outEdges[e.id] || areaOf.has(e.s) || areaOf.has(e.t)) continue;
    if (sup.edges[e.id]) outEdges[e.id] = sup.edges[e.id];
  }
  const W = sup.w, H = sup.h;
  const router = gridRouter(W, H, nodes, areas, ghosts);
  const rest = edges.filter((e) => !outEdges[e.id] && (nodes[e.s] || ghosts[e.s]) && (nodes[e.t] || ghosts[e.t]));
  // ports: each block's ends spread along the side they use, ordered by where the far end is
  const ends = new Map();
  const plan = rest.map((e) => {
    const a = nodes[e.s] || ghosts[e.s], b = nodes[e.t] || ghosts[e.t];
    const [ss, ts] = sidesOf(a, b);
    const ps = { side: ss, far: 'lr'.includes(ss) ? b.y + b.h / 2 : b.x + b.w / 2, key: e.id };
    const pt = { side: ts, far: 'lr'.includes(ts) ? a.y + a.h / 2 : a.x + a.w / 2, key: e.id };
    (ends.get(e.s) || ends.set(e.s, []).get(e.s)).push(ps);
    (ends.get(e.t) || ends.set(e.t, []).get(e.t)).push(pt);
    return { e, ps, pt };
  });
  for (const [id, list] of [...ends.entries()].sort((x, y) => byStr(x[0], y[0]))) spreadPorts(list, nodes[id] || ghosts[id]);
  for (const p of plan) {
    const r = router(p.e, p.ps, p.pt, areaOf.get(p.e.s), areaOf.get(p.e.t));
    if (r) outEdges[p.e.id] = r;
  }
  const order = Object.keys(nodes).sort((a, b) => nodes[a].L - nodes[b].L || nodes[a].y - nodes[b].y || nodes[a].x - nodes[b].x || byStr(a, b));
  return { w: Math.round(W), h: Math.round(H), mode: 'areas', dir: 'LR', nodes, ghosts, edges: outEdges, order, areas, areaOf };
}

/** True when a route passes through a block other than its own two ends. */
function throughBlock(pts, rects, skip) {
  for (let i = 0; i + 3 < pts.length; i += 3) {
    for (let s = 1; s < 12; s++) {
      const t = s / 12, u = 1 - t, a = u * u * u, b = 3 * u * u * t, c = 3 * u * t * t, d = t * t * t;
      const x = a * pts[i][0] + b * pts[i + 1][0] + c * pts[i + 2][0] + d * pts[i + 3][0];
      const y = a * pts[i][1] + b * pts[i + 1][1] + c * pts[i + 2][1] + d * pts[i + 3][1];
      for (const [id, q] of rects) if (!skip.has(id) && x > q.x + 2 && x < q.x + q.w - 2 && y > q.y + 2 && y < q.y + q.h - 2) return true;
    }
  }
  return false;
}

/** Last pass, any LR layout: an edge that runs behind a block is re-routed on the grid from its own ports. */
function unblock(lay, level, filter) {
  const rects = Object.entries(lay.nodes).sort((a, b) => byStr(a[0], b[0]));
  const ids = Object.keys(lay.edges).sort(byStr).filter((id) => {
    const e = (level.edges || []).find((x) => x.id === id);
    return e && throughBlock(lay.edges[id].pts, rects, new Set([e.s, e.t]));
  });
  if (!ids.length) { delete lay.areaOf; return lay; }
  const router = gridRouter(lay.w, lay.h, lay.nodes, lay.areas || {}, lay.ghosts);
  const sideAt = (r, p) => {
    const d = [[Math.abs(p[0] - (r.x + r.w)), 'r'], [Math.abs(p[0] - r.x), 'l'], [Math.abs(p[1] - r.y), 't'], [Math.abs(p[1] - (r.y + r.h)), 'b']];
    return d.sort((a, b) => a[0] - b[0])[0][1];
  };
  const areaOf = lay.areaOf || new Map();
  for (const id of ids) {
    const e = level.edges.find((x) => x.id === id), r = lay.edges[id], P = r.pts;
    const a = lay.nodes[e.s] || lay.ghosts[e.s], b = lay.nodes[e.t] || lay.ghosts[e.t];
    if (!a || !b) continue;
    const ps = { pt: P[0], side: sideAt(a, P[0]) }, pt = { pt: P[P.length - 1], side: sideAt(b, P[P.length - 1]) };
    const got = router(e, ps, pt, areaOf.get(e.s), areaOf.get(e.t));
    if (got && !throughBlock(got.pts, rects, new Set([e.s, e.t]))) lay.edges[id] = got;
  }
  delete lay.areaOf;
  return lay;
}

/** Which sides an edge leaves a and enters b by: facing sides, left/right unless the two overlap in x. */
function sidesOf(a, b) {
  if (b.x >= a.x + a.w) return ['r', 'l'];
  if (b.x + b.w <= a.x) return ['l', 'r'];
  return b.y >= a.y + a.h / 2 ? ['b', 't'] : ['t', 'b'];
}

/** A* on a CELL grid with a bend penalty; a route never passes a block, a title band or another area's box. */
function gridRouter(W, H, nodes, areas, ghosts) {
  const gw = Math.ceil(W / CELL) + 1, gh = Math.ceil(H / CELL) + 1, N = gw * gh;
  const hard = new Uint8Array(N), zone = new Int16Array(N).fill(-1), used = new Uint8Array(N);
  const aIds = Object.keys(areas).sort(byStr);
  const mark = (r, pad, fn) => { // the cells whose centre lies inside r grown by pad
    const x0 = Math.max(0, Math.ceil((r.x - pad) / CELL)), x1 = Math.min(gw - 1, Math.floor((r.x + r.w + pad) / CELL));
    const y0 = Math.max(0, Math.ceil((r.y - pad) / CELL)), y1 = Math.min(gh - 1, Math.floor((r.y + r.h + pad) / CELL));
    for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) fn(y * gw + x);
  };
  aIds.forEach((id, i) => { const a = areas[id]; mark(a, CLEAR, (c) => { zone[c] = i; }); mark({ x: a.x, y: a.y, w: a.w, h: AREA_TITLE }, 0, (c) => { hard[c] = 1; }); });
  for (const r of Object.values(nodes)) mark(r, CLEAR, (c) => { hard[c] = 1; });
  for (const r of Object.values(ghosts || {})) mark(r, CLEAR, (c) => { hard[c] = 1; });
  const cellOf = (x, y) => Math.max(0, Math.min(gh - 1, Math.round(y / CELL))) * gw + Math.max(0, Math.min(gw - 1, Math.round(x / CELL)));
  const DX = [1, 0, -1, 0], DY = [0, 1, 0, -1], SD = { r: 0, b: 1, l: 2, t: 3 };
  return (e, ps, pt, sa, ta) => {
    const okZone = new Set([sa, ta].filter(Boolean).map((id) => aIds.indexOf(id)));
    const free = (c) => !hard[c] && (zone[c] < 0 || okZone.has(zone[c]));
    const out = (p, side, d) => [p.pt[0] + DX[SD[side]] * d, p.pt[1] + DY[SD[side]] * d];
    const s0 = out(ps, ps.side, CLEAR + CELL), t0 = out(pt, pt.side, CLEAR + CELL);
    const S = cellOf(s0[0], s0[1]), T = cellOf(t0[0], t0[1]);
    const tx = T % gw, ty = (T / gw) | 0;
    // state = cell * 4 + heading; cost: 1 per cell, 4 per bend, 2 per cell another route already uses
    const g = new Float64Array(N * 4).fill(Infinity), from = new Int32Array(N * 4).fill(-1);
    const heap = [];
    const push = (st, f) => { heap.push([f, st]); let i = heap.length - 1; while (i > 0) { const j = (i - 1) >> 1; if (heap[j][0] < heap[i][0] || (heap[j][0] === heap[i][0] && heap[j][1] <= heap[i][1])) break; [heap[i], heap[j]] = [heap[j], heap[i]]; i = j; } };
    const pop = () => { const top = heap[0], last = heap.pop(); if (heap.length) { heap[0] = last; let i = 0; for (;;) { const l = 2 * i + 1, r = l + 1; let m = i; for (const c of [l, r]) if (c < heap.length && (heap[c][0] < heap[m][0] || (heap[c][0] === heap[m][0] && heap[c][1] < heap[m][1]))) m = c; if (m === i) break; [heap[i], heap[m]] = [heap[m], heap[i]]; i = m; } } return top; };
    const h = (c) => Math.abs((c % gw) - tx) + Math.abs(((c / gw) | 0) - ty);
    const sd = SD[ps.side];
    g[S * 4 + sd] = 0; push(S * 4 + sd, h(S));
    let end = -1, guard = 0;
    while (heap.length && guard++ < N * 8) {
      const [, st] = pop(), c = st >> 2, d = st & 3;
      if (c === T) { end = st; break; }
      const cx = c % gw, cy = (c / gw) | 0;
      for (let nd = 0; nd < 4; nd++) {
        if (nd === ((d + 2) & 3)) continue;
        const nx = cx + DX[nd], ny = cy + DY[nd];
        if (nx < 0 || ny < 0 || nx >= gw || ny >= gh) continue;
        const nc = ny * gw + nx;
        if (nc !== T && !free(nc)) continue;
        const ns = nc * 4 + nd, cost = g[st] + 1 + (nd !== d ? 4 : 0) + (used[nc] ? 2 : 0);
        if (cost < g[ns]) { g[ns] = cost; from[ns] = st; push(ns, cost + h(nc)); }
      }
    }
    if (end < 0) return null;
    const cells = [];
    for (let st = end; st >= 0; st = from[st]) cells.push(st >> 2);
    cells.reverse();
    for (const c of cells) used[c] = 1;
    const at = (c) => [(c % gw) * CELL, ((c / gw) | 0) * CELL];
    const P = [ps.pt];
    const horiz = (side) => side === 'l' || side === 'r';
    let pts = cells.map(at);
    // the first and last runs sit on the ports' own lines (the grid is coarser than the port spread)
    const snap = (list, port, side) => {
      const k = horiz(side) ? 1 : 0;
      let i = 0;
      while (i < list.length && Math.abs(list[i][k] - list[0][k]) < 0.5) i++;
      for (let j = 0; j < i; j++) list[j] = k ? [list[j][0], port[1]] : [port[0], list[j][1]];
    };
    snap(pts, ps.pt, ps.side);
    pts.reverse(); snap(pts, pt.pt, pt.side); pts.reverse();
    P.push(...pts, pt.pt);
    const o = ortho(P);
    let lab = 0, best = -1;
    for (let j = 0; j + 1 < o.P.length; j++) { const L = Math.hypot(o.P[j + 1][0] - o.P[j][0], o.P[j + 1][1] - o.P[j][1]); if (L > best) { best = L; lab = o.seg[j]; } }
    return { pts: o.pts, back: false, lab };
  };
}

// ---------------------------------------------------------------- base strips and finishing

const STRIP_H = 46, STRIP_GAP = 26;

/** layoutCore without the base blocks (shared vocabulary), which go full width in a strip under the drawing. */
function layoutFlat(level, measure, filter, aspect, room) {
  const base = (level.nodes || []).filter((n) => n.base).sort((a, b) => byStr(a.id, b.id));
  if (!base.length) return layoutCore(level, measure, null, filter, false, aspect, room);
  const ids = new Set(base.map((n) => n.id));
  const rest = { ...level, nodes: level.nodes.filter((n) => !ids.has(n.id)), edges: (level.edges || []).filter((e) => !ids.has(e.s) && !ids.has(e.t)) };
  const lay = rest.nodes.length ? layoutCore(rest, measure, null, filter, false, aspect, room)
    : { w: 240, h: PAD.top + PAD.bottom - STRIP_GAP, mode: 'shelf', dir: 'LR', nodes: {}, ghosts: {}, edges: {}, order: [] };
  const w = Math.max(lay.w - 2 * PAD.x, ...base.map((n) => nodeSize(n, measure).w));
  let y = lay.h - PAD.bottom + STRIP_GAP;
  for (const n of base) { lay.nodes[n.id] = { x: PAD.x, y, w, h: STRIP_H, L: 1e3, strip: true }; y += STRIP_H + 10; }
  lay.w = Math.max(lay.w, w + 2 * PAD.x);
  lay.h = y - 10 + PAD.bottom;
  lay.order = lay.order.concat(base.map((n) => n.id));
  return lay;
}

/** Every LR layout ends here: route the visible edges nothing routed yet (edges to a base strip) and re-route
 *  any edge that runs behind a block. */
function finish(lay, level, filter, measure) {
  const vis = (level.edges || []).filter((e) => e.s !== e.t && Object.keys(visibleKinds(e, filter)).length
    && !lay.edges[e.id] && (lay.nodes[e.s] || lay.ghosts[e.s]) && (lay.nodes[e.t] || lay.ghosts[e.t])).sort((a, b) => byStr(a.id, b.id));
  if (vis.length) {
    const router = gridRouter(lay.w, lay.h, lay.nodes, lay.areas || {}, lay.ghosts);
    const areaOf = lay.areaOf || new Map(), ends = new Map(), plan = [];
    for (const e of vis) {
      const a = lay.nodes[e.s] || lay.ghosts[e.s], b = lay.nodes[e.t] || lay.ghosts[e.t];
      const [ss, ts] = sidesOf(a, b);
      // a strip is entered right under (or above) the other end, not at its middle
      const ps = { side: ss, far: 'lr'.includes(ss) ? b.y + b.h / 2 : b.x + b.w / 2, key: e.id };
      const pt = { side: ts, far: 'lr'.includes(ts) ? a.y + a.h / 2 : a.x + a.w / 2, key: e.id };
      plan.push({ e, ps, pt, a, b });
      (ends.get(e.s) || ends.set(e.s, []).get(e.s)).push(ps);
      (ends.get(e.t) || ends.set(e.t, []).get(e.t)).push(pt);
    }
    for (const [id, list] of [...ends.entries()].sort((x, y) => byStr(x[0], y[0]))) spreadPorts(list, lay.nodes[id] || lay.ghosts[id]);
    for (const p of plan) {
      for (const [q, r, o] of [[p.ps, p.a, p.b], [p.pt, p.b, p.a]]) if (r.strip && 'tb'.includes(q.side)) q.pt = [clamp(o.x + o.w / 2, r.x + 12, r.x + r.w - 12), q.pt[1]];
      const got = router(p.e, p.ps, p.pt, areaOf.get(p.e.s), areaOf.get(p.e.t));
      if (got) lay.edges[p.e.id] = got;
    }
  }
  return unblock(lay, level, filter);
}
