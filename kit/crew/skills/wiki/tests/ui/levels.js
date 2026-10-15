// Synthetic map levels for the engine harness (no server): a root with 6 blocks + ghosts, its child level,
// a cyclic level, a 150-node / 600-edge level, code-lens levels and a shape showcase. Also boots the
// harness page: window.H = {engine, levels, show(name, mode, via), state(), events, clock, layoutLevel}.
import { createEngine } from '/assets/map/engine.js';
import { layoutLevel } from '/assets/map/layout.js';

const B = (o = {}) => ({ crit: null, status: null, state: null, cov: null, stale: 0, findings: 0, debt: 0, reqs: 0, ...o });
const mod = (id, kind, name, o = {}) => ({ id, type: 'module', tier: 'sys', kind, name, title: name, brief: '', drill: null, n: 0, item: null, src: null, sig: null, badges: B(), ...o });
const edge = (s, t, kinds, o = {}) => ({ id: `${s}>${t}`, s, t, kinds, n: Object.values(kinds).reduce((a, b) => a + b, 0), conf: 1, hist: [0, 0, 0], labels: [], dash: false, state: 'declared', x: false, prov: [], samples: [], ...o });
const ghost = (peer, side) => ({ id: `ghost:${peer}`, peer, name: peer.split('/').pop(), path: peer.split('/').join(' › '), side, at: peer.split('/').slice(0, -1).join('/') || '.' });
const crumbs = (...ids) => ids.map((id) => ({ id, name: id === '.' ? 'weather-station' : id.split('/').pop() }));

const root = {
  v: 1, rev: 'synthetic-root', lens: 'systems', at: '.', crumbs: crumbs('.'),
  nodes: [
    mod('firmware', 'system', 'firmware', { drill: 'systems', n: 7, brief: 'Station firmware: samples sensors, stores readings, uploads batches.', badges: B({ crit: 'L2', status: 'approved', state: 'verified', cov: [30, 45] }) }),
    mod('backend', 'system', 'backend', { drill: 'systems', n: 3, brief: 'Ingests uplinks, stores telemetry, serves the dashboard.', badges: B({ crit: 'L2', status: 'approved', cov: [18, 18] }) }),
    mod('dashboard', 'code', 'dashboard', { drill: 'code', n: 4, brief: 'Web dashboard for live and historical readings.', badges: B({ status: 'draft', cov: [3, 9], findings: 2 }) }),
    mod('protocol', 'protocol', 'protocol', { drill: 'code', n: 2, brief: 'weather.v1 protobuf contract shared by station and backend.', badges: B({ crit: 'L1', status: 'approved', cov: [6, 6], stale: 1 }) }),
    { id: 'deploy', type: 'group', tier: 'sys', kind: 'group', name: 'deploy', drill: 'systems', n: 2, item: null, badges: B() },
    { id: 'host', type: 'group', tier: 'sys', kind: 'group', name: 'host', drill: 'systems', n: 1, item: null, badges: B() },
  ],
  ghosts: [ghost('vendor/sdk', 'in'), ghost('ops/alerts', 'out'), ghost('cloud/edge', 'both')],
  edges: [
    edge('firmware', 'backend', { flow: 1, dep: 1 }, { labels: ['protocol: weather.v1.Reading over HTTPS'], prov: ['weather-station.md:30'] }),
    edge('backend', 'dashboard', { flow: 1 }, { labels: ['readings · SQL · 1/min'], state: 'both' }),
    edge('deploy', 'backend', { flow: 1, dep: 1 }, { labels: ['deploys'], dash: true }),
    edge('host', 'firmware', { flow: 1 }, { labels: ['debug probe'], dash: true }),
    edge('firmware', 'protocol', { dep: 1 }),
    edge('backend', 'protocol', { dep: 1, contract: 2 }, { state: 'both' }),
    edge('dashboard', 'protocol', { contract: 2 }, { state: 'observed', conf: 0.6 }),
    edge('dashboard', 'firmware', { call: 3 }, { state: 'undeclared', x: true, conf: 0.85 }),
    edge('ghost:vendor/sdk', 'firmware', { flow: 1 }, { labels: ['SDK headers'] }),
    edge('backend', 'ghost:ops/alerts', { flow: 1 }, { labels: ['alerts'] }),
    edge('dashboard', 'ghost:cloud/edge', { flow: 1 }, { labels: ['CDN'] }),
  ],
  overflow: false,
};

