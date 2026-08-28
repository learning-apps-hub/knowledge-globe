#!/usr/bin/env python3
"""Verify the generated GitHub Pages artifact is complete and self-contained."""
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "_site"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


index = (SITE / "index.html").read_text(encoding="utf-8")
require('data-static-build="true"' in index, "static mode is not enabled")
require(
    'from "./static/vendor/three.module.min.js"' in index,
    "Three.js import is not Pages-relative",
)
require("./data/subjects/index.json" in index, "static subject index is not wired")
require((SITE / ".nojekyll").is_file(), ".nojekyll is missing")
require(
    (SITE / "static" / "vendor" / "three.module.min.js").is_file(),
    "Three.js bundle is missing",
)

listing = json.loads((SITE / "data" / "subjects" / "index.json").read_text())
require(listing, "subject listing is empty")
for summary in listing:
    path = SITE / "data" / "subjects" / f"{summary['id']}.json"
    require(path.is_file(), f"subject file is missing: {summary['id']}")
    subject = json.loads(path.read_text())
    require(subject["id"] == summary["id"], f"subject id mismatch: {summary['id']}")
    require(
        all("zoom_level" in node for node in subject["nodes"]),
        f"derived zoom levels are missing: {summary['id']}",
    )

require(
    not any(path.is_symlink() for path in SITE.rglob("*")),
    "Pages artifact must not contain symlinks",
)
print(f"GitHub Pages artifact verified: {len(listing)} subjects")
sys.exit(0)
