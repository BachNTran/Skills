#!/usr/bin/env python3
"""anim_svg — one timeline drives any SVG animation plus a progress playback bar.

usage: anim_svg.py spec.json out.svg

Everything is SMIL (<animate>, <animateMotion>) on one clock of `duration` seconds,
so it plays in an <img> under a no-script CSP (wiki, GitHub, Obsidian, any Markdown
viewer that renders SVG). The playback bar is just another track on the same clock.

spec.json
{
  "title": "...", "subtitle": "...", "width": 960, "height": 540, "duration": 12, "loop": true,
  "elements": [                      # static scene; every element may have an "id"
    {"type": "box",    "id": "a", "x": 80, "y": 80, "w": 200, "h": 60, "title": "Router", "code": "→ Route",
     "style": "box|eng|db|gate"},
    {"type": "text",   "x": 40, "y": 400, "text": "hello", "cls": "t|s|c|g"},
    {"type": "path",   "id": "p", "d": "M80 300 L400 300", "cls": "lane|rd|wr"},
    {"type": "circle", "id": "dot", "cx": 0, "cy": 0, "r": 9},
    {"type": "rect",   "id": "bar1", "x": 500, "y": 400, "w": 0, "h": 30, "fill": "#5eead4"},
    {"type": "raw",    "svg": "<g id='gear'><line .../><rect .../></g>"}   # anything else
  ],
  "tracks": [                        # what moves, and when (seconds on the shared clock)
    {"kind": "highlight", "target": "a", "at": [0, 2]},                 # glow a box during a window
    {"kind": "move",  "target": "dot", "path": "p", "at": [0, 6], "points": [0, 0.5, 1]},  # ride a path
    {"kind": "fade",  "target": "a", "at": [2, 3], "from": 0.2, "to": 1},
    {"kind": "grow",  "target": "bar1", "attr": "width", "at": [1, 4], "from": 0, "to": 300},  # bars, gauges
    {"kind": "draw",  "target": "p", "at": [0, 2]},                     # stroke draws itself on
    {"kind": "count", "x": 700, "y": 80, "at": [0, 12], "values": ["t=0", "t=1", "t=2"], "cls": "t"},
    {"kind": "flow",  "target": "p"}                                     # marching dashes, always on
  ],
  "progress": {"label": "progress", "end": "→ next", "markers": [[0, "start"], [6, "half"]]},
  "footnote": "..."
}
A track window [t0, t1] holds its end state until the cycle restarts (loop) or forever (loop false).

Preset: a spec with "steps" (and no "tracks") is expanded into a step-loop: boxes around a
centre, each lit in turn, a token riding the loop, one progress marker per step. See
assets/example_request_loop.json. Any other spec uses only the generic tracks.
"""
from __future__ import annotations

import json
import math
import re
import sys
from html import escape

CSS = """.bg{fill:#0b0f0d}.box{fill:#121a16;stroke:#8da295;stroke-width:1.5}
.eng{fill:#101a2b;stroke:#5b8def;stroke-width:2}.db{fill:#1a1230;stroke:#a06bff;stroke-width:2}
.gate{fill:#121a16;stroke:#f2b84b;stroke-width:2.5}
.t{fill:#f0f5f1;font-size:14px;font-weight:600}.c{fill:#5eead4;font-size:12px;font-family:ui-monospace,monospace}
.s{fill:#8da295;font-size:11.5px}.g{fill:#4f6b5a;font-size:11px;letter-spacing:.08em;text-transform:uppercase}
.n{fill:#0b0f0d;font-size:12px;font-weight:700}.lane{fill:none;stroke:#2f4a3c;stroke-width:2}.line{fill:none;stroke:#5eead4;stroke-width:2.5}
.rd{fill:none;stroke:#8da295;stroke-width:1.5;marker-end:url(#a)}
.wr{fill:none;stroke:#a06bff;stroke-width:1.5;stroke-dasharray:5 5}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}"""

PB_H = 90  # height reserved for the playback bar


def esc(s: object) -> str:
    return escape(str(s), quote=True)


