#!/usr/bin/env python3
"""Build a validated static Knowledge Globe bundle for GitHub Pages."""
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

from app import subjects  # noqa: E402


def write_json(path, payload):
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def build(destination):
    destination = destination.resolve()
    if destination == ROOT or ROOT not in destination.parents:
        raise ValueError("output must be a directory inside the repository")

    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".pages-build-", dir=destination.parent))
    try:
        shutil.copytree(STATIC_DIR / "vendor", stage / "static" / "vendor")

        source_html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        marker = 'data-static-build="false"'
        if source_html.count(marker) != 1:
            raise ValueError("viewer is missing its static-build marker")
        (stage / "index.html").write_text(
            source_html.replace(marker, 'data-static-build="true"'),
            encoding="utf-8",
        )

        data_dir = stage / "data" / "subjects"
        data_dir.mkdir(parents=True)
        listing = subjects.list_subjects()
        write_json(data_dir / "index.json", listing)
        for summary in listing:
            subject = subjects.get_subject(summary["id"])
            problems = subjects.validate(subject)
            if problems:
                raise ValueError(f"invalid subject {summary['id']}: {'; '.join(problems)}")
            write_json(data_dir / f"{summary['id']}.json", subject)

        (stage / ".nojekyll").write_text("", encoding="utf-8")
        if destination.exists():
            shutil.rmtree(destination)
        os.replace(stage, destination)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise

    print(f"Built GitHub Pages site at {destination}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="_site", help="repository-local output directory")
    args = parser.parse_args()
    build(ROOT / args.output)


if __name__ == "__main__":
    main()
