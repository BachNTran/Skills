// wiki graph — the repo's docs as a 2D or 3D map. Lazy-loaded by app.js; ForceGraph3D is a global from vendor/.
// Look: glowing sprite nodes (shape = kind, colour = group), soft group nebulae, thin gradient arcs that
// fade with depth, and a neighbourhood focus on hover. Glow is faked with canvas textures (no bloom pass).
import * as THREE from './vendor/three.module.min.js';

const CALM = matchMedia('(prefers-reduced-motion: reduce)').matches;
const T = (ms) => (CALM ? 0 : ms);
const LIGHT = matchMedia('(prefers-color-scheme: light)').matches;
// Greens, teals, limes, ambers and warm neutrals only — never blue or purple.
const PALETTE = LIGHT
  ? ['#0f9b87', '#5f8f12', '#b07a10', '#2e9a56', '#8a7350', '#0e8a7a', '#76901a', '#a3611c', '#3d8f6a', '#6f7d3a']
  : ['#5eead4', '#a3e635', '#fbbf24', '#4ade80', '#e2c792', '#2dd4bf', '#d9f99d', '#f59e6b', '#86efac', '#c9b37e'];
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const el = (tag, props = {}) => Object.assign(document.createElement(tag), props);
const append = (node, kids) => { node.append(...kids); return node; };
const human = (g) => String(g).replace(/[_-]+/g, ' ').trim(); // group key → words (no folder spelling)
const KINDS = ['module', 'page', 'exhibit', 'figure'];
const SHAPES = { // legend glyphs, same silhouettes as the node sprites
  module: '<path d="M6 .6 11.4 6 6 11.4.6 6z"/>', page: '<circle cx="6" cy="6" r="4.8"/>',
  exhibit: '<rect x="1.3" y="1.3" width="9.4" height="9.4" rx="2"/>', figure: '<path d="M6 1 11.2 10.6H.8z"/>',
};
const ICON = {
  fit: '<path d="M2.5 6V2.5H6M10 2.5h3.5V6M13.5 10v3.5H10M6 13.5H2.5V10"/>',
  spin: '<path d="M13 8a5 5 0 1 1-1.5-3.6"/><path d="M13 2.5v3h-3"/>',
  pause: '<path d="M5.5 3.5v9M10.5 3.5v9"/>',
};
const svg = (d, s = 16) => `<svg viewBox="0 0 16 16" width="${s}" height="${s}" aria-hidden="true">${d}</svg>`;

/** host: the graph's container (sized by CSS). legend, hint, tools: overlay boxes labels must avoid.
 *  onOpen(item) fires on node click. Returns { setDim, select, fit }. */
