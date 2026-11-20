# Knowledge Globe — app repo

This is the code repo. Current state, decisions, and next steps live in the
vault, not here: `AI Projects/knowledge-globe/working files/CONTEXT.md`.
Design rationale: `working files/DESIGN_v0.1.md`.

**`AGENTS.md` is a byte-identical copy of this file** so Codex and Claude get
the same rules. Edit one, copy it over the other — `tests/conventions_test.py`
fails if they diverge.

## Setup & run

Both tracks run as systemd user units and hold 8110 (prod, `prod/` tree) and
8111 (dev, this tree). Don't start an ad-hoc server on either — use a scratch
port:

```bash
PORT=8113 python3 run.py               # scratch preview
PORT=8112 python3 tests/smoke_test.py  # temporary test port
python3 tests/conventions_test.py      # no server needed
```

Standard library only — no venv or `pip install` needed to run. `requirements.txt`
is intentionally empty; keep it that way unless there's a real reason to add a
dependency.

## Conventions

- **Backend is stdlib `http.server`** by decision (PROJECT_KICKOFF.md §5), not
  an accident of scaffolding. Don't reach for Flask/FastAPI.
- **No CDN fetches.** The viewer must work on a LAN with no internet. Any
  library gets vendored into the repo.
- **The viewer is one file** — `app/static/explore.html`, inline CSS and JS.
- **`zoom_level` is derived, never authored.** If you find yourself writing it
  into a JSON file, that's a bug.
- **Link kinds are a closed vocabulary.** `LINK_KINDS` in `app/graph.py` is
  the single source of truth (one kind = one question pair); the README mirrors
  it and `tests/conventions_test.py` fails if the two disagree. Adding a kind is
  a design decision, not an implementation detail — ratify it with Owner before
  using it. This rule deliberately states no count: the old subject-map rule
  said "six" while the code had seven, and the prose was what drifted.
- CI runs `flake8 --max-line-length=120` and `bandit -ll`. Both are clean —
  keep them that way.

## Scope guard

The app is **read-only**. No write endpoints, no curation UI, no auth. These are deliberate exclusions
(DESIGN_v0.1.md §5.1) — check there before adding anything in those areas.

DESIGN_v0.1.md §5.1 also excluded a time slider. Owner **lifted** that on
2026-11-15 for the Themes view, and on 2026-11-17 put the year control ("time
machine") in the one menu bar for every view (Explore and Learn): it turns
dated facts back through the years and hides clouds while off now. It reads
pinned data; it writes nothing.

DESIGN_v0.1.md §5.1 also excluded 3D. That exclusion was **lifted** in the
2026-07-31 redesign and the viewer is now a WebGL globe; treat the design doc
as historical on that point only.
