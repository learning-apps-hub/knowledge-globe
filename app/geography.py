"""Geography topics for the Explore preview: poles, hemispheres, named lines, continents, oceans,
countries and main cities, as ordinary topics in the one graph.

They are built from `geo.<version>.json`, which `scripts/build_earth.py` derives from Natural Earth
(ONE_GRAPH_DESIGN.md, "Earth for geography learning"). Nothing is hand-copied: if the Earth data folder is
missing, the graph simply has no geography topics.

A geography topic is an ordinary topic plus a `shape` and a `where`:

    shape "pin"   where {"lat", "lon"}                 a city, a pole
    shape "line"  where {"lat"} | {"lon"} | {"path"}   a circle of latitude, the Prime Meridian, the Date Line
    shape "area"  where {"codes": [...]}               a country or a continent (codes in the area picture)
                  where {"ocean": 1..5}                an ocean
                  where {"hemisphere": "north"|...}    half the Earth
    plus `at` {"lat", "lon"}: where the globe turns to show it.
"""
import json
import os

SOURCE = {"title": "Natural Earth", "url": "https://www.naturalearthdata.com/"}

CONTINENT_AT = {"Africa": (2, 20), "Antarctica": (-80, 20), "Asia": (45, 90), "Europe": (52, 15),
                "North America": (46, -102), "Oceania": (-24, 140), "South America": (-14, -60)}
OCEAN_AT = {1: (5, -160), 2: (10, -35), 3: (-18, 78), 4: (-65, 20), 5: (88, 0)}
HEMISPHERES = {"north": ("Northern Hemisphere", "Half the Earth: everything north of the Equator.", (45, 20)),
               "south": ("Southern Hemisphere", "Half the Earth: everything south of the Equator.", (-45, 20)),
               "east": ("Eastern Hemisphere", "Half the Earth: everything east of the Prime Meridian, as far as "
                        "the opposite side of the Earth.", (10, 90)),
               "west": ("Western Hemisphere", "Half the Earth: everything west of the Prime Meridian, as far as "
                        "the opposite side of the Earth.", (10, -90))}
LINE_TEXT = {
    "equator": ("An imaginary line round the middle of the Earth, halfway between the two poles.", (0, 20)),
    "tropic-of-cancer": ("A line of latitude {lat} north of the Equator. Once a year, in June, the Sun is straight "
                         "overhead at noon on it.", (23.4, 10)),
    "tropic-of-capricorn": ("A line of latitude {lat} south of the Equator. Once a year, in December, the Sun is "
                            "straight overhead at noon on it.", (-23.4, 25)),
    "arctic-circle": ("A line of latitude {lat} north. North of it the Sun stays up all day at midsummer and "
                      "never rises at midwinter.", (66.6, 0)),
    "antarctic-circle": ("A line of latitude {lat} south. South of it the Sun stays up all day at midsummer and "
                         "never rises at midwinter.", (-66.6, 0)),
    "date-line": ("Where one calendar day turns into the next. It follows the line of longitude 180° from the "
                  "Prime Meridian, but bends to keep each country's islands on the same day.", (0, 180)),
}
SKIP_RULE_NOTE = "A city that shares its country's name is not a second topic: the country is the topic."