export function createGraph({ wiki, host, legend, hint, tools, dim: startDim, onOpen }) {
let dim = startDim;
const name = (it) => it.name || it.title;
const byId = new Map(wiki.items.map((it) => [it.id, it]));
const groups = Object.keys(wiki.groups).sort((a, b) => wiki.groups[b] - wiki.groups[a]);
const color = (g) => PALETTE[groups.indexOf(g) % PALETTE.length];

// ---------- data ----------
// Links: tree = structure (module → its pages, group hub → member), drawn as faint spokes; ref = content
// (Markdown links, wikilinks, deps), drawn as brighter gradient arcs. An older wiki.json has no `links`: all ref.
const links = [];
if (Array.isArray(wiki.links)) {
  for (const l of wiki.links) if (byId.has(l.source) && byId.has(l.target)) links.push({ ...l, kind: l.kind === 'tree' ? 'tree' : 'ref' });
} else {
  const seen = new Set();
  for (const it of wiki.items) for (const t of it.links) {
    const key = [it.id, t].sort().join('\n');
    if (!seen.has(key) && byId.has(t)) { seen.add(key); links.push({ source: it.id, target: t, kind: 'ref' }); }
  }
}
const adj = new Map(); // node id → its links
for (const l of links) for (const id of [l.source, l.target]) adj.set(id, [...(adj.get(id) || []), l]);
// Size = importance: links in and out (log scale), modules a step up. Clamped so one hub never swallows a cluster.
const nodes = wiki.items.map((it) => {
  const d = adj.get(it.id)?.length || 0;
  const r = it.kind === 'module' ? Math.min(7.5, 3.6 + 1.1 * Math.log2(1 + d)) : Math.min(4.6, 1.5 + 0.75 * Math.log2(1 + d) + Math.sqrt(it.bytes) / 90);
  return { id: it.id, it, r, a: 1, s: 1 };
});
const members = new Map(groups.map((g) => [g, nodes.filter((n) => n.it.group === g)]));
const nodeOf = new Map(nodes.map((n) => [n.id, n]));
const degree = (n) => adj.get(n.id)?.length || 0;
const anchor = new Map([...members].map(([g, ns]) => [g, ns.find((n) => n.it.kind === 'module')
  || ns.reduce((a, b) => (degree(b) > degree(a) ? b : a))])); // the group's hub
const anchors = new Set(anchor.values());
const neighbours = new Map(nodes.map((n) => [n, new Set([n])]));
for (const l of links) { const a = nodeOf.get(l.source), b = nodeOf.get(l.target); neighbours.get(a).add(b); neighbours.get(b).add(a); }

function centroid(ns) {
  let x = 0, y = 0, z = 0;
  for (const n of ns) { x += n.x || 0; y += n.y || 0; z += n.z || 0; }
  return { x: x / ns.length, y: y / ns.length, z: z / ns.length };
}
const spread = new Map(), cent = new Map();
const radius = (g) => spread.get(g) || 24;

const room = (g) => 22 + 10 * Math.cbrt(wiki.groups[g]); // personal space of a group
function groupForce(alpha) { // pull members to their group's centroid; push overlapping groups apart
  const cs = [...members].map(([g, ns]) => [ns, centroid(ns), room(g)]);
  for (const [ns, c] of cs) {
    const k = 0.1 * alpha;
    for (const n of ns) { n.vx += (c.x - n.x) * k; n.vy += (c.y - n.y) * k; n.vz += (c.z - n.z) * k; }
  }
  for (let i = 0; i < cs.length; i++) for (let j = i + 1; j < cs.length; j++) {
    const [a, ca, ra] = cs[i], [b, cb, rb] = cs[j];
    let dx = ca.x - cb.x, dy = ca.y - cb.y, dz = ca.z - cb.z, d = Math.hypot(dx, dy, dz);
    if (d < 1e-3) { dx = Math.random() - 0.5; dy = Math.random() - 0.5; dz = Math.random() - 0.5; d = Math.hypot(dx, dy, dz); }
    const gap = ra + rb + 24 - d;
    if (gap <= 0) continue;
    const f = (gap / d) * 0.06 * alpha;
    for (const n of a) { n.vx += dx * f; n.vy += dy * f; n.vz += dz * f; }
    for (const n of b) { n.vx -= dx * f; n.vy -= dy * f; n.vz -= dz * f; }
  }
}

// ---------- textures (canvas, white; tinted by material colour) ----------
function texture(size, draw) {
  const c = el('canvas', { width: size, height: size }), x = c.getContext('2d');
  draw(x, size);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
function shapePath(x, kind, c, r) {
  x.beginPath();
  if (kind === 'module') { x.moveTo(c, c - r); x.lineTo(c + r, c); x.lineTo(c, c + r); x.lineTo(c - r, c); x.closePath(); }
  else if (kind === 'exhibit') { const s = r * 0.8; x.roundRect(c - s, c - s, 2 * s, 2 * s, s * 0.32); }
  else if (kind === 'figure') { x.moveTo(c, c - r); x.lineTo(c + r * 0.92, c + r * 0.66); x.lineTo(c - r * 0.92, c + r * 0.66); x.closePath(); }
  else x.arc(c, c, r * 0.86, 0, Math.PI * 2);
}
// Core: the kind's silhouette, filled, with a dark keyline so touching nodes stay distinct, and a faint
// inner shade so it reads as a lit bead rather than a flat dot.
const CORE = Object.fromEntries(KINDS.map((k) => [k, texture(128, (x, s) => {
  const c = s / 2;
  x.lineJoin = 'round';
  if (!LIGHT) { shapePath(x, k, c, 54); x.lineWidth = 9; x.strokeStyle = 'rgba(0,0,0,0.7)'; x.stroke(); }
  shapePath(x, k, c, 50); x.fillStyle = '#fff'; x.fill();
  const g = x.createRadialGradient(c - 12, c - 14, 2, c, c, 52);
  g.addColorStop(0, 'rgba(255,255,255,0)'); g.addColorStop(1, 'rgba(0,0,0,0.22)');
  x.fillStyle = g; x.fill();
  x.lineWidth = 3; x.strokeStyle = 'rgba(255,255,255,0.55)'; x.stroke();
})]));
const GLOW = texture(128, (x, s) => { // soft exponential halo
  const g = x.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  [[0, 0.9], [0.12, 0.55], [0.3, 0.2], [0.55, 0.06], [1, 0]].forEach(([o, a]) => g.addColorStop(o, `rgba(255,255,255,${a})`));
  x.fillStyle = g; x.fillRect(0, 0, s, s);
});
const NEBULA = texture(256, (x, s) => { // group aura: wide, gaussian-ish
  const g = x.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  [[0, 1], [0.25, 0.7], [0.5, 0.32], [0.75, 0.1], [1, 0]].forEach(([o, a]) => g.addColorStop(o, `rgba(255,255,255,${a})`));
  x.fillStyle = g; x.fillRect(0, 0, s, s);
});
const RING = texture(128, (x, s) => { // the open item: a crisp ring with a soft outer glow
  const c = s / 2;
  x.shadowColor = '#fff'; x.shadowBlur = 10;
  x.lineWidth = 5; x.strokeStyle = '#fff'; x.beginPath(); x.arc(c, c, 44, 0, Math.PI * 2); x.stroke();
  x.shadowBlur = 0; x.lineWidth = 1.5; x.strokeStyle = 'rgba(255,255,255,0.5)'; x.beginPath(); x.arc(c, c, 56, 0, Math.PI * 2); x.stroke();
});

const GLOW_A = LIGHT ? 0.22 : 0.42;
function nodeObject(n) {
  const col = color(n.it.group), o = new THREE.Group();
  const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: GLOW, color: col, transparent: true, opacity: GLOW_A, depthWrite: false }));
  halo.raycast = () => {}; // hover hits the bead, not the halo
  halo.scale.setScalar(n.r * (n.it.kind === 'module' ? 7 : 5.5));
  const core = new THREE.Sprite(new THREE.SpriteMaterial({ map: CORE[n.it.kind] || CORE.page, color: col, transparent: true, depthWrite: false }));
  core.scale.setScalar(n.r * 2.3);
  o.add(halo, core);
  n.halo = halo; n.core = core;
  return o;
}

