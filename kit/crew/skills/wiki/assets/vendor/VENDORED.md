# Vendored libraries

Pinned, unmodified dist files so the wiki UI works offline (no CDN at runtime). Each was fetched once
with `npm pack <pkg>@<version>` (2026-10-10) and copied byte-for-byte. Versions are at least two weeks
old at vendoring time. Update: re-pack the new exact version, copy the same dist file, and refresh the
row and hash below.

| File | Package | Version | License | Source (dist path in tarball) | sha256 |
|---|---|---|---|---|---|
| `three.module.min.js` | three | 0.183.2 | MIT | https://registry.npmjs.org/three/-/three-0.183.2.tgz (`build/three.module.min.js`) | `0a61c95f14e0fa015b3083475c73424f360e5f6f5b74c282b50fdbc2f4c228fc` |
| `three.core.min.js` | three | 0.183.2 | MIT | https://registry.npmjs.org/three/-/three-0.183.2.tgz (`build/three.core.min.js`) | `0a9c2f0672c7b8d993ba7639e71919db181ca50c9dff99c78476d3e19057ca9c` |
| `3d-force-graph.min.js` | 3d-force-graph | 1.80.0 | MIT | https://registry.npmjs.org/3d-force-graph/-/3d-force-graph-1.80.0.tgz (`dist/3d-force-graph.min.js`) | `d96e738edcca580edd524730c1c6b05ed2efce028c23ca95db1bf43033a72e42` |
| `marked.umd.js` | marked | 18.0.14 | MIT | https://registry.npmjs.org/marked/-/marked-18.0.14.tgz (`lib/marked.umd.js`) | `21568877a938d2c4e7d74e27f18e60da96bb73a68809610ca39216e1efebae62` |
| `purify.min.js` | dompurify | 3.4.16 | Apache-2.0 (dual MPL-2.0 OR Apache-2.0; used under Apache-2.0) | https://registry.npmjs.org/dompurify/-/dompurify-3.4.16.tgz (`dist/purify.min.js`) | `2c90a9b46d6463f26038a29b686e82bc91de01fdac9d5229e7cfe3b360134ea2` |
| `mermaid.min.js` | mermaid | 11.17.2 | MIT | https://registry.npmjs.org/mermaid/-/mermaid-11.17.2.tgz (`dist/mermaid.min.js`) | `581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8` |

## Notes
- **three** is pinned to r183 because the 3d-force-graph 1.80.0 UMD bundle embeds its own three r183.
  The app imports the ES build for its own meshes, clouds and labels; matching revisions keep the two
  copies render-compatible. Browsers log a harmless `Multiple instances of Three.js` warning.
- **3d-force-graph** UMD bundles its deps: three (MIT), three-forcegraph, three-render-objects, kapsule,
  accessor-fn, float-tooltip, data-bind-mapper, d3-force-3d, d3-octree, polished, tinycolor2,
  @tweenjs/tween.js (all MIT), ngraph.forcelayout / ngraph.graph (BSD-3-Clause), d3-* (ISC).
- **mermaid** is loaded lazily, only when a page contains a mermaid block. Its IIFE bundles d3 (ISC),
  d3-sankey (BSD-3-Clause), dagre-d3-es, cytoscape (+ fcose, cose-bilkent), katex, khroma, dayjs, roughjs,
  stylis, uuid, es-toolkit, @iconify/utils, @braintree/sanitize-url and others (MIT), plus dompurify.
- `marked.umd.js` and `purify.min.js` end with a `sourceMappingURL` comment; the `.map` files are not
  vendored (dev tools may log a 404 for them; harmless).
