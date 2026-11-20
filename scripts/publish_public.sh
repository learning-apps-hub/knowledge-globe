#!/usr/bin/env bash
#
# Publish the public Knowledge Globe site.
#
# The public repo's `main` is a DERIVED ARTIFACT: ONE commit with no parents,
# rebuilt from `main` on every release, so the public repo never carries the
# private repo's history (audit R7, Owner 2026-11-19). It is never hand-edited
# and never merged back. It also carries the credited Earth bundle needed by
# the Pages build; the large source pictures remain server-only.
#
# Usage: scripts/publish_public.sh [--yes]
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ASSUME_YES=0
[[ "${1:-}" == "--yes" ]] && ASSUME_YES=1

SOURCE_BRANCH="main"
PUBLIC_REMOTE="public"
ORIGINAL_REF="$(git rev-parse --abbrev-ref HEAD)"
[[ "$ORIGINAL_REF" == "HEAD" ]] && ORIGINAL_REF="$(git rev-parse HEAD)"

restore() {
  if [[ "$(git rev-parse --abbrev-ref HEAD)" != "$ORIGINAL_REF" ]]; then
    # -f is safe: we refused to start on a dirty tree, so nothing is at risk.
    git checkout -f "$ORIGINAL_REF" >/dev/null 2>&1 || {
      echo "!! could not return to $ORIGINAL_REF — run: git checkout -f $ORIGINAL_REF" >&2
      return
    }
    echo "Returned to $ORIGINAL_REF"
  fi
}
trap restore EXIT

# --- 1. refuse to run on a dirty tree -----------------------------------------
if [[ -n "$(git status --porcelain)" ]]; then
  echo "!! working tree is dirty — commit or stash before publishing:" >&2
  git status --short >&2
  exit 1
fi

# --- 2. pre-flight: build and verify from main --------------------------------
git fetch origin "$SOURCE_BRANCH" --quiet
git checkout --quiet "$SOURCE_BRANCH"
git merge --ff-only --quiet "origin/$SOURCE_BRANCH"

echo "Building the public artifact from $SOURCE_BRANCH ($(git rev-parse --short HEAD))..."
python3 scripts/build_pages.py --output _site
python3 tests/pages_build_test.py

# --- 3. show the operator exactly what goes out -------------------------------
echo
python3 - <<'PY'
import sys
sys.path.insert(0, ".")
from app import geography, graph
from scripts.build_pages import EXTERNAL_EARTH_DIR

snapshot = graph.build(geography.load(str(EXTERNAL_EARTH_DIR)))
print(f"PUBLISHING Explore with {len(snapshot['points'])} topics and {len(snapshot['links'])} links")
print("as ONE commit with no history (the public repo's old history is replaced)")
PY
echo

if [[ "$ASSUME_YES" -ne 1 ]]; then
  read -r -p "Force-push this to $PUBLIC_REMOTE main? [y/N] " reply
  [[ "$reply" == "y" || "$reply" == "Y" ]] || { echo "Aborted."; exit 1; }
fi

# --- 4. rebuild the derived public branch as one parentless commit -------------
RELEASE="$(git describe --tags --always "$SOURCE_BRANCH")"
git branch -D --quiet public >/dev/null 2>&1 || true
git checkout --quiet --orphan public "$SOURCE_BRANCH"
rm -rf earth-data/derived
mkdir -p earth-data/derived
# The same copy the Pages build makes (lights by year, the opening's past Earth, sea ice by month),
# so the Pages workflow, which builds from this branch's copy, gets every list the server has.
python3 - <<'PY'
from pathlib import Path
from scripts.build_pages import EXTERNAL_EARTH_DIR, copy_earth_bundle

copy_earth_bundle(EXTERNAL_EARTH_DIR, Path("earth-data/derived"))
PY
git add earth-data/derived
git commit --quiet -m "public: Knowledge Globe $RELEASE (static Explore release)"
[[ -z "$(git rev-list --parents -n 1 public | cut -s -d" " -f2)" ]] || { echo "!! public commit has a parent; refusing" >&2; exit 1; }

# Force-push is correct: the org repo's main is a published mirror of a derived
# branch, not a place where work happens. Each push replaces its whole history.
git push --force "$PUBLIC_REMOTE" public:main

echo
echo "Published. Pages workflow: https://github.com/learning-apps-hub/knowledge-globe/actions"
echo "Live site:                 https://learning-apps-hub.github.io/knowledge-globe/"
