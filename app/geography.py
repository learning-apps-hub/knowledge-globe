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

Kind topics ("Country", "Ocean", ...) have no shape: they are answered on the card only, and their "What kinds
are there?" lights every member.
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

# What kind of thing each geography topic is (link kind `kind`). Kind topics have no place: card only.
# "What kinds are there?" on one of them lights every member (Ocean → the five oceans).
KINDS = {
    "capital": ("Capital city", "The city where a country's government meets."),
    "city": ("Big city", "A city where more than five million people live."),
    "pole": ("Pole", "One of the two ends of the line the Earth spins around."),
    "latitude": ("Circle of latitude", "A circle round the Earth through every place the same distance from the "
                 "Equator."),
    "longitude": ("Line of longitude", "A half circle on the Earth from the North Pole to the South Pole."),
    "country": ("Country", "A land with its own government, accepted as a country by most other countries."),
    "territory": ("Territory", "A land that belongs to a country but is not part of its main land."),
    "own-government": ("Place with its own government", "A place that runs itself, but which not every country "
                       "accepts as a country."),
    "disputed": ("Disputed area", "Land that more than one country claims, or that no country's claim covers."),
    "leased": ("Leased land", "Land one country rents to another."),
    "continent": ("Continent", "One of the seven great areas of land on Earth."),
    "ocean": ("Ocean", "One of the five named parts of the salt water that covers most of the Earth."),
    "hemisphere": ("Hemisphere", "Half of the Earth, cut along the Equator or along the Prime Meridian."),
}

# Countries with land on two continents. Natural Earth files each under one (the first key's continent is
# Natural Earth's); both links carry a sentence saying how the land is shared.
TWO_CONTINENTS = {
    "Russia": {"Europe": "Most of its people live in Europe, west of the Ural Mountains.",
               "Asia": "Most of its land is in Asia, east of the Ural Mountains."},
    "Turkey": {"Asia": "Most of its land is in Asia.",
               "Europe": "A small part, around Istanbul, is in Europe."},
    "Kazakhstan": {"Asia": "Most of its land is in Asia.",
                   "Europe": "A small part, west of the Ural River, is in Europe."},
    "Egypt": {"Africa": "Most of its land is in Africa.",
              "Asia": "The Sinai Peninsula, east of the Suez Canal, is in Asia."},
    "Indonesia": {"Asia": "Most of its land is in Asia.",
                  "Oceania": "Its western half of the island of New Guinea is in Oceania."},
}


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


def _named(area):
    """An area's name as it reads inside a sentence ("the United Kingdom")."""
    return f"the {area['name']}" if area.get("the") else area["name"]


def _halves(north, east, what="land"):
    """[(side, why)] for the hemispheres something lies in: every side holding at least a fifth of it."""
    out = []
    for share, high, low in ((north, "north", "south"), (east, "east", "west")):
        for side, part in ((high, share), (low, 1 - share)):
            if part < .2:
                continue
            how = ("All of" if part >= .98 else "Nearly all of" if part >= .9 else "Most of" if part >= .5
                   else "Part of")
            out.append((side, f"{how} its {what} lies in the {HEMISPHERES[side][0]}."))
    return out


