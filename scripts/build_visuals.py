#!/usr/bin/env python3
"""Pin one picture to every Explore topic that has a Wikidata item (`data/visuals.json`).

The rule (ONE_GRAPH_DESIGN.md, "Card photos"): a topic's picture is the image its Wikidata item names
(property P18), looked up by item id, never by searching for the name. A name search finds whatever
file happens to share the word (France = a costumed man, Asia = a church mosaic); the item's own image
is the one editors chose to stand for it (France = Paris, Asia = the continent from space).

    item id    countries and territories: Natural Earth's WIKIDATAID, by area code
               continents, oceans, lines, hemispheres, poles, people: the English Wikipedia page in TITLES
               cities: the English Wikipedia page of that name, accepted only if the item's coordinates
               are within NEAR degrees of ours (else a Wikidata search, then the page "City, Country",
               each checked the same way)
    picture    the item's best-rank image (P18); of several, the first listed. An item with no image
               (about 40 countries) gets its locator map (P242): plain, but never the wrong thing
    credit     author and licence from Wikimedia Commons, saved with the link to the file's page

A topic with no item, or an item with neither, is left out: the viewer then falls back to its one name search. Run it
again when topics are added; a topic keeps its pinned picture while the item still names it.

    python3 scripts/build_visuals.py            # needs the Earth data folder (source + derived)

Standard library only. A few dozen requests to Wikipedia, Wikidata and Commons, paced; takes a few minutes.
"""
import argparse
import html.parser
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from app import geography, graph  # noqa: E402

DEFAULT_DIR = os.environ.get("KG_EARTH_DIR") or os.path.join(os.path.dirname(REPO), "earth-data")
OUT = os.path.join(REPO, "data", "visuals.json")
AGENT = "visuals-build/1.0 (python-urllib)"
WIKIPEDIA = "https://en.wikipedia.org/w/api.php"
WIKIDATA = "https://www.wikidata.org/w/api.php"
SPARQL = "https://query.wikidata.org/sparql"
COMMONS = "https://commons.wikimedia.org/w/api.php"
WIDTH = 500          # a size Wikimedia keeps ready (500 px): cards are about 330 px wide
NEAR = 1.5          # degrees: a city's item must sit this close to our pin

# Topics that are not a country or a city: the English Wikipedia page whose item stands for them.
TITLES = {
    "africa": "Africa", "antarctica": "Antarctica", "asia": "Asia", "europe": "Europe",
    "north-america": "North America", "oceania": "Oceania", "south-america": "South America",
    "pacific-ocean": "Pacific Ocean", "atlantic-ocean": "Atlantic Ocean", "indian-ocean": "Indian Ocean",
    "southern-ocean": "Southern Ocean", "arctic-ocean": "Arctic Ocean",
    "northern-hemisphere": "Northern Hemisphere", "southern-hemisphere": "Southern Hemisphere",
    "eastern-hemisphere": "Eastern Hemisphere", "western-hemisphere": "Western Hemisphere",
    "equator": "Equator", "tropic-of-cancer": "Tropic of Cancer", "tropic-of-capricorn": "Tropic of Capricorn",
    "arctic-circle": "Arctic Circle", "antarctic-circle": "Antarctic Circle",
    "prime-meridian": "Prime meridian", "date-line": "International Date Line",
    "north-pole": "North Pole", "south-pole": "South Pole",
    "james-cook": "James Cook", "edward-bransfield": "Edward Bransfield",
    "fabian-von-bellingshausen": "Fabian Gottlieb von Bellingshausen",
}


def call(url, params, post=False, pause=0):
    """One request, politely: `pause` seconds afterwards, and a wait when the server says slow down."""
    data = urllib.parse.urlencode(params)
    request = urllib.request.Request(url if post else f"{url}?{data}", data=data.encode() if post else None,
                                     headers={"User-Agent": AGENT, "Accept": "application/json"})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.load(response)
            time.sleep(pause)
            return payload
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            if attempt == 5:
                raise
            wait = 3 * (attempt + 1)
            if isinstance(error, urllib.error.HTTPError) and error.code == 429:
                asked = error.headers.get("Retry-After", "")
                wait = min(120, int(asked) if asked.isdigit() else 20 * (attempt + 1))
            print(f"  waiting {wait} s ({error})", file=sys.stderr)
            time.sleep(wait)


def chunks(items, size):
    items = list(items)
    for i in range(0, len(items), size):
        yield items[i:i + size]