// ---------- links: one small shader per link ----------
// Gradient from the source group's colour to the target's, ends faded under the beads, distance fog, and a
// light pulse that travels source → target while the link is in focus. Uniforms ease per frame: hover
// never rebuilds the graph.
const U = { time: { value: 0 }, fogNear: { value: 1e9 }, fogFar: { value: 2e9 } };
const LINK_VS = 'varying vec3 vW; void main() { vec4 w = modelMatrix * vec4(position, 1.0); vW = w.xyz; gl_Position = projectionMatrix * viewMatrix * w; }';
const LINK_FS = `uniform vec3 a; uniform vec3 b; uniform vec3 ca; uniform vec3 cb; uniform float opacity; uniform float flow;
uniform float time; uniform float fogNear; uniform float fogFar; varying vec3 vW;
void main() {
  vec3 ab = b - a; float t = clamp(dot(vW - a, ab) / max(dot(ab, ab), 1e-4), 0.0, 1.0);
  float ends = smoothstep(0.0, 0.1, t) * smoothstep(1.0, 0.9, t);
  vec3 col = mix(ca, cb, t);
  float p = exp(-pow((t - fract(time * 0.45)) * 9.0, 2.0)) * flow;
  col = mix(col, vec3(1.0), p * 0.55);
  float al = (opacity + p * 0.8) * ends;
  al *= 1.0 - 0.8 * smoothstep(fogNear, fogFar, distance(vW, cameraPosition));
  gl_FragColor = vec4(col, al);
}`;
const ALPHA = LIGHT ? { tree: 0.16, ref: 0.5, on: 0.9, treeOn: 0.6, off: 0.06 } : { tree: 0.12, ref: 0.45, on: 0.95, treeOn: 0.55, off: 0.04 };
for (const l of links) {
  const s = byId.get(l.source), t = byId.get(l.target);
  l.a = 0;
  l.mat = new THREE.ShaderMaterial({
    vertexShader: LINK_VS, fragmentShader: LINK_FS, transparent: true, depthWrite: false,
    uniforms: {
      a: { value: new THREE.Vector3() }, b: { value: new THREE.Vector3() },
      ca: { value: new THREE.Color(color(l.kind === 'tree' ? t.group : s.group)) }, cb: { value: new THREE.Color(color(t.group)) },
      opacity: { value: 0 }, flow: { value: 0 }, time: U.time, fogNear: U.fogNear, fogFar: U.fogFar,
    },
  });
}

