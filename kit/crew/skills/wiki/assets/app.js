// wiki — file tree + reader + 2D/3D graph + Systems/Code maps + feedback. Offline; vendored libs only.
const $ = (s) => document.querySelector(s);
const KINDS = ['wrong', 'outdated', 'unclear', 'question', 'idea', 'answer', 'praise'];
const VIEWS = ['read', 'graph2d', 'graph3d', 'systems', 'code'];
const isMap = (v) => v === 'systems' || v === 'code';
const CALM = matchMedia('(prefers-reduced-motion: reduce)').matches;
const LIGHT = matchMedia('(prefers-color-scheme: light)').matches;
const FONT = getComputedStyle(document.body).fontFamily;
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const getJSON = async (url) => (await fetch(url)).json();
const fetchJSON = async (url) => { // like getJSON, but a non-2xx answer throws an Error carrying .status
  const r = await fetch(url);
  if (!r.ok) throw Object.assign(new Error(`${r.status} ${url}`), { status: r.status });
  return r.json();
};
const el = (tag, props = {}) => Object.assign(document.createElement(tag), props);
const append = (node, kids) => { node.append(...kids); return node; };

// 16px line icons (stroke = currentColor): shape tells the kind, colour only reinforces it.
const svg = (d) => `<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">${d}</svg>`;
const ICON = {
  chev: svg('<path d="m6 4 4 4-4 4"/>'),
  folder: svg('<path d="M1.8 4.5c0-.7.5-1.2 1.2-1.2h3l1.4 1.6H13c.7 0 1.2.5 1.2 1.2v5.9c0 .7-.5 1.2-1.2 1.2H3c-.7 0-1.2-.5-1.2-1.2z"/>'),
  folderOpen: svg('<path d="M1.8 12.6V4.5c0-.7.5-1.2 1.2-1.2h3l1.4 1.6H12c.7 0 1.2.5 1.2 1.2v1.2"/><path d="M1.8 12.6 3.5 7.7c.2-.5.6-.8 1.1-.8h9.6c.6 0 1 .5.8 1.1l-1.5 4c-.2.5-.6.7-1.1.7H3"/>'),
  page: svg('<path d="M4 1.8h5l3.2 3.2v9.2H4z"/><path d="M9 1.8V5h3.2M6.2 8.2h3.6M6.2 10.6h3.6"/>'),
  exhibit: svg('<rect x="1.8" y="2.8" width="12.4" height="10.4" rx="1.6"/><path d="M1.8 6h12.4M6.6 8.2 5.2 9.6 6.6 11M9.4 8.2l1.4 1.4-1.4 1.4"/>'),
  figure: svg('<rect x="1.8" y="2.8" width="12.4" height="10.4" rx="1.6"/><circle cx="5.6" cy="6.4" r="1"/><path d="m2 12 3.6-3.2 2.6 2.2 2.2-2L14 12"/>'),
  module: svg('<path d="M8 1.6 13.7 4.8v6.4L8 14.4l-5.7-3.2V4.8z"/><circle cx="8" cy="8" r="1.7"/>'),
  copy: svg('<rect x="5.5" y="5.5" width="8" height="8" rx="1.5"/><path d="M10.5 5.5v-2a1 1 0 0 0-1-1h-6a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2"/>'),
  source: svg('<path d="M5.2 4.5 1.8 8l3.4 3.5M10.8 4.5 14.2 8l-3.4 3.5M9.2 2.8 6.8 13.2"/>'),
};

// What a person reads for an item: its title, never a file name. A title that is only the file name
// (no heading, no front matter) becomes the bare stem, and a generic stem (SKILL, README, index) the folder's name.
const GENERIC = /^(skill|readme|index|claude|agents|overview)$/i;
function nameOf(it) {
  const parts = it.path.split('/'), file = parts.at(-1);
  if (it.title !== file) return it.title;
  const stem = file.replace(/\.[^.]+$/, '');
  return (GENERIC.test(stem) && parts.length > 1 ? parts.at(-2) : stem).replace(/^[._]+/, '');
}

