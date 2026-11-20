#!/usr/bin/env python3
"""Names and fact words in other languages, from Wikidata (`data/i18n/wikidata-<code>.json`).

Owner, 2026-11-17: the app speaks English, Simplified Chinese and Polish. This script fetches the parts
Wikidata already holds (CC0), so nothing here is translated by a model:

    names   every topic whose item is pinned in visuals.json: its label in that language
    words   the word facts on a topic (languages, money, kind of government, head of state, highest
            point's name): each English word in the fact is matched to the value item it came from, by the
            item's English label, and that item's label in the language replaces it. A word with no match or
            no label stays English (the viewer tags it).

Chinese asks for zh-hans first, then zh-cn, then zh, and every Chinese label is then put into Simplified by
Chinese Wikipedia's own zh-cn conversion (plain zh is often Traditional; Owner checks the Chinese). A few states'
formal names then give way to their short names (ZH_SHORT: 台湾, 韩国, 朝鲜, 中国).

    python3 scripts/build_lang_wikidata.py           # both languages
    python3 scripts/build_lang_wikidata.py zh

Standard library only. About 30 requests to the Wikidata API, paced.
"""
import html
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_visuals  # noqa: E402

DATA = os.path.join(REPO, "data")
OUT_DIR = os.path.join(DATA, "i18n")
# Each language's label, best first. A topic's name falls back to English (in the viewer) when none is held.
# Polish also takes Wikidata's "mul" label (one spelling for every Latin-script language: Oslo, Jersey, Baguio);
# Chinese does not, since mul is written in Latin letters.
ASK = {"zh": ("zh-hans", "zh-cn", "zh"), "pl": ("pl", "mul")}
# Chinese short names, Owner 2026-11-17: "中华民国 should be 台湾，大韩民国 should be 韩国 … use the official Chinese
# names". Wikidata's zh-hans label is a state's formal name; China's own usage on maps and lists is the short name.
# Applied to the whole label after the Simplified conversion, for names and fact words alike; Wikidata wins
# everywhere else. Kept as Wikidata gives them, being the names on China's foreign-ministry country list already:
# 中非共和国, 刚果民主共和国, 刚果共和国, 密克罗尼西亚联邦, 阿拉伯联合酋长国.
ZH_SHORT = {
    "中华民国": "台湾",
    "大韩民国": "韩国",
    "朝鲜民主主义人民共和国": "朝鲜",
    "中华人民共和国": "中国",
    "北塞浦路斯土耳其共和国": "北塞浦路斯",   # Larry's pick, same rule
    "中华民国国语": "台湾华语",              # Taiwan's language (Standard Taiwanese Mandarin); zh Wikipedia's title
}
# Which property each word fact was read from (build_facts.py, build_compare.py).
WORD_FACTS = {"languages": "P37", "money": "P38", "government": "P122", "head": "P35", "highest": "P610"}


def entities(ids, props, languages):
    found = {}
    for part in build_visuals.chunks(sorted(set(ids)), 50):
        payload = build_visuals.call(build_visuals.WIKIDATA, {
            "action": "wbgetentities", "ids": "|".join(part), "props": props,
            "languages": "|".join(languages), "format": "json"}, pause=0.5)
        found.update(payload.get("entities", {}))
    return found


def label(entity, order):
    labels = entity.get("labels", {})
    for code in order:
        said = labels.get(code, {}).get("value")
        if said and (code != "mul" or re.search("[A-Za-z]", said)):   # a mul label is only used in Latin letters
            return said
    return None


def simplified(texts):
    """{text: the same in Simplified Chinese}, by Chinese Wikipedia's own variant conversion (zh-cn).

    Plain `zh` labels are often Traditional (北極點 → 北极点), and even zh-hans labels can carry a stray
    Traditional character (维林吉利島), so every Chinese label goes through it; Simplified text comes back the same."""
    out = {}
    for part in build_visuals.chunks(sorted(set(texts)), 50):
        payload = build_visuals.call("https://zh.wikipedia.org/w/api.php", {
            "action": "parse", "format": "json", "contentmodel": "wikitext", "prop": "text",
            "disablelimitreport": 1, "variant": "zh-cn", "text": "\n".join(f"* {text}" for text in part)},
            post=True, pause=1)
        said = re.findall(r"<li>(.*?)</li>", payload.get("parse", {}).get("text", {}).get("*", ""), re.S)
        if len(said) == len(part):
            out.update({text: html.unescape(one.strip()) for text, one in zip(part, said)})
    return out


