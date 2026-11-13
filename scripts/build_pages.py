#!/usr/bin/env python3
"""Build a validated static Explore bundle for GitHub Pages."""
import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "app" / "static"
sys.path.insert(0, str(ROOT))

from app import geography, graph, subjects  # noqa: E402


EXTERNAL_EARTH_DIR = ROOT.parent / "earth-data" / "derived"
PUBLIC_BRANCH_EARTH_DIR = ROOT / "earth-data" / "derived"


def write_json(path, payload):
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _assert_no_private(stage, withheld):
    """Defence in depth: even a mistaken publish must not carry private content.

    The filter above is the mechanism; this is the check that it worked. It
    scans the generated text of the artifact, not just its filenames.
    """
    if (stage / "data" / "subjects" / "private").exists():
        raise ValueError("private subject directory leaked into the artifact")
    if not withheld:
        return
    generated = [path for path in stage.rglob("*") if path.is_file() and path.suffix in {".html", ".json", ".js"}]
    for path in generated:
        text = path.read_text(encoding="utf-8")
        for subject_id in sorted(withheld):
            if subject_id in text:
                raise ValueError(
                    f"private subject {subject_id!r} leaked into {path.name}"
                )


def build(destination):
    destination = destination.resolve()
    if destination == ROOT or ROOT not in destination.parents:
        raise ValueError("output must be a directory inside the repository")

    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".pages-build-", dir=destination.parent))
    try:
        earth_dir = EXTERNAL_EARTH_DIR if EXTERNAL_EARTH_DIR.is_dir() else PUBLIC_BRANCH_EARTH_DIR
        manifest_path = earth_dir / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError("Earth bundle is missing (expected earth-data/derived/manifest.json)")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        shutil.copytree(STATIC_DIR / "vendor", stage / "static" / "vendor")
        shutil.copy2(STATIC_DIR / "sky.js", stage / "static" / "sky.js")

        source_html = (STATIC_DIR / "explore.html").read_text(encoding="utf-8")
        marker = 'data-static-build="false"'
        if source_html.count(marker) != 1:
            raise ValueError("viewer is missing its static-build marker")
        graph_url = 'fetch("./api/graph")'
        if source_html.count(graph_url) != 1:
            raise ValueError("viewer graph endpoint changed; static rewrite is unsafe")
        (stage / "index.html").write_text(
            source_html.replace(marker, 'data-static-build="true"').replace(
                graph_url, 'fetch("./data/graph.json")'
            ),
            encoding="utf-8",
        )

        data_dir = stage / "data"
        data_dir.mkdir()
        write_json(data_dir / "graph.json", graph.build(geography.load(str(earth_dir))))

        earth_out = stage / "earth"
        earth_out.mkdir()
        shutil.copy2(manifest_path, earth_out / "manifest.json")
        for name in sorted(set(manifest.get("files", {}).values())):
            source = earth_dir / name
            if not source.is_file():
                raise ValueError(f"Earth bundle file is missing: {name}")
            shutil.copy2(source, earth_out / name)

        withheld = subjects.private_ids()
        _assert_no_private(stage, withheld)

        (stage / ".nojekyll").write_text("", encoding="utf-8")
        if destination.exists():
            shutil.rmtree(destination)
        os.replace(stage, destination)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise

    withheld = sorted(subjects.private_ids())
    print(f"Built GitHub Pages site at {destination}")
    print("Bundled one static graph and the credited Earth pictures/data")
    if withheld:
        print(f"Withheld {len(withheld)} private subject(s): {', '.join(withheld)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="_site", help="repository-local output directory")
    args = parser.parse_args()
    build(ROOT / args.output)


if __name__ == "__main__":
    main()
