#!/usr/bin/env python3
"""Pin sub-theme doors to country and territory topics (`data/subthemes.json`).

A sub-theme is one smaller side of a theme: Music under Culture, Rivers under Geography. For one topic its door
is the English Wikipedia page about that side of it ("Music of Brazil"): its opening words, its picture where it
has a free photo, and where both were read.

    which topics   the ones scripts/build_themes.py gave theme doors to
    which pages    the title patterns in SUBS, filled with the topic's name as its theme pages write it
                   ("Geography of the United States" gives "the United States")
    kept           a page of its own. A title that only forwards to the topic's own page, to one of its theme
                   pages, to a part of another page, or to a page that other topics' titles forward to as well
                   ("Cuisine of Tuvalu" to "Polynesian cuisine") is not a page about this topic: left out.
    words, picture as scripts/build_themes.py

    python3 scripts/build_subthemes.py        # needs data/themes.json

Standard library only. About three hundred paced requests to Wikipedia, then Commons for the picture credits.
Wikipedia often answers "slow down" to this many: the script waits and goes on, and can take an hour or more.
"""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_themes  # noqa: E402
import build_visuals  # noqa: E402

OUT = os.path.join(REPO, "data", "subthemes.json")
# theme key -> (sub-theme key, title pattern). Checked 2026-11-15: every pattern here has its own page for 80 or
# more of 235 topics, but Climate (59) and Food, Literature and Art, whose pages sit under titles like
# "Japanese cuisine" that these titles forward to.
SUBS = {
    "facts": (("politics", "Politics of {x}"), ("people", "Demographics of {x}"),
              ("education", "Education in {x}"), ("health", "Health in {x}")),
    "geography": (("rivers", "List of rivers of {x}"), ("geology", "Geology of {x}"), ("wildlife", "Wildlife of {x}"),
                  ("mountains", "List of mountains in {x}"), ("climate", "Climate of {x}")),
    "history": (("relations", "Foreign relations of {x}"), ("military", "Military history of {x}"),
                ("postal", "Postage stamps and postal history of {x}")),
    "culture": (("music", "Music of {x}"), ("food", "Cuisine of {x}"), ("holidays", "Public holidays in {x}"),
                ("religion", "Religion in {x}"), ("languages", "Languages of {x}"), ("cinema", "Cinema of {x}"),
                ("sport", "Sport in {x}"), ("architecture", "Architecture of {x}"),
                ("literature", "Literature of {x}"), ("art", "Art of {x}")),
    "economy": (("transport", "Transport in {x}"), ("tourism", "Tourism in {x}"),
                ("telecom", "Telecommunications in {x}"), ("agriculture", "Agriculture in {x}"),
                ("energy", "Energy in {x}"), ("mining", "Mining in {x}")),
}
NAMED = re.compile(r"(?:Geography|History|Culture|Economy) of (.+)$")


def main():
    with open(build_themes.OUT, encoding="utf-8") as fh:
        themes = json.load(fh)["themes"]
    name, own = {}, {}
    for topic, doors in themes.items():
        own[topic] = {door["title"] for door in doors}
        for door in doors:
            found = NAMED.match(door["title"])
            if found:
                name[topic] = found.group(1)
                own[topic].add(re.sub(r"^the ", "", found.group(1)))
                break
    asked = {}       # title -> (topic, theme key, sub-theme key)
    for topic, x in sorted(name.items()):
        for under, subs in SUBS.items():
            for key, pattern in subs:
                asked[pattern.format(x=x)] = (topic, under, key)
    titles = sorted(asked)
    print(f"{len(name)} topics, {len(titles)} titles to ask for")

    pages, landed = {}, {}       # asked title -> its page; final title -> the asked titles that reach it
    for n, part in enumerate(build_visuals.chunks(titles, 20)):
        payload = build_visuals.call(build_visuals.WIKIPEDIA, {
            "action": "query", "format": "json", "titles": "|".join(part), "redirects": 1,
            "prop": "extracts|pageimages|info", "exintro": 1, "explaintext": 1, "exlimit": 20,
            "piprop": "name", "pilicense": "free", "pilimit": 20, "inprop": "url"}, pause=2)
        query = payload.get("query", {})
        tidy = {hop["from"]: hop["to"] for hop in query.get("normalized", [])}
        forward = {hop["from"]: hop for hop in query.get("redirects", [])}
        by_title = {page["title"]: page for page in query.get("pages", {}).values()}
        for title in part:
            at = tidy.get(title, title)
            hop = forward.get(at)
            if hop and hop.get("tofragment"):
                continue                 # a part of another page
            page = by_title.get(hop["to"] if hop else at)
            if not page or "missing" in page or "invalid" in page:
                continue
            pages[title] = dict(page, forwarded=bool(hop))
            landed.setdefault(page["title"], []).append(title)
        if n % 25 == 24:
            print(f"  {min(len(titles), (n + 1) * 20)} of {len(titles)} asked, {len(pages)} found", flush=True)

    kept, lead = [], {}
    for title, page in sorted(pages.items()):
        topic, under, key = asked[title]
        final = page["title"]
        if final in own[topic] or (page["forwarded"] and len(landed[final]) > 1):
            continue
        text = build_themes.opening(page.get("extract"))
        if not text or not page.get("canonicalurl"):
            continue
        picture = page.get("pageimage", "").replace("_", " ")
        if build_themes.PHOTO.search(picture) and not build_themes.DRAWN.search(picture):
            lead[title] = picture
        kept.append((topic, {"under": under, "key": key, "title": final, "text": text,
                             "source": page["canonicalurl"]}, title))
    credits = build_visuals.commons(sorted(set(lead.values())))

    order = {(under, key): n for n, (under, key) in enumerate(
        (under, key) for under, subs in SUBS.items() for key, _ in subs)}
    subthemes, count = {}, {}
    for topic, door, title in kept:
        picture = credits.get(lead.get(title, ""))
        if picture:
            door["picture"] = picture
        subthemes.setdefault(topic, []).append(door)
        count[door["key"]] = count.get(door["key"], 0) + 1
    for doors in subthemes.values():
        doors.sort(key=lambda door: order[(door["under"], door["key"])])
    for under, subs in SUBS.items():
        print(f"{under}:", ", ".join(f"{key} {count.get(key, 0)}" for key, _ in subs))
    note = ("Built by scripts/build_subthemes.py: pages found by title on English Wikipedia, opening words from "
            "English Wikipedia (CC BY-SA 4.0), pictures from Wikimedia Commons, each with its own credit. "
            "Do not edit by hand.")
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"note": note, "subthemes": subthemes}, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"wrote {os.path.relpath(OUT, REPO)}: {sum(count.values())} doors on {len(subthemes)} topics")


if __name__ == "__main__":
    main()