// ---------- focus: hover a node (or a legend group) → its neighbourhood stays lit, the rest steps back ----------
let hover = null, hoverGroup = null, picked = null, lastT = performance.now();
function focusSet() {
  if (hover) return neighbours.get(hover);
  if (hoverGroup) return new Set(members.get(hoverGroup));
  return null;
}
const camPos = new THREE.Vector3(), P = new THREE.Vector3();
function depthFade(n) {
  if (dim === 2) return 1;
  const d = camPos.distanceTo(P.set(n.x || 0, n.y || 0, n.z || 0));
  return 1 - 0.7 * Math.min(1, Math.max(0, (d - U.fogNear.value) / (U.fogFar.value - U.fogNear.value)));
}
let zoom2d = 1; // 2D spreads the same clusters over a plane: beads grow so they still read
function ease(now) {
  zoom2d += ((dim === 2 ? 1.6 : 1) - zoom2d) * (CALM ? 1 : 0.1);
  const f = focusSet(), dt = Math.min(now - lastT, 100);
  const k = CALM ? 1 : 1 - Math.exp(-dt / 80); // ≈ 250 ms to settle
  lastT = now;
  U.time.value = CALM ? 0.5 : now / 1000;
  for (const l of links) {
    const s = l.source, t = l.target; // node objects once the layout has started
    const on = !!f && f.has(s) && f.has(t) && (!hover || s === hover || t === hover);
    const goal = f ? (on ? (l.kind === 'ref' ? ALPHA.on : ALPHA.treeOn) : ALPHA.off) : ALPHA[l.kind];
    l.a += (goal - l.a) * k;
    const u = l.mat.uniforms;
    u.opacity.value = l.a;
    u.flow.value += ((on && !CALM ? 1 : 0) - u.flow.value) * k;
    if (l.__lineObj) l.__lineObj.visible = l.a > 0.005; // set by 3d-force-graph
  }
  for (const n of nodes) {
    n.a += ((f && !f.has(n) ? 0.12 : 1) - n.a) * k;
    n.s += ((n === hover ? 1.3 : 1) - n.s) * k;
    if (!n.core) continue;
    const fog = depthFade(n);
    n.core.material.opacity = n.a * fog;
    n.halo.material.opacity = GLOW_A * n.a * n.a * fog * (n === hover || n === picked ? 1.6 : 1);
    n.core.scale.setScalar(n.r * 2.3 * n.s * zoom2d);
    n.halo.scale.setScalar(n.r * (n.it.kind === 'module' ? 7 : 5.5) * zoom2d);
  }
}

const tip = (n) => {
  const it = n.it, sum = (it.summary || '').replace(/\s+/g, ' ').trim();
  return `<div class="tip"><span class="tk" style="--c:${color(it.group)}">${svg(`<g transform="scale(1.333)">${SHAPES[it.kind] || SHAPES.page}</g>`, 11)}${esc(it.kind)}<i>·</i>${esc(human(it.group))}</span>`
    + `<b>${esc(name(it))}</b>${sum ? `<p>${esc(sum.length > 120 ? `${sum.slice(0, 118)}…` : sum)}</p>` : ''}</div>`;
};

