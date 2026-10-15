// wiki map — drawing primitives. Blocks, ghosts and labels are drawn in screen space (crisp text at
// integer pixels); edge routes are drawn in world space from cached Path2D objects with the line width
// divided by the zoom. Glow is faked with soft wide strokes (no blur filters). Repo text only ever
// reaches the canvas through fillText.
import { ghostParents } from './layout.js';

// Same hues as graph.js: greens, teals, limes, ambers and warm neutrals — never blue or purple.
export const PALETTE = {
  dark: ['#5eead4', '#a3e635', '#fbbf24', '#4ade80', '#e2c792', '#2dd4bf', '#d9f99d', '#f59e6b', '#86efac', '#c9b37e'],
  light: ['#0f9b87', '#5f8f12', '#b07a10', '#2e9a56', '#8a7350', '#0e8a7a', '#76901a', '#a3611c', '#3d8f6a', '#6f7d3a'],
};

const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
const px = (v, dpr) => Math.round(v * dpr) / dpr;

// ---------------------------------------------------------------- colour

const CC = new Map();
export function parseColor(c) {
  let v = CC.get(c);
  if (v) return v;
  const s = String(c || '').trim();
  let m;
  if ((m = s.match(/^#([0-9a-f]{3,8})$/i))) {
    let h = m[1];
    if (h.length <= 4) h = h.split('').map((x) => x + x).join('');
    v = [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16), h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1];
  } else if ((m = s.match(/^rgba?\(([^)]+)\)$/i))) {
    const p = m[1].split(/[\s,/]+/).filter(Boolean).map(Number);
    v = [p[0] || 0, p[1] || 0, p[2] || 0, p.length > 3 ? p[3] : 1];
  } else v = [141, 162, 149, 1];
  if (CC.size > 512) CC.clear();
  CC.set(c, v);
  return v;
}
export function rgba(c, a = 1) {
  const [r, g, b, a0] = parseColor(c);
  return `rgba(${r | 0},${g | 0},${b | 0},${Math.round(clamp(a * a0, 0, 1) * 1000) / 1000})`;
}
export function mix(c1, c2, t) {
  const a = parseColor(c1), b = parseColor(c2);
  return `rgb(${Math.round(a[0] + (b[0] - a[0]) * t)},${Math.round(a[1] + (b[1] - a[1]) * t)},${Math.round(a[2] + (b[2] - a[2]) * t)})`;
}
export const isLight = (bg) => { const [r, g, b] = parseColor(bg); return 0.2126 * r + 0.7152 * g + 0.0722 * b > 140; };

// ---------------------------------------------------------------- text

const TW = new Map();
export function textW(ctx, text, font) {
  const key = font + '\n' + text;
  let w = TW.get(key);
  if (w === undefined) {
    if (TW.size > 6000) TW.clear();
    ctx.font = font; w = ctx.measureText(text).width; TW.set(key, w);
  }
  return w;
}
export function ellipsize(ctx, text, font, max) {
  text = String(text ?? '');
  if (max <= 4) return '';
  if (textW(ctx, text, font) <= max) return text;
  let lo = 0, hi = text.length;
  while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (textW(ctx, text.slice(0, mid) + '…', font) <= max) lo = mid; else hi = mid - 1; }
  return lo ? text.slice(0, lo).trimEnd() + '…' : '';
}
export function wrap2(ctx, text, font, max) {
  const words = String(text || '').split(/\s+/).filter(Boolean), lines = [];
  let cur = '';
  for (let i = 0; i < words.length; i++) {
    const t = cur ? cur + ' ' + words[i] : words[i];
    if (textW(ctx, t, font) <= max || !cur) cur = t;
    else {
      lines.push(cur); cur = words[i];
      if (lines.length === 1) { const rest = words.slice(i).join(' '); lines.push(ellipsize(ctx, rest, font, max)); return lines; }
    }
  }
  if (cur) lines.push(ellipsize(ctx, cur, font, max));
  return lines.slice(0, 2);
}
export const fontOf = (w, size, fam) => `${w} ${Math.round(size * 2) / 2}px ${fam}`;

// ---------------------------------------------------------------- paths

