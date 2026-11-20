#!/usr/bin/env python3
"""Pin theme doors to country and territory topics (`data/themes.json`).

A theme is a big area of knowledge (NAMES.md). For one topic a theme door is the Wikipedia page about that
side of it ("History of Brazil"): its opening words, its picture where it has a free photo, and where both
were read. Wikidata names the page, so nothing is guessed from a title.

    which topics   the ones scripts/build_facts.py gave facts to (countries and territories)
    geography      P2633 (geography of topic)
    history        P2184 (history of topic)
    culture        P2596 (culture)
    economy        P8744 (economy of topic)
    words          the page's first sentences (English Wikipedia, CC BY-SA 4.0), cut at a sentence end
    picture        the page's lead picture when it is a free photo; charts and drawn files are left out

    python3 scripts/build_themes.py           # needs data/facts.json and data/visuals.json

Standard library only. About seventy requests to Wikidata, Wikipedia and Commons, paced.
"""
import json
import os
import re
import sys
import urllib.parse

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_visuals  # noqa: E402

OUT = os.path.join(REPO, "data", "themes.json")
FACTS = os.path.join(REPO, "data", "facts.json")
THEMES = (("geography", "P2633"), ("history", "P2184"), ("culture", "P2596"), ("economy", "P8744"))
LONGEST = 300        # letters of the page's opening kept on a door
PHOTO = re.compile(r"\.(jpe?g|png|webp)$", re.I)
# A chart or a drawn map is not a picture of the theme: the door shows its words alone.
DRAWN = re.compile(r"pyramid|tree ?map|chart|graph|export|gdp|per.capita|locator|orthographic|location|"
                   r"logo|icon|coat.of.arms|emblem|flag|diagram|timeline", re.I)


def opening(text):
    """The first sentences of a page, whole, within LONGEST letters."""
    text = re.sub(r"\s*\([^()]*\)", "", " ".join((text or "").split()))   # sounds and dates in brackets
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    kept = ""
    for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z\"“])", text):
        if kept and len(kept) + len(sentence) + 1 > LONGEST:
            break
        kept = f"{kept} {sentence}".strip()
    return kept if len(kept) <= LONGEST + 120 else ""


def main():
    with open(FACTS, encoding="utf-8") as fh:
        topics = sorted(json.load(fh)["facts"])
    with open(build_visuals.OUT, encoding="utf-8") as fh:
        pinned = json.load(fh)["visuals"]
    item_of = {topic: pinned[topic]["item"] for topic in topics if pinned.get(topic, {}).get("item")}
    items = sorted(set(item_of.values()))
    print(f"{len(items)} countries and territories with an item")

    # Wikidata: which page stands for each theme of each topic.
    props = {prop: key for key, prop in THEMES}
    query = ("SELECT ?c ?p ?t ?art WHERE { VALUES ?c { %s } VALUES ?p { %s } ?c ?p ?t . "
             "?art schema:about ?t ; schema:isPartOf <https://en.wikipedia.org/> }"
             % (" ".join(f"wd:{item}" for item in items), " ".join(f"wdt:{prop}" for prop in props)))
    rows = build_visuals.call(build_visuals.SPARQL, {"query": query, "format": "json"}, post=True, pause=1)
    page_of = {}     # (country item, theme key) -> (theme item, page title); the first listed wins
    for row in sorted(rows["results"]["bindings"], key=lambda r: r["t"]["value"]):
        tail = {name: row[name]["value"].rsplit("/", 1)[1] for name in ("c", "p", "t", "art")}
        title = urllib.parse.unquote(tail["art"]).replace("_", " ")
        page_of.setdefault((tail["c"], props[tail["p"]]), (tail["t"], title))
    titles = sorted({title for _, title in page_of.values()})
    print(f"{len(titles)} theme pages")

    # Wikipedia: each page's opening words and lead picture.
    words, lead, address = {}, {}, {}
    for part in build_visuals.chunks(titles, 20):
        payload = build_visuals.call(build_visuals.WIKIPEDIA, {
            "action": "query", "format": "json", "titles": "|".join(part), "redirects": 1,
            "prop": "extracts|pageimages|info", "exintro": 1, "explaintext": 1, "exlimit": 20,
            "piprop": "name", "pilicense": "free", "pilimit": 20, "inprop": "url"}, post=True, pause=1)
        query = payload.get("query", {})
        back = {hop["to"]: hop["from"] for hop in query.get("normalized", []) + query.get("redirects", [])}
        for page in query.get("pages", {}).values():
            asked = back.get(page["title"], page["title"])
            asked = back.get(asked, asked)
            words[asked] = opening(page.get("extract"))
            address[asked] = page.get("canonicalurl", "")
            name = page.get("pageimage", "").replace("_", " ")
            if PHOTO.search(name) and not DRAWN.search(name):
                lead[asked] = name
    credits = build_visuals.commons(lead.values())

    themes, count, pictured = {}, {}, {}
    for topic, item in item_of.items():
        doors = []
        for key, _ in THEMES:
            theme_item, title = page_of.get((item, key), (None, None))
            if not title or not words.get(title) or not address.get(title):
                continue
            door = {"key": key, "title": title, "text": words[title], "source": address[title],
                    "item": theme_item}
            picture = credits.get(lead.get(title, ""))
            if picture:
                door["picture"] = picture
                pictured[key] = pictured.get(key, 0) + 1
            doors.append(door)
            count[key] = count.get(key, 0) + 1
        if doors:
            themes[topic] = doors
    print("themes:", ", ".join(f"{key} {count.get(key, 0)} ({pictured.get(key, 0)} with a photo)"
                               for key, _ in THEMES), f"on {len(themes)} topics")
    note = ("Built by scripts/build_themes.py: pages named by Wikidata (CC0), opening words from English Wikipedia "
            "(CC BY-SA 4.0), pictures from Wikimedia Commons, each with its own credit. Do not edit by hand.")
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"note": note, "themes": themes}, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"wrote {os.path.relpath(OUT, REPO)}")


if __name__ == "__main__":
    main()