const G = new ForceGraph3D(host, { controlType: 'orbit' })
  .numDimensions(dim)
  .width(host.clientWidth || 800).height(host.clientHeight || 600)
  .backgroundColor('rgba(0,0,0,0)')
  .showNavInfo(false)
  .enableNodeDrag(false) // also avoids an upstream OrbitControls pointerup error after drags
  .nodeThreeObject(nodeObject)
  .nodeLabel(tip)
  .linkWidth(0)
  .linkCurvature((l) => (l.kind === 'ref' ? 0.28 : 0.08))
  .linkCurveRotation(0)
  .linkMaterial((l) => l.mat)
  .linkPositionUpdate((obj, { start, end }, l) => { // 2D positions have no z
    l.mat.uniforms.a.value.set(start.x, start.y, start.z || 0); l.mat.uniforms.b.value.set(end.x, end.y, end.z || 0); return false;
  })
  .onNodeHover((n) => { hover = n || null; host.style.cursor = n ? 'pointer' : ''; })
  .onNodeClick((n) => onOpen(n.it))
  .onEngineTick(onTick)
  .cooldownTicks(320) // tick-based, so a backgrounded tab still settles the same layout
  .cooldownTime(120000)
  .warmupTicks(CALM ? 160 : 0)
  .d3Force('group', groupForce)
  .graphData({ nodes, links });
G.d3Force('charge').strength(-36);
G.d3Force('link').distance((l) => (l.source.it.group === l.target.it.group ? 14 + 2.2 * Math.sqrt(wiki.groups[l.source.it.group]) // big groups bloom out
  : room(l.source.it.group) + room(l.target.it.group) + 12)); // linked clusters sit side by side
const cam = G.camera();
const controls = G.controls();
controls.enableDamping = true; controls.dampingFactor = 0.08; controls.rotateSpeed = 0.6;
cam.position.set(0, 0, 1500); // intro: start far out, fly in once the shape forms
let fitted = 0, touched = false, ticks = 0;
function onTick() { // a first framing once the shape has formed, a final one when it settles (unless the reader took over)
  updateClouds();
  if (++ticks === 70 && !fitted) { fitted = 1; fitAll(2000); }
}
G.onEngineStop(() => { updateClouds(); if (fitted < 2 && !touched) fitAll(1200); fitted = 2; });
new ResizeObserver(() => { if (host.clientWidth) G.width(host.clientWidth).height(host.clientHeight); }).observe(host);

// 2D = the same layout flattened onto z = 0, seen from straight above; drag pans instead of orbiting.
function setDim(d) {
  if (d === dim) return;
  dim = d;
  for (const n of nodes) { n.z = d === 2 ? 0 : (Math.random() - 0.5) * 24; n.vz = 0; }
  G.numDimensions(d);
  tuneControls();
  setSpin(d === 3 && !touched);
  fitted = 0; ticks = 0; G.d3ReheatSimulation();
}
function tuneControls() {
  const flat = dim === 2;
  controls.enableRotate = !flat;
  controls.mouseButtons.LEFT = flat ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE;
  controls.touches.ONE = flat ? THREE.TOUCH.PAN : THREE.TOUCH.ROTATE;
  controls.screenSpacePanning = true;
}
tuneControls();

const mark = new THREE.Sprite(new THREE.SpriteMaterial({ map: RING, color: LIGHT ? '#5f8f12' : '#a3e635', transparent: true, depthTest: false, depthWrite: false }));
mark.renderOrder = 10; mark.visible = false;
G.scene().add(mark);
function select(it) {
  picked = (it && nodeOf.get(it.id)) || null;
  mark.visible = !!picked;
}

// Nebulae: one soft aura per group, under links and nodes.
const NEB_A = LIGHT ? 0.12 : 0.085;
const clouds = new Map(groups.map((g) => {
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: NEBULA, color: color(g), transparent: true, opacity: 0, depthWrite: false, depthTest: false }));
  s.renderOrder = -1;
  G.scene().add(s);
  return [g, s];
}));
function updateClouds() {
  for (const [g, ns] of members) {
    const c = centroid(ns);
    let s = 0;
    for (const n of ns) s += (n.x - c.x) ** 2 + (n.y - c.y) ** 2 + (n.z - c.z) ** 2;
    const rad = Math.sqrt(s / ns.length) * 1.4 + 10;
    spread.set(g, rad); cent.set(g, c);
    clouds.get(g).position.set(c.x, c.y, c.z); clouds.get(g).scale.setScalar(rad * 2.6);
  }
}

