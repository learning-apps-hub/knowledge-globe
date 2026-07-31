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

## Layout

| Path | What |
|---|---|
| `run.py` | Entry point; validates every subject map, then serves |
| `app/server.py` | Read-only HTTP API + viewer |
| `app/subjects.py` | Subject loading, zoom-level derivation, validation |
| `app/static/index.html` | The responsive 3D viewer (inline CSS + app logic) |
| `app/static/vendor/` | Vendored Three.js module and its MIT licence |
| `data/subjects/*.json` | Curated subject maps — one file per subject |
| `tests/smoke_test.py` | End-to-end smoke test |

## API

| Route | Returns |
|---|---|
| `GET /` | The viewer |
| `GET /api/subjects` | `[{id, title, summary}, ...]` |
| `GET /api/subjects/<id>` | Full subject map, `zoom_level` derived |

Read-only. Curation happens by editing the JSON directly.

The viewer includes:

- a WebGL sphere with atmosphere, stars, relationship arcs, and depth-aware
  HTML topic pins;
- drag and touch rotation, scroll/pinch-style zoom, reset controls, subject
  search, a random discovery action, and keyboard focus states;
- angle lenses that highlight science, ecology, society, power, or culture;
- a responsive reading panel that works as a desktop column or mobile sheet;
- progressive content fields (`key_fact`, `explainer`, `why_it_matters`,
  `wonder`, and optional `glossary`) while retaining the original concise
  `summary`.

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
  `correlates-with`. They may cross angles and zoom levels freely.

Adding a subject means dropping a new file in `data/subjects/`. It appears in
the picker automatically; no viewer change needed. Malformed maps fail at
startup with a specific message rather than breaking the viewer at runtime.

## Tests

```bash
PORT=8112 python3 tests/smoke_test.py
```

Starts a temporary server, exercises the API, viewer, vendored 3D asset, and
path-traversal guards. The chosen port must be free.

Full design rationale lives in the vault:
`AI Projects/knowledge-globe/working files/DESIGN_v0.1.md`.
