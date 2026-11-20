#!/usr/bin/env python3
"""Theme and sub-theme doors in another language's own Wikipedia (`data/i18n/wiki-<code>.json`).

Owner, 2026-11-17: Simplified Chinese and Polish. A door's words are never machine-translated: where that
language's Wikipedia has its own page about the same thing, the door shows that page's opening words and links
to it; where it has none, the viewer keeps the English words and tags them "English".

    theme doors      the page's Wikidata item (data/themes.json `item`) → its zhwiki / plwiki sitelink
    sub-theme doors  the English page (data/subthemes.json `source`) → its zh / pl language link
    words            the page's opening, whole sentences up to LONGEST letters (Chinese: converted to
                     Simplified with the wiki's own variant conversion, zh-cn)

    python3 scripts/build_lang_wiki.py zh
    python3 scripts/build_lang_wiki.py pl

Standard library only. About a hundred paced requests per language to Wikidata and Wikipedia; a few minutes.
Pictures stay the English door's (a picture needs no language).
"""
import argparse
import json
import os
import re
import sys
import urllib.parse

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_visuals  # noqa: E402

DATA = os.path.join(REPO, "data")
OUT = os.path.join(DATA, "i18n", "wiki-{code}.json")
SITE = {"zh": "https://zh.wikipedia.org", "pl": "https://pl.wikipedia.org"}
VARIANT = {"zh": "zh-cn", "pl": None}
# Chinese says in about 120 characters what English says in 300 letters.
LONGEST = {"zh": 120, "pl": 300}
ENDS = {
    "zh": re.compile(r"(?<=[。！？])"),
    "pl": re.compile(r"(?<=[.!?])\s+(?=[A-ZĄĆĘŁŃÓŚŹŻ\"„“])"),
}


def opening(text, code):
    """The first sentences of a page, whole, within LONGEST letters (as scripts/build_themes.py does)."""
    text = " ".join((text or "").split())
    text = re.sub(r"\s*[（(][^（）()]*[）)]", "", text)     # sounds, other names and dates in brackets
    text = re.sub(r"\s+([,.;:，。；：])", r"\1", text)
    longest, kept = LONGEST[code], ""
    for sentence in ENDS[code].split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        if kept and len(kept) + len(sentence) + 1 > longest:
            break
        kept = f"{kept}{'' if code == 'zh' else ' '}{sentence}".strip()
    return kept if len(kept) <= longest + longest // 2 else ""


def sitelinks(items, code):
    """{Wikidata item: page title on that language's Wikipedia}."""
    titles = {}
    for part in build_visuals.chunks(sorted(items), 50):
        payload = build_visuals.call(build_visuals.WIKIDATA, {
            "action": "wbgetentities", "format": "json", "ids": "|".join(part), "props": "sitelinks",
            "sitefilter": f"{code}wiki"}, post=True, pause=1)
        for item, entity in payload.get("entities", {}).items():
            link = entity.get("sitelinks", {}).get(f"{code}wiki")
            if link:
                titles[item] = link["title"]
    return titles


def langlinks(english, code):
    """{English page title: page title on that language's Wikipedia}."""
    titles = {}
    for part in build_visuals.chunks(sorted(english), 50):
        payload = build_visuals.call(build_visuals.WIKIPEDIA, {
            "action": "query", "format": "json", "titles": "|".join(part), "redirects": 1,
            "prop": "langlinks", "lllang": code, "lllimit": "max"}, post=True, pause=1)
        query = payload.get("query", {})
        back = {hop["to"]: hop["from"] for hop in query.get("normalized", []) + query.get("redirects", [])}
        for page in query.get("pages", {}).values():
            asked = back.get(page["title"], page["title"])
            asked = back.get(asked, asked)
            for link in page.get("langlinks", []):
                titles[asked] = link["*"]
    return titles


def pages(titles, code):
    """{title: {"title", "text", "source"}} from that language's Wikipedia; pages with no opening left out."""
    site, variant, found = SITE[code], VARIANT[code], {}
    for part in build_visuals.chunks(sorted(set(titles)), 20):
        params = {"action": "query", "format": "json", "titles": "|".join(part), "redirects": 1,
                  "prop": "extracts|info", "exintro": 1, "explaintext": 1, "exlimit": 20,
                  "inprop": "url|varianttitles"}
        if variant:
            params["variant"] = variant
        payload = build_visuals.call(f"{site}/w/api.php", params, post=True, pause=1)
        query = payload.get("query", {})
        back = {hop["to"]: hop["from"] for hop in query.get("normalized", []) + query.get("redirects", [])}
        for page in query.get("pages", {}).values():
            asked = back.get(page["title"], page["title"])
            asked = back.get(asked, asked)
            text = opening(page.get("extract"), code)
            url = page.get("canonicalurl", "")
            if not text or not url:
                continue
            title = page["title"]
            if variant:
                title = page.get("varianttitles", {}).get(variant) or title
                url = url.replace("/wiki/", f"/{variant}/", 1)   # the reader sees the page in Simplified too
            found[asked] = {"title": title, "text": text, "source": url}
    return found