// ---------- labels: level of detail by each cluster's radius on screen ----------
// far: one group name per nebula · middle: the hub's title · near: titles of pages near the screen centre.
// Hover: the neighbourhood's titles win. Labels never overlap each other or the chrome, and every change fades.
const LOD = { mid: [60, 130], near: [190, 320], pages: 12 }; // px
const layer = el('div', { id: 'labels' });
layer.setAttribute('aria-hidden', 'true');
host.append(layer);
const view = { W: 1, H: 1, k: 1 }, V = new THREE.Vector3(), labels = [], gview = new Map();
const smooth = (x, [a, b]) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
function screen(p) { // world point → [x, y, distance] on the canvas, or null when behind the camera
  const d = cam.position.distanceTo(V.set(p.x || 0, p.y || 0, p.z || 0));
  V.project(cam);
  return V.z > -1 && V.z < 1 ? [((V.x + 1) * view.W) / 2, ((1 - V.y) * view.H) / 2, Math.max(d, 1e-3)] : null;
}
function label(kids, cls, at) { // at() → [x, y, alignX, alignY] or null
  const e = append(el('span', { className: `lbl ${cls}` }), kids);
  layer.append(e);
  const L = { e, at, page: cls === 'p', o: 0, t: 0, w: 0, h: 0, x: 0, y: 0, vis: false };
  labels.push(L);
  return L;
}
const groupLabel = new Map(groups.map((g) => {
  const dot = el('i'); dot.style.setProperty('--c', color(g));
  const L = label([dot, human(g)], 'g', () => { const v = gview.get(g); return v && [v.s[0], v.s[1] - Math.min(v.pr * 0.85, 160) - 8, 0.5, 1]; }); // above the cluster's rim
  return [g, L];
}));
const nodeLabel = new Map();
function labelOf(n) {
  if (!nodeLabel.has(n)) {
    nodeLabel.set(n, label([name(n.it)], anchors.has(n) ? 'm' : 'p', () => {
      const s = screen(n);
      return s && [s[0] + (n.r * 1.25 * n.s * zoom2d * view.k) / s[2] + 6, s[1], 0, 0.5];
    }));
  }
  return nodeLabel.get(n);
}
let chrome = [], frames = 0;
function chromeBoxes() { // the overlay UI (legend, hint, tools, open-item chip) in label-layer coordinates
  const o = layer.getBoundingClientRect();
  return [legend, hint, tools, document.getElementById('pick')].filter(Boolean).map((e) => e.getBoundingClientRect()).filter((r) => r.width)
    .map((r) => [r.left - o.left - 8, r.top - o.top - 4, r.right - o.left + 8, r.bottom - o.top + 4]);
}