const child = {
  v: 1, rev: 'synthetic-root', lens: 'systems', at: 'firmware', crumbs: crumbs('.', 'firmware'),
  nodes: [
    mod('firmware/sensing', 'system', 'sensing', { drill: 'systems', n: 3, brief: 'Reads humidity and battery voltage every 60 s.', badges: B({ crit: 'L2', status: 'approved', state: 'verified', cov: [12, 14] }) }),
    mod('firmware/storage', 'system', 'storage', { drill: 'systems', n: 2, brief: 'Buffers readings on SD; guards against brown-out.', badges: B({ status: 'approved', cov: [9, 9] }) }),
    mod('firmware/comms', 'code', 'comms', { drill: 'code', n: 4, brief: 'Encodes readings and uploads batches over HTTPS.', badges: B({ status: 'draft', cov: [4, 7], findings: 1 }) }),
    { id: 'firmware/ports', type: 'group', tier: 'sys', kind: 'group', name: 'ports', drill: 'systems', n: 2, badges: B() },
    { id: 'firmware/adapters', type: 'group', tier: 'sys', kind: 'group', name: 'adapters', drill: 'systems', n: 3, badges: B() },
    { id: 'firmware/targets', type: 'group', tier: 'sys', kind: 'group', name: 'targets', drill: 'systems', n: 2, badges: B() },
    { id: 'firmware/:own', type: 'own', tier: 'sys', kind: 'own', name: 'firmware (own code)', drill: null, n: 0, badges: B({ cov: [2, 3] }) },
  ],
  ghosts: [ghost('backend/ingest', 'out'), ghost('host/probe_access', 'in'), ghost('protocol', 'both')],
  edges: [
    edge('firmware/sensing', 'firmware/storage', { flow: 2 }, { labels: ['Reading every 60 s', 'LOW_BATTERY'], n: 2 }),
    edge('firmware/storage', 'firmware/comms', { flow: 1 }, { labels: ['batch of readings'] }),
    edge('firmware/comms', 'ghost:backend/ingest', { flow: 1 }, { labels: ['protocol: weather.v1.Reading over HTTPS'] }),
    edge('firmware/sensing', 'firmware/ports', { flow: 1 }, { dash: true, labels: ['uses'] }),
    edge('firmware/storage', 'firmware/ports', { flow: 1 }, { dash: true, labels: ['uses'] }),
    edge('firmware/comms', 'firmware/ports', { flow: 1 }, { dash: true }),
    edge('firmware/adapters', 'firmware/ports', { flow: 1 }, { labels: ['implements'] }),
    edge('firmware/targets', 'firmware/adapters', { dep: 1 }),
    edge('ghost:host/probe_access', 'firmware/sensing', { flow: 1 }, { dash: true, labels: ['debug'] }),
    edge('firmware/:own', 'firmware/storage', { call: 2 }, { state: 'observed', conf: 0.9 }),
    edge('firmware/comms', 'ghost:protocol', { contract: 1 }, { state: 'observed', conf: 0.6 }),
  ],
  overflow: false,
};

const cyclic = {
  v: 1, rev: 'synthetic-cyclic', lens: 'systems', at: 'ring', crumbs: crumbs('.', 'ring'),
  nodes: ['a', 'b', 'c', 'd', 'e', 'f'].map((x, i) => mod(`ring/${x}`, i % 2 ? 'code' : 'system', `node_${x}`, { drill: i < 2 ? 'systems' : null, n: i < 2 ? 3 : 0 })),
  ghosts: [],
  edges: [
    edge('ring/a', 'ring/b', { flow: 1 }, { labels: ['a to b'] }), edge('ring/b', 'ring/c', { flow: 1 }, { labels: ['b to c'] }),
    edge('ring/c', 'ring/a', { flow: 1 }, { labels: ['back to a'] }), edge('ring/c', 'ring/d', { call: 4 }, { state: 'observed', conf: 0.9 }),
    edge('ring/d', 'ring/b', { call: 1 }, { state: 'observed', conf: 0.55 }), edge('ring/e', 'ring/a', { dep: 1 }),
    edge('ring/b', 'ring/e', { flow: 1 }), edge('ring/f', 'ring/f', { call: 1 }), edge('ring/d', 'ring/f', { inherit: 1 }, { state: 'observed' }),
  ],
};

