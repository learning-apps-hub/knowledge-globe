# Knowledge Globe

A living, zoomable world of connected ideas. Pick a subject, turn the 3D globe,
open a topic pin, and travel from a one-sentence overview into deeper
explanations, memorable facts, questions, definitions, relationships, and
source links.

Knowledge stays at the source. A node holds a keyword, a short curated
summary, and links out. It never stores the source's content.

## Run

```bash
python3 run.py
```

Then open `http://localhost:8110/`. No dependencies — Python standard library
only. The 3D engine is vendored with the app, so the core experience does not
depend on a CDN. `PORT` and `HOST` can be overridden via environment or a
`.env` file (see `.env.example`).

The reserved development port is `8111`:

```bash
PORT=8111 python3 run.py
```

`8110` is the local default, `8111` is the persistent development preview,
and `8112` is used by the smoke suite.

## Production

Production runs on two tracks from the same `main` commit:

| Track | Where | Serves |
|---|---|---|
| Internal | `prod/` worktree on port `8110` (LAN) | The full application, live API and **all** subject maps, private included |
| Public | GitHub Pages, `https://learning-apps-hub.github.io/knowledge-globe/` | A static, prebuilt snapshot of the **public** subject maps only |

The internal track is the read-only Python API described above, deployed by
advancing the `prod/` worktree to a release tag.

The public track is published deliberately, never automatically:

```bash
scripts/publish_public.sh
```

The script refuses to run on a dirty tree, builds and verifies the artifact
from `main`, prints the subject ids going out and the private ones being
withheld, asks for confirmation, then rebuilds the `public` branch and
force-pushes it to the public repo's `main`. That push triggers
`.github/workflows/pages.yml`, which validates the maps, generates static JSON
with derived zoom levels, and publishes over HTTPS with no application port.

`public` is a **derived artifact**, rebuilt from `main` on every release. Never
hand-edit it and never merge it back — that is what stops a long-lived
divergent branch from drifting out of sync.

Build and verify the public artifact locally without publishing:

```bash
python3 scripts/build_pages.py --output _site
python3 tests/pages_build_test.py
```

### Private subjects

A subject map placed in `data/subjects/private/` is served normally by the LAN
app on port `8110`, and is stripped from everything the public site sees.
Three independent layers enforce that:

1. `scripts/build_pages.py` builds from the public maps only, then re-scans the
   generated artifact and fails if a private id appears in it.
2. `tests/pages_build_test.py` asserts the same thing about the built artifact,
   so CI catches a leak before it deploys.
3. `scripts/publish_public.sh` removes `data/subjects/private/` from the
   `public` branch, so the private maps are never committed to the public repo
   at all — they stay versioned in the private repo only.

## Layout

| Path | What |
|---|---|
| `run.py` | Entry point; validates every subject map, then serves |
| `app/server.py` | Read-only HTTP API + viewer |
| `app/subjects.py` | Subject loading, zoom-level derivation, validation |
| `app/static/index.html` | The responsive 3D viewer (inline CSS + app logic) |
| `app/static/vendor/` | Vendored Three.js module and its MIT licence |
| `data/subjects/*.json` | Curated subject maps — one file per subject |
| `data/subjects/private/*.json` | Private maps: served on the LAN, never published |
| `scripts/build_pages.py` | Builds the static public artifact |
| `scripts/publish_public.sh` | Publishes that artifact to the public repo |
| `tests/smoke_test.py` | End-to-end smoke test |

## API

| Route | Returns |
|---|---|
| `GET /` | The viewer |
| `GET /api/subjects` | `[{id, title, summary, private}, ...]` |
| `GET /api/subjects/<id>` | Full subject map, `zoom_level` derived |

Read-only. Curation happens by editing the JSON directly.

The viewer includes:

- a WebGL sphere with atmosphere, stars, relationship arcs, and depth-aware
  HTML topic pins;
- drag and touch rotation, scroll/pinch-style zoom, reset controls, subject
  search, a random discovery action, and keyboard focus states;
- compact, shape-neutral topic pins. Selecting one greys the others and turns
  the globe to centre it in 0.2 seconds; selecting pauses rotation, while a
  click on the globe surface resumes the slow orbit;
- angle lenses that highlight science, ecology, society, power, or culture;
- subject-specific exploration controls: Singapore Oceanarium follows its
  official Animal Type, Natural Habitat, and Zone filters instead of showing
  generic knowledge lenses or a duplicate journey-section list;
- a responsive reading panel that works as a desktop column or mobile sheet;
- an adjustable desktop reading panel—drag its left edge to give a detailed
  profile more or less room;
- progressive content fields (`key_fact`, `explainer`, `why_it_matters`,
  `wonder`, and optional `glossary`) while retaining the original concise
  `summary`;
- contextual real photographs and diagrams from Wikimedia Commons, loaded on
  demand with creator and licence attribution. Visual lookup is resilient: the
  sourced text remains available if the network or media provider is offline.
- a subject-aware projected globe surface. The Oceanarium theme adds animated
  underwater caustics, expanding ripples, moving wave shadows, drifting
  particles, fish silhouettes, and reef forms. Animation honours the device's
  reduced-motion preference. Full profile photography remains in the reading
  panel, with 34 verified official images and licensed Commons fallbacks for
  the remaining nine.

The Singapore Oceanarium subject contains all 43 entries currently shown on
the official Animals A–Z page. Every profile records animal type, natural
habitat, Oceanarium zone, natural diet, presentation type, sources, and a real
photo path. Replicas and preserved specimens are explicitly labelled rather
than presented as live residents.

## Subject map format

One JSON file per subject: a header (`id`, `title`, `summary`, `angles`), a flat
list of `nodes`, and a flat list of typed `edges`.

- **Angles** are tags, not separate trees. A node can carry several. Selecting an
  angle highlights matching nodes and dims the rest — it's a lens over one
  shared graph, not a different dataset.
- **`parent`** on each node forms the zoom hierarchy. Exactly one root
  (`parent: null`). `zoom_level` is never authored — it's derived from the
  parent chain at load time, so it cannot drift.
- **Edges** are the web on top of the tree, drawn from a fixed vocabulary:
  `causes`, `enables`, `depends-on`, `conflicts-with`, `precedes`,
  `preys-on`, `correlates-with`. They may cross angles and zoom levels freely.
- **Visuals** default to an openly licensed Wikimedia Commons search based on
  the node and subject names. Set `visual_query_suffix` on a subject or
  `visual_query` on a node to make that search precise; set `visual: false` only
  when an image would be misleading. Optional `visual_alt` and
  `visual_caption` override retrieved metadata.

Adding a subject means dropping a new file in `data/subjects/`. It appears in
the picker automatically; no viewer change needed. Drop it in
`data/subjects/private/` instead and it behaves identically on the LAN but is
excluded from the public site (see "Private subjects" above). An id may not be
used in both places — that would silently shadow one of the two files, so it
fails at startup. Malformed maps fail at startup with a specific message rather
than breaking the viewer at runtime.

## Tests

```bash
PORT=8112 python3 tests/smoke_test.py
```

Starts a temporary server, exercises the API, viewer, vendored 3D asset, and
path-traversal guards. The chosen port must be free.

Full design rationale lives in the vault:
`AI Projects/knowledge-globe/working files/DESIGN_v0.1.md`.
