#!/usr/bin/env python3
"""Draft translations of the app's own English words (`data/i18n/words-<code>.json`).

Owner, 2026-11-17: Simplified Chinese and Polish. What Wikidata or another language's Wikipedia already holds
comes from there (build_lang_wikidata.py, build_lang_wiki.py). This script covers the rest, the words written
for this app:

    ui        the viewer's menu, buttons and sentences: every t("...") in explore.html, plus the static
              markup's aria-label / title / placeholder values and data-t texts
    question  the question sentences of each link kind
    line      a topic's one-line description on its card
    more      a territory's "Belongs to ..." line
    dyk       a topic's "Did you know" sentence
    why       the reason sentence on a link (why this answer answers that question)
    name      a topic's name, only where Wikidata holds no label in that language (the kind topics such as
              "Country", a few peoples and people); Wikidata's label always wins once it has one

They are drafted by Claude (`claude -p`, no tools) and shown tagged as AI-translated until a native reader
checks them (Owner reads the Chinese; Polish stays as drafted until users ask for changes). The file is keyed
by the English words, so an English sentence that changes simply has no translation until this runs again
(the viewer then shows the English, tagged). Already translated words are never sent again; delete an entry
to have it redrafted.

    python3 scripts/translate_lang.py zh            # drafts what is missing, saves after each batch
    python3 scripts/translate_lang.py pl --dry-run  # counts what is missing

    python3 scripts/translate_lang.py zh --review OUT.json   # proposes official-usage fixes to held words

--review (Owner, 2026-11-17: "refer to native Chinese official sources ... instead of direct translation")
sends the words already held, asks which read as a literal translation where official usage has its own term,
and writes the proposed fixes to OUT.json for a person to check; nothing in words-<code>.json changes. Glossary
words are not sent (they are fixed).

Needs the Claude Code CLI signed in on this machine. Not part of any running service.
"""
import argparse
import json
import os
import re
import subprocess  # nosec B404 - runs the local claude CLI with a fixed argument list
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from app import geography, graph  # noqa: E402

DATA = os.path.join(REPO, "data", "i18n")
VIEWER = os.path.join(REPO, "app", "static", "explore.html")
EARTH = os.environ.get("KG_EARTH_DIR") or os.path.join(os.path.dirname(REPO), "earth-data", "derived")
MODEL = os.environ.get("KG_TRANSLATE_MODEL", "claude-opus-5-5")
BATCH = 80

LANGUAGE = {
    "zh": """Simplified Chinese as used in mainland China (简体中文). Use the place and people names Chinese
Wikipedia uses, and countries by their short names as on the Ministry of Foreign Affairs country list (中国, 美国,
韩国, 朝鲜, 台湾), never the formal state name. Never translate word for word: wherever official Chinese sources
have an established term (外交部 国家和组织 country profiles, 国家统计局, the UN's Chinese documents, school
geography textbooks), use that term (e.g. a country's head count is 人口, its size 国土面积, its kind of
government 政体, a dependent territory 属地).
Chinese punctuation (，。、：；“”) inside Chinese text. No spaces between Chinese words; keep a
space-free style around numbers ({n}个, {year}年). Write ° and km² as in the English.""",
    "pl": """Polish. Use the Polish names (exonyms) Polish Wikipedia uses for places and people. Use the
informal "ty" form for the reader where the English speaks to the reader. Polish quotation marks „…”.""",
}
GLOSSARY = {
    "zh": {"Knowledge Globe": "知识地球", "Explore": "探索", "Learn": "学习", "topic": "话题",
           "my topic": "我的话题", "theme": "主题", "time machine": "时光机", "Now": "现在",
           "Compare": "比较", "card": "卡片", "question": "问题", "answer": "答案", "Overview": "概览",
           "Nothing yet": "暂无",
           # Owner's corrections, 2026-11-17 (official usage, not literal): fixed.
           "People": "人口", "Size": "国土面积", "Started": "建国年份", "Years people live": "人均寿命",
           "Living well score (HDI)": "人类发展指数（HDI）", "Kind of government": "政体", "Territory": "属地",
           "Made in a year (GDP)": "国内生产总值（GDP）", "GDP for each person": "人均国内生产总值",
           "Languages|official": "官方语言"},
    "pl": {"Knowledge Globe": "Globus Wiedzy", "Explore": "Odkrywaj", "Learn": "Poznawaj", "topic": "temat",
           "my topic": "mój temat", "theme": "dziedzina", "time machine": "wehikuł czasu", "Now": "Teraz",
           "Compare": "Porównaj", "card": "karta", "question": "pytanie", "answer": "odpowiedź",
           "Overview": "Przegląd", "Nothing yet": "Na razie nic"},
}
GUIDE = """You translate the words of Knowledge Globe, a calm 3D globe app for children (about 8 to 12) and
their parents. Translate each English item into {language}

Rules:
- Plain, short, friendly words a child can read; keep the meaning exact. Never add facts, never drop facts.
- Keep every placeholder in curly braces exactly as written ({{name}}, {{n}}, {{year}} ...), untranslated, and
  move it where the grammar needs it.
- Keep symbols as they are: ↗ · … × ° km² and leading/trailing spaces or punctuation.
- A UI item is a button, label or menu word: keep it as short as the English (space on a phone is tight).
- Where an item has {{n}} counting something and the language has plural forms, give an object of the forms
  instead of a string: Polish {{"one": "...", "few": "...", "many": "...", "other": "..."}}. Chinese never needs
  this.
- Use these fixed words for the app's own terms: {glossary}
- Reply with ONE JSON object only, no prose, no code fence: each item's id as key, its translation as value."""