// Item paths → nested folders (with file counts). Folders first, then files, each A→Z.
function buildTree(items) {
  const root = { name: '', path: '', dirs: new Map(), files: [], count: 0 };
  for (const it of items) {
    const parts = it.path.split('/');
    let dir = root;
    root.count++;
    for (const [i, name] of parts.slice(0, -1).entries()) {
      const path = parts.slice(0, i + 1).join('/');
      if (!dir.dirs.has(name)) dir.dirs.set(name, { name, path, dirs: new Map(), files: [], count: 0 });
      dir = dir.dirs.get(name);
      dir.count++;
    }
    dir.files.push({ name: it.name || parts.at(-1), it });
  }
  return root;
}
// Rows to draw: with a filter, only matching files and their folders, all open.
function visibleRows(root, open, terms) {
  const rows = [];
  const match = (f) => !terms.length || terms.every((t) => `${f.it.path} ${f.it.title} ${f.it.name || ''} ${f.it.ids.join(' ')}`.toLowerCase().includes(t));
  const walk = (dir, level) => {
    const out = [];
    for (const d of [...dir.dirs.values()].sort((a, b) => a.name.localeCompare(b.name))) {
      const sub = walk(d, level + 1);
      if (terms.length && !sub.length) continue;
      out.push({ dir: d, level }, ...(terms.length || open.has(d.path) ? sub : []));
    }
    for (const f of dir.files.filter(match).sort((a, b) => a.name.localeCompare(b.name))) out.push({ file: f, level });
    return out;
  };
  rows.push(...walk(root, 1));
  return rows;
}
if (typeof document === 'undefined') { globalThis.__tree = { buildTree, visibleRows, nameOf }; } else main();