/** Rounded rectangle sub-path via arcTo (works where ctx.roundRect does not exist). */
export function roundRect(ctx, x, y, w, h, r) {
  r = Math.max(0, Math.min(r, w / 2, h / 2));
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

export function shapePath(ctx, shape, x, y, w, h, r) {
  switch (shape) {
    case 'pill': return roundRect(ctx, x, y, w, h, h / 2);
    case 'notch': {
      const c = Math.min(h * 0.3, 18, w / 3);
      ctx.moveTo(x + r, y); ctx.lineTo(x + w - c, y); ctx.lineTo(x + w, y + c);
      ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r);
      return ctx.closePath();
    }
    case 'hex': {
      const i = Math.min(h / 2, w * 0.14, 24);
      ctx.moveTo(x + i, y); ctx.lineTo(x + w - i, y); ctx.lineTo(x + w, y + h / 2);
      ctx.lineTo(x + w - i, y + h); ctx.lineTo(x + i, y + h); ctx.lineTo(x, y + h / 2);
      return ctx.closePath();
    }
    case 'cyl': {
      const ry = Math.min(h * 0.13, 11, w / 4);
      ctx.moveTo(x, y + ry);
      ctx.ellipse(x + w / 2, y + ry, w / 2, ry, 0, Math.PI, 0);
      ctx.lineTo(x + w, y + h - ry);
      ctx.ellipse(x + w / 2, y + h - ry, w / 2, ry, 0, 0, Math.PI);
      return ctx.closePath();
    }
    case 'fold': {
      const f = Math.min(h * 0.32, 14, w / 4);
      ctx.moveTo(x + r, y); ctx.lineTo(x + w - f, y); ctx.lineTo(x + w, y + f);
      ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r);
      return ctx.closePath();
    }
    case 'half-r': { // flat left, round right
      const q = h / 2;
      ctx.moveTo(x, y); ctx.lineTo(x + w - q, y); ctx.arc(x + w - q, y + q, q, -Math.PI / 2, Math.PI / 2);
      ctx.lineTo(x, y + h); return ctx.closePath();
    }
    case 'half-l': {
      const q = h / 2;
      ctx.moveTo(x + w, y); ctx.lineTo(x + q, y); ctx.arc(x + q, y + q, q, -Math.PI / 2, Math.PI / 2, true);
      ctx.lineTo(x + w, y + h); return ctx.closePath();
    }
    case 'half-b': { // flat top, round bottom
      const q = Math.min(h / 2, w / 2);
      ctx.moveTo(x, y); ctx.lineTo(x + w, y); ctx.lineTo(x + w, y + h - q); ctx.arcTo(x + w, y + h, x + w - q, y + h, q);
      ctx.lineTo(x + q, y + h); ctx.arcTo(x, y + h, x, y + h - q, q); return ctx.closePath();
    }
    case 'half-t': {
      const q = Math.min(h / 2, w / 2);
      ctx.moveTo(x, y + h); ctx.lineTo(x, y + q); ctx.arcTo(x, y, x + q, y, q); ctx.lineTo(x + w - q, y);
      ctx.arcTo(x + w, y, x + w, y + q, q); ctx.lineTo(x + w, y + h); return ctx.closePath();
    }
    default: return roundRect(ctx, x, y, w, h, r);
  }
}

// ---------------------------------------------------------------- looks

const LETTER = { class: 'C', struct: 'S', interface: 'I', enum: 'E', type: 'T', namespace: 'N', function: 'ƒ', method: 'm', ctor: 'c',
  test: '✓', const: 'K', macro: '#', message: 'M', table: 'T' };
/** Shape and decoration for a level node (§8.6). */
export function nodeLook(n) {
  const t = n.type, k = n.kind;
  if (t === 'group') return { shape: 'rect', frame: true, dashed: true, tab: true, glyph: k === 'project' ? 'project' : 'group' };
  if (t === 'own') return { shape: 'rect', own: true, glyph: 'code' };
  if (t === 'actor') return { shape: 'pill', outline: true, dashed: k === 'ext', req: k === 'req', glyph: k === 'req' ? 'req' : 'actor' };
  if (t === 'dir' || t === 'bucket') return { shape: 'rect', frame: true, dashed: true, tab: true, glyph: 'dir', muted: !!n.vendor };
  if (t === 'file') return { shape: 'fold', glyph: 'file', muted: !!n.test };
  if (t === 'symbol') {
    const letter = LETTER[k] || '·';
    if (k === 'class' || k === 'struct') return { shape: 'rect', band: true, letter };
    if (k === 'interface') return { shape: 'rect', band: true, outline: true, letter };
    if (k === 'message') return { shape: 'hex', letter };
    if (k === 'table') return { shape: 'cyl', letter };
    if (k === 'namespace') return { shape: 'rect', dashed: true, letter };
    if (k === 'enum' || k === 'type') return { shape: 'rect', letter };
    return { shape: 'pill', letter, muted: k === 'const' || k === 'macro' || n.test === true && k !== 'test' };
  }
  switch (k) {
    case 'system': return { shape: 'rect', double: true, glyph: 'stack' };
    case 'adapter': return { shape: 'notch', glyph: 'adapter' };
    case 'protocol': return { shape: 'hex', glyph: 'proto' };
    case 'data': return { shape: 'cyl', glyph: 'data' };
    case 'deploy': return { shape: 'rect', dashed: true, glyph: 'deploy' };
    case 'host-service': return { shape: 'rect', glyph: 'plug' };
    case 'study': return { shape: 'rect', dashed: true, muted: true, glyph: 'study' };
    case 'tool': return { shape: 'rect', glyph: 'gear' };
    default: return { shape: 'rect', glyph: t === 'root' ? 'stack' : 'code' };
  }
}

export function healthColor(b, T) {
  const cov = b && b.cov;
  if (!cov || !cov[1]) return T.muted;
  const r = clamp(cov[0] / cov[1], 0, 1);
  if (r >= 1) return (b.stale || 0) > 0 ? T.mint : T.lime;
  return mix(T.muted, T.mint, r);
}

// ---------------------------------------------------------------- glyphs (vector, stroke)