def items_for_titles(titles):
    """{title: item id} for English Wikipedia page titles (redirects followed)."""
    found = {}
    for part in chunks(sorted(set(titles)), 50):
        payload = call(WIKIPEDIA, {"action": "query", "prop": "pageprops", "ppprop": "wikibase_item",
                                   "redirects": 1, "titles": "|".join(part), "format": "json"}, post=True)
        query = payload.get("query", {})
        step = {}
        for key in ("normalized", "redirects"):
            for hop in query.get(key, []):
                step[hop["from"]] = hop["to"]
        by_title = {page["title"]: page.get("pageprops", {}).get("wikibase_item")
                    for page in query.get("pages", {}).values()}
        for title in part:
            end = title
            for _ in range(4):
                end = step.get(end, end)
            if by_title.get(end):
                found[title] = by_title[end]
    return found


def facts(item_ids):
    """{item id: {"images": [file names], "maps": [file names], "at": (lat, lon) or None}}, best rank only."""
    out = {}
    for part in chunks(sorted(set(item_ids)), 150):
        values = " ".join(f"wd:{i}" for i in part)
        query = ("SELECT ?item ?image ?map ?at WHERE { VALUES ?item { %s } OPTIONAL { ?item wdt:P18 ?image } "
                 "OPTIONAL { ?item wdt:P242 ?map } OPTIONAL { ?item wdt:P625 ?at } }" % values)
        payload = call(SPARQL, {"query": query, "format": "json"}, post=True, pause=1)
        for row in payload["results"]["bindings"]:
            item = row["item"]["value"].rsplit("/", 1)[1]
            entry = out.setdefault(item, {"images": [], "maps": [], "at": None})
            for key, into in (("image", "images"), ("map", "maps")):
                if key in row:
                    name = urllib.parse.unquote(row[key]["value"].rsplit("/", 1)[1]).replace("_", " ")
                    if name not in entry[into]:
                        entry[into].append(name)
            if "at" in row and entry["at"] is None:
                lon, lat = row["at"]["value"].removeprefix("Point(").removesuffix(")").split()
                entry["at"] = (float(lat), float(lon))
    return out


def first_listed(item_id, names, prop):
    """Of several best-rank pictures, the one listed first on the item."""
    payload = call(WIKIDATA, {"action": "wbgetclaims", "entity": item_id, "property": prop, "format": "json"},
                   pause=1.5)
    for claim in payload.get("claims", {}).get(prop, []):
        name = claim.get("mainsnak", {}).get("datavalue", {}).get("value", "").replace("_", " ")
        if name in names:
            return name
    return sorted(names)[0]


def search_items(name):
    payload = call(WIKIDATA, {"action": "wbsearchentities", "search": name, "language": "en", "limit": 8,
                              "format": "json"}, pause=1.5)
    return [hit["id"] for hit in payload.get("search", [])]


def apart(a, b):
    """Degrees between two (lat, lon) spots on the globe."""
    la, lb = math.radians(a[0]), math.radians(b[0])
    cos = math.sin(la) * math.sin(lb) + math.cos(la) * math.cos(lb) * math.cos(math.radians(a[1] - b[1]))
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


class Plain(html.parser.HTMLParser):
    """The words of a Commons credit, without markup and without the duplicate Commons hides."""
    VOID = {"br", "img", "hr", "wbr", "input", "meta", "link"}

    def __init__(self):
        super().__init__()
        self.words, self.stack = [], []

    def handle_starttag(self, tag, attrs):
        if tag in self.VOID:
            return
        style = (dict(attrs).get("style") or "").replace(" ", "").lower()
        self.stack.append("display:none" in style)

    def handle_endtag(self, tag):
        if tag not in self.VOID and self.stack:
            self.stack.pop()

    def handle_data(self, data):
        if not any(self.stack):
            self.words.append(data)


def plain(value):
    parser = Plain()
    parser.feed(value or "")
    return " ".join("".join(parser.words).split())


