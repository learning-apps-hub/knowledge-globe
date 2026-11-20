#!/usr/bin/env python3
"""Pin the facts the theme doors compare, and their values through the years (`data/compare.json`).

A theme door shows the same facts at the same places for every row, so two countries can be read side by
side, and the year control turns the dated ones back in time. Same rule as scripts/build_facts.py: a fact
is one sourced value about one topic and names where it was read; a value with no source is not stored.

    which topics   the ones scripts/build_facts.py gave facts to (countries and territories)
    people         P1082 by year (pq:P585): the values the year control walks through
    life           P2250 (life expectancy) by year
    hdi            P1081 (Human Development Index) by year
    gdp            P2131 (nominal GDP), the newest dated value
    gdp-each       gdp divided by the people of the nearest year, at most 3 away (worked out here;
                   Wikidata holds it for 9 countries only)
    highest        P610 (highest point) with its height P2044
    began          P571 (inception), the year
    government     P122 (basic form of government), the ones in force
    head           P35 (head of state), the one in office
    nobel          how many Nobel prize winners were citizens (P27 + P166), counted by a query
    heritage       how many World Heritage sites (P1435 + P757), counted by a query

    python3 scripts/build_compare.py          # needs data/facts.json and data/visuals.json

Standard library only. About fifty requests to Wikidata, paced.
"""
import json
import os
import sys
import urllib.parse

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_visuals  # noqa: E402
from build_facts import amount, listed, sparql  # noqa: E402

OUT = os.path.join(REPO, "data", "compare.json")
FACTS = os.path.join(REPO, "data", "facts.json")
FIRST_YEAR = 1960    # the year control starts here: before it most countries have no dated value
SERIES = (("people", "P1082"), ("life", "P2250"), ("hdi", "P1081"))
NOBEL = "Q38104 Q44585 Q80061 Q37922 Q35637 Q47170"   # physics, chemistry, medicine, literature, peace, economics


def source(item, prop):
    return f"https://www.wikidata.org/wiki/{item}#{prop}"


def asked(query):
    """A link that runs a counting query, so the count can be checked."""
    return "https://query.wikidata.org/#" + urllib.parse.quote(query)


def say(key, number):
    if key == "people":
        return f"{amount(number)} people"
    if key == "life":
        return f"{number:.1f}".rstrip("0").rstrip(".") + " years"
    return f"{number:.3f}".rstrip("0").rstrip(".") + " out of 1"


def dollars(number):
    if number >= 1e12:
        scaled = number / 1e12
        return (f"{scaled:.1f}".rstrip("0").rstrip(".") if scaled < 10 else f"{round(scaled)}") + " trillion US dollars"
    return f"{amount(number)} US dollars"