export function drawGlyph(ctx, g, x, y, s, color) {
  ctx.save();
  ctx.translate(x, y); ctx.scale(s / 16, s / 16);
  ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 1.5; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  ctx.beginPath();
  switch (g) {
    case 'stack': roundRect(ctx, 1.5, 5.5, 9, 9, 2); ctx.stroke(); ctx.beginPath(); ctx.moveTo(5.5, 3.2); ctx.lineTo(5.5, 3); ctx.arcTo(5.5, 1.5, 7, 1.5, 1.5); ctx.lineTo(13, 1.5); ctx.arcTo(14.5, 1.5, 14.5, 3, 1.5); ctx.lineTo(14.5, 9); ctx.arcTo(14.5, 10.5, 13, 10.5, 1.5); ctx.lineTo(12.8, 10.5); break;
    case 'code': ctx.moveTo(5.5, 4); ctx.lineTo(1.8, 8); ctx.lineTo(5.5, 12); ctx.moveTo(10.5, 4); ctx.lineTo(14.2, 8); ctx.lineTo(10.5, 12); ctx.moveTo(9, 3); ctx.lineTo(7, 13); break;
    case 'gear': ctx.arc(8, 8, 2.4, 0, 7); ctx.moveTo(13.2, 8); for (let i = 0; i < 8; i++) { const a = (i * Math.PI) / 4; ctx.moveTo(8 + Math.cos(a) * 4.6, 8 + Math.sin(a) * 4.6); ctx.lineTo(8 + Math.cos(a) * 6.6, 8 + Math.sin(a) * 6.6); } ctx.moveTo(12.6, 8); ctx.arc(8, 8, 4.6, 0, 7); break;
    case 'plug': ctx.moveTo(5.5, 1.5); ctx.lineTo(5.5, 5); ctx.moveTo(10.5, 1.5); ctx.lineTo(10.5, 5); roundRect(ctx, 3, 5, 10, 5, 2); ctx.moveTo(8, 10); ctx.lineTo(8, 14.5); break;
    case 'proto': ctx.moveTo(4, 2); ctx.lineTo(12, 2); ctx.lineTo(15, 8); ctx.lineTo(12, 14); ctx.lineTo(4, 14); ctx.lineTo(1, 8); ctx.closePath(); ctx.moveTo(5.5, 8); ctx.lineTo(10.5, 8); break;
    case 'data': ctx.ellipse(8, 3.8, 5.8, 2.3, 0, 0, 7); ctx.moveTo(2.2, 3.8); ctx.lineTo(2.2, 12.2); ctx.ellipse(8, 12.2, 5.8, 2.3, 0, Math.PI, 0, true); ctx.lineTo(13.8, 3.8); ctx.moveTo(13.8, 8); ctx.ellipse(8, 8, 5.8, 2.3, 0, 0, Math.PI); break;
    case 'adapter': ctx.moveTo(1.5, 5.5); ctx.lineTo(12.5, 5.5); ctx.moveTo(10, 3); ctx.lineTo(12.5, 5.5); ctx.lineTo(10, 8); ctx.moveTo(14.5, 10.5); ctx.lineTo(3.5, 10.5); ctx.moveTo(6, 8); ctx.lineTo(3.5, 10.5); ctx.lineTo(6, 13); break;
    case 'deploy': ctx.moveTo(8, 10); ctx.lineTo(8, 1.8); ctx.moveTo(4.8, 5); ctx.lineTo(8, 1.8); ctx.lineTo(11.2, 5); ctx.moveTo(2, 9.5); ctx.lineTo(2, 14); ctx.lineTo(14, 14); ctx.lineTo(14, 9.5); break;
    case 'study': ctx.arc(7, 7, 4.6, 0, 7); ctx.moveTo(10.4, 10.4); ctx.lineTo(14.5, 14.5); break;
    case 'group': ctx.setLineDash([2.2, 2.2]); roundRect(ctx, 1.5, 1.5, 13, 13, 3); ctx.stroke(); ctx.setLineDash([]); ctx.beginPath(); roundRect(ctx, 5, 5, 6, 6, 1.5); break;
    case 'project': roundRect(ctx, 1.5, 1.5, 13, 13, 3); ctx.moveTo(5, 8); ctx.lineTo(11, 8); ctx.moveTo(8, 5); ctx.lineTo(8, 11); break;
    case 'dir': ctx.moveTo(1.5, 4); ctx.arcTo(1.5, 2.5, 3, 2.5, 1.5); ctx.lineTo(6, 2.5); ctx.lineTo(7.6, 4.4); ctx.lineTo(13, 4.4); ctx.arcTo(14.5, 4.4, 14.5, 6, 1.5); ctx.lineTo(14.5, 12); ctx.arcTo(14.5, 13.5, 13, 13.5, 1.5); ctx.lineTo(3, 13.5); ctx.arcTo(1.5, 13.5, 1.5, 12, 1.5); ctx.closePath(); break;
    case 'file': ctx.moveTo(3, 1.5); ctx.lineTo(9.5, 1.5); ctx.lineTo(13, 5); ctx.lineTo(13, 14.5); ctx.lineTo(3, 14.5); ctx.closePath(); ctx.moveTo(9.5, 1.5); ctx.lineTo(9.5, 5); ctx.lineTo(13, 5); ctx.moveTo(5.5, 9); ctx.lineTo(10.5, 9); ctx.moveTo(5.5, 11.6); ctx.lineTo(9, 11.6); break;
    case 'actor': ctx.arc(8, 5, 3, 0, 7); ctx.moveTo(2.5, 14.5); ctx.bezierCurveTo(2.5, 9.5, 13.5, 9.5, 13.5, 14.5); break;
    case 'req': ctx.moveTo(3, 2); ctx.lineTo(3, 14.5); ctx.moveTo(3, 2.5); ctx.lineTo(13, 2.5); ctx.lineTo(10.5, 5.5); ctx.lineTo(13, 8.5); ctx.lineTo(3, 8.5); break;
    default: ctx.arc(8, 8, 3, 0, 7);
  }
  ctx.stroke();
  ctx.restore();
}

function letterChip(ctx, letter, x, y, s, color, T, fam) {
  ctx.beginPath(); roundRect(ctx, x, y, s, s, s * 0.28);
  ctx.fillStyle = rgba(color, 0.16); ctx.fill();
  ctx.strokeStyle = rgba(color, 0.55); ctx.lineWidth = 1; ctx.stroke();
  ctx.fillStyle = color; ctx.font = fontOf(700, s * 0.66, fam); ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText(letter, x + s / 2, y + s / 2 + 0.5);
  ctx.textAlign = 'left';
}

// ---------------------------------------------------------------- badges

