#!/usr/bin/env python3
"""Pin sourced facts to country and territory topics (`data/facts.json`).

The rule (ONE_GRAPH_DESIGN.md, "Facts on topics"): a fact is one sourced value about one topic. It is
not a topic and not a link. Every fact names the Wikidata item and property it was read from; a value
with no source is not stored.

    which topics   areas with a status (countries and territories) whose item is pinned in visuals.json
    people         P1082, best rank, the newest dated value
    size           P2046, best rank, in km²
    languages      P37 (official language), English names
    money          P38 (currency), English names
    flag           P41, with author and licence from Wikimedia Commons; only where FLAG_STATUS and
                   FLAG_HELD allow
    flag-colours   P462 on the flag's own item (P163), folded to colour words a child knows
    flag-shapes    P180 on the flag's item, kept only when it is one of SHAPES (the rest is noise:
                   Brazil's flag lists every star by name)

    python3 scripts/build_facts.py            # needs the Earth data folder (derived/) and visuals.json

Standard library only. About a dozen requests to Wikidata and Commons, paced.
"""
import argparse
import json
import os
import sys
import urllib.parse

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_visuals  # noqa: E402
from app import geography, graph  # noqa: E402

OUT = os.path.join(REPO, "data", "facts.json")
FLAG_WIDTH = 250     # a size Wikimedia keeps ready
# Topics whose pinned item is the wrong thing: no facts until the item is fixed in build_visuals.py.
WRONG_ITEM = {"spratly-islands"}     # Natural Earth's id for it is Wake Island's
# A flag is shown for a country, and for a territory or self-governing area that flies its own. Not for a
# disputed or leased area, not when the picture is another country's flag (Clipperton flies France's), and
# not for these, where which flag is "the" flag is itself the argument. Owner decides each one.
FLAG_STATUS = {"country", "territory", "own-government"}
FLAG_HELD = {
    "afghanistan": "Wikidata gives the Taliban's flag; the United Nations still uses the older tricolour",
    "new-caledonia": "Wikidata gives the independence movement's flag; it flies beside France's",
    "dhekelia-cantonment": "a garrison's flag, not a territory's",
}
# Wikidata's colour names, folded to the few a child knows. First match wins, so "blue-green" is blue.
COLOURS = (
    ("red", ("red", "crimson", "scarlet", "maroon", "carmine", "vermilion", "gules", "burgundy")),
    ("orange", ("orange", "saffron")),
    ("yellow", ("yellow", "gold", "or ")),
    ("blue", ("blue", "azure", "navy", "ultramarine", "cyan", "turquoise", "aquamarine", "teal", "cerulean")),
    ("green", ("green", "vert", "emerald")),
    ("white", ("white", "silver", "argent")),
    ("black", ("black", "sable")),
    ("purple", ("purple", "violet")),
    ("brown", ("brown",)),
    ("pink", ("pink",)),
)
ORDER = [name for name, _ in COLOURS]
# What a flag shows, by words in Wikidata's label. Anything else is dropped.
SHAPES = (
    ("coat of arms", ("coat of arms", "emblem", "seal", "escutcheon")),
    ("star", ("star", "pentagram", "hexagram")),
    ("sun", ("sun",)),
    ("moon", ("crescent", "moon")),
    ("cross", ("cross", "saltire")),
    ("circle", ("disk", "disc", "circle", "roundel")),
    ("triangle", ("triangle", "chevron")),
    ("stripes", ("stripe", "tricolour", "tricolor", "triband", "bicolour", "bicolor", "tribar")),
    ("animal", ("eagle", "lion", "bird", "dragon", "condor", "parrot", "crane", "leopard", "elephant", "horse")),
    ("plant", ("tree", "leaf", "maple", "cedar", "palm", "flower", "wreath", "olive", "laurel")),
)


def sparql(select, where, items):
    rows = []
    for part in build_visuals.chunks(sorted(set(items)), 80):
        values = " ".join(f"wd:{i}" for i in part)
        query = f"SELECT {select} WHERE {{ VALUES ?item {{ {values} }} {where} }}"
        payload = build_visuals.call(build_visuals.SPARQL, {"query": query, "format": "json"}, post=True, pause=1)
        for row in payload["results"]["bindings"]:
            flat = {key: cell["value"] for key, cell in row.items()}
            flat["item"] = flat["item"].rsplit("/", 1)[1]
            rows.append(flat)
    return rows


def round_to(number, figures=2):
    if number == 0:
        return 0
    digits = len(str(int(abs(number))))
    step = 10 ** max(0, digits - figures)
    return int(round(number / step) * step)


def amount(number):
    """A number a child can read: 203 million, 1.4 billion, 56,000, 728."""
    for size, word in ((1e9, "billion"), (1e6, "million")):
        if number >= size:
            scaled = number / size
            return f"{scaled:.1f}".rstrip("0").rstrip(".") + f" {word}" if scaled < 10 else f"{round(scaled)} {word}"
    if number >= 1000:
        return f"{round_to(number):,}"
    return f"{round(number):,}" if number >= 10 or number == int(number) else f"{number:.2g}"


def listed(words, most=4):
    words = list(words)
    if len(words) > most:
        return ", ".join(words[:most - 1]) + f" and {len(words) - most + 1} more"
    return ", ".join(words)