function placeLabels() {
  view.W = G.width(); view.H = G.height(); view.k = view.H / (2 * Math.tan((cam.fov * Math.PI) / 360));
  if (!(frames++ % 30)) chrome = chromeBoxes();
  const cx = view.W / 2, cy = view.H / 2, R = 0.34 * Math.min(view.W, view.H), f = focusSet();
  let focus = 0; // how far the camera is inside the cluster under the screen centre
  for (const g of groups) {
    const c = cent.get(g), s = c && screen(c);
    if (!s) { gview.delete(g); continue; }
    const pr = (radius(g) * view.k) / s[2], v = { s, pr, mid: smooth(pr, LOD.mid), near: smooth(pr, LOD.near) };
    gview.set(g, v);
    if (Math.hypot(s[0] - cx, s[1] - cy) < pr) focus = Math.max(focus, v.near);
  }
  const want = []; // [label, target opacity, priority]
  const dimmed = (n) => (f && !f.has(n) ? 0.15 : 1);
  for (const [g, v] of gview) {
    const gd = f ? (members.get(g).some((n) => f.has(n)) ? 0.9 : 0.12) : 1;
    want.push([groupLabel.get(g), (1 - v.mid) * (1 - focus) * gd, 1 + wiki.groups[g] / wiki.items.length / 2]);
    const a = anchor.get(g);
    if (a !== hover && a !== picked && v.mid > 0.02) want.push([labelOf(a), v.mid * dimmed(a), 3 + Math.min(v.pr, 2000) / 4000]);
  }
  if (hover) for (const n of neighbours.get(hover)) if (n !== hover) want.push([labelOf(n), 0.92, 8 + degree(n) / 1000]); // the tooltip carries the hovered title
  if (picked && picked !== hover) want.push([labelOf(picked), 1, 9]);
  for (const n of nodes) {
    const near = gview.get(n.it.group)?.near;
    if (!(near > 0.02) || n === hover || n === picked || anchors.has(n)) continue;
    const s = screen(n), dc = s && Math.hypot(s[0] - cx, s[1] - cy);
    if (s && dc < R) want.push([labelOf(n), near * dimmed(n), 2 + 0.4 * (1 - dc / R)]); // nearest the centre first
  }

  const rank = (w) => w[2] + (w[0].o > 0.5 ? 0.3 : 0); // hysteresis: a showing label keeps its place
  want.sort((a, b) => rank(b) - rank(a));
  const boxes = [...chrome], keep = new Set();
  const tipBox = hover && host.querySelector('.float-tooltip-kap')?.getBoundingClientRect(); // the tooltip wins over labels
  if (tipBox?.width) { const o = layer.getBoundingClientRect(); boxes.push([tipBox.left - o.left - 6, tipBox.top - o.top - 4, tipBox.right - o.left + 6, tipBox.bottom - o.top + 4]); }
  let pages = 0;
  for (const [L, t] of want) {
    if (t < 0.02 || keep.has(L) || (L.page && pages >= LOD.pages && !hover)) continue;
    const p = L.at();
    if (!p) continue;
    if (!L.w) { L.w = L.e.offsetWidth; L.h = L.e.offsetHeight; }
    const x = p[0] - L.w * p[2], y = p[1] - L.h * p[3];
    if (x < 4 || y < 4 || x + L.w > view.W - 4 || y + L.h > view.H - 4) continue; // whole label on screen, or none
    if (boxes.some((b) => x < b[2] && x + L.w > b[0] && y < b[3] && y + L.h > b[1])) continue;
    boxes.push([x - 6, y - 2, x + L.w + 6, y + L.h + 2]);
    keep.add(L); L.t = t; L.x = x; L.y = y; pages += L.page;
  }
  for (const L of labels) {
    const t = keep.has(L) ? L.t : 0;
    if (!t && !L.o) continue;
    L.o = CALM ? t : L.o + (t - L.o) * 0.16;
    const p = !t && L.o >= 0.01 && L.at(); // fading out: keep following its anchor
    if (!t && !p) { L.o = 0; L.vis = false; L.e.style.visibility = 'hidden'; continue; }
    if (p) { L.x = p[0] - L.w * p[2]; L.y = p[1] - L.h * p[3]; }
    if (!L.vis) { L.vis = true; L.e.style.visibility = 'visible'; }
    L.e.style.opacity = L.o.toFixed(3);
    L.e.style.transform = `translate3d(${L.x.toFixed(1)}px,${L.y.toFixed(1)}px,0)`;
  }
}

let R0 = 200; // the layout's radius, for fog
(function frame(now = performance.now()) {
  requestAnimationFrame(frame);
  if (!host.clientWidth) return; // hidden view: no work
  camPos.copy(cam.position);
  if (dim === 3) { // fog band: from just in front of the layout's centre to just past its far side
    const c = centroid(nodes), d = camPos.distanceTo(P.set(c.x, c.y, c.z));
    U.fogNear.value = Math.max(1, d - R0 * 0.2); U.fogFar.value = d + R0 * 1.3;
  } else { U.fogNear.value = 1e9; U.fogFar.value = 2e9; }
  ease(now);
  if (picked) { mark.position.set(picked.x || 0, picked.y || 0, picked.z || 0); mark.scale.setScalar(picked.r * 4.2); }
  const f = focusSet();
  for (const [g, s] of clouds) { // nebulae dissolve as the camera enters them, and step back under a focus
    const rad = radius(g), d = cam.position.distanceTo(s.position);
    const lit = !f || members.get(g).some((n) => f.has(n)) ? 1 : 0.3;
    s.material.opacity = NEB_A * lit * Math.min(1, Math.max(0, (d - rad) / (rad * 1.5)));
  }
  placeLabels();
})();

function fitAll(ms = 1600) { // frame the nodes: a bounding sphere in 3D, the bounding box in 2D (outliers beyond the 97th percentile are left out)
  const c = centroid(nodes), tanV = Math.tan((cam.fov * Math.PI) / 360);
  const q = (xs) => xs.sort((a, b) => a - b)[Math.floor(xs.length * 0.97)] || 50;
  if (dim === 2) {
    const hw = q(nodes.map((n) => Math.abs(n.x - c.x))), hh = q(nodes.map((n) => Math.abs(n.y - c.y)));
    R0 = Math.max(hw, hh);
    flyToPoint(c, Math.max(hh / tanV, hw / (tanV * cam.aspect)) * 1.15, ms);
    return;
  }
  const r = q(nodes.map((n) => Math.hypot(n.x - c.x, n.y - c.y, n.z - c.z)));
  R0 = r;
  const half = Math.min(cam.fov, (2 * Math.atan(tanV * cam.aspect) * 180) / Math.PI) / 2;
  flyToPoint(c, (r / Math.sin((half * Math.PI) / 180)) * (cam.aspect > 1 ? 0.85 : 0.95), ms); // portrait: room for the spin
}

