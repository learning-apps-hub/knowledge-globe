#!/usr/bin/env python3
"""
Conventions test — Knowledge Globe

Asserts that the project's written constraints still match the code. Every
check here exists because the two drifted once already: CLAUDE.md said the edge
vocabulary had six types while subjects.py and the README carried seven
(`preys-on`, added for the Oceanarium and never ratified), and the rule was
only spotted by reading both files side by side.

Prose is what drifts, so it gets a test. Needs no server and no network — it is
the cheap check that runs on every PR.

Run from project root: python3 tests/conventions_test.py
"""
import os
import re
import sys

PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJ_ROOT)

from app.subjects import EDGE_TYPES  # noqa: E402

PASSED = []
FAILED = []


def check(label, ok, detail=""):
    if ok:
        PASSED.append(label)
        print(f"  [PASS] {label}")
    else:
        FAILED.append(label)
        print(f"  [FAIL] {label}{' — ' + detail if detail else ''}")


def read(*parts):
    with open(os.path.join(PROJ_ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def documented_edge_types(readme):
    """The `backticked` tokens in the README's '- **Edges**' bullet."""
    lines = readme.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("- **Edges**"):
            continue
        bullet = [line]
        # A bullet continues on indented lines until the next bullet or a blank.
        for following in lines[index + 1:]:
            if not following.strip() or following.startswith("- "):
                break
            bullet.append(following)
        return set(re.findall(r"`([a-z-]+)`", " ".join(bullet)))
    return None


print("--- Agent instruction parity ---")
# Codex reads AGENTS.md, Claude reads CLAUDE.md. When only one existed, the
# tool that could not see the conventions is the one that broke them.
claude_md = read("CLAUDE.md")
agents_path = os.path.join(PROJ_ROOT, "AGENTS.md")
check("AGENTS.md exists", os.path.isfile(agents_path),
      "Codex sessions read AGENTS.md and would see no conventions at all")
if os.path.isfile(agents_path):
    check("AGENTS.md is byte-identical to CLAUDE.md", read("AGENTS.md") == claude_md,
          "edit one, then copy it over the other")

print("\n--- Edge vocabulary ---")
readme = read("README.md")
documented = documented_edge_types(readme)
check("README documents the edge vocabulary", documented is not None,
      "no '- **Edges**' bullet found in README.md")
if documented is not None:
    check("README edge types match subjects.py EDGE_TYPES", documented == EDGE_TYPES,
          f"README-only: {sorted(documented - EDGE_TYPES)}; "
          f"code-only: {sorted(EDGE_TYPES - documented)}")

# The rule that drifted stated a count. A count in prose has to be updated by
# hand every time the set changes, so the convention now names none.
check("CLAUDE.md states no hard-coded edge-type count",
      not re.search(r"closed vocabulary\*{0,2} of (a |an )?\w+", claude_md),
      "name subjects.py as the source of truth instead of restating the number")

print("\n--- Subject data conforms to the vocabulary ---")
sys.path.insert(0, PROJ_ROOT)
from app import subjects  # noqa: E402

for subject_summary in subjects.list_subjects():
    subject_id = subject_summary["id"]
    subject = subjects.get_subject(subject_id)
    problems = subjects.validate(subject)
    check(f"{subject_id} validates clean", not problems, "; ".join(problems[:3]))

print(f"\n{'=' * 50}")
print(f"Results: {len(PASSED)} passed, {len(FAILED)} failed")
if FAILED:
    print(f"Failed: {', '.join(FAILED)}")
    sys.exit(1)
else:
    print("All checks passed.")
