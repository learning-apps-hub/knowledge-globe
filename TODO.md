# TODO — Knowledge Globe

## Blocked on review

- [ ] **Owner — visual review of the 3D redesign.** Open the dev build on
      port 8111 and check desktop/mobile layout, drag/zoom feel, and reading
      comfort before release.
- [ ] **IRIS — visual language.** Review the implemented 3D direction:
      luminous knowledge globe, depth-aware pins, angle lenses, and layered
      reading panel. Three.js is vendored; D3 is no longer relevant.
- [ ] **PAX — decomposition sanity-check.** Is 5 angles / 3 zoom levels the
      right granularity? Review the seeded `data/subjects/water.json`, not the
      design-doc excerpt.

## v0.1 follow-ups

- [x] Replace the flat SVG viewer with a rotatable, zoomable 3D globe.
- [x] Enrich every water node with layered, age-friendly reading content.
- [x] Add or strengthen sources for the thinner culture and power branches.
- [ ] Complete Owner visual review in a real browser; automated checks verify
      routes and JavaScript syntax but cannot judge rendered polish.
- [ ] Decide what to show when a node's relations point off-screen — currently
      only edges between visible nodes are drawn; the rest appear in the detail
      panel but have no on-canvas hint.

## v0.2 candidates

- [ ] Second subject, to prove the schema generalizes past water.
- [ ] Curation UI — out of scope for v0.1 by decision, not oversight.
- [ ] Cross-subject correlation lens — needs 3+ subject maps to mean anything.
