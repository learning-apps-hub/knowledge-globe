#!/usr/bin/env python3
"""Verify the generated GitHub Pages Explore artifact is complete and safe."""
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "_site"
sys.path.insert(0, str(ROOT))

from scripts.build_pages import _assert_no_private  # noqa: E402


def require(condition, message):
    if not condition:
        raise AssertionError(message)


index = (SITE / "index.html").read_text(encoding="utf-8")
require('data-static-build="true"' in index, "static mode is not enabled")
require(
    'from "./static/vendor/three.module.min.js"' in index,
    "Three.js import is not Pages-relative",
)
require("./data/graph.json" in index, "static graph snapshot is not wired")
require((SITE / ".nojekyll").is_file(), ".nojekyll is missing")
require(
    (SITE / "static" / "vendor" / "three.module.min.js").is_file(),
    "Three.js bundle is missing",
)

graph = json.loads((SITE / "data" / "graph.json").read_text())
require(len(graph.get("points", [])) >= 500, "static graph is incomplete")
require(len(graph.get("links", [])) >= 2000, "static graph links are incomplete")
require(graph.get("starts"), "static graph has no starting points")

manifest = json.loads((SITE / "earth" / "manifest.json").read_text())
require(manifest.get("layers"), "Earth credits are missing")
require(
    all(layer.get("credit") and layer.get("licence") for layer in manifest["layers"]),
    "an Earth layer is missing its credit or licence",
)
for name in manifest.get("files", {}).values():
    require((SITE / "earth" / name).is_file(), f"Earth asset is missing: {name}")

require(
    not any(path.is_symlink() for path in SITE.rglob("*")),
    "Pages artifact must not contain symlinks",
)

# No folder named `private` may reach the published artifact.
_assert_no_private(SITE)

# Keep the assertion non-vacuous: prove it rejects a canary private folder.
with tempfile.TemporaryDirectory() as directory:
    probe = Path(directory)
    (probe / "data" / "private").mkdir(parents=True)
    try:
        _assert_no_private(probe)
    except ValueError:
        pass
    else:
        raise AssertionError("private-folder check did not reject its canary")

print(
    f"GitHub Pages artifact verified: {len(graph['points'])} topics, "
    f"{len(graph['links'])} links, no private folder"
)
sys.exit(0)
