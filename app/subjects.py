"""Loading and validating subject maps from data/subjects/*.json."""
import json
import os
import re

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "subjects"
)
# Private subject maps: served by the LAN app, never published (README "Production").
PRIVATE_DIR = os.path.join(DATA_DIR, "private")

EDGE_TYPES = {
    "causes",
    "enables",
    "depends-on",
    "conflicts-with",
    "precedes",
    "preys-on",
    "correlates-with",
}

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class SubjectError(Exception):
    pass


def _ids_in(directory):
    if not os.path.isdir(directory):
        return []
    return sorted(
        name[:-5]
        for name in os.listdir(directory)
        if name.endswith(".json") and os.path.isfile(os.path.join(directory, name))
    )


def list_subjects(include_private=True):
    """Summaries of every subject map, public first. Each carries a `private` flag.

    `include_private=False` is what the Pages build uses — private maps must
    never reach the published artifact (README "Production").
    """
    public_ids = _ids_in(DATA_DIR)
    private_ids = _ids_in(PRIVATE_DIR)
    clash = sorted(set(public_ids) & set(private_ids))
    if clash:
        # A shadowed file would load one map and silently ignore the other.
        raise SubjectError(f"subject id defined both publicly and privately: {', '.join(clash)}")

    out = []
    for subject_id, private in [(i, False) for i in public_ids] + [
        (i, True) for i in private_ids
    ]:
        if private and not include_private:
            continue
        subject = _read(_subject_path(subject_id))
        out.append(
            {
                "id": subject["id"],
                "title": subject["title"],
                "summary": subject.get("summary", ""),
                "private": private,
            }
        )
    return out


def private_ids():
    """Ids that must never appear in a published artifact."""
    return set(_ids_in(PRIVATE_DIR))


def get_subject(subject_id):
    """Return a subject with zoom_level derived. Raises SubjectError if unknown."""
    path = _subject_path(subject_id)
    if path is None:
        raise SubjectError("unknown subject")
    subject = _read(path)
    _derive_zoom_levels(subject)
    return subject


def _subject_path(subject_id):
    """Resolve an id to a readable map file, or None. Public maps shadow private."""
    if not ID_RE.match(subject_id or ""):
        return None
    for directory in (DATA_DIR, PRIVATE_DIR):
        path = os.path.join(directory, subject_id + ".json")
        # Resolve and confirm the path stayed inside `directory` (traversal guard).
        expected = os.path.join(os.path.realpath(directory), subject_id + ".json")
        if os.path.realpath(path) != expected:
            continue
        if os.path.isfile(path):
            return path
    return None


def _read(path):
    with open(path, encoding="utf-8") as fh:
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
        if node.get("catalogue") == "animals-a-z":
            animal = node.get("animal", {})
            for field in ("type", "habitat", "zone", "diet", "presentation"):
                if not animal.get(field):
                    problems.append(f"node {node['id']}: missing animal profile field {field}")
            if not isinstance(node.get("visual"), dict) and not node.get("visual_query"):
                problems.append(f"node {node['id']}: missing animal photo source or fallback query")

    for edge in subject.get("edges", []):
        if edge["type"] not in EDGE_TYPES:
            problems.append(f"edge {edge['from']}->{edge['to']}: unknown type {edge['type']}")
        for end in ("from", "to"):
            if edge[end] not in node_ids:
                problems.append(f"edge {edge['from']}->{edge['to']}: unknown node {edge[end]}")

    return problems