/** The badges that leave the name at least up to minLeft: all, else the findings dot alone, else none. */
function pickBadges(ctx, b, xr, yc, s, T, fam, minLeft) {
  if (!b) return null;
  for (const c of [b, b.findings > 0 ? { findings: b.findings } : null]) {
    if (!c) continue;
    ctx.save(); ctx.globalAlpha = 0; const left = badges(ctx, c, xr, yc, s, T, fam); ctx.restore();
    if (left >= minLeft) return c;
  }
  return null;
}

function badges(ctx, b, xr, yc, s, T, fam) {
  // right-aligned at xr; returns the left edge
  if (!b) return xr;
  let x = xr;
  const r = Math.max(2.5, s * 0.24);
  if (b.findings > 0) {
    const t = String(b.findings > 99 ? '99+' : b.findings), f = fontOf(700, s * 0.62, fam);
    const w = Math.max(s * 0.95, textW(ctx, t, f) + s * 0.5);
    ctx.beginPath(); roundRect(ctx, x - w, yc - s * 0.45, w, s * 0.9, s * 0.45); ctx.fillStyle = T.rose; ctx.fill();
    ctx.fillStyle = T.bg; ctx.font = f; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(t, x - w / 2, yc + 0.5); ctx.textAlign = 'left';
    x -= w + s * 0.35;
  }
  if (b.cov) { // coverage: a ring that fills with the documented share
    const [d, p] = b.cov, rr = r * 1.45, cx = x - rr, ratio = p ? clamp(d / p, 0, 1) : 0;
    const col = p && ratio >= 1 && !(b.stale > 0) ? T.lime : b.stale > 0 ? T.sand : p ? T.mint : T.muted;
    ctx.beginPath(); ctx.arc(cx, yc, rr, 0, Math.PI * 2); ctx.strokeStyle = rgba(T.muted, 0.35); ctx.lineWidth = Math.max(1.4, s * 0.13); ctx.stroke();
    if (ratio > 0) { ctx.beginPath(); ctx.arc(cx, yc, rr, -Math.PI / 2, -Math.PI / 2 + ratio * Math.PI * 2); ctx.strokeStyle = col; ctx.stroke(); }
    x -= rr * 2 + s * 0.4;
  }
  const st = b.state === 'drift' ? T.rose : b.status === 'approved' || b.state === 'verified' ? T.lime : b.status === 'draft' ? T.sand : null;
  if (st) { ctx.beginPath(); ctx.arc(x - r, yc, r, 0, Math.PI * 2); ctx.fillStyle = st; ctx.fill(); x -= r * 2 + s * 0.4; }
  if (b.crit) {
    const f = fontOf(650, s * 0.6, fam), w = textW(ctx, b.crit, f) + s * 0.6;
    ctx.beginPath(); roundRect(ctx, x - w, yc - s * 0.42, w, s * 0.84, s * 0.22);
    ctx.strokeStyle = rgba(T.soft, 0.4); ctx.lineWidth = 1; ctx.stroke();
    ctx.fillStyle = T.soft; ctx.font = f; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(b.crit, x - w / 2, yc + 0.5); ctx.textAlign = 'left';
    x -= w + s * 0.35;
  }
  return x;
}

// ---------------------------------------------------------------- blocks

/**
 * rect: screen CSS px. lod: 0 dot · 1 shape · 2 name · 3 glyph + badges · 4 brief.
 * style: {T, fam, dpr, tint, alpha, k, sel, hov, lit, litN, health, stale, moving, peek, peeking, textAlpha}
 */
