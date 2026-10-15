// map/view.js — the Systems and Code views around the canvas engine: crumbs, search, tools, legend,
// details panel, tooltip, a11y list, keys, trace lifting and the level cache. Lazy-loaded by app.js.
// Repo text is data: the DOM gets textContent only; doc text goes through marked + DOMPurify as a fragment.
const SYS_KINDS = ['flow', 'dep'];
const CODE_KINDS = ['call', 'import', 'inherit', 'contract', 'data'];
const ALL_KINDS = [...SYS_KINDS, ...CODE_KINDS];
const KIND_LABEL = { flow: 'Flows (diagram)', dep: 'Uses (deps)', call: 'Calls', import: 'Imports', inherit: 'Inherits', contract: 'Contracts', data: 'Data' };
const CONF_STEPS = [[0, 'All'], [0.5, '≥ 0.5'], [0.8, '≥ 0.8']];
const ROLE_LABEL = { overview: 'Overview', brief: 'Brief', req: 'Requirements', icd: 'ICD', tests: 'Tests', resource: 'Resource', figure: 'Figure' };
const STATE_LABEL = { both: 'declared and traced', declared: 'declared · not traced', observed: 'observed in code', undeclared: 'undeclared coupling' };
const TOKENS = ['bg', 's1', 's2', 's3', 'ink', 'soft', 'muted', 'line', 'faint', 'mint', 'lime', 'sand', 'rose'];
const LRU_MAX = 64, PREFETCH_MAX = 8, PREFETCH_MS = 150, SEARCH_MS = 120, CONN_SHOWN = 8;
const MD_CFG = { FORBID_TAGS: ['style', 'form', 'input'], FORBID_ATTR: ['style'] };
const NS = 'http://www.w3.org/2000/svg';
const ICONS = {
  fit: 'M2.5 6V2.5H6M10 2.5h3.5V6M13.5 10v3.5H10M6 13.5H2.5V10',
  up: 'M8 13V3.5M3.8 7.7 8 3.5l4.2 4.2',
  filter: 'M2 3.5h12L9.4 8.8v4.2l-2.8-1.4V8.8z',
  compare: 'M2.5 5h7.5M2.5 11h11M11.5 3l2 2-2 2',
  health: 'M1.5 8.5h3l1.6-4.2 2.6 8 1.8-5.6 1.1 1.8h2.9',
  through: 'M7 2.5a4.5 4.5 0 1 0 0 9 4.5 4.5 0 1 0 0-9M10.3 10.3 14 14M7 5v4M5 7h4',
  untrace: 'M2 13c3-1 4-5 6-7s4-2.5 6-3M3 3l4 4M7 3 3 7',
  close: 'M4 4l8 8M12 4l-8 8',
  copy: 'M5.5 5.5h8v8h-8zM10.5 5.5v-2a1 1 0 0 0-1-1h-6a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2',
  legend: 'M2.5 4h1.5M6.5 4h7M2.5 8h1.5M6.5 8h7M2.5 12h1.5M6.5 12h7',
  search: 'M7 2.6a4.4 4.4 0 1 0 0 8.8 4.4 4.4 0 1 0 0-8.8M10.2 10.2 14 14',
};

const el = (tag, attrs = {}, ...kids) => { // attributes and text only: never markup
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === 'class') n.className = v;
    else if (k === 'text') n.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? '' : String(v));
  }
  for (const c of kids.flat()) if (c != null && c !== false) n.append(c);
  return n;
};
const svgEl = (tag, attrs = {}) => {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
  return n;
};
function icon(d, size = 16) {
  const s = svgEl('svg', { viewBox: '0 0 16 16', width: size, height: size, 'aria-hidden': 'true' });
  s.append(svgEl('path', { d }));
  return s;
}
const shortConf = (c) => (typeof c === 'number' ? c.toFixed(2).replace(/0$/, '') : '');
const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const shortQual = (id) => { // `a/b.cpp#ns::Cls::m` -> `Cls::m`, a file id -> its basename
  const [path, q] = String(id).split('#');
  if (!q) return path.split('/').at(-1);
  const sep = q.includes('::') ? '::' : '.';
  return q.split(sep).slice(-2).join(sep);
};

