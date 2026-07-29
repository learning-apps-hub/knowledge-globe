# Knowledge Globe — app repo

This is the code repo. Current state, decisions, and next steps live in the
vault, not here: `AI Projects/knowledge-globe/working files/CONTEXT.md`.
Design rationale: `working files/DESIGN_v0.1.md`.

## Setup & run

```bash
python3 run.py          # serves on 8110
python3 tests/smoke_test.py
```

Standard library only — no venv or `pip install` needed to run. `requirements.txt`
is intentionally empty; keep it that way unless there's a real reason to add a
dependency.

## Conventions

- **Backend is stdlib `http.server`** by decision (PROJECT_KICKOFF.md §5), not
  an accident of scaffolding. Don't reach for Flask/FastAPI.
- **No CDN fetches.** The viewer must work on a LAN with no internet. Any
  library gets vendored into the repo.
- **The viewer is one file** — `app/static/index.html`, inline CSS and JS.
- **`zoom_level` is derived, never authored.** If you find yourself writing it
  into a JSON file, that's a bug.
- **Edge types are a closed vocabulary** of six (see README). Adding a seventh
  is a design decision, not an implementation detail.
- CI runs `flake8 --max-line-length=120` and `bandit -ll`. Both are clean —
  keep them that way.

## Scope guard

v0.1 is read-only. No write endpoints, no curation UI, no auth, no 3D. These
are deliberate exclusions documented in DESIGN_v0.1.md §5.1 — check there
before adding anything in those areas.