def ui_strings():
    text = open(VIEWER, encoding="utf-8").read()
    head, _, script = text.partition('<script type="module">')
    found = set()
    for match in re.finditer(r'\bt\("((?:[^"\\]|\\.)*)"', script):
        found.add(json.loads(f'"{match.group(1)}"'))
    body = head.partition("<body")[2]
    for match in re.finditer(r'\b(?:aria-label|title|placeholder)="([^"$]+)"', body):
        found.add(match.group(1))
    for match in re.finditer(r'data-t>([^<]+)<', body):
        found.add(match.group(1).strip())
    return {s for s in found if re.search(r"[A-Za-z]{2}", s)}


def sources(code):
    """Every English string to translate, with a short note on where it is shown."""
    built = graph.build(geography.load(EARTH))
    labelled = os.path.join(DATA, f"wikidata-{code}.json")
    wikidata = json.load(open(labelled, encoding="utf-8")).get("names", {}) if os.path.exists(labelled) else {}
    names = {point["id"]: point["name"] for point in built["points"]}
    items = {}

    def add(english, note):
        if english and english.strip() and english not in items:
            items[english] = note
    for english in sorted(ui_strings()):
        # "Languages|official": the English is the part before "|", the rest says which sense is meant
        add(english, "ui" if "|" not in english else f"ui, in the sense: {english.split('|')[1]}")
    for kind, words in built["kinds"].items():
        add(words["out"], f"question asked about a topic (link kind '{kind}')")
        add(words["back"], f"question asked about a topic (link kind '{kind}', other way)")
    for point in built["points"]:
        add(point.get("line"), f"one-line description on the card of '{point['name']}'")
        add(point.get("more"), f"line on the card of '{point['name']}'")
        add(point.get("did_you_know"), f"'Did you know' sentence on the card of '{point['name']}'")
    for point in built["points"]:
        if point["id"] in wikidata:
            continue
        if point["id"].startswith("kind-"):
            add(point["name"], "name of a kind of place, shown on every card as its kind (\"Kind: Country\"): "
                               "the usual short noun, as a heading word")
        else:
            add(point["name"], f"name of a topic on the globe (the name Wikipedia uses, if it has one): "
                               f"{point.get('line') or ''}")
    for link in built["links"]:
        add(link.get("why"), f"why '{names.get(link['to'], link['to'])}' answers the question "
                             f"'{built['kinds'][link['kind']]['out']}' about '{names.get(link['from'], link['from'])}'")
    return items


def ask(code, batch):
    numbered = {f"s{i}": english for i, (english, _) in enumerate(batch)}
    listing = "\n".join(json.dumps({"id": key, "en": english, "where": note}, ensure_ascii=False)
                        for key, (english, note) in zip(numbered, batch))
    system = GUIDE.format(language=LANGUAGE[code], glossary=json.dumps(GLOSSARY[code], ensure_ascii=False))
    run = subprocess.run(  # nosec B603 B607 - fixed argument list, no shell
        ["claude", "-p", "--model", MODEL, "--tools", "", "--no-session-persistence", "--system-prompt", system],
        input=f"Items to translate, one JSON per line:\n{listing}", capture_output=True, text=True, timeout=900)
    reply = run.stdout.strip()
    reply = reply[reply.find("{"):reply.rfind("}") + 1]
    got = json.loads(reply)
    return {numbered[key]: value for key, value in got.items() if key in numbered and value}


