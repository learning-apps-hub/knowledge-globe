#!/usr/bin/env python3
"""Start Knowledge Globe on a scratch port and verify the released Explore app."""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request


PORT = int(os.environ.get("PORT", 8110))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASSED = []
FAILED = []


def check(label, ok, detail=""):
    target = PASSED if ok else FAILED
    target.append(label)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{'' if ok or not detail else ' — ' + detail}")


def get(path):
    try:
        response = urllib.request.urlopen(f"http://localhost:{PORT}{path}", timeout=5)
        return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, str(error).encode()
    except Exception as error:
        return None, str(error).encode()


def wait_for_server(timeout=15):
    for _ in range(timeout * 2):
        if get("/")[0] == 200:
            return True
        time.sleep(.5)
    return False


process = None
try:
    print(f"Smoke test — Knowledge Globe (port {PORT})")
    try:
        urllib.request.urlopen(f"http://localhost:{PORT}/", timeout=1)
        check(f"Port {PORT} is free", False, "another process is listening")
        sys.exit(1)
    except Exception:
        pass

    process = subprocess.Popen(
        ["python3", "run.py"], cwd=ROOT,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    check("Server process starts", process.poll() is None)
    ready = wait_for_server()
    check(f"Server ready on port {PORT}", ready)

    if ready:
        print("\n--- Viewer and assets ---")
        status, viewer = get("/")
        check("GET / → 200", status == 200, f"got {status}")
        check("GET / serves Explore", b"Knowledge Globe \xe2\x80\x94 Explore" in viewer and b"api/graph" in viewer)
        status, alias = get("/explore")
        check("GET /explore remains an alias", status == 200 and alias == viewer, f"got {status}")

        for path, marker in (
            ("/static/vendor/three.module.min.js", b"WebGLRenderer"),
            ("/static/vendor/three.core.min.js", b"REVISION"),
            ("/static/sky.js", b"sunDir"),
        ):
            status, body = get(path)
            check(f"GET {path} → 200", status == 200 and marker in body, f"got {status}")

        print("\n--- One graph ---")
        status, body = get("/api/graph")
        check("GET /api/graph → 200", status == 200, f"got {status}")
        graph = json.loads(body) if status == 200 else {"points": [], "links": [], "kinds": {}, "starts": []}
        ids = {point["id"] for point in graph["points"]}
        check("graph has at least 500 topics", len(ids) >= 500, str(len(ids)))
        check("graph has at least 2,000 links", len(graph["links"]) >= 2000, str(len(graph["links"])))
        check("every link joins known topics with a known kind", all(
            link["from"] in ids and link["to"] in ids and link["kind"] in graph["kinds"]
            for link in graph["links"]
        ))
        check("every starting topic exists", all(point_id in ids for point_id in graph["starts"]))
        check("every link kind asks a question from both ends", all(
            kind.get("out") and kind.get("back") for kind in graph["kinds"].values()
        ))
        check("the old dummy subjects are gone", not ({"water", "singapore-oceanarium"} & ids))
        check("core geography is present", {
            "north-pole", "south-pole", "equator", "prime-meridian", "date-line",
            "asia", "pacific-ocean", "northern-hemisphere", "japan", "tokyo",
        } <= ids)
        pinned = [point["visual"] for point in graph["points"] if isinstance(point.get("visual"), dict)]
        check("pinned pictures carry Commons page, credit and licence", all(
            visual.get("page", "").startswith("https://commons.wikimedia.org/wiki/File:")
            and visual.get("credit") and visual.get("licence") for visual in pinned
        ))

        facts = [fact for point in graph["points"] for fact in point.get("facts", [])]
        check("at least 1,000 facts on topics", len(facts) >= 1000, str(len(facts)))
        check("every fact has a key, words to read and a Wikidata source", all(
            fact.get("key") and fact.get("text")
            and fact.get("source", "").startswith(("https://www.wikidata.org/wiki/Q", "https://query.wikidata.org/#"))
            for fact in facts
        ))
        dated = [fact for fact in facts if fact.get("by_year")]
        check("at least 500 facts hold their values through the years", len(dated) >= 500, str(len(dated)))
        check("a fact through the years has a number for each year it names", all(
            year.isdigit() and isinstance(value, (int, float))
            for fact in dated for year, value in fact["by_year"].items()
        ))
        check("the facts theme doors compare are there (GDP, highest point, government)", all(
            sum(fact["key"] == key for fact in facts) >= 150 for key in ("gdp", "highest", "government", "began")
        ))
        check("every flag picture carries Commons page, credit and licence", all(
            fact.get("src") and fact.get("page", "").startswith("https://commons.wikimedia.org/wiki/File:")
            and fact.get("credit") and fact.get("licence") for fact in facts if fact["key"] == "flag"
        ))
        by_id = {point["id"]: point for point in graph["points"]}
        doors = [door for point in graph["points"] for door in point.get("themes", [])]
        check("at least 800 theme doors on topics", len(doors) >= 800, str(len(doors)))
        check("every theme door has words, a title and its Wikipedia page", all(
            door.get("key") in ("geography", "history", "culture", "economy") and door.get("title")
            and door.get("text") and door.get("source", "").startswith("https://en.wikipedia.org/wiki/")
            for door in doors
        ))
        check("every theme picture has a credit, a licence and its Commons page", all(
            door["picture"].get("src") and door["picture"].get("credit") and door["picture"].get("licence")
            and door["picture"].get("page", "").startswith("https://commons.wikimedia.org/wiki/File:")
            for door in doors if door.get("picture")
        ))
        subs = [(point, door) for point in graph["points"] for door in point.get("subs", [])]
        check("every sub-theme door names its theme, has words, a title and its Wikipedia page", all(
            door.get("under") in ("facts", "geography", "history", "culture", "economy") and door.get("key")
            and door.get("title") and door.get("text")
            and door.get("source", "").startswith("https://en.wikipedia.org/wiki/") for _, door in subs
        ), str(len(subs)))
        check("sub-theme doors sit only on topics with theme doors", all(point.get("themes") for point, _ in subs))
        check("theme doors sit only on countries and territories", all(
            point.get("status") for point in graph["points"] if point.get("themes")
        ))
        check("facts sit only on countries and territories", all(
            point.get("status") for point in graph["points"] if point.get("facts")
        ))
        check("held flags stay off (Owner decides each)", not any(
            fact["key"].startswith("flag") for held in ("afghanistan", "new-caledonia", "spratly-islands")
            for fact in by_id.get(held, {}).get("facts", [])
        ))

        print("\n--- Hardening (audit R11) ---")
        page = urllib.request.urlopen(f"http://localhost:{PORT}/", timeout=5)
        check("pages carry X-Content-Type-Options: nosniff", page.headers.get("X-Content-Type-Options") == "nosniff")
        check("the viewer declares a Content-Security-Policy",
              b'http-equiv="Content-Security-Policy"' in page.read())

        print("\n--- Removed content and traversal guards ---")
        for path in (
            "/api/subjects", "/api/subjects/water", "/api/subjects/singapore-oceanarium",
            "/api/subjects/..%2f..%2fetc%2fpasswd", "/static/../server.py", "/earth/../../run.py",
        ):
            status, _ = get(path)
            check(f"GET {path} → 404", status == 404, f"got {status}")

        print("\n--- Earth bundle ---")
        status, body = get("/earth/manifest.json")
        check("GET /earth/manifest.json → 200", status == 200, f"got {status}")
        manifest = json.loads(body) if status == 200 else {"files": {}, "layers": []}
        check("every Earth layer carries credit and licence", all(
            layer.get("credit") and layer.get("licence") for layer in manifest["layers"]
        ))
        for key in ("day4096", "pack4096", "stars", "moon", "areas", "geo"):
            status, asset = get(f"/earth/{manifest['files'].get(key, 'missing')}")
            check(f"Earth asset {key} is served", status == 200 and len(asset) > 1000, f"got {status}")

        # Other languages (Owner, 2026-11-17): Chinese and Polish, each one file; any other code is refused.
        for code, brazil in (("zh", "巴西"), ("pl", "Brazylia")):
            status, body = get(f"/api/lang/{code}.json")
            said = json.loads(body) if status == 200 else {}
            check(f"language {code} is served with names and words",
                  said.get("names", {}).get("brazil") == brazil and len(said.get("words", {})) > 500,
                  f"got {status}, {len(said.get('words', {}))} words")
        status, _ = get("/api/lang/xx.json")
        check("an unknown language is refused", status == 404, f"got {status}")
finally:
    if process:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        stderr = process.stderr.read().decode(errors="replace") if process.stderr else ""
        if stderr.strip():
            print(f"\n--- Server stderr ---\n{stderr.strip()}")

print(f"\nResults: {len(PASSED)} passed, {len(FAILED)} failed")
if FAILED:
    print(f"Failed: {', '.join(FAILED)}")
    sys.exit(1)
print("All checks passed.")