export function drawNode(ctx, node, rect, style, lod) {
  const { x, y, w, h } = rect, T = style.T, fam = style.fam, dpr = style.dpr || 1;
  if (w < 0.5 || h < 0.5 || style.alpha <= 0.003) return;
  ctx.globalAlpha = style.alpha;
  const L = nodeLook(node);
  const tint = style.health ? healthColor(node.badges, T) : style.tint;
  const base = L.muted ? T.muted : tint;
  if (lod <= 0) {
    ctx.fillStyle = base; ctx.beginPath(); ctx.arc(x + w / 2, y + h / 2, clamp(Math.min(w, h) / 2, 1.5, 4), 0, 7); ctx.fill();
    ctx.globalAlpha = 1; return;
  }
  const r = clamp(Math.min(w, h) * 0.13, 2, 12);
  const light = style.light;
  const sel = style.sel, hov = style.hov, lit = style.lit;
  const tab = L.tab && lod >= 2 ? clamp(h * 0.24, 12, 30) : 0;
  const fy = y + tab * 0.5, fh = h - tab * 0.5; // frame body below the tab
  const path = () => { ctx.beginPath(); shapePath(ctx, L.shape, x, L.tab ? fy : y, w, L.tab ? fh : h, r); };

  if (style.only !== 'text') {
    // glow: two soft strokes (only when calm enough to matter)
    if (lod >= 2 && !style.moving && !style.peek && !L.frame) {
      path();
      const g = sel ? 0.22 : hov ? 0.15 : lit ? 0.18 : 0.07;
      ctx.strokeStyle = rgba(lit ? T.lime : base, g * 0.55); ctx.lineWidth = 9; ctx.stroke();
      ctx.strokeStyle = rgba(lit ? T.lime : base, g); ctx.lineWidth = 4; ctx.stroke();
    }
    // body
    path();
    if (L.frame) {
      ctx.fillStyle = rgba(light ? T.s1 : T.bg, 0.6); ctx.fill();
      ctx.fillStyle = rgba(base, light ? 0.05 : 0.035); ctx.fill();
    } else {
      ctx.fillStyle = L.outline ? T.bg : T.s1; ctx.fill();
      const gr = ctx.createLinearGradient(0, y, 0, y + h);
      const a0 = L.outline ? 0.06 : light ? 0.2 : 0.17, a1 = L.outline ? 0.02 : light ? 0.08 : 0.045;
      gr.addColorStop(0, rgba(base, a0)); gr.addColorStop(1, rgba(base, a1));
      ctx.fillStyle = gr; ctx.fill();
    }
    if (L.band && lod >= 2) { // class header band
      ctx.save(); path(); ctx.clip();
      ctx.fillStyle = rgba(base, L.outline ? 0.1 : 0.26); ctx.fillRect(x, y, w, Math.min(h * 0.32, 15));
      ctx.restore();
    }
    // border
    path();
    ctx.lineWidth = sel ? 1.8 : 1.25;
    ctx.strokeStyle = rgba(lit ? T.lime : base, sel ? 1 : hov ? 0.9 : L.frame ? 0.5 : 0.6);
    if (L.dashed) ctx.setLineDash(L.frame ? [6, 5] : [5, 4]);
    ctx.stroke(); ctx.setLineDash([]);
    if (L.double && lod >= 1 && w > 24) {
      ctx.beginPath(); shapePath(ctx, 'rect', x + 3.5, y + 3.5, w - 7, h - 7, Math.max(1, r - 3));
      ctx.strokeStyle = rgba(base, 0.26); ctx.lineWidth = 1; ctx.stroke();
    }
    if (!L.frame && !L.outline && lod >= 2 && !light) { // glass highlight along the top edge
      ctx.beginPath(); ctx.moveTo(x + r + 2, y + 1.1); ctx.lineTo(x + w - r - (L.shape === 'notch' || L.shape === 'fold' ? 16 : 2), y + 1.1);
      ctx.strokeStyle = 'rgba(255,255,255,0.07)'; ctx.lineWidth = 1; ctx.stroke();
    }
    if (L.shape === 'cyl' && w > 16) {
      const ry = Math.min(h * 0.13, 11, w / 4);
      ctx.beginPath(); ctx.ellipse(x + w / 2, y + ry, w / 2, ry, 0, 0, Math.PI); ctx.strokeStyle = rgba(base, 0.45); ctx.lineWidth = 1; ctx.stroke();
    }
    if (L.shape === 'fold' && w > 16) {
      const f = Math.min(h * 0.32, 14, w / 4);
      ctx.beginPath(); ctx.moveTo(x + w - f, y); ctx.lineTo(x + w - f, y + f); ctx.lineTo(x + w, y + f); ctx.closePath();
      ctx.fillStyle = rgba(base, 0.3); ctx.fill();
    }
    if (L.own && w > 30) {
      ctx.beginPath(); shapePath(ctx, 'rect', x + 6, y + 6, w - 12, h - 12, Math.max(1, r - 4));
      ctx.setLineDash([3, 3]); ctx.strokeStyle = rgba(base, 0.32); ctx.lineWidth = 1; ctx.stroke(); ctx.setLineDash([]);
    }
    if (style.stale && style.health) {
      path(); ctx.strokeStyle = T.sand; ctx.lineWidth = 2; ctx.stroke();
    }
    if (sel || lit) { // selection / trace ring, offset outside the block
      ctx.beginPath(); shapePath(ctx, L.shape === 'pill' ? 'pill' : 'rect', x - 4, (L.tab ? fy : y) - 4, w + 8, (L.tab ? fh : h) + 8, r + 4);
      ctx.strokeStyle = rgba(sel ? T.mint : T.lime, sel ? 0.9 : 0.75); ctx.lineWidth = sel ? 2 : 1.6; ctx.stroke();
    }
  }
  if (lod < 2 || style.only === 'body') { ctx.globalAlpha = 1; return; }

  // ---------- text
  const ta = style.textAlpha ?? 1;
  if (ta <= 0.01) { ctx.globalAlpha = 1; return; }
  ctx.globalAlpha = style.alpha * ta;
  const k = style.k || 1;
  const baseFs = node.type === 'symbol' ? 12.5 : node.type === 'file' ? 13 : 14;
  const fs = clamp(baseFs * k, 10.5, baseFs * 1.55);
  const nameFont = fontOf(L.frame || node.type === 'symbol' ? 600 : 650, fs, fam);
  const ink = L.muted ? T.soft : T.ink;
  ctx.textBaseline = 'middle'; ctx.textAlign = 'left';
  const label = node.name || node.id;

  if (lod === 2 || (h < fs * 1.9 && !L.tab)) { // compact: one centred (or left) line
    const lead = L.letter && lod >= 3 ? Math.min(h - 8, fs * 1.25) : 0;
    const avail = w - 16 - (lead ? lead + 6 : 0) - (L.shape === 'hex' ? h * 0.3 : 0);
    const s = ellipsize(ctx, label, nameFont, avail);
    if (s) {
      const tw = textW(ctx, s, nameFont), tot = tw + (lead ? lead + 6 : 0);
      const lx = lod >= 3 && node.type === 'symbol' ? x + (L.shape === 'pill' ? h * 0.32 : 8) : x + (w - tot) / 2;
      const cy = (L.tab ? fy + fh / 2 : y + h / 2);
      if (lead) letterChip(ctx, L.letter, px(lx, dpr), px(cy - lead / 2, dpr), lead, base, T, fam);
      ctx.font = nameFont; ctx.fillStyle = ink; ctx.fillText(s, px(lx + (lead ? lead + 6 : 0), dpr), px(cy, dpr));
      if (lod >= 3 && node.badges && w - tot > 70) { ctx.globalAlpha = style.alpha * ta; badges(ctx, node.badges, x + w - 9, cy, fs * 0.95, T, fam); }
    }
    ctx.globalAlpha = 1; return;
  }

  const pad = clamp(12 * k, 9, 18);
  if (L.tab) { // group / dir: the name sits in a tab on the frame's top edge
    const tf = fontOf(650, clamp(fs * 0.92, 10.5, 20), fam);
    const want = x + r + textW(ctx, label, tf) + pad * 2 + (lod >= 3 ? tab * 0.8 : 0) + 6; // the tab with the whole name
    const set = lod >= 3 ? pickBadges(ctx, node.badges, x + w - pad, y + tab / 2, fs * 0.9, T, fam, Math.min(want, x + w * 0.62)) : null;
    const bl = set ? badges(ctx, set, x + w - pad, y + tab / 2, fs * 0.9, T, fam) : x + w - pad;
    const tw = Math.max(Math.min(w - 2 * r, tab * 2.4), Math.min(bl - 6 - (x + r), textW(ctx, label, tf) + pad * 2 + (lod >= 3 ? tab * 0.8 : 0)));
    ctx.beginPath(); roundRect(ctx, x + r, y, tw, tab, Math.min(6, tab / 2));
    ctx.fillStyle = light ? T.s2 : T.s2; ctx.fill();
    ctx.strokeStyle = rgba(base, 0.5); ctx.lineWidth = 1; ctx.stroke();
    let lx = x + r + pad * 0.7;
    if (lod >= 3) { const gs = tab * 0.56; drawGlyph(ctx, L.glyph, px(lx, dpr), px(y + (tab - gs) / 2, dpr), gs, base); lx += gs + pad * 0.45; }
    const s = ellipsize(ctx, label, tf, x + r + tw - lx - pad * 0.5);
    ctx.font = tf; ctx.fillStyle = ink; ctx.fillText(s, px(lx, dpr), px(y + tab / 2 + 0.5, dpr));
    if (lod >= 3) {
      if (node.drill && !style.peeking && h > tab + fs * 2) {
        const cf = fontOf(500, fs * 0.8, fam); ctx.font = cf; ctx.fillStyle = T.muted; ctx.textAlign = 'right';
        ctx.fillText(`${node.n || 0} inside  ›`, px(x + w - pad, dpr), px(y + h - pad * 0.9, dpr)); ctx.textAlign = 'left';
      }
    }
    ctx.globalAlpha = 1; return;
  }

  // full header: glyph · name · badges, then kind line, then brief
  const top = y + pad + fs * 0.55 + (L.shape === 'cyl' ? Math.min(h * 0.13, 11, w / 4) * 0.9 : 0);
  let lx = x + pad + (L.shape === 'hex' ? Math.min(h / 2, w * 0.14, 24) * 0.6 : 0);
  const gsz = fs * 1.15;
  if (lod >= 3) {
    if (L.letter) letterChip(ctx, L.letter, px(lx, dpr), px(top - gsz / 2, dpr), gsz, base, T, fam);
    else drawGlyph(ctx, L.glyph, px(lx, dpr), px(top - gsz / 2, dpr), gsz, base);
    lx += gsz + fs * 0.5;
  }
  let bl = x + w - pad, kr = x + w - pad - 4;
  const y2 = top + fs * 1.3, kindRow = lod >= 3 && y2 + fs * 0.5 < y + h - 4;
  if (lod >= 3 && node.badges) { // badges share the name row; when the name would not fit they move to the kind row (names win)
    const bx = x + w - pad - (L.shape === 'notch' ? 10 : 0);
    ctx.save(); ctx.globalAlpha = 0; const left = badges(ctx, node.badges, bx, top, fs * 0.95, T, fam); ctx.restore();
    const need = textW(ctx, label, nameFont) + 6 + (L.req ? fs * 3 : 0);
    const down = kindRow && need > left - lx;
    // no kind row to move to (34 px pills): keep the findings dot only, or no badges, so the name is whole
    const set = kindRow ? node.badges : pickBadges(ctx, node.badges, bx, top, fs * 0.95, T, fam, lx + need);
    ctx.globalAlpha = style.alpha * ta;
    if (set) {
      const l2 = badges(ctx, set, bx, down ? y2 : top, fs * 0.95, T, fam) - 6;
      if (down) kr = l2 - 2; else bl = l2;
    }
  }
  if (lod >= 3 && L.req) bl = chip(ctx, 'REQ', bl, top, T.sand, T, fam, fs * 0.66, 'right').x - 6;
  const nm = ellipsize(ctx, label, nameFont, bl - lx);
  ctx.font = nameFont; ctx.fillStyle = ink; ctx.fillText(nm, px(lx, dpr), px(top, dpr));
  if (lod >= 3) {
    const sf = fontOf(500, fs * 0.76, fam);
    let kind = node.type === 'module' || node.type === 'root' ? node.kind : node.type === 'symbol' ? node.kind : node.type === 'file' ? (node.kind || 'file') : node.kind || node.type;
    if (node.type === 'own') kind = 'own code';
    if (L.req) kind = 'requirement';
    if (kindRow) {
      ctx.font = sf; ctx.fillStyle = T.muted;
      ctx.fillText(ellipsize(ctx, String(kind || '').toUpperCase().split('').join(' '), sf, kr - lx), px(lx, dpr), px(y2, dpr));
    }
    if (lod >= 4 && node.brief && !style.peeking) {
      const bf = fontOf(400, clamp(fs * 0.84, 10.5, 15), fam), lh = fs * 1.2;
      const lines = wrap2(ctx, node.brief, bf, w - pad * 2);
      ctx.font = bf; ctx.fillStyle = rgba(T.soft, 0.9);
      lines.forEach((ln, i) => { const yy = y2 + fs * 1.15 + i * lh + lh * 0.3; if (yy + lh * 0.4 < y + h - 2) ctx.fillText(ln, px(x + pad, dpr), px(yy, dpr)); });
    }
    if (node.drill && !style.peeking) {
      const cf = fontOf(500, fs * 0.78, fam), t = `${node.n || 0}  ›`;
      ctx.font = cf; ctx.fillStyle = rgba(base, 0.85); ctx.textAlign = 'right';
      ctx.fillText(t, px(x + w - pad - (L.shape === 'hex' ? 10 : 0), dpr), px(y + h - pad * 0.85 - (L.shape === 'cyl' ? 6 : 0), dpr)); ctx.textAlign = 'left';
      if (L.double) drawGlyph(ctx, 'stack', px(x + w - pad - textW(ctx, t, cf) - fs * 1.1, dpr), px(y + h - pad * 0.85 - fs * 0.42, dpr), fs * 0.82, rgba(base, 0.7));
    }
    if (L.own && w > 90) chip(ctx, 'own code', x + w - pad - 2, y + h - pad * 0.95, T.muted, T, fam, fs * 0.7, 'right');
  }
  ctx.globalAlpha = 1;
}

