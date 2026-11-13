# Knowledge Globe

Knowledge Globe is one graph of places and ideas, drawn on a realistic WebGL
Earth. Pick a topic, follow the questions around it, and move through the graph
without leaving the globe.

The current graph contains more than 500 topics and 2,000 links. Places use
their true shapes: cities and poles are pins, named lines are lines, and
countries, continents, oceans, and hemispheres are areas. Earth, Sun, Moon,
stars, clouds, city lights, and the day/night line are rendered from credited
source data listed in the in-app “Pictures and data” panel.

## Run

```bash
python3 run.py
```

Then open `http://localhost:8110/`. The backend uses only the Python standard
library. Three.js is vendored, and the Earth bundle is read from
`../earth-data/derived` by default. Override the port, host, or Earth folder
with `PORT`, `HOST`, or `KG_EARTH_DIR`.

Reserved ports:

- `8110`: LAN production (`prod/` checkout)
- `8111`: development (`app/` checkout)
- `8112`: smoke tests

## Production tracks

Both tracks are released from the same tagged `main` commit.

| Track | Location | Delivery |
|---|---|---|
| Private LAN | `prod/` on port `8110` | Python server with live `/api/graph` |
| Public | <https://learning-apps-hub.github.io/knowledge-globe/> | Static Pages snapshot with the Earth bundle |

Build and verify the public artifact locally:

```bash
python3 scripts/build_pages.py --output _site
python3 tests/pages_build_test.py
```

Publish deliberately from a clean `main` release:

```bash
scripts/publish_public.sh
```

The publish script rebuilds the derived `public` branch, carries only the
Earth files named by the credited manifest, strips private subject-map files,
and force-pushes that branch to the public repository. The Pages workflow then
rebuilds and verifies the artifact before deployment. Never hand-edit or merge
the derived branch back.

The private-content gate remains active even though the released Explore graph
does not read the old subject maps. Anything under `data/subjects/private/` is
excluded from the public branch and scanned for leakage in the generated site.

## Layout

| Path | Purpose |
|---|---|
| `run.py` | Entry point |
| `app/server.py` | Read-only HTTP server and graph endpoint |
| `app/graph.py` | Builds the one graph |
| `app/geography.py` | Converts Earth geography into topics and links |
| `app/static/explore.html` | The complete responsive viewer |
| `app/static/sky.js` | Sun, Moon, and star calculations |
| `data/graph_extra.json` | Hand-authored topics, links, and starting points |
| `data/visuals.json` | Pinned Wikimedia Commons images and credits |
| `scripts/build_earth.py` | Builds the credited Earth data and pictures |
| `scripts/build_pages.py` | Builds the static public bundle |
| `scripts/publish_public.sh` | Publishes the derived public branch |

## API

| Route | Returns |
|---|---|
| `GET /` | Explore viewer |
| `GET /explore` | Alias for the Explore viewer |
| `GET /api/graph` | `{kinds, starts, points, links}` |

The old subject-map loader remains for private-content compatibility, but the
two dummy public maps (Water and Singapore Oceanarium) are no longer shipped.

- **Edges** use `causes`, `enables`, `depends-on`, `conflicts-with`, `precedes`,
  `preys-on`, and `correlates-with` in legacy subject maps.

## Tests

```bash
PORT=8112 python3 tests/smoke_test.py
python3 tests/conventions_test.py
flake8 app/ tests run.py --max-line-length=120
```

The design of record is in
`AI Projects/knowledge-globe/working files/ONE_GRAPH_DESIGN.md` in the vault.