class Clock:
    """Turns second windows into SMIL keyTimes on one shared cycle."""

    def __init__(self, duration: float, loop: bool):
        self.T, self.loop = float(duration), loop

    def k(self, t: float) -> float:
        return min(max(t / self.T, 0.0), 1.0)

    def anim(self, attr: str, before: object, during: list, t0: float, t1: float, tag: str = "animate") -> str:
        """`before` until t0, interpolate `during` over [t0, t1], hold the last value after."""
        k0, k1 = self.k(t0), self.k(t1)
        vals, keys = [before], [0.0]
        if k0 > 0:
            vals.append(before); keys.append(k0)
        n = len(during)
        for i, v in enumerate(during):
            vals.append(v); keys.append(k0 + (k1 - k0) * (i / (n - 1) if n > 1 else 1))
        if keys[-1] < 1:
            vals.append(during[-1]); keys.append(1.0)
        keys = _monotone(keys)
        rep = 'repeatCount="indefinite"' if self.loop else 'fill="freeze"'
        return (f'<{tag} attributeName="{attr}" dur="{self.T:g}s" {rep} calcMode="linear" '
                f'values="{";".join(map(str, vals))}" keyTimes="{";".join(f"{x:.4f}" for x in keys)}"/>')

    def window(self, t0: float, t1: float, on: float = 1.0, off: float = 0.0) -> str:
        """Opacity `on` only inside [t0, t1)."""
        k0, k1 = self.k(t0), self.k(t1)
        vals, keys = [off], [0.0]
        if k0 > 0:
            vals += [off, on]; keys += [max(k0 - 1e-4, 0), k0]
        else:
            vals[0] = on
        if k1 < 1:
            vals += [on, off, off]; keys += [max(k1 - 1e-4, k0), k1, 1.0]
        else:
            vals.append(on); keys.append(1.0)
        rep = 'repeatCount="indefinite"' if self.loop else 'fill="freeze"'
        return (f'<animate attributeName="opacity" dur="{self.T:g}s" {rep} calcMode="discrete" '
                f'values="{";".join(map(str, vals))}" keyTimes="{";".join(f"{x:.4f}" for x in _monotone(keys))}"/>')


def _monotone(keys: list[float]) -> list[float]:
    out: list[float] = []
    for k in keys:
        out.append(max(k, out[-1]) if out else 0.0)
    out[-1] = 1.0
    return out


# ---------- static elements ----------
def element(e: dict, anims: dict[str, list[str]]) -> str:
    i = e.get("id")
    idattr = f' id="{esc(i)}"' if i else ""
    inner = "".join(anims.get(i, [])) if i else ""
    t = e["type"]
    if t == "box":
        x, y, w, h = e["x"], e["y"], e.get("w", 220), e.get("h", 60)
        cx = x + w / 2
        g = [f'<g{idattr}>',
             f'<rect class="{e.get("style", "box")}" x="{x}" y="{y}" width="{w}" height="{h}" rx="9"/>',
             f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="#5eead4" opacity="0">'
             f'{"".join(anims.get(f"{i}#hl", []))}</rect>']
        if e.get("badge") is not None:
            col = "#f2b84b" if e.get("style") == "gate" else "#5eead4"
            g.append(f'<circle cx="{x}" cy="{y}" r="11" fill="{col}"/><text x="{x}" y="{y + 4}" '
                     f'text-anchor="middle" class="n">{esc(e["badge"])}</text>')
        if e.get("group"):
            g.append(f'<text x="{x}" y="{y - 8}" class="g">{esc(e["group"])}</text>')
        lines = [("t", e.get("title", ""))] + ([("c", e["code"])] if e.get("code") else []) + [("s", ln) for ln in e.get("lines", [])]
        top = y + h / 2 - (len(lines) - 1) * 9.5 + 5
        for j, (cls, txt) in enumerate(lines):
            g.append(f'<text x="{cx}" y="{top + 19 * j:.0f}" text-anchor="middle" class="{cls}">{esc(txt)}</text>')
        return "".join(g) + inner + "</g>"
    if t == "text":
        anchor = f' text-anchor="{e["anchor"]}"' if e.get("anchor") else ""
        return f'<text{idattr} x="{e["x"]}" y="{e["y"]}" class="{e.get("cls", "s")}"{anchor}>{esc(e["text"])}{inner}</text>'
    if t == "path":
        return f'<path{idattr} class="{e.get("cls", "lane")}" d="{e["d"]}">{inner}</path>'
    if t == "circle":
        return (f'<g{idattr}><circle cx="{e.get("cx", 0)}" cy="{e.get("cy", 0)}" r="{e.get("r", 9)}" '
                f'fill="{e.get("fill", "#5eead4")}"/><circle cx="{e.get("cx", 0)}" cy="{e.get("cy", 0)}" '
                f'r="{e.get("r", 9) + 7}" fill="none" stroke="{e.get("fill", "#5eead4")}" opacity=".5"/>{inner}</g>')
    if t == "rect":
        return (f'<rect{idattr} x="{e["x"]}" y="{e["y"]}" width="{e["w"]}" height="{e["h"]}" rx="{e.get("rx", 3)}" '
                f'fill="{e.get("fill", "#5eead4")}">{inner}</rect>')
    if t == "raw":  # any SVG you like; give its root an id to animate it with tracks
        return e["svg"]
    raise ValueError(f"unknown element type {t}")