function flyToPoint(p, dist, ms = 1400) {
  let [dx, dy, dz] = [cam.position.x - p.x, cam.position.y - p.y, cam.position.z - p.z];
  if (dim === 2) [dx, dy, dz] = [0, 0, 1]; // straight above
  else if (Math.hypot(dx, dy) < 1e-3 * Math.abs(dz)) [dx, dy, dz] = [0.35, 0.3, 1]; // leaving the 2D view: tilt
  const k = dist / (Math.hypot(dx, dy, dz) || 1);
  G.cameraPosition({ x: p.x + dx * k, y: p.y + dy * k, z: p.z + dz * k }, p, T(ms));
}

// ---------- tools: fit · spin ----------
// Ambient spin in 3D: slow, stops for good on the first touch (the spin button brings it back).
let spin = false;
const tool = (icon, text, fn) => {
  const b = el('button', { type: 'button', className: 'tool', title: text, innerHTML: svg(icon) });
  b.setAttribute('aria-label', text); b.onclick = fn;
  tools.append(b);
  return b;
};
tool(ICON.fit, 'Fit to view', () => { touched = true; fitAll(900); });
const spinBtn = tool(ICON.spin, 'Rotate', () => setSpin(!spin));
function setSpin(on) {
  spin = on && dim === 3 && !CALM;
  controls.autoRotate = spin; controls.autoRotateSpeed = 0.35;
  spinBtn.hidden = dim === 2 || CALM;
  spinBtn.innerHTML = svg(spin ? ICON.pause : ICON.spin);
  const t = spin ? 'Stop rotating' : 'Rotate';
  spinBtn.title = t; spinBtn.setAttribute('aria-label', t); spinBtn.setAttribute('aria-pressed', String(spin));
}
controls.addEventListener('start', () => { touched = true; setSpin(false); });
setSpin(dim === 3);

// ---------- legend ----------
const swatch = (kind) => `<svg viewBox="0 0 12 12" width="11" height="11" aria-hidden="true">${SHAPES[kind]}</svg>`;
const TOP = 6;
legend.append(el('h3', { textContent: 'Groups' }));
const list = el('div', { className: 'groups' });
groups.forEach((g, i) => {
  const b = el('button', { type: 'button', className: i >= TOP ? 'extra' : '', title: `Fly to ${human(g)}` });
  const dot = el('i', { className: 'sw' }); dot.style.setProperty('--c', color(g));
  b.append(dot, el('span', { className: 'gn', textContent: human(g) }), el('small', { textContent: wiki.groups[g] }));
  b.onclick = () => { touched = true; setSpin(false); flyToPoint(centroid(members.get(g)), radius(g) * 3.2); };
  b.onpointerenter = () => { hoverGroup = g; }; b.onpointerleave = () => { hoverGroup = null; };
  b.onfocus = b.onpointerenter; b.onblur = b.onpointerleave;
  list.append(b);
});
legend.append(list);
if (groups.length > TOP) {
  const more = el('button', { type: 'button', className: 'more', textContent: `Show all ${groups.length}` });
  more.setAttribute('aria-expanded', 'false');
  more.onclick = () => {
    const on = legend.classList.toggle('all');
    more.textContent = on ? 'Show fewer' : `Show all ${groups.length}`;
    more.setAttribute('aria-expanded', String(on));
    chrome = chromeBoxes();
  };
  legend.append(more);
}
legend.append(el('div', { className: 'kinds', innerHTML: KINDS.map((k) => `<span>${swatch(k)}${k}</span>`).join('') }));
legend.append(el('div', { className: 'lk', innerHTML: '<span><i class="ln ref"></i>links to</span><span><i class="ln tree"></i>part of</span>' }));

return { setDim, select, fit: () => fitAll() };
}