def _slug(text):
    import re
    import unicodedata
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def load(earth_dir):
    """The geography JSON the Earth data folder points at, or None if there is none."""
    try:
        with open(os.path.join(earth_dir, "manifest.json"), encoding="utf-8") as fh:
            name = json.load(fh).get("files", {}).get("geo")
        if not name:
            return None
        with open(os.path.join(earth_dir, name), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _degrees(value):
    return f"{abs(value):.1f}°"


def build(geo):
    """(points, links) for the geography topics. Link = (kind, from, to, why)."""
    points, links = [], []

    def add(point_id, name, line, shape, where, at, query=None, fact=""):
        points.append({"id": point_id, "name": name, "line": line, "fact": fact, "shape": shape, "where": where,
                       "at": {"lat": at[0], "lon": at[1]}, "sources": [SOURCE], "visual_query": query or name})
        return point_id

    areas = geo["areas"]
    by_code = {a["code"]: a for a in areas}
    by_name = {a["name"]: a for a in areas}
    ids = {a["id"] for a in areas}

    # The two poles and the two kinds of dividing line.
    north_pole = add("north-pole", "North Pole", "The point farthest north on Earth. Every line of longitude "
                     "meets here.", "pin", {"lat": 90, "lon": 0}, (90, 0))
    south_pole = add("south-pole", "South Pole", "The point farthest south on Earth. Every line of longitude "
                     "meets here.", "pin", {"lat": -90, "lon": 0}, (-90, 0))
    lines = geo["lines"]
    line_ids = {}
    for key, (text, at) in LINE_TEXT.items():
        if key not in lines:
            continue
        entry = lines[key]
        where = {"path": key} if "paths" in entry else {"lat": entry["lat"]}
        line_ids[key] = add(key, entry["name"], text.format(lat=_degrees(entry.get("lat", 0))), "line", where, at)
    prime = add("prime-meridian", "Prime Meridian", "The line of longitude marked 0°. It runs from the North Pole to "
                "the South Pole through Greenwich, in London.", "line", {"lon": 0}, (50, 0))
    line_ids["prime-meridian"] = prime
    hemisphere_ids = {}
    for key, (name, text, at) in HEMISPHERES.items():
        hemisphere_ids[key] = add(_slug(name), name, text, "area", {"hemisphere": key}, at)

    # Continents: members come from each country's row, so borders and continents always agree.
    continent_ids = {}
    shares = {c["name"]: c for c in geo["continents"]}
    for name in geo["continents"] and [c["name"] for c in geo["continents"]]:
        members = [a for a in areas if a["continent"] == name]
        point_id = _slug(name)
        if point_id in ids:                       # never meets a country's id; guard anyway
            point_id += "-continent"
        count = len(members)
        line = "One of Earth's seven continents." if name != "Antarctica" else \
            "The continent around the South Pole. No country owns it."
        continent_ids[name] = add(point_id, name, line, "area", {"codes": [a["code"] for a in members]},
                                  CONTINENT_AT[name], fact=f"It holds {count} countries and territories." if
                                  name != "Antarctica" else "")
        share = shares[name]
        for axis, high, low in (("north", "north", "south"), ("east", "east", "west")):
            value = share[axis]
            if value >= .8 or value <= .2:
                side = high if value >= .8 else low
                strength = max(value, 1 - value)
                how = "All of" if strength >= .98 else "Nearly all of" if strength >= .9 else "Most of"
                links.append(("place", continent_ids[name], hemisphere_ids[side],
                              f"{how} its land lies in the {HEMISPHERES[side][0]}."))

    # Oceans.
    ocean_ids = {}
    for ocean in geo["oceans"]:
        number = ocean["number"]
        ocean_ids[number] = add(_slug(ocean["name"]), ocean["name"], "One of Earth's five oceans.", "area",
                                {"ocean": number}, OCEAN_AT[number])
    links.append(("place", north_pole, ocean_ids[5], "It lies on floating ice in the middle of the Arctic Ocean."))
    if "Antarctica" in continent_ids:
        links.append(("place", south_pole, continent_ids["Antarctica"], "It lies on the ice of Antarctica."))

    # Countries and territories (the area picture's codes).
    area_ids = {}
    for area in areas:
        kind = {"country": "A country", "own-government": "A place with its own government",
                "territory": "A territory", "disputed": "An area whose status is disputed",
                "unowned": "A continent no country owns"}[area["status"]]
        where_in = f" in {area['continent']}" if area["continent"] else " far from any continent"
        text = f"{kind}{where_in}."
        if area["status"] == "unowned":
            text = "The continent around the South Pole."
        point_id = area["id"]
        if point_id in {p["id"] for p in points}:
            point_id += "-area"
        at = (area["label"][1], area["label"][0])
        area_ids[area["code"]] = add(point_id, area["name"], text, "area", {"codes": [area["code"]]}, at)
        points[-1].update({"tiny": area["tiny"], "status": area["status"], "more": area["sentence"]})
        if area["status"] != "unowned" and area["continent"]:
            links.append(("place", area_ids[area["code"]], continent_ids[area["continent"]],
                          f"It is in {area['continent']}."))
    for area in areas:                            # a territory belongs to its sovereign state
        if area["status"] == "territory" and area["sovereign"] in by_name:
            parent = by_name[area["sovereign"]]
            if parent["code"] != area["code"]:
                links.append(("inside", area_ids[parent["code"]], area_ids[area["code"]],
                              f"It belongs to {parent['name']}."))

    # Main cities: every national capital, and any city over five million people.
    taken = {p["id"] for p in points}
    for place in geo["places"]:
        owner = by_code.get(place["area"])
        if owner is None or _slug(place["name"]) == _slug(owner["name"]) or _slug(place["name"]) in ids:
            continue                              # a city-state: the country is the topic (SKIP_RULE_NOTE)
        point_id = _slug(place["name"])
        if point_id in taken:
            point_id = f"{point_id}-{_slug(owner['name'])}"
        if point_id in taken:
            continue
        taken.add(point_id)
        text = (f"The capital of {owner['name']}." if place["capital"] else f"A big city in {owner['name']}.")
        add(point_id, place["name"], text, "pin", {"lat": place["lat"], "lon": place["lon"]},
            (place["lat"], place["lon"]), query=f"{place['name']} skyline")
        links.append(("place", point_id, area_ids[owner["code"]],
                      f"It is the capital of {owner['name']}." if place["capital"] else f"It is in {owner['name']}."))

    # The lines teach by comparison.
    for a, b in (("equator", "tropic-of-cancer"), ("equator", "tropic-of-capricorn"), ("equator", "arctic-circle"),
                 ("equator", "antarctic-circle"), ("prime-meridian", "date-line")):
        if a in line_ids and b in line_ids:
            links.append(("like", line_ids[a], line_ids[b], "Both are lines drawn round the Earth."))
    links.append(("like", hemisphere_ids["north"], hemisphere_ids["south"], "The Equator divides them."))
    links.append(("like", hemisphere_ids["east"], hemisphere_ids["west"], "The Prime Meridian divides them."))
    return points, links