# ---------- tracks ----------
def polyline_length(d: str) -> float:
    """Length of an M/L-only path; 0 if it uses curves (then pass "length" in the track)."""
    if re.search(r"[^MLZml0-9.,\s-]", d):
        return 0.0
    nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", d)]
    pts = list(zip(nums[::2], nums[1::2]))
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)) + 1


def tracks(spec: dict, clock: Clock, paths: dict[str, str]) -> tuple[dict[str, list[str]], list[str]]:
    anims: dict[str, list[str]] = {}
    extra: list[str] = []

    def add(key: str, a: str) -> None:
        anims.setdefault(key, []).append(a)

    for tr in spec.get("tracks", []):
        k, tgt = tr["kind"], tr.get("target")
        t0, t1 = tr.get("at", [0, clock.T])
        if k == "highlight":
            add(f"{tgt}#hl", clock.window(t0, t1, tr.get("strength", 0.22)))
        elif k == "fade":
            add(tgt, clock.anim("opacity", tr.get("from", 0), [tr.get("from", 0), tr.get("to", 1)], t0, t1))
        elif k == "grow":
            add(tgt, clock.anim(tr.get("attr", "width"), tr.get("from", 0), [tr.get("from", 0), tr["to"]], t0, t1))
        elif k == "draw":
            L = tr.get("length") or polyline_length(paths.get(tgt, "")) or 2000
            add(tgt, f'<set attributeName="stroke-dasharray" to="{L} {L}"/>')
            add(tgt, clock.anim("stroke-dashoffset", L, [L, 0], t0, t1))
        elif k == "flow":
            add(tgt, '<animate attributeName="stroke-dashoffset" values="0;-20" dur="1.2s" repeatCount="indefinite"/>')
        elif k == "move":
            pts = tr.get("points", [0, 1])
            k0, k1 = clock.k(t0), clock.k(t1)
            kt = [0.0] + [k0 + (k1 - k0) * i / (len(pts) - 1) for i in range(len(pts))] + [1.0]
            kp = [pts[0]] + pts + [pts[-1]]
            kt = _monotone(kt)
            rep = 'repeatCount="indefinite"' if clock.loop else 'fill="freeze"'
            add(tgt, f'<animateMotion dur="{clock.T:g}s" {rep} calcMode="linear" '
                     f'keyPoints="{";".join(f"{p:.4f}" for p in kp)}" keyTimes="{";".join(f"{x:.4f}" for x in kt)}">'
                     f'<mpath href="#{tr["path"]}"/></animateMotion>')
        elif k == "count":
            vals = tr["values"]
            step = (t1 - t0) / len(vals)
            for j, v in enumerate(vals):
                extra.append(f'<text x="{tr["x"]}" y="{tr["y"]}" class="{tr.get("cls", "t")}" opacity="0">{esc(v)}'
                             f'{clock.window(t0 + j * step, t0 + (j + 1) * step)}</text>')
        else:
            raise ValueError(f"unknown track kind {k}")
    return anims, extra


def playback_bar(spec: dict, clock: Clock, W: int, H: int) -> list[str]:
    pb = spec.get("progress")
    if pb is None:
        return []
    x0, Wb, yb = 60, W - 320, H + 40
    out = [f'<text x="24" y="{yb - 18}" class="g">{esc(pb.get("label", "progress"))}</text>',
           f'<rect x="{x0}" y="{yb - 4}" width="{Wb}" height="8" rx="4" fill="#1c2621"/>',
           f'<rect x="{x0}" y="{yb - 4}" width="0" height="8" rx="4" fill="#5eead4" opacity=".7">'
           f'{clock.anim("width", 0, [0, Wb], 0, clock.T)}</rect>']
    for j, (t, label) in enumerate(pb.get("markers", [])):
        x = x0 + Wb * clock.k(t)
        out += [f'<circle cx="{x:.0f}" cy="{yb}" r="9" fill="#121a16" stroke="#5eead4" stroke-width="1.5"/>',
                f'<circle cx="{x:.0f}" cy="{yb}" r="9" fill="#5eead4" opacity="0">{clock.window(t, clock.T)}</circle>',
                f'<text x="{x:.0f}" y="{yb + 4}" text-anchor="middle" class="n">{j + 1}</text>',
                f'<text x="{x:.0f}" y="{yb + 26}" text-anchor="middle" class="s">{esc(label)}</text>']
    out.append(f'<text x="{x0 + Wb + 14}" y="{yb + 4}" class="c">{esc(pb.get("end", ""))}</text>')
    return out