def fold(labels, table):
    out = []
    for name, keys in table:
        if any(key in f"{label.lower()} " for label in labels for key in keys):
            out.append(name)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dir", default=build_visuals.DEFAULT_DIR, help="the Earth data folder (derived/)")
    args = parser.parse_args()
    geo = geography.load(os.path.join(args.dir, "derived"))
    if not geo:
        sys.exit(f"no geography in {args.dir}/derived: run scripts/build_earth.py first")
    with open(build_visuals.OUT, encoding="utf-8") as fh:
        pinned = json.load(fh)["visuals"]
    points = graph.build(geo, visuals={}, facts={})["points"]
    item_of = {p["id"]: pinned[p["id"]]["item"] for p in points
               if p.get("shape") == "area" and p.get("status") and pinned.get(p["id"], {}).get("item")
               and p["id"] not in WRONG_ITEM}
    status = {p["id"]: p.get("status") for p in points}
    topic_of = {}
    for topic, item in sorted(item_of.items()):
        topic_of.setdefault(item, topic)
    items = list(topic_of)
    print(f"{len(items)} countries and territories with an item")

    def source(item, prop):
        return f"https://www.wikidata.org/wiki/{item}#{prop}"

    facts = {topic: [] for topic in item_of}

    def add(item, prop, key, value, text, **more):
        for topic, its in item_of.items():
            if its == item and (not key.startswith("flag") or topic in flag_ok):
                facts[topic].append(dict({"key": key, "value": value, "text": text}, **more,
                                         source=source(item, prop)))

    people = {}
    for row in sparql("?item ?n ?when", "?item p:P1082 ?s . ?s a wikibase:BestRank ; ps:P1082 ?n . "
                      "OPTIONAL { ?s pq:P585 ?when }", items):
        seen = (row.get("when", ""), float(row["n"]))
        people[row["item"]] = max(people.get(row["item"], seen), seen)
    size = {}
    for row in sparql("?item ?m2", "?item p:P2046 ?s . ?s a wikibase:BestRank ; psn:P2046 ?v . "
                      "?v wikibase:quantityAmount ?m2", items):
        size[row["item"]] = max(size.get(row["item"], 0), float(row["m2"]) / 1e6)
    names = {"languages": {}, "money": {}}
    for key, prop in (("languages", "P37"), ("money", "P38")):
        for row in sparql("?item ?name", f"?item p:{prop} ?s . ?s a wikibase:BestRank ; ps:{prop} ?x . "
                          "FILTER NOT EXISTS { ?s pq:P582 ?ended } FILTER NOT EXISTS { ?s pq:P518 ?part } "
                          "?x rdfs:label ?name FILTER(LANG(?name) = 'en')", items):
            names[key].setdefault(row["item"], set()).add(row["name"])
    flags = {}
    for row in sparql("?item ?flag", "?item wdt:P41 ?flag", items):
        name = urllib.parse.unquote(row["flag"].rsplit("/", 1)[1]).replace("_", " ")
        flags[row["item"]] = min(flags.get(row["item"], name), name)
    shows = {"P462": {}, "P180": {}}
    for prop in shows:
        for row in sparql("?item ?name", f"?item wdt:P163 ?f . ?f wdt:{prop} ?x . "
                          "?x rdfs:label ?name FILTER(LANG(?name) = 'en')", items):
            shows[prop].setdefault(row["item"], set()).add(row["name"])
    build_visuals.WIDTH = FLAG_WIDTH
    files = build_visuals.commons(flags.values())

    # A flag picture used by a country is that country's: another topic showing it has no flag of its own.
    national = {flags[item_of[t]] for t in item_of if status[t] == "country" and item_of[t] in flags}
    flag_ok = {t for t in item_of if status[t] in FLAG_STATUS and t not in FLAG_HELD
               and (status[t] == "country" or flags.get(item_of[t]) not in national)}
    unknown = set()
    for item in items:
        if item in people:
            when, number = people[item]
            more = {"as_of": when[:4]} if when[:4].isdigit() else {}
            add(item, "P1082", "people", int(number), f"{amount(number)} people", **more)
        if size.get(item):
            add(item, "P2046", "size", round(size[item], 2), f"{amount(size[item])} km²")
        for key, prop in (("languages", "P37"), ("money", "P38")):
            words = sorted(names[key].get(item, ()), key=str.lower)
            if words:
                add(item, prop, key, words, listed([w[:1].upper() + w[1:] for w in words]))
        flag = files.get(flags.get(item))
        if flag:
            add(item, "P41", "flag", flags[item], "Flag", **flag)
            colours = fold(shows["P462"].get(item, ()), COLOURS)
            unknown.update(label for label in shows["P462"].get(item, ()) if not fold([label], COLOURS))
            if colours:
                add(item, "P462", "flag-colours", colours, listed(colours, most=len(ORDER)))
            shapes = fold(shows["P180"].get(item, ()), SHAPES)
            if shapes:
                add(item, "P180", "flag-shapes", shapes, listed(shapes, most=len(SHAPES)))
    facts = {topic: found for topic, found in sorted(facts.items()) if found}
    count = {}
    for found in facts.values():
        for fact in found:
            count[fact["key"]] = count.get(fact["key"], 0) + 1
    print("facts:", ", ".join(f"{key} {n}" for key, n in sorted(count.items())), f"on {len(facts)} topics")
    if unknown:
        print("colour names not folded (dropped):", ", ".join(sorted(unknown)))
    note = ("Built by scripts/build_facts.py from Wikidata (CC0); flag pictures from Wikimedia Commons, each with "
            "its own credit. Do not edit by hand.")
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"note": note, "facts": facts}, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"wrote {os.path.relpath(OUT, REPO)}")


if __name__ == "__main__":
    main()