REVIEW = """You check {language}

Each item is an English UI string from a children's globe app with its current translation. Find translations
that read as a word-for-word rendering where native official sources say it another way, or that are wrong,
unnatural, or inconsistent with the rules. Keep placeholders in curly braces exactly; keep it short and plain.
Reply with ONE JSON object only, no prose, no code fence: only the items that need a change, each id as key and
{{"zh": "the corrected text", "why": "a few words: the official term or the problem"}} as value. {{}} if none."""


def review(code, held, out):
    fixed = set(GLOSSARY[code])
    pairs = [(english, said) for english, said in sorted(held.items())
             if english not in fixed and isinstance(said, str)]
    system = REVIEW.format(language=LANGUAGE[code])
    found = {}
    for start in range(0, len(pairs), BATCH):
        part = pairs[start:start + BATCH]
        numbered = {f"s{i}": pair for i, pair in enumerate(part)}
        listing = "\n".join(json.dumps({"id": key, "en": en, "now": now}, ensure_ascii=False)
                            for key, (en, now) in numbered.items())
        run = subprocess.run(  # nosec B603 B607 - fixed argument list, no shell
            ["claude", "-p", "--model", MODEL, "--tools", "", "--no-session-persistence", "--system-prompt", system],
            input=f"Items, one JSON per line:\n{listing}", capture_output=True, text=True, timeout=900)
        reply = run.stdout.strip()
        try:
            got = json.loads(reply[reply.find("{"):reply.rfind("}") + 1])
        except ValueError as error:
            print(f"  batch {start}: failed ({error})", file=sys.stderr)
            continue
        for key, value in got.items():
            if key in numbered and isinstance(value, dict) and value.get(code):
                english, now = numbered[key]
                if placeholders(value[code]) == placeholders(english) and value[code] != now:
                    found[english] = {"now": now, code: value[code], "why": value.get("why", "")}
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(found, fh, ensure_ascii=False, indent=1)
        print(f"  {min(start + BATCH, len(pairs))} of {len(pairs)} checked, {len(found)} proposed", file=sys.stderr)


def placeholders(text):
    return sorted(re.findall(r"\{\w+\}", text))


def save(path, held):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"note": "Drafted by Claude with scripts/translate_lang.py, keyed by the English words. "
                           "AI-translated: shown tagged until a native reader checks it. Hand corrections "
                           "are welcome here; they are kept while the English stays the same.",
                   "words": dict(sorted(held.items()))}, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("code", choices=sorted(LANGUAGE))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", help="only this kind of source: ui, question, line, why ...")
    parser.add_argument("--review", metavar="OUT", help="propose official-usage fixes to held words into OUT")
    args = parser.parse_args()
    path = os.path.join(DATA, f"words-{args.code}.json")
    held = json.load(open(path, encoding="utf-8"))["words"] if os.path.exists(path) else {}
    if args.review:
        review(args.code, held, args.review)
        return
    items = sources(args.code)
    stale = [english for english in held if english not in items]
    held = {english: said for english, said in held.items() if english in items}   # words no longer used go
    missing = [(english, note) for english, note in items.items() if english not in held
               and (not args.only or note.startswith(args.only))]
    print(f"{args.code}: {len(items)} English strings, {len(held)} held, {len(missing)} to draft, "
          f"{len(stale)} no longer used", file=sys.stderr)
    if args.dry_run:
        return
    os.makedirs(DATA, exist_ok=True)
    if stale and not missing:
        save(path, held)
    for start in range(0, len(missing), BATCH):
        batch = missing[start:start + BATCH]
        try:
            got = ask(args.code, batch)
        except (ValueError, subprocess.SubprocessError) as error:
            print(f"  batch {start}: failed ({error}); left for the next run", file=sys.stderr)
            continue
        for english, value in got.items():
            forms = value.values() if isinstance(value, dict) else [value]
            if all(placeholders(form) == placeholders(english) for form in forms):
                held[english] = value
            else:
                print(f"  dropped (placeholders differ): {english!r} -> {value!r}", file=sys.stderr)
        save(path, held)
        print(f"  {min(start + BATCH, len(missing))} of {len(missing)} done", file=sys.stderr)


if __name__ == "__main__":
    main()