def build(geo):
    """(points, links) for the geography topics. Link = (kind, from, to, why)."""
    points, links = [], []

    def add(point_id, name, line, shape, where, at, query=None, fact=""):
        points.append({"id": point_id, "name": name, "line": line, "fact": fact, "shape": shape, "where": where,
                       "at": {"lat": at[0], "lon": at[1]}, "sources": [SOURCE], "visual_query": query or name})
        return point_id

    kind_ids = {}

    def kind_of(point_id, key, why=None):
        if key not in kind_ids:
            name, line = KINDS[key]
            kind_ids[key] = "kind-" + _slug(name)
            points.append({"id": kind_ids[key], "name": name, "line": line, "fact": "", "sources": [SOURCE],
                           "visual": False})           # a photo search for "Country" finds country music
        links.append(("kind", point_id, kind_ids[key], why))

    areas = geo["areas"]
    by_code = {a["code"]: a for a in areas}
    by_name = {a["name"]: a for a in areas}
    ids = {a["id"] for a in areas if a["status"] != "unowned"}   # Antarctica's area IS the continent topic

    # The two poles and the two kinds of dividing line.
    north_pole = add("north-pole", "North Pole", "The point farthest north on Earth. Every line of longitude "
                     "meets here.", "pin", {"lat": 90, "lon": 0}, (90, 0))
    south_pole = add("south-pole", "South Pole", "The point farthest south on Earth. Every line of longitude "
                     "meets here.", "pin", {"lat": -90, "lon": 0}, (-90, 0))
    for pole in (north_pole, south_pole):
        kind_of(pole, "pole")
    links.append(("like", north_pole, south_pole, "Both are ends of the line the Earth spins around."))
    lines = geo["lines"]
    line_ids = {}
    for key, (text, at) in LINE_TEXT.items():
        if key not in lines:
            continue
        entry = lines[key]
        where = {"path": key} if "paths" in entry else {"lat": entry["lat"]}
        line_ids[key] = add(key, entry["name"], text.format(lat=_degrees(entry.get("lat", 0))), "line", where, at)
        kind_of(key, "latitude" if "lat" in entry else "longitude",
                None if "lat" in entry else "It mostly follows the line of longitude 180°.")
    prime = add("prime-meridian", "Prime Meridian", "The line of longitude marked 0°. It runs from the North Pole to "
                "the South Pole through Greenwich, in London.", "line", {"lon": 0}, (50, 0))
    kind_of(prime, "longitude")
    line_ids["prime-meridian"] = prime
    hemisphere_ids = {}
    for key, (name, text, at) in HEMISPHERES.items():
        hemisphere_ids[key] = add(_slug(name), name, text, "area", {"hemisphere": key}, at)
        kind_of(hemisphere_ids[key], "hemisphere")

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
        kind_of(continent_ids[name], "continent")
        for side, why in _halves(shares[name]["north"], shares[name]["east"]):
            links.append(("place", continent_ids[name], hemisphere_ids[side], why))

    # Oceans.
    ocean_ids = {}
    for ocean in geo["oceans"]:
        number = ocean["number"]
        ocean_ids[number] = add(_slug(ocean["name"]), ocean["name"], "One of Earth's five oceans.", "area",
                                {"ocean": number}, OCEAN_AT[number])
        kind_of(ocean_ids[number], "ocean")
        if "north" in ocean:
            for side, why in _halves(ocean["north"], ocean["east"], "water"):
                links.append(("place", ocean_ids[number], hemisphere_ids[side], why))
    for ocean in geo["oceans"]:
        for other in ocean.get("next", []):
            if ocean["number"] < other:
                links.append(("next", ocean_ids[ocean["number"]], ocean_ids[other], "Their waters meet."))
    links.append(("place", north_pole, ocean_ids[5], "It lies on floating ice in the middle of the Arctic Ocean."))
    if "Antarctica" in continent_ids:
        links.append(("place", south_pole, continent_ids["Antarctica"], "It lies on the ice of Antarctica."))

    # Countries and territories (the area picture's codes).
    by_number = {o["number"]: o["name"] for o in geo["oceans"]}
    area_ids = {}
    for area in areas:
        kind = {"country": "A country", "own-government": "A place with its own government",
                "territory": "A territory", "disputed": "An area whose status is disputed",
                "leased": "Land rented to another country",
                "unowned": "A continent no country owns"}[area["status"]]   # unowned: never used, see below
        where_in = f" in {area['continent']}" if area["continent"] else " far from any continent"
        text = f"{kind}{where_in}."
        if area["status"] == "unowned" and "Antarctica" in continent_ids:
            # One topic, not two: the continent answers for its area (2026-11-13; it was "antarctica" +
            # "antarctica-continent", and the area had no answers).
            area_ids[area["code"]] = continent_ids["Antarctica"]
            next(p for p in points if p["id"] == continent_ids["Antarctica"])["more"] = area["sentence"]
            continue
        point_id = area["id"]
        if point_id in {p["id"] for p in points}:
            point_id += "-area"
        at = (area["label"][1], area["label"][0])
        area_ids[area["code"]] = add(point_id, area["name"], text, "area", {"codes": [area["code"]]}, at)
        points[-1].update({"tiny": area["tiny"], "status": area["status"], "more": area["sentence"]})
        kind_of(point_id, area["status"])
        two = TWO_CONTINENTS.get(area["name"])
        if two:
            for continent, why in two.items():
                links.append(("place", point_id, continent_ids[continent], why))
        elif area["continent"]:
            links.append(("place", point_id, continent_ids[area["continent"]], f"It is in {area['continent']}."))
        elif area.get("ocean") in ocean_ids:
            links.append(("place", point_id, ocean_ids[area["ocean"]],
                          f"It lies in the {by_number[area['ocean']]}, far from any continent."))
        if "north" in area:
            for side, why in _halves(area["north"], area["east"]):
                links.append(("place", point_id, hemisphere_ids[side], why))
    for area in areas:                            # a territory belongs to its sovereign state
        if area["status"] == "territory" and area["sovereign"] in by_name:
            parent = by_name[area["sovereign"]]
            if parent["code"] != area["code"]:
                links.append(("inside", area_ids[parent["code"]], area_ids[area["code"]],
                              f"It belongs to {_named(parent)}."))
        belongs = area.get("belongs")             # a disputed or leased area: the country that runs it
        if belongs and belongs["name"] in by_name:
            links.append(("inside", area_ids[by_name[belongs["name"]]["code"]], area_ids[area["code"]],
                          belongs["why"]))
    unowned = {a["code"] for a in areas if a["status"] == "unowned"}

    def topic_of(code):
        return continent_ids["Antarctica"] if code in unowned else area_ids[code]

    for area in areas:                            # neighbours: their borders touch
        for other in area.get("next", []):
            if area["code"] < other and other in area_ids and area["code"] in area_ids:
                links.append(("next", topic_of(area["code"]), topic_of(other), "They share a border."))

    # What each line runs across.
    for key, entry in lines.items():
        line_id = line_ids.get(key, prime if key == "prime-meridian" else None)
        if not line_id or "crosses" not in entry:
            continue
        for code in entry["crosses"]["areas"]:
            name = "Antarctica" if code in unowned else _named(by_code[code])
            links.append(("place", line_id, topic_of(code), f"The {entry['name']} runs across {name}."))
        for number in entry["crosses"]["oceans"]:
            links.append(("place", line_id, ocean_ids[number], f"The {entry['name']} runs across the "
                          f"{by_number[number]}."))

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
        text = (f"The capital of {_named(owner)}." if place["capital"] else f"A big city in {_named(owner)}.")
        add(point_id, place["name"], text, "pin", {"lat": place["lat"], "lon": place["lon"]},
            (place["lat"], place["lon"]), query=f"{place['name']} skyline")
        kind_of(point_id, "capital" if place["capital"] else "city")
        links.append(("place", point_id, area_ids[owner["code"]],
                      f"It is the capital of {_named(owner)}." if place["capital"] else f"It is in {_named(owner)}."))

    # The lines teach by comparison.
    for a, b in (("equator", "tropic-of-cancer"), ("equator", "tropic-of-capricorn"), ("equator", "arctic-circle"),
                 ("equator", "antarctic-circle"), ("prime-meridian", "date-line")):
        if a in line_ids and b in line_ids:
            links.append(("like", line_ids[a], line_ids[b], "Both are lines drawn round the Earth."))
    links.append(("like", hemisphere_ids["north"], hemisphere_ids["south"], "The Equator divides them."))
    links.append(("like", hemisphere_ids["east"], hemisphere_ids["west"], "The Prime Meridian divides them."))
    return points, links