/** Small rounded chip, anchored left (default) or right at x, centred on y. */
export function chip(ctx, text, x, y, color, T, fam, size = 10, align = 'left') {
  const f = fontOf(650, size, fam), w = textW(ctx, text, f) + size * 1.1, h = size * 1.65;
  const x0 = align === 'right' ? x - w : align === 'center' ? x - w / 2 : x;
  ctx.beginPath(); roundRect(ctx, x0, y - h / 2, w, h, h / 2);
  ctx.fillStyle = rgba(T.s2, 0.96); ctx.fill();
  ctx.strokeStyle = rgba(color, 0.7); ctx.lineWidth = 1; ctx.stroke();
  ctx.fillStyle = color; ctx.font = f; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText(text, x0 + w / 2, y + 0.5); ctx.textAlign = 'left';
  return { x: x0, y: y - h / 2, w, h };
}

/** Ghost: a muted dashed half-pill whose flat side faces the frame, with a "› path" sub-label. */
export function drawGhost(ctx, g, rect, style, lod) {
  const { x, y, w, h } = rect, T = style.T, fam = style.fam, dpr = style.dpr || 1;
  if (w < 0.5 || style.alpha <= 0.003) return;
  ctx.globalAlpha = style.alpha;
  const pos = rect.pos || (rect.side === 'in' ? 'left' : rect.side === 'both' ? 'top' : 'right'); // where the ghost sits around the frame
  const shape = { left: 'half-l', right: 'half-r', top: 'half-t', bottom: 'half-b' }[pos] || 'half-r';
  if (lod <= 0) { ctx.fillStyle = T.muted; ctx.beginPath(); ctx.arc(x + w / 2, y + h / 2, 2, 0, 7); ctx.fill(); ctx.globalAlpha = 1; return; }
  ctx.beginPath(); shapePath(ctx, shape, x, y, w, h, 4);
  ctx.fillStyle = rgba(T.bg, 0.85); ctx.fill();
  ctx.fillStyle = rgba(T.muted, style.hov ? 0.16 : 0.08); ctx.fill();
  ctx.setLineDash([4, 3]); ctx.lineWidth = style.sel ? 1.6 : 1.1;
  ctx.strokeStyle = rgba(style.lit ? T.lime : T.muted, style.hov || style.sel ? 0.95 : 0.65); ctx.stroke(); ctx.setLineDash([]);
  if (lod >= 2) {
    const k = style.k || 1, fs = clamp(12 * k, 10, 17);
    const nf = fontOf(600, fs, fam), sf = fontOf(500, fs * 0.82, fam);
    const padL = pos === 'left' ? h * 0.5 : 9, padR = pos === 'right' ? h * 0.5 : 9;
    const avail = w - padL - padR;
    const name = ellipsize(ctx, g.name || g.peer || g.id, nf, avail);
    const nw = textW(ctx, name, nf);
    ctx.textBaseline = 'middle'; ctx.font = nf; ctx.fillStyle = T.soft;
    ctx.fillText(name, px(x + padL, dpr), px(y + h / 2, dpr));
    // where the peer lives, below what the crumbs show; cut from the left so the nearest parent survives,
    // and only whole segments (`› ports`, `› … › targets`)
    const rest = ghostParents(g, style.crumbs), room = avail - nw - 8;
    let sub = '';
    for (let i = 0; i < rest.length && !sub; i++) {
      const t = (i ? '› … › ' : '› ') + rest.slice(i).join(' › ');
      if (textW(ctx, t, sf) <= room) sub = t;
    }
    if (sub) { ctx.font = sf; ctx.fillStyle = T.muted; ctx.fillText(sub, px(x + padL + nw + 7, dpr), px(y + h / 2 + 0.5, dpr)); }
  }
  ctx.globalAlpha = 1;
}