def english_title(source):
    return urllib.parse.unquote(source.rsplit("/wiki/", 1)[1]).replace("_", " ")


def own_page(topic, page, names):
    """True when the door's page is the topic's own page (a theme page that redirects to the country, as pl
    "Gospodarka Portugalii" → "Portugalia"): the door would open on the whole country, so it keeps English."""
    own = names.get(topic)
    return bool(own) and re.sub(r"\s*\(.*\)$", "", page.get("title", "")).strip() == own


def prune(code, out_themes, out_subs):
    """Drop doors that landed on the topic's own page; returns how many."""
    with open(os.path.join(DATA, "i18n", f"wikidata-{code}.json"), encoding="utf-8") as fh:
        names = json.load(fh).get("names", {})
    dropped = 0
    for out in (out_themes, out_subs):
        for topic in list(out):
            for key in [k for k, page in out[topic].items() if own_page(topic, page, names)]:
                del out[topic][key]
                dropped += 1
            if not out[topic]:
                del out[topic]
    return dropped


def write(code, out_themes, out_subs):
    note = (f"Built by scripts/build_lang_wiki.py {code}: the same pages in {code} Wikipedia (CC BY-SA 4.0), "
            "found by Wikidata sitelinks and English language links. Do not edit by hand.")
    path = OUT.format(code=code)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"note": note, "themes": out_themes, "subs": out_subs}, fh, ensure_ascii=False, indent=1,
                  sort_keys=True)
        fh.write("\n")
    print(f"wrote {os.path.relpath(path, REPO)}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("code", choices=sorted(SITE))
    parser.add_argument("--prune", action="store_true",
                        help="only re-apply the own-page rule to the file already built (no Wikipedia calls)")
    args = parser.parse_args()
    code = args.code
    if args.prune:
        with open(OUT.format(code=code), encoding="utf-8") as fh:
            built = json.load(fh)
        print(f"{code}: dropped {prune(code, built['themes'], built['subs'])} doors on the topic's own page",
              file=sys.stderr)
        return write(code, built["themes"], built["subs"])
    with open(os.path.join(DATA, "themes.json"), encoding="utf-8") as fh:
        themes = json.load(fh)["themes"]
    with open(os.path.join(DATA, "subthemes.json"), encoding="utf-8") as fh:
        subthemes = json.load(fh)["subthemes"]

    titled = sitelinks({door["item"] for doors in themes.values() for door in doors if door.get("item")}, code)
    print(f"theme doors: {len(titled)} pages on {code} Wikipedia", file=sys.stderr)
    english = {english_title(door["source"]) for doors in subthemes.values() for door in doors}
    linked = langlinks(english, code)
    print(f"sub-theme doors: {len(linked)} of {len(english)} pages on {code} Wikipedia", file=sys.stderr)
    read = pages(list(titled.values()) + list(linked.values()), code)

    out_themes, out_subs = {}, {}
    for topic, doors in themes.items():
        for door in doors:
            page = read.get(titled.get(door.get("item"), ""))
            if page:
                out_themes.setdefault(topic, {})[door["key"]] = page
    for topic, doors in subthemes.items():
        for door in doors:
            page = read.get(linked.get(english_title(door["source"]), ""))
            if page:
                out_subs.setdefault(topic, {})[f"{door['under']}/{door['key']}"] = page
    print(f"{code}: dropped {prune(code, out_themes, out_subs)} doors on the topic's own page", file=sys.stderr)
    count = (sum(len(one) for one in out_themes.values()), sum(len(one) for one in out_subs.values()))
    print(f"{code}: {count[0]} of {sum(len(d) for d in themes.values())} theme doors, "
          f"{count[1]} of {sum(len(d) for d in subthemes.values())} sub-theme doors", file=sys.stderr)
    write(code, out_themes, out_subs)


if __name__ == "__main__":
    main()
