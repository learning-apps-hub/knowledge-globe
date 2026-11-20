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

from app import geography, graph, language  # noqa: E402


EXTERNAL_EARTH_DIR = ROOT.parent / "earth-data" / "derived"
PUBLIC_BRANCH_EARTH_DIR = ROOT / "earth-data" / "derived"


def write_json(path, payload):
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _assert_no_private(stage):
    """Defence in depth: the artifact carries no folder named `private`, wherever it sits.

    The private subject maps are retired (audit R8, 2026-11-19); this keeps any
    future private folder from reaching the public site by accident.
    """
    for path in stage.rglob("private"):
        raise ValueError(f"a private folder leaked into the artifact: {path.relative_to(stage)}")


def copy_earth_bundle(earth_dir, earth_out):
    """Copy the Earth pictures the viewer needs from earth_dir into earth_out (an existing, empty folder).

    Used both by the Pages build and by publish_public.sh (which fills the public branch's
    earth-data/derived), so the two can never ship different sets.
    """
    manifest_path = earth_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    shutil.copy2(manifest_path, earth_out / "manifest.json")
    for name in sorted(set(manifest.get("files", {}).values())):
        source = earth_dir / name
        if not source.is_file():
            raise ValueError(f"Earth bundle file is missing: {name}")
        shutil.copy2(source, earth_out / name)
    # Optional lists, each naming its pictures: city lights by year (time machine) and the Earth's
    # past for the opening (intro). Without one, the viewer keeps today's lights / skips the intro.
    # Sea ice month by month too; its "now" (one day) is copied as it stands and the viewer stops using it
    # after three days, so a static site falls back to the same month of the newest year.
    for folder, list_key in EARTH_LISTS:
        index_path = earth_dir / folder / f"{folder}.json"
        if not index_path.is_file():
            continue
        (earth_out / folder).mkdir()
        shutil.copy2(index_path, earth_out / folder / f"{folder}.json")
        index = json.loads(index_path.read_text(encoding="utf-8"))
        for entry in index.get(list_key, []) + ([index["now"]] if index.get("now") else []):
            source = earth_dir / entry["file"]
            if not source.is_file():
                raise ValueError(f"Earth bundle file is missing: {entry['file']}")
            shutil.copy2(source, earth_out / entry["file"])
    # Deep time (the time machine's 750 million years ago → now): per era an atlas map and a plate map,
    # each big (at rest) and small (while dragging). Without the list the viewer offers no deep time.
    deep_path = earth_dir / "paleo" / "deep.json"
    if deep_path.is_file():
        (earth_out / "paleo").mkdir(exist_ok=True)
        shutil.copy2(deep_path, earth_out / "paleo" / "deep.json")
        deep = json.loads(deep_path.read_text(encoding="utf-8"))
        for era in deep.get("eras", []):
            for key in DEEP_FILES:
                if not era.get(key):
                    continue
                source = earth_dir / era[key]
                if not source.is_file():
                    raise ValueError(f"Earth bundle file is missing: {era[key]}")
                shutil.copy2(source, earth_out / era[key])


EARTH_LISTS = (("lights", "years"), ("paleo", "eras"), ("ice", "months"))
DEEP_FILES = ("file", "plates", "small", "smallPlates")


def build(destination):
    destination = destination.resolve()
    if destination == ROOT or ROOT not in destination.parents:
        raise ValueError("output must be a directory inside the repository")

    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".pages-build-", dir=destination.parent))
    try:
        earth_dir = EXTERNAL_EARTH_DIR if EXTERNAL_EARTH_DIR.is_dir() else PUBLIC_BRANCH_EARTH_DIR
        if not (earth_dir / "manifest.json").is_file():
            raise ValueError("Earth bundle is missing (expected earth-data/derived/manifest.json)")

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

        # The other languages, one file each, at the address the viewer asks the server for.
        lang_dir = stage / "api" / "lang"
        lang_dir.mkdir(parents=True)
        for code in language.CODES:
            write_json(lang_dir / f"{code}.json", language.build(code))

        earth_out = stage / "earth"
        earth_out.mkdir()
        copy_earth_bundle(earth_dir, earth_out)

        _assert_no_private(stage)

        (stage / ".nojekyll").write_text("", encoding="utf-8")
        if destination.exists():
            shutil.rmtree(destination)
        os.replace(stage, destination)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise

    print(f"Built GitHub Pages site at {destination}")
    print("Bundled one static graph and the credited Earth pictures/data")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="_site", help="repository-local output directory")
    args = parser.parse_args()
    build(ROOT / args.output)


if __name__ == "__main__":
    main()