def main(codes):
    visuals = json.load(open(os.path.join(DATA, "visuals.json"), encoding="utf-8"))["visuals"]
    items = {topic: entry["item"] for topic, entry in visuals.items() if entry.get("item")}
    every = sorted({code for code in codes for code in ASK[code]} | {"en"})
    print(f"{len(items)} topics with an item", file=sys.stderr)
    topic_entities = entities(items.values(), "labels|claims", every)

    # Word facts: the topic's facts (facts.json + compare.json), their item from the source link.
    facts = {}
    for name in ("facts.json", "compare.json"):
        payload = json.load(open(os.path.join(DATA, name), encoding="utf-8"))
        for topic, rows in (payload.get("facts") or payload.get("compare") or {}).items():
            for fact in rows:
                if fact["key"] in WORD_FACTS:
                    facts.setdefault(topic, {})[fact["key"]] = fact
    wanted = set()
    for topic, rows in facts.items():
        for key, fact in rows.items():
            item = re.search(r"wiki/(Q\d+)", fact.get("source", ""))
            claims = topic_entities.get(item.group(1), {}).get("claims", {}) if item else {}
            for claim in claims.get(WORD_FACTS[key], []):
                value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
                if isinstance(value, dict) and value.get("id"):
                    wanted.add(value["id"])
    print(f"{len(wanted)} value items to name", file=sys.stderr)
    value_entities = entities(wanted, "labels", every)
    chinese = set()
    if "zh" in codes:
        for entity in list(topic_entities.values()) + list(value_entities.values()):
            said = label(entity, ASK["zh"])
            if said:
                chinese.add(said)
    converted = simplified(chinese) if chinese else {}
    print(f"zh: {len(converted)} of {len(chinese)} labels checked, {sum(a != b for a, b in converted.items())} "
          "changed to Simplified", file=sys.stderr)

    for code in codes:
        order = ASK[code]

        def named(entity, order=order, code=code):
            said = label(entity, order)
            if code != "zh" or not said:
                return said
            said = converted.get(said, said)
            return ZH_SHORT.get(said, said)
        names = {topic: named(topic_entities.get(item, {})) for topic, item in items.items()}
        names = {topic: name for topic, name in names.items() if name}
        words, missed = {}, 0
        for topic, rows in facts.items():
            item = None
            for key, fact in rows.items():
                item = re.search(r"wiki/(Q\d+)", fact.get("source", ""))
                claims = topic_entities.get(item.group(1), {}).get("claims", {}) if item else {}
                by_english = {}
                for claim in claims.get(WORD_FACTS[key], []):
                    value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
                    entity = value_entities.get(value.get("id", "")) if isinstance(value, dict) else None
                    if entity:
                        english = label(entity, ("en", "mul"))
                        if english:
                            by_english[english.lower()] = named(entity)
                english_words = [fact["name"]] if key == "highest" else fact.get("value") or []
                said = []
                for word in english_words:
                    local = by_english.get(str(word).lower())
                    if not local:
                        missed += 1
                    said.append(local or None)
                if any(said):
                    words.setdefault(topic, {})[key] = said
        os.makedirs(OUT_DIR, exist_ok=True)
        out = os.path.join(OUT_DIR, f"wikidata-{code}.json")
        with open(out, "w", encoding="utf-8") as fh:
            json.dump({
                "note": "Built by scripts/build_lang_wikidata.py from Wikidata labels (CC0). Do not edit by hand. "
                        "words: one entry per English word of the fact, null = no label in this language.",
                "names": dict(sorted(names.items())),
                "words": dict(sorted(words.items())),
            }, fh, ensure_ascii=False, indent=1, sort_keys=False)
            fh.write("\n")
        print(f"{code}: {len(names)} of {len(items)} names; word facts on {len(words)} topics, "
              f"{missed} words with no label", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:] or sorted(ASK))
