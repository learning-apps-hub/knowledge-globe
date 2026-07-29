#!/usr/bin/env python3
"""Entry point — Knowledge Globe."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import server, subjects  # noqa: E402


def _load_env():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def main():
    _load_env()

    failed = False
    for summary in subjects.list_subjects():
        problems = subjects.validate(subjects.get_subject(summary["id"]))
        for problem in problems:
            print(f"INVALID {summary['id']}: {problem}", file=sys.stderr)
            failed = True
    if failed:
        sys.exit(1)

    server.serve(int(os.environ.get("PORT", 8110)))


if __name__ == "__main__":
    main()