// ---------------------------------------------------------------- edges

const CODE = ['call', 'import', 'inherit', 'contract', 'data'];
/**
 * How an aggregated level edge looks, given the kinds that pass the filter (§8.6).
 * → {key, color, width, alpha, dash, head:'arrow'|'open'|'tri', flow, chip, label}
 */
export function edgeLook(e, vk, T) {
  const has = (k) => (vk[k] || 0) > 0;
  const code = CODE.filter(has);
  const codeN = code.reduce((s, k) => s + vk[k], 0);
  if (e.state === 'undeclared' && code.length) return { key: 'x', color: T.rose, width: 2, alpha: 0.95, dash: null, head: 'arrow', chip: '!', label: false };
  if (has('flow')) {
    if (code.length && e.state === 'declared') return { key: 'decl', color: T.mint, width: 1.6, alpha: 0.75, dash: [5, 5], head: 'arrow', label: true, note: 'declared · not traced' };
    if (e.dash) return { key: 'flowd', color: T.mint, width: 1.7, alpha: 0.8, dash: [6, 5], head: 'arrow', flow: true, label: true };
    return { key: 'flow', color: T.mint, width: 2, alpha: 0.55, dash: null, head: 'arrow', flow: true, label: true };
  }
  if (has('call') || has('import')) {
    const c = e.conf ?? 1, w = Math.min(4.5, 1 + Math.log2(Math.max(1, codeN)));
    const chipT = codeN > 1 ? `×${codeN}` : null;
    if (c >= 0.8) return { key: 'obs', color: T.mint, width: w, alpha: 0.7, dash: null, head: 'arrow', chip: chipT };
    if (c >= 0.5) return { key: 'obs5', color: T.mint, width: w, alpha: 0.5, dash: [6, 4], head: 'arrow', chip: chipT };
    return { key: 'obs0', color: T.mint, width: w, alpha: 0.35, dash: [1.5, 4], head: 'arrow', chip: chipT };
  }
  if (has('inherit')) return { key: 'inh', color: T.muted, width: 1.4, alpha: 0.85, dash: null, head: 'tri' };
  if (has('contract') || has('data')) return { key: 'con', color: T.sand, width: 1.5, alpha: 0.8, dash: [8, 4, 2, 4], head: 'arrow', chip: codeN > 1 ? `×${codeN}` : null };
  return { key: 'dep', color: T.muted, width: 1.25, alpha: 0.75, dash: [1.5, 4], head: 'open', label: true };
}