export function createMapView({ root, getJSON, openDoc, openSource, onState }) {
  const $ = (s) => root.querySelector(s);
  const mapEl = $('#map'), crumbsEl = $('#map-crumbs'), q = $('#map-q'), results = $('#map-results');
  const toolsEl = $('#map-tools'), legendEl = $('#map-legend'), mini = $('#map-mini'), panel = $('#map-panel');
  const tip = $('#map-tip'), a11y = $('#map-a11y'), status = $('#map-status'), empty = $('#map-empty'), load = $('#map-load');
  const calmQ = matchMedia('(prefers-reduced-motion: reduce)');
  const calm = () => calmQ.matches;
  const tokens = () => {
    const cs = getComputedStyle(document.documentElement);
    return Object.fromEntries(TOKENS.map((k) => [k, cs.getPropertyValue(`--${k}`).trim()]));
  };

  // ---------- state ----------
  let engine = null, enginePromise = null, active = false;
  let idx = null, byIdx = new Map();
  const levels = new Map(); // `${lens}\n${at}` -> Promise<level|null>, LRU
  let lens = 'systems', at = '.', sel = '', level = null;
  let levelNodes = new Map(), ghostIds = new Map(), edgeByPair = new Map(), ownId = null;
  let switchAt = null, switchVia = null; // where the walk left the Systems lens for Code ('leaf' hand-off or 'own' block)
  let navGen = 0, nav = Promise.resolve();
  let trace = null, panelData = null, panelTok = 0, searchTok = 0;
  let prefetching = 0, hoverTimer = 0, searchTimer = 0, loadTimer = 0;
  let health = false, autoDrill = true;
  const filters = {
    systems: { kinds: new Set(SYS_KINDS), minConf: 0, compare: false },
    code: { kinds: new Set(CODE_KINDS), minConf: 0.5, compare: false },
  };

  // ---------- index and level cache ----------
  async function loadIndex(force = false) {
    if (idx && !force) return false;
    const next = await getJSON('/api/map');
    const changed = !!idx && next.rev !== idx.rev;
    idx = next;
    byIdx = new Map((next.nodes || []).map((n) => [n.id, n]));
    if (changed) levels.clear();
    return changed;
  }
  function fetchLevel(l, a) { // null for 404 (cached); other failures are not cached
    const k = `${l}\n${a}`;
    let p = levels.get(k);
    if (p) { levels.delete(k); levels.set(k, p); return p; }
    p = getJSON(`/api/map/level?lens=${encodeURIComponent(l)}&at=${encodeURIComponent(a)}`).catch((err) => {
      if (err && err.status === 404) return null;
      if (levels.get(k) === p) levels.delete(k);
      throw err;
    });
    levels.set(k, p);
    while (levels.size > LRU_MAX) levels.delete(levels.keys().next().value);
    return p;
  }
  const nameOf = (id) => levelNodes.get(id)?.name || byIdx.get(id)?.name || (id === '.' ? idx?.repo : id.split(/[/#]/).at(-1)) || id;
  const drillOf = (n, l = lens) => (n && n.drill && typeof n.drill === 'object' ? n.drill[l] : n?.drill) || null;
  function drillLens(n) { // which lens drilling this level node opens, or null for a leaf
    if (!n) return null;
    if (n.type === 'own') return 'code';
    const d = drillOf(n);
    if (!d) return null;
    return lens === 'code' ? 'code' : d === 'systems' ? 'systems' : 'code';
  }
  function chainOf(id) { // root-first ids down to id, from the index (symbols hang off their file)
    if (id == null) return [];
    let base = id;
    if (!byIdx.has(base) && base.includes('#')) base = base.slice(0, base.indexOf('#'));
    if (!byIdx.has(base) && base.endsWith('/:own')) base = base.slice(0, -5) || '.';
    const out = [];
    for (let cur = base, guard = 0; cur != null && byIdx.has(cur) && guard < 256; guard++) {
      out.unshift(cur);
      cur = byIdx.get(cur).parent;
    }
    if (out.length && out[0] !== '.' && byIdx.has('.')) out.unshift('.');
    if (base !== id) out.push(id);
    return out;
  }
  const isAncestor = (a, id) => a !== id && chainOf(id).includes(a);

  // ---------- trace lifting: base ids -> what this level shows ----------
  function lift(full) { // full = root-first chain ending at the base node
    const i = full.indexOf(at);
    if (i >= 0) {
      if (i === full.length - 1) return null;
      for (let j = full.length - 1; j > i; j--) if (levelNodes.has(full[j])) return full[j]; // nearest shown (buckets, classes)
      return ownId; // a code-tier child in the Systems lens
    }
    const here = level?.crumbs?.map((c) => c.id) || chainOf(at);
    let k = 0;
    while (k < here.length && k < full.length && here[k] === full[k]) k++;
    for (let j = full.length - 1; j >= k; j--) if (ghostIds.has(`ghost:${full[j]}`)) return `ghost:${full[j]}`;
    return null;
  }
  function liftId(id, anc) {
    const full = anc ? [...anc, id] : chainOf(id);
    if (!anc && levelNodes.size && full.at(-1) !== id) full.push(id);
    const hit = lift(full);
    if (hit || anc) return hit;
    // a symbol inside a class the index does not hold: the longest level id that prefixes it
    let best = null;
    for (const nid of levelNodes.keys()) if ((id.startsWith(`${nid}::`) || id.startsWith(`${nid}.`)) && (!best || nid.length > best.length)) best = nid;
    return best;
  }
  function traceLight() {
    if (!trace || !level) return null;
    const nodes = new Map(), edges = new Set(), lifted = new Map();
    for (const [id, anc] of Object.entries(trace.nodes || {})) {
      const l = liftId(id, Array.isArray(anc) ? anc : []);
      lifted.set(id, l);
      if (l) nodes.set(l, (nodes.get(l) || 0) + 1);
    }
    for (const e of trace.edges || []) {
      const a = lifted.get(e.s), b = lifted.get(e.t);
      const eid = a && b && a !== b ? edgeByPair.get(`${a}\n${b}`) : null;
      if (eid) edges.add(eid);
    }
    return { nodes, edges };
  }
  const relight = () => engine?.highlight(traceLight());

  // ---------- engine ----------
  const handlers = {
    select: (id) => { clearTimeout(hoverTimer); tip.hidden = true; if ((id || '') !== sel) choose(id || ''); }, // the panel now says it
    activate: (id, o = {}) => {
      if (String(id).startsWith('ghost:')) { const g = ghostIds.get(id); if (g && !o.auto) onGhost(g); return; }
      drill(id, !!o.auto);
    },
    up: () => run(upOne),
    ghost: (g) => onGhost(g),
    hover: (hit, pos) => onHover(hit, pos),
    peek: (id) => {
      const n = levelNodes.get(id), l = drillLens(n);
      if (!l || n.type === 'own') return Promise.resolve(null);
      return fetchLevel(l, id).catch(() => null);
    },
    view: () => {},
  };
  function ensureEngine() {
    enginePromise ||= import('./engine.js').then(({ createEngine }) => {
      engine = createEngine({ host: mapEl, tokens, calm, on: handlers });
      if (new URLSearchParams(location.hash.slice(1)).get('test') === '1') mapEl.__engine = engine;
      engine.setAutoDrill?.(autoDrill);
      if (mini && engine.minimap) engine.minimap(mini);
    }).catch((err) => { enginePromise = null; throw err; });
    return enginePromise;
  }

  // ---------- navigation: one task at a time; a newer one supersedes the rest ----------
  function run(task) {
    const gen = ++navGen;
    const alive = () => gen === navGen;
    nav = nav.then(async () => {
      if (!alive()) return;
      const before = `${lens}\n${at}`;
      await task(alive);
      if (alive() && level) after(before !== `${lens}\n${at}`);
    }).catch((err) => fail(err));
    return nav;
  }
  function after(moved) { // once per task: crumbs, a11y list, announcements, hash
    const ae = document.activeElement;
    const refocus = active && !!ae && root.contains(ae) && !!ae.closest('#map-a11y, #map-crumbs, #map-panel'); // it is about to vanish
    renderCrumbs();
    renderA11y();
    const blocks = level.nodes?.length || 0;
    if (moved) say(`${lens === 'code' ? 'Code lens · inside' : 'Inside'} ${nameOf(at)}, ${plural(blocks, 'block')}`);
    empty.hidden = blocks > 0;
    if (!blocks) empty.textContent = `Nothing inside ${nameOf(at)} in the ${lens === 'code' ? 'Code' : 'Systems'} lens.`;
    toolsEl.querySelector('[data-tool="up"]')?.toggleAttribute('disabled', at === '.');
    toolsEl.querySelector('[data-tool="compare"]')?.toggleAttribute('disabled', lens !== 'systems');
    if (refocus) mapEl.focus({ preventScroll: true });
    emit();
  }
  const emit = () => onState?.({ lens, at, sel });
  function fail(err) {
    console.warn('map', err);
    loading(false);
    say('The map could not load this level.');
    if (!level) { empty.hidden = false; empty.textContent = 'The map could not load.'; }
  }
  function loading(on) {
    clearTimeout(loadTimer);
    if (!on) { load.hidden = true; return; }
    if (!level) load.hidden = false; // first paint: at once; later levels: only when slow
    else loadTimer = setTimeout(() => { load.hidden = false; }, 200);
  }
  let filterSig = '';
  function applyFilter(l) { // setFilter re-lays the current level, so only on a real change
    const f = filterFor(l), sig = `${[...f.kinds].sort().join(',')}@${f.minConf}`;
    if (sig === filterSig || !engine) return;
    filterSig = sig;
    engine.setFilter(f);
  }
  function filterFor(l) {
    const f = filters[l];
    const kinds = new Set(f.kinds);
    if (l === 'systems' && f.compare) for (const k of CODE_KINDS) kinds.add(k);
    return { kinds, minConf: f.minConf };
  }
  // Show one level. A Systems level that is not there (a leaf with code inside) hands off to the Code lens.
  async function show(l, a, { mode = 'jump', via = null } = {}) {
    loading(true);
    const ix = byIdx.get(a); // the index already knows a Systems leaf: skip the 404 round trip
    let lv = l === 'systems' && ix && drillOf(ix, 'systems') !== 'systems' ? null : await fetchLevel(l, a);
    if (!lv && l === 'systems') {
      lv = await fetchLevel('code', a);
      if (lv) {
        l = 'code';
        if (lens === 'systems' || !switchAt) { switchAt = a; switchVia = 'leaf'; }
        say(`Code lens: ${nameOf(a)} has no subsystems, showing its code`);
      }
    }
    loading(false);
    if (!lv) { say(`Nothing to open inside ${nameOf(a)}`); return false; }
    if (l === 'systems') { switchAt = null; switchVia = null; }
    lens = l; at = a; level = lv;
    levelNodes = new Map((lv.nodes || []).map((n) => [n.id, n]));
    ghostIds = new Map((lv.ghosts || []).map((g) => [g.id, g]));
    edgeByPair = new Map((lv.edges || []).map((e) => [`${e.s}\n${e.t}`, e.id]));
    ownId = (lv.nodes || []).find((n) => n.type === 'own')?.id || null;
    if (idx && lv.rev && lv.rev !== idx.rev) refresh(); // the server rebuilt: re-check the index
    if (sel && !levelNodes.has(sel) && !ghostIds.has(sel) && mode !== 'refresh' && mode !== 'lens') { sel = ''; closePanel(); }
    applyFilter(l);
    syncTools();
    clearTimeout(hoverTimer); tip.hidden = true; // the hovered thing belongs to the old level
    await engine.show(lv, { mode, via });
    if (sel && levelNodes.has(sel)) { engine.select(sel); reveal(sel); }
    relight();
    return true;
  }
  function drill(id, auto = false) {
    const n = levelNodes.get(id);
    if (!n) return;
    const l = drillLens(n);
    if (!l) { if (!auto) openLeaf(n); return; }
    if (n.type === 'own') { // the module's own code: same container, Code lens
      run(async () => {
        if (await show('code', at, { mode: 'drill', via: id })) { switchAt = at; switchVia = 'own'; sel = ''; closePanel(); }
      });
      return;
    }
    run(async () => {
      const wasSystems = lens === 'systems';
      sel = ''; closePanel();
      if (await show(l, id, { mode: 'drill', via: id }) && wasSystems && lens === 'code' && !switchAt) { switchAt = id; switchVia = 'leaf'; }
    });
  }
  async function upOne() {
    if (at === '.' || !level) return false;
    if (lens === 'code' && switchVia === 'own' && switchAt === at) { // back out of the own-code block
      const via = ownId || `${at}/:own`;
      return show('systems', at, { mode: 'up', via });
    }
    const crumbs = level.crumbs || [];
    const parent = crumbs.length > 1 ? crumbs.at(-2).id : byIdx.get(at)?.parent ?? '.';
    let l = lens;
    if (l === 'code' && switchAt && parent !== switchAt && isAncestor(parent, switchAt)) l = 'systems';
    return show(l, parent, { mode: 'up', via: at });
  }
  // Fly along a root-first chain of containers: up to the common ancestor, then down hop by hop.
  async function flyChain(alive, to, { lensWanted = lens, select = '', pulse = false } = {}) {
    if (!to.length) return false;
    const from = level?.crumbs?.map((c) => c.id) || chainOf(at);
    let k = 0;
    while (k < from.length && k < to.length && from[k] === to[k]) k++;
    const hops = (from.length - k) + (to.length - k);
    if (hops > 8 || !level) { // far away: one jump
      const target = to.at(-1);
      if (!(await show(hopLens(target, lensWanted), target, { mode: 'jump' }))) return false;
    } else {
      for (let i = from.length - 1; i >= k && alive(); i--) if (!(await upOne())) break;
      if (alive() && lensWanted !== lens && k === to.length) await show(lensWanted, at, { mode: 'lens' });
      for (let i = k; i < to.length && alive(); i++) {
        const target = to[i], before = lens;
        if (!(await show(hopLens(target, lensWanted), target, { mode: 'drill', via: target }))) break;
        if (before === 'systems' && lens === 'code' && !switchAt) { switchAt = target; switchVia = 'leaf'; }
      }
    }
    if (!alive()) return false;
    if (select) {
      sel = select;
      if (levelNodes.has(select) || ghostIds.has(select)) { engine.focus(select); if (pulse) engine.pulse(select); }
      openPanel(select);
    }
    return true;
  }
  function hopLens(target, wanted) { // stay in Systems while the index says there is a Systems level
    if (wanted === 'systems') return 'systems';
    if (lens === 'code') return 'code';
    return drillOf(byIdx.get(target), 'systems') === 'systems' ? 'systems' : 'code';
  }
  function flyTo(levelAt, { lensWanted = lens, select = '', pulse = true, chain = null } = {}) {
    const to = chain && chain.length ? chain : chainOf(levelAt);
    return run((alive) => flyChain(alive, to.length ? to : [levelAt], { lensWanted, select, pulse }));
  }
  async function flyToNode(id) { // a base node anywhere: its parent level, via the server's ancestor chain
    let d;
    try { d = await getJSON(`/api/map/node?id=${encodeURIComponent(id)}`); } catch { say(`Cannot find ${id}`); return; }
    const node = d.node || {};
    const chain = (d.chain || []).map((c) => c.id).filter((c) => c !== id);
    const parent = node.parent ?? chain.at(-1) ?? '.';
    if (chain.at(-1) !== parent) chain.push(parent);
    const l = node.tier === 'code' || byIdx.get(parent)?.tier === 'code' ? 'code' : lens;
    flyTo(parent, { lensWanted: l, select: id, pulse: true, chain });
  }
  function onGhost(g) {
    if (!g) return;
    const peer = g.peer || String(g.id).replace(/^ghost:/, '');
    const levelAt = g.at ?? byIdx.get(peer)?.parent ?? '.';
    flyTo(levelAt, { lensWanted: lens, select: peer, pulse: true });
  }
  function toggleLens() {
    const next = lens === 'systems' ? 'code' : 'systems';
    let target = at;
    if (next === 'systems') { // the nearest container that has a Systems level
      const ch = chainOf(at);
      while (ch.length > 1 && drillOf(byIdx.get(ch.at(-1)), 'systems') !== 'systems' && ch.at(-1) !== '.') ch.pop();
      target = ch.at(-1) || '.';
    }
    run(async () => {
      switchAt = null; switchVia = null;
      await show(next, target, { mode: target === at ? 'lens' : 'jump' });
    });
  }
  function walkTo(id) { // crumb click: up hop by hop
    run(async (alive) => {
      for (let guard = 0; at !== id && alive() && guard < 32; guard++) if (!(await upOne())) break;
    });
  }
  function openLeaf(n) {
    const s = n.src || (panelData?.node?.id === n.id ? panelData.node.src : null);
    if (s && s[0]) openSource(s[0], s[1], s[2]);
    else if (n.item) openDoc(n.item);
    else choose(n.id);
  }

  // ---------- selection and the details panel ----------
  function choose(id, { center = false } = {}) {
    sel = id || '';
    if (engine && (levelNodes.has(sel) || ghostIds.has(sel) || !sel)) {
      if (center && sel) engine.focus(sel); else engine.select(sel || null);
    }
    if (sel) openPanel(sel); else closePanel();
    for (const b of a11y.querySelectorAll('button')) b.setAttribute('aria-current', String(b.dataset.id === sel));
    if (active) emit();
  }
  function closePanel() {
    panelTok++;
    panelData = null;
    panel.hidden = true;
    panel.replaceChildren();
    root.classList.remove('has-panel');
  }
  function md(text) { // doc text: Markdown formatting yes, raw HTML no (shown as text), sanitised either way
    const safe = String(text).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c]);
    const P = globalThis.DOMPurify, M = globalThis.marked;
    if (!P || !M) return el('p', { text: String(text) });
    return P.sanitize(M.parse(safe), { ...MD_CFG, RETURN_DOM_FRAGMENT: true });
  }
  const chip = (text, cls = '', title = '') => el('span', { class: `chip ${cls}`.trim(), text, title: title || null });
  const section = (cls, title, ...kids) => el('section', { class: cls }, title ? el('h4', { text: title }) : null, ...kids);
  async function openPanel(id) {
    const tok = ++panelTok;
    const nid = String(id).replace(/^ghost:/, '');
    let d;
    try { d = await getJSON(`/api/map/node?id=${encodeURIComponent(nid)}`); } catch { d = null; }
    if (tok !== panelTok) return;
    if (!d || !d.node) {
      const g = ghostIds.get(id), n = levelNodes.get(id);
      if (!g && !n) { closePanel(); return; }
      d = { node: { id: nid, name: (g || n).name, type: n?.type || 'ghost', kind: n?.kind, path: g?.path }, chain: [], docs: [] };
    }
    panelData = d;
    renderPanel(d);
  }
  function renderPanel(d) {
    const n = d.node, b = n.badges || {};
    const chainText = (d.chain || []).map((c) => c.name).filter(Boolean).join(' › ');
    const close = el('button', { type: 'button', class: 'mp-x', 'aria-label': 'Close details', title: 'Close (Esc)', onclick: () => { choose(''); mapEl.focus({ preventScroll: true }); } }, icon(ICONS.close));
    const chips = el('div', { class: 'mp-chips' },
      chip([n.type, n.kind].filter((x, i, a) => x && a.indexOf(x) === i).join(' · ') || 'node', 'k'),
      n.lang ? chip(n.lang) : null,
      b.crit || n.crit ? chip(b.crit || n.crit, 'crit', 'criticality') : null,
      b.status || n.status ? chip(b.status || n.status, `st-${b.status || n.status}`, 'status') : null,
      b.state || n.state ? chip(b.state || n.state, `st-${b.state || n.state}`, 'trace state') : null,
      n.version ? chip(`v${String(n.version).replace(/^v/i, '')}`, '', 'version') : null,
      Array.isArray(b.cov) ? chip(`docs ${b.cov[0]}/${b.cov[1]}`, b.stale ? 'warn' : b.cov[0] >= b.cov[1] ? 'ok' : '', 'documented / public symbols') : null,
      b.stale ? chip(`${b.stale} stale`, 'warn') : null,
      b.findings ? chip(plural(b.findings, 'finding'), 'bad') : null,
      b.debt ? chip(`${b.debt} debt`, '', 'findings recorded as debt in the baseline') : null,
      n.type === 'symbol' && n.pub != null ? chip(n.pub ? 'public' : 'internal') : null,
      n.test ? chip('test') : null, n.vendor ? chip('vendor') : null,
      n.doc?.deprecated ? chip('deprecated', 'warn') : null);
    const parts = [el('header', { class: 'mp-head' },
      el('div', { class: 'mp-titles' }, el('h3', { class: 'mp-title', text: n.title || n.name || n.id }),
        chainText || n.path ? el('p', { class: 'mp-path', text: chainText || n.path }) : null),
      close), chips];
    if (n.sig) parts.push(el('pre', { class: 'mp-sig' }, el('code', { text: n.sig })));
    const doc = n.doc;
    const lead = doc?.brief || n.brief || n.summary;
    if (lead || doc?.text) {
      const box = el('div', { class: 'mp-doc md' });
      if (lead) box.append(md(lead));
      if (doc) {
        const params = Object.entries(doc.params || {});
        if (params.length) box.append(el('dl', { class: 'mp-params' }, params.flatMap(([k, v]) => [el('dt', { text: k }), el('dd', { text: v })])));
        if (doc.returns) box.append(el('p', { class: 'mp-ret' }, el('b', { text: 'Returns ' }), doc.returns));
        if (doc.raises?.length) box.append(el('p', { class: 'mp-ret' }, el('b', { text: 'Raises ' }), doc.raises.join(', ')));
        if (doc.text && doc.text.trim() !== String(lead || '').trim()) {
          box.append(el('details', { class: 'mp-full' }, el('summary', { text: 'Full comment' }), md(doc.text)));
        }
        if (n.doc_src === 'decl') box.append(el('p', { class: 'mp-note', text: 'Doc from the header declaration' }));
      }
      box.addEventListener('click', (e) => {
        const a = e.target.closest('a[href]');
        if (!a) return;
        if (/^https?:/i.test(a.getAttribute('href'))) { a.target = '_blank'; a.rel = 'noopener noreferrer'; } else e.preventDefault();
      });
      parts.push(box);
    } else if (n.type === 'symbol' || n.type === 'file') {
      parts.push(el('p', { class: 'mp-doc mp-none', text: 'No doc comment.' }));
    }
    const docs = (d.docs || []).filter((x) => x && x.item);
    const icd = n.icd && n.icd.item ? n.icd : null;
    const icdBtn = icd ? el('button', {
      type: 'button', class: 'btn sm mp-icd', title: icd.head ? `${icd.item} § ${icd.head}` : icd.item, text: icd.head ? `ICD · ${icd.head}` : 'ICD',
      onclick: () => openDoc(icd.item, icd.head || ''),
    }) : null;
    if (docs.length || icdBtn) { // the node's own ICD section replaces the plain ICD document button
      const btns = docs.filter((x) => !(icdBtn && x.role === 'icd' && x.item === icd.item)).map((x) => el('button', {
        type: 'button', class: 'btn sm', title: x.title || x.item, text: ROLE_LABEL[x.role] || x.role || 'Doc',
        onclick: () => openDoc(x.item),
      }));
      parts.push(section('mp-docs', 'Documents', el('div', { class: 'mp-row' }, btns, icdBtn)));
    }
    const srcRows = [];
    const tail = (t, max = 40) => (t.length > max ? '…' + t.slice(t.length - max + 1) : t); // the file name and line matter most
    if (Array.isArray(n.src) && n.src[0]) {
      const [p, a, e] = n.src;
      srcRows.push(el('button', { type: 'button', class: 'btn sm mono', title: `Show the source (s): ${p}:${a || 1}`, onclick: () => openSource(p, a, e) }, tail(`${p}:${a || 1}`)));
    }
    if (Array.isArray(n.decl) && n.decl[0]) {
      const [p, a] = n.decl;
      srcRows.push(el('button', { type: 'button', class: 'btn sm mono', title: `Declaration: ${p}:${a || 1}`, onclick: () => openSource(p, a, a) }, 'decl ' + tail(`${p}:${a || 1}`, 35)));
    }
    if (srcRows.length) parts.push(section('mp-src', 'Source', el('div', { class: 'mp-row' }, srcRows)));
    if (d.reqs?.length) {
      parts.push(section('mp-reqs', 'Requirements', el('div', { class: 'mp-row' }, d.reqs.map((r) => el('button', {
        type: 'button', class: 'chip req', title: r.title || r.id, text: r.id,
        onclick: () => (r.item ? openDoc(r.item, r.id) : null), disabled: !r.item,
      })))));
    }
    const conn = [['Callers', d.callers], ['Callees', d.callees], ['Implementations', d.impls], ['Implements', d.implements], ['Tests', d.tests]]
      .filter(([, rows]) => rows && rows.length);
    if (conn.length) parts.push(el('section', { class: 'mp-conn' }, conn.map(([title, rows]) => connGroup(title, rows, n.id))));
    if (d.findings?.length) {
      const lines = d.findings.map(String);
      const copy = el('button', { type: 'button', class: 'mp-copy', title: 'Copy findings', 'aria-label': 'Copy findings' }, icon(ICONS.copy, 14));
      copy.onclick = async () => {
        try { await navigator.clipboard.writeText(lines.join('\n')); copy.classList.add('done'); setTimeout(() => copy.classList.remove('done'), 1200); } catch { /* clipboard blocked */ }
      };
      parts.push(section('mp-find', `Findings (${lines.length})`, copy, el('ul', { class: 'mp-flist' }, lines.map(findingRow))));
    }
    const ln = levelNodes.get(n.id);
    const canDrill = !!(ln && drillLens(ln));
    const openable = n.item || (Array.isArray(n.src) && n.src[0]);
    const act = el('div', { class: 'mp-act' },
      canDrill ? el('button', { type: 'button', class: 'btn sm primary', text: 'Drill', title: 'Open this block (Enter)', onclick: () => drill(n.id) }) : null,
      el('button', { type: 'button', class: 'btn sm', text: 'Trace ↑', title: 'Who calls this', onclick: () => traceFrom(n.id, 'in') }),
      el('button', { type: 'button', class: 'btn sm', text: 'Trace ↓', title: 'What this calls', onclick: () => traceFrom(n.id, 'out') }),
      openable ? el('button', { type: 'button', class: 'btn sm', text: 'Open', title: n.item ? 'Read its doc (o)' : 'Show the source (s)', onclick: () => (n.item ? openDoc(n.item) : openSource(...n.src)) }) : null,
      el('button', { type: 'button', class: 'btn sm', text: lens === 'systems' ? 'Show in Code' : 'Show in Systems', title: 'Switch lens (l)', onclick: toggleLens }));
    parts.push(act);
    panel.replaceChildren(...parts);
    panel.hidden = false;
    root.classList.add('has-panel');
    reveal(n.id);
  }
  // Keep the selected block clear of the panel (a bottom sheet on phones): glide it into the free area, same zoom.
  let revealRaf = 0;
  function reveal(id) {
    cancelAnimationFrame(revealRaf);
    if (!engine || !id || panel.hidden) return;
    const until = performance.now() + 2000;
    const check = () => {
      if (panel.hidden || sel !== id) return;
      if (engine.state().animating && performance.now() < until) { revealRaf = requestAnimationFrame(check); return; } // after the drill
      const r = engine.rects()[id];
      if (!r) return;
      const h = mapEl.getBoundingClientRect(), p = panel.getBoundingClientRect();
      const top = Math.max(crumbsEl.getBoundingClientRect().bottom, p.left - h.left < 8 ? $('#map-search').getBoundingClientRect().bottom : 0);
      const box = p.left - h.left < 8 // bottom sheet: the free area is above it
        ? { x0: 12, x1: h.width - 12, y0: top - h.top + 10, y1: p.top - h.top - 12 }
        : { x0: 16, x1: p.left - h.left - 20, y0: top - h.top + 10, y1: h.height - 16 };
      const need = (a, b, lo, hi) => (a >= lo && b <= hi ? 0 : (lo + hi) / 2 - (a + b) / 2);
      const dx = need(r.x, r.x + r.w, box.x0, box.x1), dy = need(r.y, r.y + r.h, box.y0, box.y1);
      if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return;
      if (calm()) { engine.panBy(dx, dy); return; }
      const t0 = performance.now();
      let done = 0;
      const step = (t) => {
        const e = 1 - (1 - Math.min(1, (t - t0) / 280)) ** 3; // easeOutCubic
        engine.panBy(dx * e - dx * done, dy * e - dy * done); done = e;
        if (e < 1) revealRaf = requestAnimationFrame(step);
      };
      revealRaf = requestAnimationFrame(step);
    };
    revealRaf = requestAnimationFrame(check);
  }
  /** Text nodes with <wbr> break chances after `/`, `::` and `.`, so ids and paths wrap between segments. */
  function breakable(text) {
    const out = [];
    for (const part of String(text).split(/(?<=\/|::|\.)/)) { if (out.length) out.push(document.createElement('wbr')); out.push(part); }
    return out;
  }
  function findingRow(line) { // `CODE      module  id  files  → action` (Finding.line) as code · id / files / action
    const cut = line.indexOf('  → ');
    const [code = '', , id = '', ...files] = (cut < 0 ? line : line.slice(0, cut)).split(/\s{2,}/);
    const bad = code.startsWith('E:');
    return el('li', { title: line },
      el('div', { class: 'mf-top' }, el('span', { class: `mf-code${bad ? ' bad' : ''}`, text: code }), el('code', { class: 'mf-id' }, breakable(id))),
      files.length ? el('code', { class: 'mf-files' }, breakable(files.join('  '))) : null,
      cut < 0 ? null : el('p', { class: 'mf-act', text: line.slice(cut + 4) }));
  }
  function connGroup(title, rows, selfId) {
    const list = el('ul', { class: 'mp-list' });
    const draw = (all) => list.replaceChildren(...rows.slice(0, all ? rows.length : CONN_SHOWN).map((r) => {
      const b = el('button', { type: 'button', class: 'mp-item', title: r.path || r.id },
        el('span', { class: 'nm', text: r.name || r.id }),
        r.path ? el('small', { text: r.path }) : null,
        typeof r.conf === 'number' ? el('span', { class: `cf ${r.conf >= 0.8 ? 'hi' : r.conf >= 0.5 ? 'mid' : 'lo'}`, text: shortConf(r.conf), title: r.why ? `confidence ${r.conf} · ${r.why}` : `confidence ${r.conf}` }) : null);
      if (title === 'Tests' && Array.isArray(r.src)) b.onclick = () => openSource(...r.src);
      else b.onclick = () => flyToNode(r.id);
      const light = () => {
        const a = liftId(selfId), z = liftId(r.id);
        if (!a || !z) return;
        const eid = edgeByPair.get(`${a}\n${z}`) || edgeByPair.get(`${z}\n${a}`);
        engine?.highlight({ nodes: new Map([[a, 1], [z, 1]]), edges: new Set(eid ? [eid] : []) });
      };
      b.addEventListener('pointerenter', light); b.addEventListener('focus', light);
      b.addEventListener('pointerleave', relight); b.addEventListener('blur', relight);
      return el('li', {}, b);
    }));
    draw(false);
    const more = rows.length > CONN_SHOWN ? el('button', { type: 'button', class: 'mp-more', text: `Show all ${rows.length}` }) : null;
    if (more) more.onclick = () => { draw(true); more.remove(); };
    return el('div', { class: 'mp-group' }, el('h4', {}, title, el('small', { text: String(rows.length) })), list, more);
  }

  // ---------- trace ----------
  async function traceFrom(id, dir = 'both') {
    let t;
    try { t = await getJSON(`/api/map/trace?id=${encodeURIComponent(id)}&dir=${dir}&depth=2`); } catch { t = null; }
    if (!t || !t.nodes) { say(`Nothing to trace from ${nameOf(id)}`); return; }
    trace = { ...t, id, dir };
    relight();
    syncTools();
    const n = Object.keys(t.nodes).length - 1;
    say(`Tracing ${dir === 'in' ? 'callers of' : dir === 'out' ? 'callees of' : 'calls around'} ${nameOf(id)}: ${plural(Math.max(0, n), 'symbol')}`);
  }
  function clearTrace() { trace = null; relight(); syncTools(); say('Trace cleared'); }

  // ---------- hover: tooltip and prefetch ----------
  function onHover(hit, pos) {
    clearTimeout(hoverTimer);
    if (!hit || !pos || !level) { tip.hidden = true; return; }
    let body = null;
    if (hit.type === 'edge') body = edgeTip((level.edges || []).find((e) => e.id === hit.id));
    else if (hit.type === 'ghost') {
      const g = ghostIds.get(hit.id);
      if (g) body = [el('b', { text: g.name }), el('p', { text: `outside · ${g.path || g.peer}` }), el('p', { class: 'dim', text: 'Click to go there' })];
    } else {
      const n = levelNodes.get(hit.id);
      if (n) {
        body = [el('span', { class: 'tk', text: [n.type, n.kind].filter((x, i, a) => x && a.indexOf(x) === i).join(' · ') }), el('b', { text: n.title || n.name })];
        if (n.brief) body.push(el('p', { text: n.brief }));
        if (drillLens(n)) body.push(el('p', { class: 'dim', text: `${n.n ? plural(n.n, 'item') + ' inside · ' : ''}double-click to open` }));
        const l = drillLens(n);
        if (l && n.type !== 'own') hoverTimer = setTimeout(() => {
          if (prefetching >= PREFETCH_MAX) return;
          prefetching++;
          fetchLevel(l, n.id).catch(() => null).finally(() => { prefetching--; });
        }, PREFETCH_MS);
      }
    }
    const open = !panel.hidden && panel.offsetWidth > 0;
    if (!body || (sel && hit.id === sel)) { tip.hidden = true; return; } // the selection's panel already shows it
    tip.replaceChildren(...body);
    tip.hidden = false;
    const box = root.getBoundingClientRect(), host = mapEl.getBoundingClientRect();
    const x = pos.x + host.left - box.left, y = pos.y + host.top - box.top;
    const w = tip.offsetWidth, h = tip.offsetHeight;
    let left = Math.max(8, Math.min(x + 14, box.width - w - 8));
    const top = Math.max(8, y + 18 + h > box.height ? y - h - 12 : y + 18);
    if (open) { // never cover the details panel: flip left of the cursor, else hide
      const pr = panel.getBoundingClientRect(), px0 = pr.left - box.left, py0 = pr.top - box.top;
      const over = (l) => l < px0 + pr.width && l + w > px0 && top < py0 + pr.height && top + h > py0;
      if (over(left)) left = x - w - 14;
      if (left < 8 || over(left)) { tip.hidden = true; return; }
    }
    tip.style.left = `${left}px`;
    tip.style.top = `${top}px`;
  }
  function edgeTip(e) {
    if (!e) return null;
    const kinds = Object.entries(e.kinds || {}).map(([k, c]) => (c > 1 ? `${k} ×${c}` : k)).join(' · ');
    const out = [el('span', { class: 'tk', text: kinds || 'edge' }), el('b', { text: `${nameOf(e.s)} → ${nameOf(e.t)}` })];
    if (e.labels?.length) out.push(el('p', { text: e.labels.join(' · ') }));
    const meta = [STATE_LABEL[e.state] || e.state, typeof e.conf === 'number' ? `conf ${shortConf(e.conf)}` : '', e.n > 1 ? `${e.n} links` : ''].filter(Boolean).join(' · ');
    if (meta) out.push(el('p', { class: e.state === 'undeclared' ? 'bad' : 'dim', text: meta }));
    const samples = (e.samples || []).slice(0, 5);
    if (samples.length) {
      out.push(el('ul', { class: 'tip-samples' }, samples.map((s) => el('li', {},
        el('code', { text: `${shortQual(s.s)} → ${shortQual(s.t)}` }),
        el('small', { text: `${s.k}${s.why ? ` · ${s.why}` : ''}${typeof s.conf === 'number' ? ` · ${shortConf(s.conf)}` : ''}${s.file ? ` · ${s.file.split('/').at(-1)}:${s.line}` : ''}` })))));
    } else if (e.prov?.length) out.push(el('p', { class: 'dim', text: `from ${e.prov.slice(0, 2).join(', ')}` }));
    return out;
  }

  // ---------- crumbs, a11y list, status ----------
  function renderCrumbs() {
    const cs = level?.crumbs?.length ? level.crumbs : [{ id: at, name: nameOf(at) }];
    const kids = [];
    cs.forEach((c, i) => {
      if (i) kids.push(el('span', { class: 'sep', 'aria-hidden': 'true', text: '›' }));
      if (lens === 'code' && switchAt === c.id) {
        kids.push(el('span', { class: 'lens-glyph', title: 'Code lens from here', role: 'img', 'aria-label': 'Code lens from here', text: '</>' }));
      }
      const last = i === cs.length - 1;
      kids.push(el('button', { type: 'button', class: last ? 'crumb cur' : 'crumb', 'aria-current': last ? 'location' : null, text: c.name || c.id, onclick: last ? null : () => walkTo(c.id) }));
    });
    crumbsEl.replaceChildren(...kids);
    crumbsEl.scrollLeft = crumbsEl.scrollWidth;
  }
  function renderA11y() {
    const deg = new Map();
    for (const e of level.edges || []) for (const id of [e.s, e.t]) deg.set(id, (deg.get(id) || 0) + 1);
    let order = [];
    try { order = engine.order() || []; } catch { order = []; }
    if (!order.length) order = [...levelNodes.keys(), ...ghostIds.keys()];
    const seen = new Set();
    a11y.replaceChildren(...order.filter((id) => (levelNodes.has(id) || ghostIds.has(id)) && !seen.has(id) && seen.add(id)).map((id) => {
      const n = levelNodes.get(id), g = ghostIds.get(id);
      const label = n ? `${n.name}, ${n.kind || n.type}, ${plural(n.n || 0, 'child', 'children')}, ${plural(deg.get(id) || 0, 'connection')}`
        : `${g.name}, outside in ${g.path || g.peer}, ${plural(deg.get(id) || 0, 'connection')}`;
      const b = el('button', { type: 'button', 'aria-label': label, 'aria-current': String(id === sel), text: n ? n.name : g.name });
      b.dataset.id = id;
      b.addEventListener('focus', () => { if (sel !== id) choose(id, { center: true }); else engine.focus(id); });
      b.addEventListener('click', () => (g ? onGhost(g) : drill(id)));
      return el('li', {}, b);
    }));
  }
  const say = (t) => { status.textContent = ''; requestAnimationFrame(() => { status.textContent = t; }); };

  // ---------- search ----------
  let hits = [], hitAt = -1, hitsFor = '';
  async function search(now = false) {
    clearTimeout(searchTimer);
    const text = q.value.trim().slice(0, 200);
    const tok = ++searchTok;
    if (!text) { closeResults(); return; }
    if (!now) { await new Promise((ok) => { searchTimer = setTimeout(ok, SEARCH_MS); }); if (tok !== searchTok) return; }
    let rows;
    try { rows = await getJSON(`/api/map/search?q=${encodeURIComponent(text)}&limit=20`); } catch { rows = []; }
    if (tok !== searchTok) return;
    hits = Array.isArray(rows) ? rows : [];
    hitsFor = text;
    hitAt = hits.length ? 0 : -1;
    renderResults();
  }
  function renderResults() {
    q.setAttribute('aria-expanded', String(true));
    results.hidden = false;
    if (!hits.length) {
      results.replaceChildren(el('li', { class: 'res none', role: 'option', 'aria-disabled': 'true', text: 'No matches' }));
      q.removeAttribute('aria-activedescendant');
      return;
    }
    results.replaceChildren(...hits.map((r, i) => {
      const li = el('li', { class: 'res', role: 'option', id: `map-res-${i}`, 'aria-selected': String(i === hitAt) },
        el('span', { class: 'nm', text: r.name }), el('small', { text: [r.kind || r.type, r.path].filter(Boolean).join(' · ') }));
      li.addEventListener('pointerdown', (e) => e.preventDefault()); // keep focus in the box
      li.addEventListener('click', () => pick(r));
      return li;
    }));
    q.setAttribute('aria-activedescendant', `map-res-${hitAt}`);
  }
  function closeResults() {
    results.hidden = true;
    results.replaceChildren();
    q.setAttribute('aria-expanded', 'false');
    q.removeAttribute('aria-activedescendant');
    hits = []; hitAt = -1; hitsFor = '';
  }
  function pick(r) {
    closeResults();
    q.blur();
    mapEl.focus({ preventScroll: true });
    const levelAt = r.at ?? byIdx.get(r.id)?.parent ?? '.';
    flyTo(levelAt, { lensWanted: r.lens === 'code' ? 'code' : 'systems', select: r.id, pulse: true });
  }
  q.addEventListener('input', () => search());
  q.addEventListener('keydown', async (e) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!hits.length) return;
      hitAt = (hitAt + (e.key === 'ArrowDown' ? 1 : -1) + hits.length) % hits.length;
      renderResults();
      results.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const text = q.value.trim();
      if (!text) return;
      if (results.hidden || hitsFor !== text.slice(0, 200)) await search(true);
      if (hits[hitAt >= 0 ? hitAt : 0]) pick(hits[hitAt >= 0 ? hitAt : 0]);
    } else if (e.key === 'Escape') {
      e.preventDefault(); e.stopPropagation();
      if (q.value) { q.value = ''; closeResults(); } else { q.blur(); mapEl.focus({ preventScroll: true }); }
    }
  });
  q.addEventListener('blur', () => setTimeout(() => { if (document.activeElement !== q) closeResults(); }, 120));

  // ---------- tools, filters popover, legend ----------
  const tool = (name, label, d, onclick, toggle = false) => {
    const b = el('button', { type: 'button', class: 'tool', 'data-tool': name, title: label, 'aria-label': label, 'aria-pressed': toggle ? 'false' : null, onclick }, icon(d));
    return b;
  };
  let pop = null;
  function buildTools() {
    toolsEl.replaceChildren(
      tool('fit', 'Fit to view (0)', ICONS.fit, () => engine?.fit(true)),
      tool('up', 'Up one level (Backspace)', ICONS.up, () => run(upOne)),
      el('span', { class: 'tsep', 'aria-hidden': 'true' }),
      tool('filters', 'Edge filters', ICONS.filter, () => togglePop()),
      tool('compare', 'Compare with code: show observed links in Systems', ICONS.compare, () => { filters.systems.compare = !filters.systems.compare; applyFilter(lens); syncTools(); }, true),
      tool('health', 'Doc health overlay (h)', ICONS.health, () => setHealth(!health), true),
      tool('through', 'Zoom through blocks', ICONS.through, () => { autoDrill = !autoDrill; engine?.setAutoDrill(autoDrill); syncTools(); }, true),
      tool('untrace', 'Clear the trace', ICONS.untrace, clearTrace));
    toolsEl.querySelector('[data-tool="filters"]').setAttribute('aria-expanded', 'false');
    toolsEl.querySelector('[data-tool="filters"]').setAttribute('aria-haspopup', 'dialog');
    syncTools();
  }
  function syncTools() {
    const set = (name, on) => toolsEl.querySelector(`[data-tool="${name}"]`)?.setAttribute('aria-pressed', String(!!on));
    set('compare', filters.systems.compare && lens === 'systems');
    set('health', health); set('through', autoDrill);
    const un = toolsEl.querySelector('[data-tool="untrace"]');
    if (un) un.hidden = !trace;
    if (pop && !pop.hidden) fillPop();
  }
  function setHealth(on) { health = on; engine?.setOverlay(on ? 'health' : 'none'); syncTools(); say(on ? 'Doc health overlay on' : 'Doc health overlay off'); }
  function togglePop(force) {
    pop ||= el('div', { class: 'mt-pop', role: 'dialog', 'aria-label': 'Edge filters', hidden: true });
    if (!pop.isConnected) root.append(pop);
    const open = force ?? pop.hidden;
    pop.hidden = !open;
    toolsEl.querySelector('[data-tool="filters"]')?.setAttribute('aria-expanded', String(open));
    if (open) { fillPop(); pop.querySelector('input')?.focus(); }
  }
  function fillPop() {
    const f = filters[lens];
    const kinds = el('fieldset', {}, el('legend', { text: `Links shown · ${lens === 'code' ? 'Code' : 'Systems'}` }),
      ALL_KINDS.map((k) => {
        const box = el('input', { type: 'checkbox', value: k });
        box.checked = f.kinds.has(k);
        box.onchange = () => { if (box.checked) f.kinds.add(k); else f.kinds.delete(k); applyFilter(lens); };
        return el('label', { class: `k-${k}` }, box, el('i', { 'aria-hidden': 'true' }), KIND_LABEL[k]);
      }));
    const conf = el('fieldset', {}, el('legend', { text: 'Minimum confidence' }), el('div', { class: 'seg' }, CONF_STEPS.map(([v, label]) => {
      const r = el('input', { type: 'radio', name: 'map-conf', value: String(v) });
      r.checked = f.minConf === v;
      r.onchange = () => { f.minConf = v; applyFilter(lens); };
      return el('label', {}, r, el('span', { text: label }));
    })));
    const reset = el('button', { type: 'button', class: 'btn sm', text: 'Defaults', onclick: () => {
      f.kinds = new Set(lens === 'code' ? CODE_KINDS : SYS_KINDS); f.minConf = lens === 'code' ? 0.5 : 0;
      applyFilter(lens); fillPop();
    } });
    pop.replaceChildren(kinds, conf, el('div', { class: 'end' }, reset));
  }
  root.addEventListener('pointerdown', (e) => {
    if (pop && !pop.hidden && !pop.contains(e.target) && !e.target.closest('[data-tool="filters"]')) togglePop(false);
  });

  const LEGEND_KEY = 'wiki.map.legend';
  function buildLegend() {
    let open = false;
    try { open = localStorage.getItem(LEGEND_KEY) === '1'; } catch { /* no storage */ }
    const sw = (draw, cls = '') => { const s = svgEl('svg', { viewBox: '0 0 28 16', width: 28, height: 16, class: `lg ${cls}`, 'aria-hidden': 'true' }); draw(s); return s; };
    const add = (s, tag, attrs) => { s.append(svgEl(tag, attrs)); return s; };
    const row = (svg, label) => el('li', {}, svg, el('span', { text: label }));
    const blocks = [
      [sw((s) => { add(s, 'rect', { x: 2, y: 2, width: 24, height: 12, rx: 3 }); add(s, 'rect', { x: 4.5, y: 4.5, width: 19, height: 7, rx: 1.8 }); }, 'c-mint'), 'system'],
      [sw((s) => add(s, 'rect', { x: 2, y: 2, width: 24, height: 12, rx: 3 }), 'c-mint'), 'code'],
      [sw((s) => add(s, 'path', { d: 'M2 5 5 2h21v12H2z' }), 'c-mint'), 'adapter'],
      [sw((s) => add(s, 'path', { d: 'M7 2h14l5 6-5 6H7L2 8z' }), 'c-lime'), 'protocol'],
      [sw((s) => { add(s, 'path', { d: 'M4 4v8c0 1.4 4.5 2.5 10 2.5s10-1.1 10-2.5V4' }); add(s, 'ellipse', { cx: 14, cy: 4, rx: 10, ry: 2.4 }); }, 'c-sand'), 'data'],
      [sw((s) => add(s, 'rect', { x: 2, y: 3, width: 24, height: 11, rx: 3, 'stroke-dasharray': '3 2' }), 'c-muted'), 'group · deploy'],
      [sw((s) => add(s, 'rect', { x: 2, y: 3, width: 24, height: 10, rx: 5 }), 'c-soft'), 'actor'],
      [sw((s) => add(s, 'path', { d: 'M3 2h17l5 5v7H3zM20 2v5h5' }), 'c-soft'), 'file'],
      [sw((s) => add(s, 'rect', { x: 4, y: 4.5, width: 20, height: 7, rx: 3.5 }), 'c-soft'), 'function · method'],
      [sw((s) => add(s, 'path', { d: 'M26 3H9a5 5 0 0 0 0 10h17', 'stroke-dasharray': '3 2' }), 'c-muted'), 'outside this level'],
    ];
    const line = (attrs, cls, head = 'arrow') => sw((s) => {
      add(s, 'path', { d: 'M2 8h20', ...attrs });
      if (head === 'arrow') add(s, 'path', { d: 'M20 4.5 25 8l-5 3.5', fill: 'none' });
      if (head === 'tri') add(s, 'path', { d: 'M20 4.5 25.5 8 20 11.5z' });
      if (head === 'bang') add(s, 'circle', { cx: 25, cy: 8, r: 2.2, class: 'fill' });
    }, cls);
    const edges = [
      [line({ 'stroke-width': 2 }, 'c-mint'), 'flow · declared and traced'],
      [line({ 'stroke-dasharray': '4 3' }, 'c-mint'), 'declared · not traced'],
      [line({ 'stroke-dasharray': '1.2 2.6' }, 'c-muted'), 'uses (deps)'],
      [line({ 'stroke-width': 1.3, opacity: 0.75 }, 'c-mint'), 'observed in code'],
      [line({ 'stroke-width': 1.6 }, 'c-rose', 'bang'), 'undeclared coupling'],
      [line({}, 'c-muted', 'tri'), 'inherits'],
      [line({ 'stroke-dasharray': '5 2 1 2' }, 'c-sand'), 'contract · data'],
      [line({ 'stroke-width': 2 }, 'c-lime'), 'traced'],
    ];
    const dot = (cls, text) => el('li', {}, el('i', { class: `pip ${cls}`, 'aria-hidden': 'true' }), el('span', { text }));
    const body = el('div', { class: 'lg-body', id: 'map-legend-body', hidden: !open },
      el('h3', { text: 'Blocks' }), el('ul', {}, blocks.map(([s, t]) => row(s, t))),
      el('h3', { text: 'Links' }), el('ul', {}, edges.map(([s, t]) => row(s, t))),
      el('h3', { text: 'Badges' }), el('ul', { class: 'pips' }, dot('ok', 'approved · verified'), dot('warn', 'draft · stale docs'), dot('bad', 'drift · findings'), dot('none', 'no doc data')));
    const btn = el('button', { type: 'button', class: 'lg-toggle', 'aria-expanded': String(open), 'aria-controls': 'map-legend-body' }, icon(ICONS.legend, 14), el('span', { text: 'Legend' }));
    btn.onclick = () => {
      const on = body.hidden;
      body.hidden = !on; btn.setAttribute('aria-expanded', String(on));
      try { localStorage.setItem(LEGEND_KEY, on ? '1' : '0'); } catch { /* no storage */ }
    };
    legendEl.replaceChildren(btn, body);
  }

  // ---------- keys (on the map and its a11y list) ----------
  function nearest(dir) {
    let rects;
    try { rects = engine.rects() || {}; } catch { return null; }
    const ids = Object.keys(rects).filter((id) => levelNodes.has(id) || ghostIds.has(id));
    if (!ids.length) return null;
    const from = rects[sel];
    if (!from) return (engine.order?.() || ids).find((id) => rects[id]) || ids[0];
    const cx = from.x + from.w / 2, cy = from.y + from.h / 2;
    let best = null, score = Infinity;
    for (const id of ids) {
      if (id === sel) continue;
      const r = rects[id], dx = r.x + r.w / 2 - cx, dy = r.y + r.h / 2 - cy;
      const along = dir === 'ArrowRight' ? dx : dir === 'ArrowLeft' ? -dx : dir === 'ArrowDown' ? dy : -dy;
      const across = dir === 'ArrowRight' || dir === 'ArrowLeft' ? Math.abs(dy) : Math.abs(dx);
      if (along <= 1) continue;
      const s = along + 2 * across;
      if (s < score) { score = s; best = id; }
    }
    return best;
  }
  function selected() { return levelNodes.get(sel) || (panelData?.node?.id === sel ? panelData.node : null); }
  document.addEventListener('keydown', (e) => { // on the map, its a11y list, the panel, or nothing focused at all
    if (!active || !engine || e.metaKey || e.ctrlKey || e.altKey || e.defaultPrevented) return;
    const t = e.target, idle = t === document.body || t === document.documentElement;
    if (!idle && !root.contains(t)) return;
    if (t === q || t.closest?.('.mt-pop') || document.body.classList.contains('drawer')) return;
    const onMap = idle || t === mapEl || !!t.closest('#map-a11y');
    const k = e.key;
    if (k === 'Escape') {
      if (pop && !pop.hidden) togglePop(false);
      else if (!panel.hidden) { choose(''); mapEl.focus({ preventScroll: true }); }
      else run(upOne);
      e.preventDefault();
      return;
    }
    if (!onMap) return;
    if ((k === 'Enter' || k === ' ') && !idle && t !== mapEl) return; // a11y buttons click natively
    if (k.startsWith('Arrow')) {
      if (e.shiftKey) {
        const step = 80;
        engine.panBy(k === 'ArrowLeft' ? step : k === 'ArrowRight' ? -step : 0, k === 'ArrowUp' ? step : k === 'ArrowDown' ? -step : 0);
      } else {
        const id = nearest(k);
        if (id) { choose(id, { center: true }); a11y.querySelector(`button[data-id="${CSS.escape(id)}"]`)?.focus({ preventScroll: true }); }
      }
    } else if (k === '+' || k === '=') engine.zoomBy(1.25);
    else if (k === '-' || k === '_') engine.zoomBy(0.8);
    else if (k === '0') engine.fit(true);
    else if (k === 'Enter') { const n = selected(); if (n) (levelNodes.has(n.id) ? drill(n.id) : openLeaf(n)); }
    else if (k === 'Backspace') run(upOne);
    else if (k === '/') q.focus();
    else if (k === 'o') { const n = selected(); const item = n?.item || byIdx.get(at)?.item; if (item) openDoc(item); }
    else if (k === 's') { const n = selected(); const s = n?.src || (panelData?.node?.id === sel ? panelData.node.src : null); if (s && s[0]) openSource(s[0], s[1], s[2]); }
    else if (k === 't') { if (sel) (trace?.id === sel ? clearTrace() : traceFrom(sel, 'both')); }
    else if (k === 'l') toggleLens();
    else if (k === 'h') setHealth(!health);
    else return;
    e.preventDefault();
  });
  addEventListener('focus', () => { if (active) refresh(); });

  // ---------- public ----------
  async function refresh() {
    let changed = false;
    try { changed = await loadIndex(true); } catch { return; }
    if (changed && active && level) {
      const l = lens, a = at;
      run(() => show(l, a, { mode: 'refresh' }));
    }
  }
  return {
    async enter(l, a = '.', s = '') {
      active = true;
      l = l === 'code' ? 'code' : 'systems';
      a = a || '.';
      loading(true);
      try {
        await ensureEngine();
        if (!toolsEl.childElementCount) { buildTools(); buildLegend(); }
        engine.resize();
        await loadIndex();
      } catch (err) { fail(err); return; }
      loading(false);
      if (level && l === lens && a === at) { // already here (back from the reader, or our own hash)
        if (s !== sel) choose(s, { center: true });
        return;
      }
      await run(async () => {
        let ok;
        if (!level) ok = await show(l, a, { mode: 'jump' });
        else if (a === at) { switchAt = null; switchVia = null; ok = await show(l, a, { mode: 'lens' }); }
        else if (byIdx.get(a)?.parent === at) ok = await show(l, a, { mode: 'drill', via: a });
        else if (byIdx.get(at)?.parent === a) ok = await show(l, a, { mode: 'up', via: at });
        else ok = await show(l, a, { mode: 'jump' });
        if (!ok && !level) await show('systems', '.', { mode: 'jump' });
        if (s && level) {
          sel = s;
          if (levelNodes.has(s) || ghostIds.has(s)) engine.focus(s);
          openPanel(s);
        }
      });
    },
    leave() {
      active = false;
      clearTimeout(hoverTimer);
      tip.hidden = true;
      closeResults();
      if (pop) pop.hidden = true;
    },
    select(itemId) { // the reader opened a doc: mark the block it belongs to, quietly
      if (!level || !itemId) return;
      const n = (level.nodes || []).find((x) => x.item === itemId);
      if (!n || n.id === sel) return;
      sel = n.id;
      engine?.select(n.id);
    },
    refresh,
  };
}
