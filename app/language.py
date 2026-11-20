"""The app's words in another language (Owner, 2026-11-17: Simplified Chinese and Polish).

One file per language for the viewer, merged from what the build scripts pinned in `data/i18n/`:

    words-<code>.json     this app's own English words → drafts (scripts/translate_lang.py, AI-translated)
    wikidata-<code>.json  topic names and word facts from Wikidata labels (scripts/build_lang_wikidata.py)
    wiki-<code>.json      theme doors and sub-themes from that language's Wikipedia (optional)

Anything missing stays English in the viewer and is tagged as English. English itself needs no file.
"""
import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "i18n")
CODES = ("zh", "pl")


class LanguageError(ValueError):
    pass


def _read(name):
    path = os.path.join(DATA_DIR, name)
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _first_up(text):
    return text[:1].upper() + text[1:] if isinstance(text, str) else text


def build(code):
    """Return {"code", "words", "names", "facts", "themes", "subs"} for one language."""
    if code not in CODES:
        raise LanguageError(f"unknown language: {code}")
    wikidata = _read(f"wikidata-{code}.json")
    wiki = _read(f"wiki-{code}.json")
    # Polish Wikidata labels start small (biegun północny, język japoński); a name or a fact starts big here.
    names = {topic: _first_up(name) for topic, name in wikidata.get("names", {}).items()}
    facts = {topic: {key: [_first_up(word) if word else None for word in said] for key, said in keys.items()}
             for topic, keys in wikidata.get("words", {}).items()}
    return {
        "code": code,
        "words": _read(f"words-{code}.json").get("words", {}),
        "names": names,
        "facts": facts,
        "themes": wiki.get("themes", {}),
        "subs": wiki.get("subs", {}),
    }


def stamp():
    """Something that changes when any language file changes (for the server's cache)."""
    try:
        return tuple(sorted((name, os.stat(os.path.join(DATA_DIR, name)).st_mtime_ns)
                            for name in os.listdir(DATA_DIR)))
    except FileNotFoundError:
        return ()