def commons(names):
    """{file name: {"src", "page", "credit", "licence"}} for Commons files."""
    out = {}
    for part in chunks(sorted(set(names)), 40):
        payload = call(COMMONS, {"action": "query", "titles": "|".join(f"File:{n}" for n in part),
                                 "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": WIDTH,
                                 "format": "json"}, post=True, pause=1)
        query = payload.get("query", {})
        back = {hop["to"]: hop["from"] for hop in query.get("normalized", [])}
        for page in query.get("pages", {}).values():
            info = (page.get("imageinfo") or [{}])[0]
            if not info.get("thumburl"):
                continue
            asked = back.get(page["title"], page["title"]).removeprefix("File:")
            meta = info.get("extmetadata") or {}
            out[asked] = {
                "src": info["thumburl"],
                "page": info["descriptionurl"],
                "credit": (plain(meta.get("Artist", {}).get("value")) or "Wikimedia Commons contributor")[:48],
                "licence": plain(meta.get("LicenseShortName", {}).get("value")) or "see source",
            }
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dir", default=DEFAULT_DIR, help="the Earth data folder (source/ and derived/)")
    args = parser.parse_args()

    geo = geography.load(os.path.join(args.dir, "derived"))
    if not geo:
        sys.exit(f"no geography in {args.dir}/derived: run scripts/build_earth.py first")
    built = graph.build(geo, visuals={})
    points = {p["id"]: p for p in built["points"]}
    old = {}
    if os.path.isfile(OUT):
        with open(OUT, encoding="utf-8") as fh:
            old = json.load(fh).get("visuals", {})

    # 1. Each topic's item.
    item_of = {}
    with open(os.path.join(args.dir, "source", "ne_10m_admin_0_countries.geojson"), encoding="utf-8") as fh:
        features = json.load(fh)["features"]
    features.sort(key=lambda f: (f["properties"]["ADM0_A3"], f["properties"]["NAME"]))   # build_earth's codes
    code_item = {i + 1: f["properties"].get("WIKIDATAID") for i, f in enumerate(features)}
    for point in points.values():
        codes = point.get("where", {}).get("codes") or []
        if point["id"] not in TITLES and point.get("shape") == "area" and len(codes) == 1:
            item = code_item.get(codes[0]) or ""
            if item[:1] == "Q" and item[1:].isdigit():
                item_of[point["id"]] = item
    cities = {p["id"]: p for p in points.values() if p.get("shape") == "pin" and p["id"] not in TITLES}
    titles = items_for_titles(list(TITLES.values()) + [p["name"] for p in cities.values()])
    for point_id, title in TITLES.items():
        if point_id in points and title in titles:
            item_of[point_id] = titles[title]
    print(f"items: {len(item_of)} by id or page; {len(cities)} cities to place")

    # 2. Cities: the page of that name, if its item is where our pin is; else a search, checked the same way.
    known = facts(list(item_of.values()) + [titles[p["name"]] for p in cities.values() if p["name"] in titles])
    lost = []
    for point_id, point in cities.items():
        here = (point["at"]["lat"], point["at"]["lon"])
        item = titles.get(point["name"])
        if item and known.get(item, {}).get("at") and apart(known[item]["at"], here) <= NEAR:
            item_of[point_id] = item
            continue
        hits = search_items(point["name"])
        known.update(facts([h for h in hits if h not in known]))
        near = [h for h in hits if known.get(h, {}).get("at") and apart(known[h]["at"], here) <= NEAR]
        if near:
            item_of[point_id] = near[0]
        else:
            lost.append(point_id)
    if lost:                                      # "Victoria" finds eight others: ask for "Victoria, Seychelles"
        country = {k["from"]: points[k["to"]]["name"] for k in built["links"]
                   if k["kind"] == "place" and k["from"] in lost
                   and len(points[k["to"]]["where"].get("codes", [])) == 1}
        full = {i: f"{cities[i]['name']}, {country[i]}" for i in lost if i in country}
        pages = items_for_titles(full.values())
        known.update(facts([pages[t] for t in full.values() if t in pages and pages[t] not in known]))
        for point_id, title in full.items():
            item = pages.get(title)
            here = (cities[point_id]["at"]["lat"], cities[point_id]["at"]["lon"])
            if item and known.get(item, {}).get("at") and apart(known[item]["at"], here) <= NEAR:
                item_of[point_id] = item
                lost.remove(point_id)
    if lost:
        print(f"no item found for {len(lost)} cities (name search stays): {', '.join(sorted(lost))}")

    # 3. Each item's picture, then its credit.
    chosen, mapped = {}, 0
    for point_id, item in sorted(item_of.items()):
        prop, names = "P18", known.get(item, {}).get("images") or []
        if not names:
            prop, names = "P242", known.get(item, {}).get("maps") or []
            mapped += bool(names)
        if not names:
            continue
        kept = old.get(point_id, {}).get("file")
        chosen[point_id] = (kept if kept in names else names[0] if len(names) == 1
                            else first_listed(item, names, prop))
    print(f"{mapped} items have no image: their locator map stands in")
    files = commons(chosen.values())
    visuals = {}
    for point_id, name in sorted(chosen.items()):
        if name in files:
            visuals[point_id] = {**files[name], "file": name, "item": item_of[point_id]}
    bare = sorted(i for i in item_of if i not in visuals)
    print(f"pictures: {len(visuals)} of {len(points)} topics; {len(bare)} items without one"
          + (f": {', '.join(bare)}" if bare else ""))

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"note": "Built by scripts/build_visuals.py: each topic's picture is its Wikidata item's image "
                           "(P18), with author and licence from Wikimedia Commons. Do not edit by hand.",
                   "visuals": visuals}, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"wrote {os.path.relpath(OUT, REPO)}")


if __name__ == "__main__":
    main()