# ---------- preset: step loop ----------
def expand_step_loop(spec: dict) -> dict:
    steps, dt = spec["steps"], float(spec.get("step_seconds", 2))
    n = len(steps)
    els, trs = [], []
    pts = [(s["x"], s["y"]) for s in steps] + [(steps[0]["x"], steps[0]["y"])]
    seg = [math.dist(pts[i], pts[i + 1]) for i in range(n)]
    acc, kp = 0.0, [0.0]
    for s in seg:
        acc += s; kp.append(acc / sum(seg))
    els.append({"type": "path", "id": "loop", "cls": "lane", "d": "M" + " L".join(f"{x} {y}" for x, y in pts[:-1]) + " Z"})
    if spec.get("center"):
        c = spec["center"]
        els.append({"type": "box", "x": c["x"] - 115, "y": c["y"] - 42, "w": 230, "h": 84, "style": "eng",
                    "title": c["title"], "code": c.get("code", ""), "lines": [c["note"]] if c.get("note") else []})
    for i, s in enumerate(steps):
        els.append({"type": "box", "id": f"step{i}", "x": s["x"] - 110, "y": s["y"] - 30, "title": s["title"],
                    "code": s.get("code", ""), "group": s.get("group"), "badge": i + 1,
                    "style": "gate" if s.get("gate") else "box"})
        trs.append({"kind": "highlight", "target": f"step{i}", "at": [i * dt, (i + 1) * dt]})
    for e in spec.get("extras", []):
        w, h = e.get("w", 200), e.get("h", 56)
        els.append({"type": "box", "x": e["x"] - w / 2, "y": e["y"] - h / 2, "w": w, "h": h,
                    "title": e["title"], "lines": e.get("lines", []), "style": e.get("style", "box")})
    for a in spec.get("arrows", []):
        x1, y1, x2, y2, *kind = a
        write = bool(kind) and kind[0] == "write"
        els.append({"type": "path", "id": f"arr{len(els)}" if write else None, "cls": "wr" if write else "rd",
                    "d": f"M{x1} {y1} L{x2} {y2}"})
        if write:
            trs.append({"kind": "flow", "target": f"arr{len(els) - 1}"})
    els.append({"type": "circle", "id": "token"})
    trs.append({"kind": "move", "target": "token", "path": "loop", "at": [0, n * dt], "points": kp})
    out = {k: v for k, v in spec.items() if k not in ("steps", "center", "extras", "arrows", "progress_label", "progress_end", "step_seconds")}
    out.update(duration=n * dt, elements=els, tracks=trs)
    out.setdefault("progress", {"label": spec.get("progress_label", "progress"), "end": spec.get("progress_end", "")})
    out["progress"].setdefault("markers", [[i * dt, s.get("short", s["title"])] for i, s in enumerate(steps)])
    return out


def build(spec: dict) -> str:
    if "steps" in spec and "tracks" not in spec:
        spec = expand_step_loop(spec)
    W, H = spec.get("width", 960), spec.get("height", 540)
    clock = Clock(spec.get("duration", 10), spec.get("loop", True))
    HT = H + (PB_H if spec.get("progress") is not None else 0)
    anims, extra = tracks(spec, clock, {e["id"]: e["d"] for e in spec["elements"] if e["type"] == "path" and e.get("id")})
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {HT}" font-family="system-ui, sans-serif">',
           f"<title>{esc(spec.get('title', 'animation'))}</title><style>{CSS}</style>",
           '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
           'orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#8da295"/></marker></defs>',
           f'<rect class="bg" width="{W}" height="{HT}"/>']
    if spec.get("title"):
        out.append(f'<text x="24" y="32" class="t" font-size="18">{esc(spec["title"])}</text>')
    if spec.get("subtitle"):
        out.append(f'<text x="24" y="52" class="s">{esc(spec["subtitle"])}</text>')
    paths = [e for e in spec["elements"] if e["type"] == "path"]
    movers = [e for e in spec["elements"] if e["type"] == "circle"]
    rest = [e for e in spec["elements"] if e not in paths and e not in movers]
    out += [element(e, anims) for e in paths + rest + movers]  # paths under boxes, movers on top
    # tracks aimed at ids inside raw SVG: emit standalone animations that point at them
    known = {e.get("id") for e in spec["elements"] if e["type"] != "raw"}
    for key, items in anims.items():
        tid = key.split("#")[0]
        if tid not in known:
            out += [a.replace("<animate", f'<animate href="#{tid}"', 1).replace(
                "<set", f'<set href="#{tid}"', 1) for a in items]
    out += extra
    if spec.get("footnote"):
        out.append(f'<text x="24" y="{H - 20}" class="s">{esc(spec["footnote"])}</text>')
    out += playback_bar(spec, clock, W, H)
    out.append("</svg>")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: anim_svg.py spec.json out.svg")
    with open(sys.argv[1], encoding="utf-8") as f:
        svg = build(json.load(f))
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {sys.argv[2]}")