// 150 nodes, 600 edges, deterministic (mulberry32)
function rng(seed) { return () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
function bigLevel(n = 150, m = 600) {
  const r = rng(7), nodes = [], edges = new Map();
  const kinds = ['function', 'method', 'class', 'struct', 'function', 'method', 'enum', 'test'];
  for (let i = 0; i < n; i++) {
    const file = i % 5 !== 4;
    const id = file ? `lib/gen/src/f${String(i).padStart(3, '0')}.cpp` : `lib/gen/src/f${String(i - 1).padStart(3, '0')}.cpp#gen::sym_${i}`;
    nodes.push(file ? { id, type: 'file', tier: 'code', kind: 'cpp', name: `f${String(i).padStart(3, '0')}.cpp`, drill: 'code', n: 1 + (i % 6), test: i % 17 === 0, badges: B({ cov: [i % 7, 6] }) }
      : { id, type: 'symbol', tier: 'code', kind: kinds[i % kinds.length], name: `sym_${i}`, drill: null, n: 0, badges: B() });
  }
  // tiers of 19 blocks; most edges go one or two tiers right, a few point back
  const tier = (i) => Math.floor(i / 19), inTier = (t) => nodes.filter((_, i) => tier(i) === t).length;
  let guard = 0;
  while (edges.size < m && guard++ < m * 40) {
    const a = Math.floor(r() * n), ta = tier(a), c0 = r();
    const tb = c0 < 0.76 ? ta + 1 : c0 < 0.93 ? ta + 2 : ta - 1 - Math.floor(r() * 2);
    if (tb < 0 || tb > tier(n - 1)) continue;
    const b = tb * 19 + Math.floor(r() * inTier(tb));
    if (a === b || b >= n) continue;
    const s = nodes[a].id, t = nodes[b].id, id = `${s}>${t}`;
    if (edges.has(id)) continue;
    const c = r(), k = c < 0.6 ? 'call' : c < 0.85 ? 'import' : c < 0.95 ? 'inherit' : 'contract';
    edges.set(id, edge(s, t, { [k]: 1 + Math.floor(r() * 4) }, { state: 'observed', conf: Math.round((0.3 + r() * 0.7) * 100) / 100 }));
  }
  return { v: 1, rev: 'synthetic-big', lens: 'code', at: 'lib/gen/src', crumbs: crumbs('.', 'lib', 'lib/gen', 'lib/gen/src'), nodes, ghosts: [ghost('lib/core', 'out'), ghost('app/main', 'in')],
    edges: [...edges.values(), edge('lib/gen/src/f000.cpp', 'ghost:lib/core', { call: 3 }, { state: 'observed', conf: 0.9 }), edge('ghost:app/main', 'lib/gen/src/f001.cpp', { call: 1 }, { state: 'observed', conf: 0.8 })] };
}

const M = 'firmware/sensing/battery_monitor';
const code = {
  v: 1, rev: 'synthetic-code', lens: 'code', at: M, crumbs: crumbs('.', 'firmware', 'firmware/sensing', M),
  nodes: [
    { id: `${M}/include/battery_monitor`, type: 'dir', tier: 'code', kind: 'dir', name: 'include/battery_monitor', drill: 'code', n: 2, badges: B({ cov: [5, 6] }) },
    { id: `${M}/src`, type: 'dir', tier: 'code', kind: 'dir', name: 'src', drill: 'code', n: 3, badges: B({ cov: [7, 8] }) },
    { id: `${M}/test`, type: 'dir', tier: 'code', kind: 'dir', name: 'test', drill: 'code', n: 2, badges: B() },
    { id: `${M}/fakes`, type: 'dir', tier: 'code', kind: 'dir', name: 'fakes', drill: 'code', n: 1, badges: B() },
    { id: `${M}/CMakeLists.txt`, type: 'file', tier: 'code', kind: 'text', name: 'CMakeLists.txt', drill: null, n: 0, badges: B() },
  ],
  ghosts: [ghost('firmware/ports/hal_ports', 'out'), ghost('firmware/storage', 'out'), ghost('firmware/sensing/humidity', 'in')],
  edges: [
    edge(`${M}/src`, `${M}/include/battery_monitor`, { import: 4, call: 6 }, { state: 'observed', conf: 0.9 }),
    edge(`${M}/test`, `${M}/src`, { call: 5 }, { state: 'observed', conf: 0.85 }),
    edge(`${M}/test`, `${M}/fakes`, { import: 2, call: 2 }, { state: 'observed', conf: 0.6 }),
    edge(`${M}/fakes`, `${M}/include/battery_monitor`, { inherit: 1 }, { state: 'observed', conf: 0.9 }),
    edge(`${M}/src`, 'ghost:firmware/ports/hal_ports', { call: 3 }, { state: 'observed', conf: 0.85 }),
    edge(`${M}/src`, 'ghost:firmware/storage', { call: 1 }, { state: 'undeclared', x: true, conf: 0.9 }),
    edge('ghost:firmware/sensing/humidity', `${M}/src`, { call: 1 }, { state: 'observed', conf: 0.4 }),
  ],
};

const F = `${M}/src/battery_monitor.cpp`;
const sym = (q, kind, name, o = {}) => ({ id: `${F}#${q}`, type: 'symbol', tier: 'code', kind, name, drill: null, n: 0, badges: B(), ...o });
const file = {
  v: 1, rev: 'synthetic-file', lens: 'code', at: F, crumbs: crumbs('.', 'firmware', 'firmware/sensing', M, `${M}/src`, F),
  nodes: [
    sym('battery_monitor::BatteryMonitor', 'class', 'BatteryMonitor', { drill: 'code', n: 4 }),
    sym('battery_monitor::BatteryMonitor::sample', 'method', 'BatteryMonitor::sample', { badges: B({ findings: 1 }) }),
    sym('battery_monitor::BatteryMonitor::BatteryMonitor', 'ctor', 'BatteryMonitor::BatteryMonitor'),
    sym('battery_monitor::update_brownout', 'function', 'update_brownout'),
    sym('battery_monitor::kBrownoutMv', 'const', 'kBrownoutMv'),
    sym('battery_monitor::Sink', 'interface', 'Sink'),
    sym('battery_monitor::Level', 'enum', 'Level'),
    sym('battery_monitor::Reading', 'message', 'weather.v1.Reading'),
  ],
  ghosts: [ghost('firmware/ports/hal_ports/include/hal/adc.hpp', 'out')],
  edges: [
    edge(`${F}#battery_monitor::BatteryMonitor::sample`, `${F}#battery_monitor::update_brownout`, { call: 1 }, { state: 'observed', conf: 0.85 }),
    edge(`${F}#battery_monitor::BatteryMonitor::sample`, `${F}#battery_monitor::kBrownoutMv`, { call: 1 }, { state: 'observed', conf: 0.5 }),
    edge(`${F}#battery_monitor::BatteryMonitor::BatteryMonitor`, `${F}#battery_monitor::BatteryMonitor::sample`, { call: 1 }, { state: 'observed', conf: 0.9 }),
    edge(`${F}#battery_monitor::BatteryMonitor`, `${F}#battery_monitor::Sink`, { inherit: 1 }, { state: 'observed', conf: 0.9 }),
    edge(`${F}#battery_monitor::update_brownout`, `${F}#battery_monitor::Level`, { call: 2 }, { state: 'observed', conf: 0.9 }),
    edge(`${F}#battery_monitor::BatteryMonitor::sample`, `${F}#battery_monitor::Reading`, { contract: 1 }, { state: 'observed', conf: 0.6 }),
    edge(`${F}#battery_monitor::BatteryMonitor::sample`, 'ghost:firmware/ports/hal_ports/include/hal/adc.hpp', { call: 1 }, { state: 'observed', conf: 0.85 }),
  ],
};

const show = (id, kind, name, o = {}) => mod(`shapes/${id}`, kind, name, o);
const kinds = {
  v: 1, rev: 'synthetic-kinds', lens: 'systems', at: 'shapes', crumbs: crumbs('.', 'shapes'),
  nodes: [
    show('system', 'system', 'system', { drill: 'systems', n: 4, brief: 'Double border, stacked squares glyph and child count.', badges: B({ crit: 'L1', status: 'approved', state: 'verified', cov: [8, 8] }) }),
    show('code', 'code', 'code', { brief: 'Plain rounded block.', badges: B({ cov: [2, 5] }) }),
    show('adapter', 'adapter', 'adapter', { brief: 'Notched corner.', badges: B({ status: 'draft' }) }),
    show('protocol', 'protocol', 'protocol', { brief: 'Hexagon.', badges: B({ cov: [3, 3], stale: 1 }) }),
    show('data', 'data', 'data', { brief: 'Cylinder.' }),
    show('tool', 'tool', 'tool', { brief: 'Gear glyph.', badges: B({ findings: 3 }) }),
    show('deploy', 'deploy', 'deploy', { brief: 'Dashed border.' }),
    show('host', 'host-service', 'host-service', { brief: 'Plug glyph.' }),
    show('study', 'study', 'study', { brief: 'Muted dashed.' }),
    { id: 'shapes/group', type: 'group', tier: 'sys', kind: 'group', name: 'group', drill: 'systems', n: 3, badges: B() },
    { id: 'shapes/:own', type: 'own', tier: 'sys', kind: 'own', name: 'shapes (own code)', badges: B() },
    { id: 'shapes#m:OUT', type: 'actor', tier: 'sys', kind: 'actor', name: 'Reading', badges: B() },
    { id: 'shapes#m:OP', type: 'actor', tier: 'sys', kind: 'ext', name: 'Operator', badges: B() },
    { id: 'shapes#m:P', type: 'actor', tier: 'sys', kind: 'req', name: 'REQ-STOR-001', badges: B() },
  ],
  ghosts: [], edges: [],
};

export const LEVELS = { root, child, cyclic, big: bigLevel(), code, file, kinds };

function synthChild(id) {
  const base = id.split('/').pop();
  const names = ['core', 'io', 'util', 'api'].slice(0, 2 + (base.length % 3));
  const nodes = names.map((x, i) => mod(`${id}/${x}`, i ? 'code' : 'system', `${base}_${x}`, { brief: `Part of ${base}.`, badges: B({ cov: [i + 1, 3] }) }));
  const edges = nodes.slice(1).map((n, i) => edge(nodes[i].id, n.id, { flow: 1 }, { labels: [i ? 'calls' : 'feeds'] }));
  return { v: 1, rev: 'synthetic-root', lens: 'systems', at: id, crumbs: crumbs('.', id), nodes, ghosts: [], edges };
}
export function childOf(id) {
  if (id === 'firmware') return LEVELS.child;
  if (id === 'firmware/sensing/battery_monitor/src') return LEVELS.file;
  return synthChild(id);
}

// ---------------------------------------------------------------- harness boot
const host = document.getElementById('map');
if (host) {
  let frozen = null;
  const clock = { now: () => (frozen ?? performance.now()), freeze() { frozen = performance.now(); return frozen; }, set(t) { frozen = t; }, release() { frozen = null; } };
  const tokens = () => Object.fromEntries(['bg', 's1', 's2', 's3', 'ink', 'soft', 'muted', 'line', 'faint', 'mint', 'lime', 'sand', 'rose'].map((k) => [k, getComputedStyle(document.documentElement).getPropertyValue('--' + k).trim()]));
  const events = [];
  const stack = [];
  let current = null;
  const engine = createEngine({
    host, tokens, now: clock.now,
    calm: () => matchMedia('(prefers-reduced-motion: reduce)').matches,
    on: {
      select: (id) => events.push({ ev: 'select', id }),
      activate: (id, o) => {
        events.push({ ev: 'activate', id, auto: !!(o && o.auto), t: clock.now() });
        const n = current && current.nodes.find((x) => x.id === id);
        if (!n || !n.drill || H.manual) return;
        const lv = childOf(id);
        stack.push(current); current = lv;
        engine.show(lv, { mode: 'drill', via: id });
      },
      up: (o) => {
        events.push({ ev: 'up', auto: !!(o && o.auto), t: clock.now() });
        if (!stack.length || H.manual) return;
        const from = current.at;
        current = stack.pop();
        engine.show(current, { mode: 'up', via: from });
      },
      ghost: (g) => events.push({ ev: 'ghost', id: g.id }),
      hover: (h) => { if (h) events.push({ ev: 'hover', type: h.type, id: h.id }); },
      peek: (id) => new Promise((res) => setTimeout(() => res(childOf(id)), 10)),
      view: (v) => events.push({ ev: 'view', at: v.at }),
    },
  });
  engine.minimap(document.getElementById('map-mini'));
  const H = window.H = {
    engine, levels: LEVELS, childOf, events, clock, layoutLevel, manual: false,
    show(name, mode = 'jump', via = null) {
      const lv = typeof name === 'string' ? LEVELS[name] : name;
      if (mode === 'drill') stack.push(current); else if (mode !== 'up' && mode !== 'refresh' && mode !== 'lens') stack.length = 0;
      current = lv;
      return engine.show(lv, { mode, via });
    },
    current: () => current,
    state: () => engine.state(),
    idle: async (ms = 3000) => { const t0 = performance.now(); while (performance.now() - t0 < ms) { const s = engine.state(); if (!s.mode && !s.animating) return true; await new Promise((r) => setTimeout(r, 30)); } return false; },
    frame: () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))),
  };
  const want = new URLSearchParams(location.search).get('level') || 'root';
  H.ready = H.show(want, 'jump').then(() => { H.ok = true; });
}
