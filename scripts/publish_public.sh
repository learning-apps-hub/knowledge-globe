#!/usr/bin/env bash
#
# Publish the public Knowledge Globe site.
#
# The `public` branch is a DERIVED ARTIFACT, rebuilt from `main` on every
# release. It is never hand-edited and never merged back — that is what keeps
# a long-lived divergent branch from drifting. Private subject maps under
# data/subjects/private/ are stripped here, so they exist only in the private
# repo and on the LAN server.
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
from app import subjects

public = subjects.list_subjects(include_private=False)
private = sorted(subjects.private_ids())
print(f"PUBLISHING {len(public)} subject(s) to the public site:")
for summary in public:
    print(f"  + {summary['id']:<28} {summary['title']}")
print(f"WITHHELD {len(private)} private subject(s):")
for subject_id in private:
    print(f"  - {subject_id}")
if not private:
    print("  (none)")
PY
echo

if [[ "$ASSUME_YES" -ne 1 ]]; then
  read -r -p "Force-push this to $PUBLIC_REMOTE main? [y/N] " reply
  [[ "$reply" == "y" || "$reply" == "Y" ]] || { echo "Aborted."; exit 1; }
fi

# --- 4. rebuild the derived public branch -------------------------------------
git checkout --quiet -B public "$SOURCE_BRANCH"
# Not --cached: leaving the files on disk untracked blocks the checkout back.
git rm -r --quiet --ignore-unmatch data/subjects/private/
if ! git diff --cached --quiet; then
  git commit --quiet -m "public: exclude private subjects"
fi

# Force-push is correct: the org repo's main is a published mirror of a derived
# branch, not a place where work happens.
git push --force "$PUBLIC_REMOTE" public:main

echo
echo "Published. Pages workflow: https://github.com/learning-apps-hub/knowledge-globe/actions"
echo "Live site:                 https://learning-apps-hub.github.io/knowledge-globe/"
