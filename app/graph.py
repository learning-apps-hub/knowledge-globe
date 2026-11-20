"""One graph of topics and links for the Explore preview.

The design is `working files/ONE_GRAPH_DESIGN.md` in the vault. Explore shows
real geography only: the topics and links come from the Earth data folder
(geography.py). `data/graph_extra.json` adds hand-written words and the
"good places to start". The old subject maps (Water, the Oceanarium) were
dummy data and are retired with their loader (Owner, 2026-11-13; audit R8, 2026-11-19).
"""
import json
import os
import re

from . import geography

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
EXTRA_PATH = os.path.join(DATA_DIR, "graph_extra.json")
VISUALS_PATH = os.path.join(DATA_DIR, "visuals.json")
FACTS_PATH = os.path.join(DATA_DIR, "facts.json")
SUBTHEMES_PATH = os.path.join(DATA_DIR, "subthemes.json")
THEMES_PATH = os.path.join(DATA_DIR, "themes.json")
COMPARE_PATH = os.path.join(DATA_DIR, "compare.json")
# A Commons file that is a drawn map or a flag, not a photograph (satellite pictures are photographs).
_MAP_FILE = re.compile(
    r"(?!.*satellite).*(location|locator|orthographic|on_the_globe|in_its_region|map|mappa|harta|carte|flag)|\.svg$",
    re.I)

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


def _facts():
    """{topic id: [fact]} pinned by scripts/build_facts.py (sourced values about one topic), or {}."""
    try:
        with open(FACTS_PATH, encoding="utf-8") as fh:
            return json.load(fh).get("facts", {})
    except (OSError, ValueError):
        return {}


def _compare():
    """{topic id: [fact]} pinned by scripts/build_compare.py (the facts theme doors compare), or {}."""
    try:
        with open(COMPARE_PATH, encoding="utf-8") as fh:
            return json.load(fh).get("compare", {})
    except (OSError, ValueError):
        return {}


def _themes():
    """{topic id: [theme door]} pinned by scripts/build_themes.py (one sourced page per theme), or {}."""
    try:
        with open(THEMES_PATH, encoding="utf-8") as fh:
            return json.load(fh).get("themes", {})
    except (OSError, ValueError):
        return {}


def _subthemes():
    """{topic id: [sub-theme door]} pinned by scripts/build_subthemes.py (one sourced page each), or {}."""
    try:
        with open(SUBTHEMES_PATH, encoding="utf-8") as fh:
            return json.load(fh).get("subthemes", {})
    except (OSError, ValueError):
        return {}


def _calm_country_cards(points, links):
    """A country's card shows its capital's photograph, and says so.

    A country's own Wikidata image is a grab-bag (locator maps in ten styles, flags, stamps, a few
    photographs), and the globe already shows where the country is. A capital's image is reliably a
    photograph. A country or territory with no capital topic keeps its own picture unless that is a
    drawn map or a flag, which is dropped (`visual: False`: no picture, and no name search either).
    """
    capitals = {i["from"] for i in links if i["kind"] == "kind" and i["to"] == "kind-capital-city"}
    capital_of = {}
    for link in sorted(links, key=lambda i: i["from"]):
        if link["kind"] == "place" and link["from"] in capitals:
            capital_of.setdefault(link["to"], link["from"])
    for point in points.values():
        if point.get("shape") != "area" or point.get("status") is None:
            continue
        capital = points.get(capital_of.get(point["id"]), {})
        if isinstance(capital.get("visual"), dict):
            point["visual"] = dict(capital["visual"], of=f"{capital['name']}, its capital", capital=capital["id"])
        elif isinstance(point.get("visual"), dict) and _MAP_FILE.search(point["visual"].get("page", "")):
            point["visual"] = False


def build(geo=None, visuals=None, facts=None, themes=None, compare=None, subthemes=None):
    """Return {"kinds", "starts", "points", "links"}.

    `geo` is the geography JSON from the Earth data folder (geography.load); without it there are no
    geography topics, only the hand-written extras that stand on their own. `visuals` is the pinned
    pictures (default: `data/visuals.json`); a topic without one is searched for by name in the viewer.
    `facts` is the pinned facts (default: `data/facts.json`): sourced values on a topic, never links.
    `compare` is the facts the theme doors compare (default: `data/compare.json`): more facts of the same
    kind, some with their values through the years (`by_year`); a key the topic already has keeps its value
    and gains the years. Given `facts` but no `compare`, none are added.
    `themes` is the pinned theme doors (default: `data/themes.json`): one sourced page per theme of a topic.
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
    _calm_country_cards(points, links)
    for point_id, found in (_facts() if facts is None else facts).items():
        if point_id in points and found:
            points[point_id]["facts"] = found
    if compare is None:
        compare = _compare() if facts is None else {}
    for point_id, found in compare.items():
        held = points.get(point_id, {}).get("facts")
        if not held:
            continue
        by_key = {fact["key"]: fact for fact in held}
        for fact in found:
            if fact["key"] in by_key:
                if fact.get("by_year"):
                    by_key[fact["key"]]["by_year"] = fact["by_year"]
            else:
                held.append(fact)
    for point_id, found in (_themes() if themes is None else themes).items():
        if point_id in points and found:
            points[point_id]["themes"] = found
    # Sub-themes hang under a theme door: a topic with no theme doors gets none.
    for point_id, found in (_subthemes() if subthemes is None else subthemes).items():
        if point_id in points and found and points[point_id].get("themes"):
            points[point_id]["subs"] = found

    return {
        "kinds": LINK_KINDS,
        "starts": starts,
        "points": sorted(points.values(), key=lambda p: p["id"]),
        "links": links,
    }
