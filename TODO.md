# TODO — Knowledge Globe

## Blocked on review

- [ ] **IRIS — visual language.** v0.1 ships deliberately plain. Node card
      design, angle color coding, zoom transition, and whether to vendor D3
      for a richer layout (DESIGN_v0.1.md §6) are all open.
- [ ] **PAX — decomposition sanity-check.** Is 5 angles / 3 zoom levels the
      right granularity? Review the seeded `data/subjects/water.json`, not the
      design-doc excerpt.

## v0.1 follow-ups

- [ ] Verify the viewer in a real browser — built without one available;
      layout, edge hover labels, and zoom transitions are unconfirmed.
- [ ] Fill out the water map's thinner branches (culture and power nodes are
      light on sources).
- [ ] Decide what to show when a node's relations point off-screen — currently
      only edges between visible nodes are drawn; the rest appear in the detail
      panel but have no on-canvas hint.

## v0.2 candidates

- [ ] Second subject, to prove the schema generalizes past water.
- [ ] Curation UI — out of scope for v0.1 by decision, not oversight.
- [ ] Cross-subject correlation lens — needs 3+ subject maps to mean anything.
