"""Loading and validating subject maps from data/subjects/*.json."""
import json
import os
import re

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "subjects"
)

EDGE_TYPES = {
    "causes",
    "enables",
    "depends-on",
    "conflicts-with",
    "precedes",
    "correlates-with",
}

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class SubjectError(Exception):
    pass


def list_subjects():
    out = []
    for name in sorted(os.listdir(DATA_DIR)):
        if not name.endswith(".json"):
            continue
        subject = _read(name[:-5])
        out.append(
            {
                "id": subject["id"],
                "title": subject["title"],
                "summary": subject.get("summary", ""),
            }
        )
    return out


def get_subject(subject_id):
    """Return a subject with zoom_level derived. Raises SubjectError if unknown."""
    if not ID_RE.match(subject_id or ""):
        raise SubjectError("unknown subject")
    path = os.path.join(DATA_DIR, subject_id + ".json")
    # Resolve and confirm the path stayed inside DATA_DIR (traversal guard).
    if os.path.realpath(path) != os.path.join(os.path.realpath(DATA_DIR), subject_id + ".json"):
        raise SubjectError("unknown subject")
    if not os.path.isfile(path):
        raise SubjectError("unknown subject")
    subject = _read(subject_id)
    _derive_zoom_levels(subject)
    return subject


def _read(subject_id):
    with open(os.path.join(DATA_DIR, subject_id + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


def _derive_zoom_levels(subject):
    """zoom_level is never authored — walk parent links so it can't drift (§1.2)."""
    by_id = {n["id"]: n for n in subject["nodes"]}
    for node in subject["nodes"]:
        depth = 0
        cursor = node
        seen = {node["id"]}
        while cursor.get("parent") is not None:
            parent = by_id.get(cursor["parent"])
            if parent is None or parent["id"] in seen:
                raise SubjectError(
                    f"node {node['id']!r} has a broken or cyclic parent chain"
                )
            seen.add(parent["id"])
            cursor = parent
            depth += 1
        node["zoom_level"] = depth


def validate(subject):
    """Structural checks. Returns a list of problem strings (empty == valid)."""
    problems = []
    node_ids = set()
    for node in subject.get("nodes", []):
        if node["id"] in node_ids:
            problems.append(f"duplicate node id: {node['id']}")
        node_ids.add(node["id"])

    angle_ids = {a["id"] for a in subject.get("angles", [])}
    roots = [n for n in subject.get("nodes", []) if n.get("parent") is None]
    if len(roots) != 1:
        problems.append(f"expected exactly one root node, found {len(roots)}")

    for node in subject.get("nodes", []):
        parent = node.get("parent")
        if parent is not None and parent not in node_ids:
            problems.append(f"node {node['id']}: unknown parent {parent}")
        for tag in node.get("angle_tags", []):
            if tag not in angle_ids:
                problems.append(f"node {node['id']}: unknown angle tag {tag}")

    for edge in subject.get("edges", []):
        if edge["type"] not in EDGE_TYPES:
            problems.append(f"edge {edge['from']}->{edge['to']}: unknown type {edge['type']}")
        for end in ("from", "to"):
            if edge[end] not in node_ids:
                problems.append(f"edge {edge['from']}->{edge['to']}: unknown node {edge[end]}")

    return problems
