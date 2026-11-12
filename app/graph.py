"""One graph of points and links, derived from the subject maps (preview).

The design is `working files/ONE_GRAPH_DESIGN.md` in the vault. Nothing is
migrated yet: this reads the existing subject files and re-expresses them as
points joined by the nine link kinds, so the Explore preview can be judged
before any data is rewritten. `data/graph_extra.json` adds the few hand-written
points and links the subject files cannot express.
"""
import json
import os
import re

from . import geography, subjects

EXTRA_PATH = os.path.join(os.path.dirname(subjects.DATA_DIR), "graph_extra.json")

# One link kind = one question from each end. `out` is asked on the link's
# `from` point, `back` on its `to` point. `like` reads the same both ways.
LINK_KINDS = {
    "time": {"out": "What does it become?", "back": "What was it before?"},
    "inside": {"out": "What is inside it?", "back": "What does it belong to?"},
    "place": {"out": "Where is it found?", "back": "What is found here?"},
    "need": {"out": "What does it need?", "back": "What needs it?"},
    "effect": {"out": "What does it help or harm?", "back": "What helps or harms it?"},
    "like": {"out": "What is it like?", "back": "What is it like?"},
    "kind": {"out": "What kind of thing is it?", "back": "What kinds are there?"},
    "who": {"out": "Who made, found or leads it?", "back": "What did they make, find or lead?"},
    "happened": {"out": "What happened to it?", "back": "What was part of this?"},
}

# Existing edge type → (link kind, helps/harms mark). To be confirmed edge by
# edge at the real migration; the preview shows what the mapping gives.
EDGE_TO_KIND = {
    "precedes": ("time", None),
    "depends-on": ("need", None),
    "preys-on": ("need", None),
    "causes": ("effect", None),
    "enables": ("effect", "helps"),
    "conflicts-with": ("effect", "harms"),
    "correlates-with": ("like", None),
}


class GraphError(Exception):
    pass


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _visual_query(node, subject, has_children):
    """The Commons search the viewer would run for this node (index.html)."""
    if node.get("visual_query"):
        return node["visual_query"]
    if has_children:
        return f"{node['keyword']} {subject['title']}"
    return f"{node['keyword']} {subject.get('visual_query_suffix') or subject['title']}"


def build(include_private=True, geo=None):
    """Return {"kinds", "starts", "points", "links"} for every subject map.

    `geo` is the geography JSON from the Earth data folder (geography.load); without it there are no
    geography topics.
    """
    points = {}
    links = []
    starts = []

    def add_point(point):
        if point["id"] in points:
            raise GraphError(f"point id used twice: {point['id']}")
        points[point["id"]] = point

    def stub(name, prefix):
        """A point that is only a name so far. Reuses a real point of that name."""
        for point in points.values():
            if point["name"].lower() == name.lower() and not point.get("stub"):
                return point["id"]
        point_id = f"{prefix}-{_slug(name)}"
        if point_id not in points:
            points[point_id] = {"id": point_id, "name": name, "stub": True, "visual_query": name}
        return point_id

    def add_link(kind, source, target, why=None, mark=None):
        if kind not in LINK_KINDS:
            raise GraphError(f"unknown link kind: {kind}")
        for end in (source, target):
            if end not in points:
                raise GraphError(f"link {source}->{target}: unknown point {end}")
        if any(k["kind"] == kind and k["from"] == source and k["to"] == target for k in links):
            return
        link = {"kind": kind, "from": source, "to": target}
        if why:
            link["why"] = why
        if mark:
            link["mark"] = mark
        links.append(link)

    extra = {}
    if os.path.isfile(EXTRA_PATH):
        with open(EXTRA_PATH, encoding="utf-8") as fh:
            extra = json.load(fh)
    # Old edges whose mapped kind reads wrong as a question, corrected one by one.
    rekind = {(r["from"], r["to"]): r["kind"] for r in extra.get("rekind", [])}

    loaded = []
    for summary in subjects.list_subjects(include_private=include_private):
        subject = subjects.get_subject(summary["id"])
        loaded.append(subject)
        parents = {n["parent"] for n in subject["nodes"]}
        for node in subject["nodes"]:
            point = {
                "id": node["id"],
                "name": node["keyword"],
                "line": node.get("summary", ""),
                "fact": node.get("key_fact", ""),
                "more": node.get("explainer", ""),
                "sources": node.get("sources", []),
                "visual_query": _visual_query(node, subject, node["id"] in parents),
            }
            if isinstance(node.get("visual"), dict):
                point["visual"] = node["visual"]
            add_point(point)
            if node["parent"] is None:
                starts.append(node["id"])

    for subject in loaded:
        for node in subject["nodes"]:
            if node["parent"] is not None:
                add_link("inside", node["parent"], node["id"])
        for edge in subject.get("edges", []):
            kind, mark = EDGE_TO_KIND[edge["type"]]
            kind = rekind.get((edge["from"], edge["to"]), kind)
            add_link(kind, edge["from"], edge["to"], edge.get("label"), mark)
        # The animal profile already holds three questions' worth of answers.
        for node in subject["nodes"]:
            animal = node.get("animal")
            if not animal:
                continue
            if animal.get("type"):
                add_link("kind", node["id"], stub(animal["type"], "kind"))
            if animal.get("habitat"):
                add_link("place", node["id"], stub(animal["habitat"], "place"))
            for food in animal.get("diet", []):
                add_link("need", node["id"], stub(food, "food"), "Part of its natural diet.")

    for point in extra.get("points", []):
        add_point(dict(point))
    for link in extra.get("links", []):
        add_link(link["kind"], link["from"], link["to"], link.get("why"), link.get("mark"))
    starts.extend(i for i in extra.get("starts", []) if i in points and i not in starts)

    if geo:
        geo_points, geo_links = geography.build(geo)
        for point in geo_points:
            if point["id"] in points:
                # A hand-written topic of the same id (Singapore) keeps its words and gains its place.
                points[point["id"]].update({k: point[k] for k in ("shape", "where", "at", "tiny") if k in point})
            else:
                add_point(point)
        for kind, source, target, why in geo_links:
            add_link(kind, source, target, why)

    return {
        "kinds": LINK_KINDS,
        "starts": starts,
        "points": sorted(points.values(), key=lambda p: p["id"]),
        "links": links,
    }