def main():
    with open(FACTS, encoding="utf-8") as fh:
        topics = sorted(json.load(fh)["facts"])
    with open(build_visuals.OUT, encoding="utf-8") as fh:
        pinned = json.load(fh)["visuals"]
    item_of = {topic: pinned[topic]["item"] for topic in topics if pinned.get(topic, {}).get("item")}
    items = sorted(set(item_of.values()))
    print(f"{len(items)} countries and territories with an item")
    found = {item: [] for item in items}

    def add(item, prop, key, value, text, **more):
        found[item].append(dict({"key": key, "value": value, "text": text, "source": source(item, prop)}, **more))

    # Values through the years: one per year, the preferred statement winning over a normal one.
    years = {key: {} for key, _ in SERIES}
    for key, prop in SERIES:
        for row in sparql("?item ?n ?when ?rank", f"?item p:{prop} ?s . ?s ps:{prop} ?n ; pq:P585 ?when ; "
                          "wikibase:rank ?rank . FILTER(?rank != wikibase:DeprecatedRank)", items):
            year = row["when"][:4]
            if not year.isdigit() or int(year) < FIRST_YEAR:
                continue
            try:
                number = float(row["n"])
            except ValueError:
                continue
            if key == "hdi" and not 0 < number <= 1 or key == "life" and not 15 < number < 100 or number <= 0:
                continue
            best = row["rank"].endswith("PreferredRank")
            held = years[key].setdefault(row["item"], {})
            if year not in held or best > held[year][0]:
                held[year] = (best, number)
        for item, held in years[key].items():
            by_year = {year: (int(n) if key == "people" else round(n, 3)) for year, (_, n) in sorted(held.items())}
            newest = max(by_year)
            add(item, prop, key, by_year[newest], say(key, by_year[newest]), as_of=newest, by_year=by_year)

    print("by year:", ", ".join(f"{key} {len(held)}" for key, held in years.items()), flush=True)
    gdp = {}
    for row in sparql("?item ?n ?when", "?item p:P2131 ?s . ?s ps:P2131 ?n ; pq:P585 ?when ; wikibase:rank ?rank . "
                      "FILTER(?rank != wikibase:DeprecatedRank)", items):
        seen = (row["when"][:4], float(row["n"]))
        gdp[row["item"]] = max(gdp.get(row["item"], seen), seen)
    for item, (year, number) in gdp.items():
        if not year.isdigit() or number <= 0:
            continue
        add(item, "P2131", "gdp", round(number), dollars(number), as_of=year)
        people = {y: n for y, (_, n) in years["people"].get(item, {}).items()}
        near = sorted((y for y in people if abs(int(y) - int(year)) <= 3), key=lambda y: abs(int(y) - int(year)))
        if near:
            each = number / people[near[0]]
            add(item, "P2131", "gdp-each", round(each), dollars(each), as_of=year,
                worked="everything made in the year, divided by the people")

    peaks = {}
    for row in sparql("?item ?name ?m", "?item p:P610 ?s . ?s a wikibase:BestRank ; ps:P610 ?x . "
                      "FILTER NOT EXISTS { ?s pq:P518 ?part } "
                      "?x rdfs:label ?name FILTER(LANG(?name) = 'en') "
                      "OPTIONAL { ?x p:P2044 ?h . ?h a wikibase:BestRank ; psn:P2044 ?v . "
                      "?v wikibase:quantityAmount ?m }", items):
        height = float(row["m"]) if row.get("m") else None
        seen = (height or 0, row["name"])
        peaks[row["item"]] = max(peaks.get(row["item"], seen), seen)
    for item, (height, name) in peaks.items():
        if height > 0:
            add(item, "P610", "highest", round(height), f"{name}, {round(height):,} m", name=name)

    began = {}
    for row in sparql("?item ?when", "?item p:P571 ?s . ?s a wikibase:BestRank ; ps:P571 ?when", items):
        when = row["when"]
        year = -int(when[1:].split("-")[0]) if when.startswith("-") else int(when.split("-")[0])
        began[row["item"]] = min(began.get(row["item"], year), year)
    for item, year in began.items():
        add(item, "P571", "began", year, str(year) if year > 0 else f"{-year} BC")

    for key, prop in (("government", "P122"), ("head", "P35")):
        names = {}
        for row in sparql("?item ?name", f"?item p:{prop} ?s . ?s a wikibase:BestRank ; ps:{prop} ?x . "
                          "FILTER NOT EXISTS { ?s pq:P582 ?ended } "
                          "?x rdfs:label ?name FILTER(LANG(?name) = 'en')", items):
            names.setdefault(row["item"], set()).add(row["name"])
        for item, words in names.items():
            words = sorted(words, key=str.lower)
            add(item, prop, key, words, listed([w[:1].upper() + w[1:] for w in words]))

    # Counts. Each count's source is the query that made it, for that one country.
    counts = (
        ("nobel", "(COUNT(DISTINCT ?x) AS ?n)",
         "VALUES ?prize { %s } ?x wdt:P166 ?prize ; wdt:P27 ?item ."
         % " ".join(f"wd:{q}" for q in NOBEL.split()),
         lambda n: f"{n:,} winner{'' if n == 1 else 's'} who were citizens"),
        # A site in several parts lists every part with its own id ("1234-005", "1234bis"): count the site once.
        ("heritage", '(COUNT(DISTINCT ?site) AS ?n)',
         '?x wdt:P1435 wd:Q9259 ; wdt:P17 ?item ; wdt:P757 ?id . BIND(REPLACE(?id, "[^0-9].*$", "") AS ?site)',
         lambda n: f"{n:,} site{'' if n == 1 else 's'}"),
    )
    for key, select, where, words in counts:
        # One query for the whole world (a thousand winners, a thousand sites), not one per country.
        print(f"counting {key}", flush=True)
        query = f"SELECT ?item {select} WHERE {{ {where} }} GROUP BY ?item"
        payload = build_visuals.call(build_visuals.SPARQL, {"query": query, "format": "json"}, post=True, pause=1)
        for row in payload["results"]["bindings"]:
            item = row["item"]["value"].rsplit("/", 1)[1]
            number = int(row["n"]["value"])
            one = f"SELECT {select} WHERE {{ VALUES ?item {{ wd:{item} }} {where} }}"
            if number and item in found:
                found[item].append({"key": key, "value": number, "text": words(number), "source": asked(one)})

    compare = {topic: found[item] for topic, item in sorted(item_of.items()) if found[item]}
    count = {}
    for facts in compare.values():
        for fact in facts:
            count[fact["key"]] = count.get(fact["key"], 0) + 1
    print("facts:", ", ".join(f"{key} {n}" for key, n in sorted(count.items())), f"on {len(compare)} topics")
    note = ("Built by scripts/build_compare.py from Wikidata (CC0): the facts the theme doors compare, and their "
            "values through the years. Do not edit by hand.")
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"note": note, "first_year": FIRST_YEAR, "compare": compare}, fh, ensure_ascii=False,
                  separators=(",", ":"), sort_keys=True)
        fh.write("\n")
    print(f"wrote {os.path.relpath(OUT, REPO)} ({os.path.getsize(OUT) // 1024} KB)")


if __name__ == "__main__":
    main()
