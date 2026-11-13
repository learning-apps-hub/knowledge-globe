#!/usr/bin/env python3
"""Verify the generated GitHub Pages Explore artifact is complete and safe."""
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "_site"
sys.path.insert(0, str(ROOT))

from app import subjects  # noqa: E402
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

# Private subject maps must never reach the published artifact — not as files,
# not as ids in the listing, not as a stray string anywhere in the generated text.
withheld = subjects.private_ids()
require(
    not (SITE / "data" / "subjects" / "private").exists(),
    "private subject directory is present in the artifact",
)
for generated in [path for path in SITE.rglob("*") if path.is_file() and path.suffix in {".html", ".json", ".js"}]:
    text = generated.read_text(encoding="utf-8")
    for subject_id in sorted(withheld):
        require(
            subject_id not in text,
            f"private subject {subject_id!r} appears in {generated}",
        )

# Keep the private-content assertion non-vacuous even when the private folder is
# empty: prove the scanner rejects a canary id placed in generated output.
with tempfile.TemporaryDirectory() as directory:
    probe = Path(directory)
    (probe / "index.html").write_text("private-leak-canary", encoding="utf-8")
    try:
        _assert_no_private(probe, {"private-leak-canary"})
    except ValueError:
        pass
    else:
        raise AssertionError("private-content scanner did not reject its leak canary")

print(
    f"GitHub Pages artifact verified: {len(graph['points'])} topics, "
    f"{len(graph['links'])} links, {len(withheld)} private ids withheld"
)
sys.exit(0)
