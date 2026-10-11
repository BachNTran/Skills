---
name: svg-animation
description: Make documentation livelier and easier to grasp with a diagram or a self-contained animated SVG (optionally with a progress playback bar) when a doc explains something that moves — a request through a system, a state machine, a training or experiment replay, a data pipeline, a before/after. Plays in the wiki, GitHub, Obsidian and any Markdown viewer that renders SVG. Use when writing or reviewing docs that explain a process, and for "animate this", "animated diagram", "playback bar", "show how X flows".
---

# svg-animation — nudge: show it, don't only tell it

When a doc explains **something that moves or changes over time**, ask whether a picture would make it
click faster. If yes, add one; if a static Mermaid diagram already does the job, stop there. Not every doc
needs one, and a forced animation is worse than none.

Good candidates: one request/event/tick through a system · a lifecycle or state machine · a pipeline stage by
stage · an experiment or training replay (curve draws, checkpoints appear) · a before/after of a change ·
how a number accumulates (latency, cost, error, reward).

## How to make one
- **Design for the content.** Draw what the thing actually looks like: a queue for a
  queue, real class names on boxes, real fields on messages. Pick the motion that tells the story — a token
  travelling, a line drawing on, bars growing, labels appearing, a counter ticking. No house style required.
- **Self-contained SVG, no script**, so it plays as an image in Markdown: CSS keyframes or SMIL
  (`<animate>`, `<animateMotion>`, `<set>`). Respect `prefers-reduced-motion`. Keep one idea per figure and
  a 5–12 s cycle.
- **A playback bar helps when order matters**: a thin track that fills over the cycle with markers at the
  key moments tells the reader where they are in the story. Skip it when the motion is ambient.
- **Embed it where it is explained** — `![alt text that says what moves](docs/<name>.svg)` — and keep the
  text (and in modgate projects the Mermaid diagram) as the source of truth; the figure helps a human see it.
- **Look before you ship**: render a few frames (headless Chromium/Playwright is enough) and check the right
  thing moves at the right time and no label overflows or is covered.

## Optional helper
`scripts/anim_svg.py spec.json out.svg` (stdlib) saves hand-writing SMIL timing: a scene of `elements`
(`box`, `text`, `path`, `circle`, `rect`, or `raw` SVG for anything else) and `tracks` on one clock
(`highlight`, `move`, `draw`, `grow`, `fade`, `count`, `flow`), plus an optional playback bar on the same
clock. Tracks can target ids inside `raw` SVG. A spec with `steps` expands into a step-loop preset.
Examples: `assets/example_request_loop.json`, `assets/example_training_curve.json`. Use it when it fits;
hand-write the SVG when it doesn't.
