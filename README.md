# Knowledge Globe

A map of a subject, not an archive of it. Pick a subject, see its big picture,
zoom into any facet, and view the whole thing through different angles —
science, ecology, human use, power, culture.

Knowledge stays at the source. A node holds a keyword, a short curated
summary, and links out. It never stores the source's content.

## Run

```bash
python3 run.py
```

Then open `http://localhost:8110/`. No dependencies — Python standard library
only. `PORT` and `HOST` can be overridden via environment or a `.env` file
(see `.env.example`).

## Layout

| Path | What |
|---|---|
| `run.py` | Entry point; validates every subject map, then serves |
| `app/server.py` | Read-only HTTP API + viewer |
| `app/subjects.py` | Subject loading, zoom-level derivation, validation |
| `app/static/index.html` | The viewer (single file, inline CSS+JS) |
| `data/subjects/*.json` | Curated subject maps — one file per subject |
| `tests/smoke_test.py` | End-to-end smoke test |

## API

| Route | Returns |
|---|---|
| `GET /` | The viewer |
| `GET /api/subjects` | `[{id, title, summary}, ...]` |
| `GET /api/subjects/<id>` | Full subject map, `zoom_level` derived |

Read-only. Curation happens by editing the JSON directly.

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
python3 tests/smoke_test.py
```

Starts the server, exercises the routes, and checks the traversal guard.
Requires port 8110 to be free.

Full design rationale lives in the vault:
`AI Projects/knowledge-globe/working files/DESIGN_v0.1.md`.