/** Stroke one route (ctx in world transform; k = zoom). o: {alpha, lit, flowOn, flowOff, heads} */
export function drawEdge(ctx, route, look, k, T, o) {
  const color = o.lit ? T.lime : look.color;
  const a = o.alpha * (o.lit ? 1 : look.alpha);
  if (a <= 0.003) return;
  const lw = (o.lit ? Math.max(2.4, look.width) : look.width) / k;
  ctx.strokeStyle = rgba(color, a); ctx.lineWidth = lw;
  ctx.setLineDash(look.dash && !o.lit ? look.dash.map((d) => d / k) : []);
  ctx.lineDashOffset = look.dash && look.flow && o.flowOn ? -o.flowOff : 0;
  ctx.stroke(route.path);
  if (look.flow && !look.dash && o.flowOn && !o.lit) { // moving flow dashes over the solid line
    ctx.setLineDash([7 / k, 17 / k]); ctx.lineDashOffset = -o.flowOff;
    ctx.strokeStyle = rgba(color, Math.min(1, o.alpha * 0.95)); ctx.lineWidth = (look.width + 0.4) / k;
    ctx.stroke(route.path);
  }
  ctx.setLineDash([]); ctx.lineDashOffset = 0;
  if (o.heads) drawHead(ctx, route, o.lit ? 'arrow' : look.head, color, Math.min(1, o.alpha), k, look.width, T);
}

function drawHead(ctx, route, head, color, a, k, w, T) {
  const [ex, ey] = route.end, [dx, dy] = route.dir;
  const s = (7 + Math.min(3, w)) / k, nx = -dy, ny = dx;
  const bx = ex - dx * s, by = ey - dy * s;
  ctx.beginPath();
  ctx.moveTo(ex, ey); ctx.lineTo(bx + nx * s * 0.52, by + ny * s * 0.52);
  if (head === 'open') { ctx.moveTo(ex, ey); ctx.lineTo(bx - nx * s * 0.52, by - ny * s * 0.52); ctx.strokeStyle = rgba(color, a); ctx.lineWidth = 1.4 / k; ctx.stroke(); return; }
  if (head !== 'tri') ctx.lineTo(ex - dx * s * 0.72, ey - dy * s * 0.72);
  ctx.lineTo(bx - nx * s * 0.52, by - ny * s * 0.52); ctx.closePath();
  if (head === 'tri') { ctx.fillStyle = T.bg; ctx.fill(); ctx.strokeStyle = rgba(color, a); ctx.lineWidth = 1.3 / k; ctx.stroke(); return; }
  ctx.fillStyle = rgba(color, a); ctx.fill();
}

/** Edge label pill: text (one line, or two when it would be wider than max). → {lines, w, h, f} */
export function labelRect(ctx, text, fam, fs, max = Infinity) {
  const f = fontOf(500, fs, fam);
  let lines = [String(text ?? '')];
  if (textW(ctx, lines[0], f) > max) lines = wrap2(ctx, lines[0], f, max).filter(Boolean);
  const tw = Math.max(0, ...lines.map((l) => textW(ctx, l, f)));
  return { lines, w: tw + fs * 1.3, h: fs * (lines.length > 1 ? 2.95 : 1.8), f };
}
/** Draws the pill centred at x, y (screen px). lr: labelRect result. Returns its rect. */
export function drawLabel(ctx, lr, x, y, look, T, fam, fs, alpha, lit, dpr = 1) {
  const { w, h, f, lines } = lr;
  const x0 = px(x - w / 2, dpr), y0 = px(y - h / 2, dpr);
  ctx.globalAlpha = alpha;
  ctx.beginPath(); roundRect(ctx, x0, y0, w, h, Math.min(h / 2, fs * 0.9));
  ctx.fillStyle = rgba(T.s1, 0.94); ctx.fill();
  ctx.strokeStyle = rgba(lit ? T.lime : look.color, 0.42); ctx.lineWidth = 1; ctx.stroke();
  ctx.font = f; ctx.fillStyle = lit ? T.lime : T.soft; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  const lh = fs * 1.2, top = y - ((lines.length - 1) * lh) / 2;
  lines.forEach((ln, i) => ctx.fillText(ln, px(x, dpr), px(top + i * lh + 0.5, dpr)));
  ctx.textAlign = 'left';
  ctx.globalAlpha = 1;
  return { x: x0, y: y0, w, h };
}