async function main() {
const wiki = await getJSON('/api/wiki');
for (const it of wiki.items) it.name = nameOf(it);
const feedback = await getJSON('/api/feedback');
const byId = new Map(wiki.items.map((it) => [it.id, it]));
const back = new Map();
for (const it of wiki.items) for (const t of it.links) back.set(t, [...(back.get(t) || []), it.id]);

// ---------- side panel: repo, counts, filter, tree ----------
$('#repo').textContent = wiki.repo;
$('#counts').textContent = `${wiki.items.length} items · ${Object.keys(wiki.groups).length} groups`;
document.title = `${wiki.repo} · wiki`;
const root = buildTree(wiki.items), tree = $('#tree'), filter = $('#filter');
const openDirs = new Set();
let current = null, quote = '', kind = null, focusPath = null, fm = {};

function expandTo(it) { // open every folder above the item
  const parts = it.path.split('/');
  for (let i = 1; i < parts.length; i++) openDirs.add(parts.slice(0, i).join('/'));
}
function renderTree(refocus) {
  const terms = filter.value.toLowerCase().split(/\s+/).filter(Boolean);
  const rows = visibleRows(root, openDirs, terms);
  if (!rows.some((r) => (r.dir?.path ?? r.file.it.id) === focusPath)) focusPath = current && rows.some((r) => r.file?.it === current) ? current.id : null;
  tree.replaceChildren(...(rows.length ? rows.map((r) => {
    const d = r.dir, f = r.file, key = d ? d.path : f.it.id;
    const row = el('div', { className: 'tr' });
    row.setAttribute('role', 'treeitem');
    row.setAttribute('aria-level', r.level);
    row.dataset.key = key;
    row.tabIndex = key === (focusPath ?? (rows[0].dir?.path ?? rows[0].file.it.id)) ? 0 : -1;
    row.style.setProperty('--lv', r.level);
    if (d) {
      const isOpen = !!(terms.length || openDirs.has(d.path));
      row.setAttribute('aria-expanded', String(isOpen));
      row.classList.add('dir');
      row.append(el('span', { className: 'chev', innerHTML: ICON.chev }), el('span', { className: 'ic', innerHTML: isOpen ? ICON.folderOpen : ICON.folder }),
        el('span', { className: 'nm', textContent: d.name }), el('small', { className: 'ct', textContent: d.count }));
    } else {
      const sel = f.it === current;
      row.setAttribute('aria-selected', String(sel));
      if (f.it.name !== f.it.title) row.title = f.it.title;
      row.classList.add('file', f.it.kind);
      if (sel) row.setAttribute('aria-current', 'page');
      row.append(el('span', { className: 'chev' }), el('span', { className: 'ic', innerHTML: ICON[f.it.kind] || ICON.page }),
        el('span', { className: 'nm', textContent: f.name }));
      if (f.it.kind === 'module') row.append(el('small', { className: 'tag', textContent: 'module' }));
    }
    return row;
  }) : [el('p', { className: 'empty', textContent: 'No files match.' })]));
  if (refocus) tree.querySelector(`[data-key="${CSS.escape(refocus)}"]`)?.focus();
  else tree.querySelector('[aria-current]')?.scrollIntoView({ block: 'nearest' });
}
function activate(key) { // dir toggles, file opens
  const it = byId.get(key);
  if (it) { open(it); return; }
  if (!openDirs.delete(key)) openDirs.add(key);
  focusPath = key; renderTree(key);
}
tree.addEventListener('click', (e) => { const r = e.target.closest('[data-key]'); if (r) activate(r.dataset.key); });
tree.addEventListener('keydown', (e) => {
  const r = e.target.closest('[data-key]');
  if (!r) return;
  const rows = [...tree.querySelectorAll('[data-key]')], i = rows.indexOf(r), key = r.dataset.key, isDir = r.classList.contains('dir');
  const go = (n) => { if (n) { focusPath = n.dataset.key; r.tabIndex = -1; n.tabIndex = 0; n.focus(); } };
  const k = e.key;
  if (k === 'ArrowDown') go(rows[i + 1]);
  else if (k === 'ArrowUp') go(rows[i - 1]);
  else if (k === 'Home') go(rows[0]);
  else if (k === 'End') go(rows.at(-1));
  else if (k === 'ArrowRight' && isDir) { if (r.getAttribute('aria-expanded') === 'false') activate(key); else go(rows[i + 1]); }
  else if (k === 'ArrowLeft') {
    if (isDir && r.getAttribute('aria-expanded') === 'true' && !filter.value) activate(key);
    else { const lv = +r.getAttribute('aria-level'); go(rows.slice(0, i).reverse().find((x) => +x.getAttribute('aria-level') < lv)); }
  } else if (k === 'Enter' || k === ' ') activate(key);
  else return;
  e.preventDefault();
});
filter.oninput = () => renderTree();
filter.onkeydown = (e) => {
  if (e.key === 'ArrowDown') { e.preventDefault(); (tree.querySelector('[tabindex="0"]') || tree.querySelector('[data-key]'))?.focus(); }
  else if (e.key === 'Escape' && filter.value) { filter.value = ''; renderTree(); }
};

// narrow screens: the tree is a drawer
const setDrawer = (on) => {
  document.body.classList.toggle('drawer', on);
  $('#files').setAttribute('aria-expanded', String(on)); $('#scrim').hidden = !on;
  if (on) filter.focus(); else $('#files').focus({ preventScroll: true });
};
$('#files').onclick = () => setDrawer(!document.body.classList.contains('drawer'));
$('#scrim').onclick = () => setDrawer(false);

// ---------- views: Read · Graph 2D · Graph 3D · Systems · Code ----------
const TEST = new URLSearchParams(location.hash.slice(1)).get('test') === '1';
let view = 'read', graph = null, graphLoading = null, mapView = null, mapLoading = null;
let mapAt = '.', mapSel = '', find = '', src = null, srcFromMap = false; // src: {path, line, end} while the reader shows code
if (wiki.map) for (const b of $('#views').children) if (isMap(b.dataset.view)) b.hidden = false;
const saved = () => { try { return localStorage.getItem('wiki.view'); } catch { return null; } };
const hashState = () => {
  const h = new URLSearchParams(location.hash.slice(1)), v = h.get('view');
  return { view: VIEWS.includes(v) ? v : null, item: h.get('item') || '', find: h.get('find') || '',
    at: h.get('at') || '', sel: h.get('sel') || '', src: h.get('src') || '', line: h.get('line') || '' };
};
const lineRange = (spec) => { const [a, b] = String(spec || '').split('-').map((n) => parseInt(n, 10) || 0); return [a, b || a]; };
function hashFor() { // only the keys that apply to the view
  const h = { view };
  if (view === 'read') {
    if (src) { h.src = src.path; if (src.line) h.line = src.end > src.line ? `${src.line}-${src.end}` : `${src.line}`; }
    else if (current) { h.item = current.id; if (find) h.find = find; }
  } else if (isMap(view)) {
    if (mapAt && mapAt !== '.') h.at = mapAt;
    if (mapSel) h.sel = mapSel;
  } else if (current && !src) h.item = current.id;
  if (TEST) h.test = '1';
  return new URLSearchParams(h).toString();
}
function writeHash(replace = false) { // a selection change replaces the entry; a new level or page pushes one
  const h = hashFor();
  if (location.hash.slice(1) === h) return;
  // pushState fires no hashchange for our own writes (a map flight emits once, at its end); back/forward still do
  if (replace) history.replaceState(null, '', `#${h}`); else history.pushState(null, '', `#${h}`);
}
const HINT = {
  graph2d: 'Drag to pan · scroll to zoom · click a node to read',
  graph3d: 'Drag to orbit · right-drag to pan · scroll to zoom · click to read',
  systems: 'Drag to pan · scroll to zoom into a block · double-click or Enter to open it · Backspace goes up',
  code: 'Drag to pan · scroll to zoom into a file · double-click or Enter to open it · s shows the source',
};
function markView(v) { // the radio group, body flag and remembered view
  view = v;
  try { localStorage.setItem('wiki.view', v); } catch { /* private mode: the view is not remembered */ }
  document.body.dataset.view = v;
  for (const b of $('#views').children) b.setAttribute('aria-checked', String(b.dataset.view === v));
}
function loadGraph() { // vendor scripts and graph.js load on first use, never for Read-only visits
  graphLoading ||= new Promise((ok, fail) => {
    document.head.append(el('script', { src: '/assets/vendor/3d-force-graph.min.js', onload: ok, onerror: () => fail(new Error('3d-force-graph')) }));
  }).then(() => import('./graph.js')).then(({ createGraph }) => {
    graph = createGraph({
      wiki, host: $('#graph'), legend: $('#legend'), hint: $('#hint'), tools: $('#gtools'), dim: view === 'graph2d' ? 2 : 3,
      onOpen: (it) => { open(it); setView('read'); },
    });
    if (current && current.kind !== 'source') graph.select(current);
  });
  return graphLoading;
}
function loadMap() { // map/view.js (and through it the canvas engine) load on first use
  mapLoading ||= import('./map/view.js').then(({ createMapView }) => {
    mapView = createMapView({
      root: $('#mapview'), getJSON: fetchJSON, openDoc, openSource,
      onState: ({ lens, at, sel }) => {
        const moved = (at || '.') !== mapAt || (isMap(view) && lens !== view);
        mapAt = at || '.'; mapSel = sel || '';
        if (!isMap(view)) return;
        if (lens !== view && isMap(lens)) markView(lens); // hand-off or `l` inside the map
        writeHash(!moved);
      },
    });
  }).catch((err) => { mapLoading = null; throw err; });
  return mapLoading;
}
async function setView(v) {
  if (!VIEWS.includes(v) || (isMap(v) && !wiki.map)) v = 'read';
  const was = view;
  markView(v);
  $('#readview').hidden = v !== 'read'; $('#graphview').hidden = !v.startsWith('graph'); $('#mapview').hidden = !isMap(v);
  if (isMap(was) && !isMap(v)) mapView?.leave();
  writeHash(); showPick();
  if (isMap(v)) {
    $('#map').setAttribute('aria-description', HINT[v]);
    try {
      await loadMap();
    } catch (err) {
      console.warn('map', err);
      $('#map-empty').hidden = false; $('#map-empty').textContent = 'The map could not load.';
      return;
    }
    if (view === v) await mapView.enter(v, mapAt, mapSel);
    return;
  }
  if (v === 'read') { if (current && current.kind !== 'exhibit' && current.kind !== 'source') mermaidize(body); return; } // diagrams wait until they can be measured
  $('#hint').textContent = HINT[v];
  $('#gload').hidden = !!graph;
  try {
    if (!graph) await loadGraph();
    else graph.setDim(v === 'graph2d' ? 2 : 3);
    $('#gload').hidden = true;
  } catch (err) {
    console.warn('graph', err);
    $('#gload').hidden = false; $('#gload').textContent = 'The graph could not load.';
  }
}
for (const b of $('#views').children) b.onclick = () => setView(b.dataset.view);

// The open item, offered as a way back to the page while a graph is showing (not in Read or the maps).
function showPick() {
  const b = $('#pick');
  b.hidden = !current || view === 'read' || isMap(view);
  if (b.hidden) return;
  b.replaceChildren(el('span', { className: 'ic', innerHTML: ICON[current.kind] || ICON.page }), el('span', { className: 'nm', textContent: current.title }), el('span', { className: 'go', textContent: 'Read' }));
  b.title = `Read ${current.name}`;
}
$('#pick').onclick = () => setView('read');

// ---------- reader ----------
const reader = $('#reader'), body = $('#r-body'), form = $('#fb'), text = $('#fb-text'), outline = $('#outline');

function readFrontmatter(raw) { // flat `key: value` lines only; the server owns the real parse
  const m = raw.match(/^---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(\r?\n|$)/), out = {};
  for (const line of m ? m[1].split(/\r?\n/) : []) {
    const kv = line.match(/^([A-Za-z][\w-]*):[ \t]*(.+?)[ \t]*$/);
    if (kv) out[kv[1].toLowerCase()] = kv[2].replace(/^["']|["']$/g, '');
  }
  return out;
}
function renderMeta() {
  const open = feedback.filter((f) => f.item === current.id && f.status === 'open').length;
  const chip = (cls, html, title) => `<span class="chip ${cls}"${title ? ` title="${esc(title)}"` : ''}>${html}</span>`;
  $('#r-meta').innerHTML = [
    chip(`k-${current.kind}`, `<span class="ic">${ICON[current.kind] || ICON.page}</span>${esc(current.kind)}`),
    src && chip('path', esc(src.path), 'repository path'),
    src?.line && chip('ver', src.end > src.line ? `lines ${src.line}–${src.end}` : `line ${src.line}`),
    fm.version && chip('ver', `v${esc(fm.version.replace(/^v/i, ''))}`, 'version'),
    fm.status && chip('st', esc(fm.status), 'status'),
    open && chip('fbk', `${open} open feedback`),
  ].filter(Boolean).join('');
}
function linkSection(title, ids) {
  if (!ids.length) return '';
  return append(el('section', { className: 'links' }), [el('h4', { textContent: title }),
    append(el('ul'), ids.map((id) => {
      const a = el('a', { href: '#' });
      a.dataset.id = id;
      a.append(el('span', { className: 'ic', innerHTML: ICON[byId.get(id)?.kind] || ICON.page }), el('span', { textContent: byId.get(id)?.name || 'Untitled' }));
      return append(el('li'), [a]);
    }))]);
}

async function open(it) {
  current = it; quote = ''; fm = {}; find = ''; src = null;
  expandTo(it); focusPath = it.id; renderTree();
  graph?.select(it);
  mapView?.select(it.id);
  writeHash(); showPick();
  if (document.body.classList.contains('drawer')) setDrawer(false);
  closeComposer();
  $('#r-head').hidden = false; $('#r-title').textContent = it.name; $('#fb-sent').textContent = '';
  $('#r-raw').href = `/api/item?id=${encodeURIComponent(it.id)}`;
  renderMeta(); setOutline([]);
  const exhibit = it.kind === 'exhibit';
  $('#readview').classList.toggle('exhibit', exhibit);
  body.className = exhibit ? 'md exhibit' : 'md';
  body.replaceChildren(); reader.scrollTop = 0;
  $('#outline').hidden = true;
  if (it.kind === 'figure') { // <img> never runs script; the server adds a CSP on top. CSS/SMIL animate inside.
    body.append(append(el('figure'), [el('img', { className: 'figure', src: `/figure?id=${encodeURIComponent(it.id)}`, alt: it.name })])); // the title above is the caption
  } else if (exhibit) {
    const f = el('iframe', { src: `/exhibit?id=${encodeURIComponent(it.id)}`, title: it.title });
    f.setAttribute('sandbox', 'allow-scripts');
    body.append(f);
    return;
  } else {
    const raw = await (await fetch(`/api/item?id=${encodeURIComponent(it.id)}`)).text();
    if (current !== it) return;
    fm = readFrontmatter(raw); renderMeta();
    const md = raw.replace(/^---[ \t]*\r?\n[\s\S]*?\r?\n---[ \t]*(\r?\n|$)/, '');
    body.innerHTML = DOMPurify.sanitize(marked.parse(md), { FORBID_TAGS: ['style', 'form', 'input'], FORBID_ATTR: ['style'] });
    for (const img of body.querySelectorAll('img[src]')) { // page images: relative to the page, repo-root only (server-checked)
      const src = img.getAttribute('src');
      if (!/^([a-z][a-z0-9+.-]*:|\/\/)/i.test(src)) img.src = `/img?path=${encodeURIComponent(resolveRel(it.id, src))}`;
    }
    decorate(it);
    if (view === 'read') mermaidize(body);
  }
  body.append(linkSection('Links', it.links), linkSection('Linked from', back.get(it.id) || []));
}

// Reading furniture on the sanitized DOM: title de-dup, captioned figures, scrolling tables, code copy, heading anchors.
function decorate(it) {
  const first = body.firstElementChild;
  if (first?.tagName === 'H1' && first.textContent.trim().toLowerCase() === it.title.trim().toLowerCase()) first.remove();
  for (const img of body.querySelectorAll('p > img:only-child, p > a:only-child > img:only-child')) {
    const p = img.closest('p'), fig = el('figure');
    p.replaceWith(fig); fig.append(p.firstElementChild);
    if (img.alt) fig.append(el('figcaption', { textContent: img.alt }));
  }
  for (const t of body.querySelectorAll('table')) t.replaceWith(append(el('div', { className: 'tbl' }), [t.cloneNode(true)]));
  for (const pre of body.querySelectorAll('pre')) {
    if (pre.querySelector('code.language-mermaid')) continue;
    const b = el('button', { type: 'button', className: 'copy', title: 'Copy code', innerHTML: ICON.copy });
    b.setAttribute('aria-label', 'Copy code');
    b.onclick = async () => {
      try {
        await navigator.clipboard.writeText(pre.querySelector('code')?.textContent ?? pre.textContent);
        b.classList.add('done'); setTimeout(() => b.classList.remove('done'), 1200);
      } catch { /* clipboard blocked: nothing to do */ }
    };
    pre.append(b);
  }
  const used = new Set(), heads = [...body.querySelectorAll('h1, h2, h3, h4')];
  for (const h of heads) {
    const label = h.textContent.trim(), base = label.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '-').replace(/^-|-$/g, '') || 'section';
    let id = base;
    for (let n = 2; used.has(id); n++) id = `${base}-${n}`;
    used.add(id); h.id = id; h.dataset.t = label;
    h.append(el('a', { className: 'anchor', href: `#${id}`, textContent: '#', title: 'Link to this section' }));
  }
  setOutline(heads.filter((h) => h.tagName === 'H2' || h.tagName === 'H3'));
}

// On-page outline (wide screens): scroll-spied list of h2/h3.
function setOutline(heads) {
  outline.hidden = heads.length < 2;
  outline.replaceChildren(...(heads.length < 2 ? [] : [el('h2', { textContent: 'On this page' }), append(el('ul'), heads.map((h) => {
    const a = el('a', { href: `#${h.id}`, className: h.tagName === 'H3' ? 'l3' : 'l2', textContent: h.dataset.t });
    a.dataset.h = h.id;
    return append(el('li'), [a]);
  }))]));
  spy();
}
function spy() {
  const heads = [...body.querySelectorAll('h2[id], h3[id]')];
  if (!heads.length) return;
  const top = reader.getBoundingClientRect().top + 90;
  const at = heads.findLast((h) => h.getBoundingClientRect().top <= top) || heads[0];
  for (const a of outline.querySelectorAll('a')) {
    const on = a.dataset.h === at.id;
    a.classList.toggle('on', on);
    if (on) a.setAttribute('aria-current', 'location'); else a.removeAttribute('aria-current');
  }
}
let spyTick = 0;
reader.addEventListener('scroll', () => { cancelAnimationFrame(spyTick); spyTick = requestAnimationFrame(spy); });
const jump = (id) => document.getElementById(id)?.scrollIntoView({ block: 'start', behavior: CALM ? 'auto' : 'smooth' });
outline.addEventListener('click', (e) => { const a = e.target.closest('a[data-h]'); if (a) { e.preventDefault(); jump(a.dataset.h); } });

// From the map: open a doc and land on a heading or line. The reader's own heading slugs are used, never re-made.
async function openDoc(item, findText) {
  const it = byId.get(item);
  if (!it) return false;
  await open(it);
  find = findText || '';
  await setView('read');
  if (find) jumpText(find);
  return true;
}
function jumpText(t) { // a heading named t, else one starting with t, else the first block containing t
  const heads = [...body.querySelectorAll('h1, h2, h3, h4')];
  const hit = heads.find((h) => h.dataset.t === t) || heads.find((h) => h.dataset.t?.startsWith(t))
    || [...body.querySelectorAll('li, p, td, th, h1, h2, h3, h4')].find((n) => n.textContent.includes(t));
  if (!hit) return false;
  hit.scrollIntoView({ block: 'center' });
  hit.classList.remove('flash'); void hit.offsetWidth; hit.classList.add('flash');
  setTimeout(() => hit.classList.remove('flash'), 1200);
  return true;
}

// Source reader: a code file the map indexed, as numbered plain-text lines (textContent only; no highlighting).
async function openSource(path, line, end) {
  const name = path.split('/').at(-1) || path;
  const a = Math.max(0, parseInt(line, 10) || 0), b = Math.max(a, parseInt(end, 10) || a);
  if (isMap(view)) srcFromMap = true;
  else if (!src) srcFromMap = false;
  current = { id: path, kind: 'source', title: name, name, path, links: [], ids: [] };
  src = { path, line: a, end: b }; find = ''; quote = ''; fm = {};
  renderTree(); closeComposer();
  await setView('read');
  $('#r-head').hidden = false; $('#r-title').textContent = name; $('#fb-sent').textContent = '';
  $('#r-raw').href = `/api/source?path=${encodeURIComponent(path)}`;
  renderMeta(); setOutline([]);
  $('#readview').classList.remove('exhibit');
  body.className = 'md source';
  body.replaceChildren(el('p', { className: 'empty', textContent: 'Loading source…' })); reader.scrollTop = 0;
  const back = el('button', { type: 'button', className: 'btn', textContent: srcFromMap ? 'Back to map' : 'Show in map' });
  back.onclick = () => {
    if (srcFromMap) { history.back(); return; }
    mapAt = path; mapSel = ''; setView('code');
  };
  back.hidden = !wiki.map;
  let text;
  try {
    const r = await fetch(`/api/source?path=${encodeURIComponent(path)}`);
    if (!r.ok) throw Object.assign(new Error(String(r.status)), { status: r.status });
    text = await r.text();
  } catch (err) {
    if (src?.path !== path) return;
    body.replaceChildren(append(el('div', { className: 'src-head' }), [el('code', { textContent: path }), back]),
      el('p', { className: 'empty', textContent: err.status === 415 ? 'Binary file: not shown.' : 'This file is not available.' }));
    return;
  }
  if (src?.path !== path || current?.id !== path) return; // the reader moved on meanwhile
  const lines = text.split(/\r?\n/);
  if (lines.length > 1 && lines.at(-1) === '') lines.pop();
  const ol = el('ol', { className: 'src' });
  ol.setAttribute('aria-label', `${path}, ${lines.length} lines`);
  ol.append(...lines.map((t, i) => {
    const li = el('li', { textContent: t });
    if (a && i + 1 >= a && i + 1 <= b) li.className = 'hit';
    return li;
  }));
  const n = el('span', { className: 'src-n', textContent: `${lines.length} line${lines.length === 1 ? '' : 's'}` }); // the path is in the meta chips
  body.replaceChildren(append(el('div', { className: 'src-head' }), [n, back]), ol);
  revealHits(ol);
}

/** Scroll the hit lines into the reader only as far as needed, so the file name and path stay in view. */
function revealHits(ol) {
  const hits = ol.querySelectorAll('li.hit'), box = $('#reader')?.getBoundingClientRect();
  if (!hits.length || !box) return;
  const f = hits[0].getBoundingClientRect(), l = hits[hits.length - 1].getBoundingClientRect();
  if (f.top >= box.top && l.bottom <= box.bottom) return; // already fully visible: no scroll
  if (l.bottom - f.top > box.height - 32) { hits[0].scrollIntoView({ block: 'center' }); return; }
  $('#reader').scrollTop += f.top < box.top ? f.top - box.top - 16 : l.bottom - box.bottom + 16;
}

function resolveRel(from, href) {
  let path;
  try { path = decodeURIComponent(href.split(/[#?]/)[0]); } catch { return ''; }
  const parts = path.startsWith('/') ? [] : from.split('/').slice(0, -1);
  for (const p of path.split('/')) { if (p === '..') parts.pop(); else if (p && p !== '.') parts.push(p); }
  return parts.join('/');
}
body.addEventListener('click', (e) => {
  const a = e.target.closest('a[href]');
  if (!a) return;
  const href = a.getAttribute('href');
  if (!a.dataset.id && /^[a-z][a-z0-9+.-]*:/i.test(href)) { a.target = '_blank'; a.rel = 'noopener noreferrer'; return; }
  e.preventDefault();
  if (!a.dataset.id && href.startsWith('#')) { if (href.length > 1) jump(decodeURIComponent(href.slice(1))); return; }
  const id = a.dataset.id || resolveRel(current.id, href);
  if (byId.has(id)) open(byId.get(id));
});

let mermaidReady = null;
async function mermaidize(root) {
  const blocks = [...root.querySelectorAll('pre > code.language-mermaid')];
  if (!blocks.length) return;
  mermaidReady ||= new Promise((ok, fail) => {
    const s = el('script', { src: '/assets/vendor/mermaid.min.js', onload: ok, onerror: fail });
    document.head.append(s);
  }).then(() => mermaid.initialize({
    startOnLoad: false, securityLevel: 'strict', theme: LIGHT ? 'default' : 'dark', fontFamily: FONT,
    themeVariables: { background: 'transparent', fontFamily: FONT },
  }));
  const targets = blocks.map((code) => {
    const d = el('div', { className: 'mermaid', textContent: code.textContent });
    code.parentElement.replaceWith(d);
    return d;
  });
  try { await mermaidReady; await mermaid.run({ nodes: targets }); } catch (err) { console.warn('mermaid', err); }
}

// ---------- feedback composer ----------
const kinds = $('#fb-kinds');
for (const k of KINDS) {
  const b = el('button', { type: 'button', textContent: k });
  b.setAttribute('role', 'radio'); b.setAttribute('aria-checked', 'false');
  b.onclick = () => { kind = k; syncComposer(); text.focus(); };
  kinds.append(b);
}
function syncComposer() {
  for (const b of kinds.children) b.setAttribute('aria-checked', String(b.textContent === kind));
  $('#fb-send').disabled = !kind || !text.value.trim();
}
function grabSelection() {
  const s = getSelection();
  return s && s.rangeCount && body.contains(s.anchorNode) ? s.toString().trim().slice(0, 4000) : '';
}
function compose(pre = {}) {
  if (!current) return;
  kind = KINDS.includes(pre.kind) ? pre.kind : null;
  if (pre.quote !== undefined) quote = pre.quote;
  text.value = pre.text || '';
  $('#fb-quote').textContent = quote ? `“${quote.length > 180 ? `${quote.slice(0, 180)}…` : quote}”` : '';
  $('#fb-sent').textContent = '';
  form.hidden = false; $('#fb-open').hidden = true;
  syncComposer();
  requestAnimationFrame(() => { text.focus(); text.setSelectionRange(text.value.length, text.value.length); });
}
function closeComposer() { form.hidden = true; $('#fb-open').hidden = !current || current.kind === 'source'; }
$('#fb-open').addEventListener('pointerdown', () => { quote = grabSelection(); });
$('#fb-open').onclick = () => compose({ quote: quote || grabSelection() });
$('#fb-cancel').onclick = closeComposer;
text.oninput = syncComposer;
form.onsubmit = async (e) => {
  e.preventDefault();
  if (!kind || !text.value.trim()) return;
  const payload = { item: current.id, sha256: current.sha256, kind, text: text.value, ...(quote ? { quote } : {}) };
  $('#fb-send').disabled = true;
  const r = await fetch('/api/feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  const out = await r.json().catch(() => ({}));
  if (!r.ok) { $('#fb-sent').textContent = `Not sent · ${out.error || r.status}`; syncComposer(); return; }
  feedback.push(out); quote = '';
  closeComposer(); renderMeta();
  $('#fb-sent').textContent = `Sent · ${out.id}`;
};
// Exhibit bridge: an exhibit may ask the parent to open the composer prefilled. Never auto-sends.
addEventListener('message', (e) => {
  const f = body.querySelector('iframe');
  if (!f || e.source !== f.contentWindow || current?.kind !== 'exhibit') return;
  const d = e.data;
  if (!d || typeof d !== 'object' || d.type !== 'wiki-feedback') return;
  const str = (v) => (typeof v === 'string' ? v : '');
  if (str(d.text).length > 4000 || str(d.quote).length > 4000) return;
  compose({ kind: d.kind, text: str(d.text), quote: str(d.quote) });
});

addEventListener('keydown', (e) => {
  if (e.defaultPrevented) return; // the map handled it
  const typing = /^(INPUT|TEXTAREA)$/.test(document.activeElement?.tagName);
  if (e.key === '/' && !typing && isMap(view)) { e.preventDefault(); $('#map-q').focus(); return; }
  if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !typing)) {
    e.preventDefault();
    if (matchMedia('(max-width: 760px)').matches) setDrawer(true); else filter.focus();
    return;
  }
  if (e.key !== 'Escape') return;
  if (document.body.classList.contains('drawer')) setDrawer(false);
  else if (!form.hidden) closeComposer();
});

// ---------- start: #view=<view>&item=… | &find=… | &src=…&line=N-M | &at=…&sel=…; back/forward follow the hash ----------
async function applyHash() {
  const h = hashState();
  if (h.view === 'read' && h.src) {
    const [a, b] = lineRange(h.line);
    if (src?.path !== h.src || src.line !== a || src.end !== b) await openSource(h.src, a, b);
    else if (view !== 'read') await setView('read');
    return;
  }
  if (h.item && byId.has(h.item) && (byId.get(h.item) !== current || src)) await open(byId.get(h.item));
  if (isMap(h.view)) {
    mapAt = h.at || '.'; mapSel = h.sel || '';
    if (h.view !== view) await setView(h.view);
    else await mapView?.enter(h.view, mapAt, mapSel);
    return;
  }
  if (h.view && h.view !== view) await setView(h.view);
  if (view === 'read' && h.find && h.find !== find) { find = h.find; jumpText(find); }
}
body.replaceChildren(append(el('div', { className: 'welcome' }), [
  el('h2', { textContent: wiki.repo }),
  el('p', { textContent: wiki.map ? 'Pick a file from the tree to read it, open a graph to see how the documents connect, or open Systems and Code to walk the architecture.'
    : 'Pick a file from the tree to read it, or open a graph to see how the documents connect.' }),
]));
renderTree();
{
  const h = hashState();
  // a bare URL lands on the Systems map; a link to a page or source opens Read; no map → the remembered view
  let v = h.view || (h.item || h.src ? 'read' : wiki.map ? 'systems' : VIEWS.includes(saved()) ? saved() : 'read');
  if (isMap(v) && !wiki.map) v = 'read'; // a saved or linked map view, on a wiki without maps
  mapAt = h.at || '.'; mapSel = h.sel || '';
  if (v === 'read' && h.src) {
    const [a, b] = lineRange(h.line);
    await openSource(h.src, a, b);
  } else {
    view = v;
    if (h.item && byId.has(h.item)) await open(byId.get(h.item));
    await setView(v);
    if (v === 'read' && h.find && current) { find = h.find; writeHash(true); jumpText(find); }
  }
}
addEventListener('hashchange', applyHash);
}
