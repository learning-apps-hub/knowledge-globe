"""One graph of topics and links for the Explore preview.

The design is `working files/ONE_GRAPH_DESIGN.md` in the vault. Explore shows
real geography only: the topics and links come from the Earth data folder
(geography.py). `data/graph_extra.json` adds hand-written words and the
"good places to start". The old subject maps (Water, the Oceanarium) are NOT
read here: their preview data was dummy and misleading (Owner, 2026-11-13).
"""
import json
import os

from . import geography, subjects

EXTRA_PATH = os.path.join(os.path.dirname(subjects.DATA_DIR), "graph_extra.json")
VISUALS_PATH = os.path.join(os.path.dirname(subjects.DATA_DIR), "visuals.json")

# One link kind = one question from each end. `out` is asked on the link's
# `from` point, `back` on its `to` point. `like` and `next` read the same both ways (out == back).
# `next` (neighbours) added 2026-11-13, Owner's yes: a real link that fits none of the other nine.
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
    "next": {"out": "What is next to it?", "back": "What is next to it?"},
}


class GraphError(Exception):
    pass


def _visuals():
    """{topic id: picture} pinned by scripts/build_visuals.py (each topic's Wikidata image), or {}."""
    try:
        with open(VISUALS_PATH, encoding="utf-8") as fh:
            return json.load(fh).get("visuals", {})
    except (OSError, ValueError):
        return {}


def build(geo=None, visuals=None):
    """Return {"kinds", "starts", "points", "links"}.

    `geo` is the geography JSON from the Earth data folder (geography.load); without it there are no
    geography topics, only the hand-written extras that stand on their own. `visuals` is the pinned
    pictures (default: `data/visuals.json`); a topic without one is searched for by name in the viewer.
    """
    points = {}
    links = []

    def add_point(point):
        if point["id"] in points:
            raise GraphError(f"point id used twice: {point['id']}")
        points[point["id"]] = point

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
    for point in extra.get("points", []):
        add_point(dict(point))

    if geo:
        geo_points, geo_links = geography.build(geo)
        for point in geo_points:
            if point["id"] in points:
                # A hand-written topic of the same id (Singapore) keeps its words and gains its place.
                keep = ("shape", "where", "at", "tiny", "status")
                points[point["id"]].update({k: point[k] for k in keep if k in point})
            else:
                add_point(point)
        for kind, source, target, why in geo_links:
            add_link(kind, source, target, why)

    for link in extra.get("links", []):
        add_link(link["kind"], link["from"], link["to"], link.get("why"), link.get("mark"))
    # "Who found it?" must answer for that one topic. One answer shared by several topics (early
    # humans for Africa, Asia and Europe) says nothing, so it is not a valid answer (Owner, 2026-11-13).
    who_from = {}
    for link in links:
        if link["kind"] == "who":
            who_from.setdefault(link["to"], []).append(link["from"])
    shared = {to: sources for to, sources in who_from.items() if len(sources) > 1}
    if shared:
        raise GraphError(f"a who-answer is shared by several topics: {shared}")
    starts = [i for i in extra.get("starts", []) if i in points]
    for point_id, visual in (_visuals() if visuals is None else visuals).items():
        # A topic that says "no picture" (a kind: visual False) keeps saying so.
        if point_id in points and "visual" not in points[point_id] and visual.get("src"):
            points[point_id]["visual"] = {k: visual[k] for k in ("src", "page", "credit", "licence") if k in visual}

    return {
        "kinds": LINK_KINDS,
        "starts": starts,
        "points": sorted(points.values(), key=lambda p: p["id"]),
        "links": links,
    }
