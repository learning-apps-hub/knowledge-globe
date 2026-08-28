#!/usr/bin/env python3
"""
Smoke test — Knowledge Globe

Verifies the app starts and key endpoints respond.
Run from project root: python3 tests/smoke_test.py
"""
import json
import subprocess
import time
import urllib.request
import urllib.error
import sys
import os

PORT = int(os.environ.get("PORT", 8110))
START_CMD = ["python3", "run.py"]
PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PASSED = []
FAILED = []


def check(label, ok, detail=""):
    if ok:
        PASSED.append(label)
        print(f"  [PASS] {label}")
    else:
        FAILED.append(label)
        print(f"  [FAIL] {label}{' — ' + detail if detail else ''}")


def get(path):
    try:
        resp = urllib.request.urlopen(f"http://localhost:{PORT}{path}", timeout=5)
        return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, str(e)
    except Exception as e:
        return None, str(e)


def wait_for_server(timeout=15):
    for _ in range(timeout * 2):
        try:
            urllib.request.urlopen(f"http://localhost:{PORT}/", timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


proc = None
try:
    print(f"\n{'='*50}")
    print(f"Smoke test — Knowledge Globe (port {PORT})")
    print(f"{'='*50}\n")

    # Check only this project's port — do not scan system-wide processes
    print("--- Server ---")
    try:
        urllib.request.urlopen(f"http://localhost:{PORT}/", timeout=1)
        check(f"Port {PORT} is free", False,
              f"something is already running on port {PORT} — stop it before running smoke tests")
        sys.exit(1)
    except Exception:
        pass  # port is free, good

    proc = subprocess.Popen(
        START_CMD,
        cwd=PROJ_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    time.sleep(1)

    check("Server process starts", proc.poll() is None, "process exited immediately")

    ready = wait_for_server()
    check(f"Server ready on port {PORT}", ready, "did not respond after 15s")

    if ready:
        print("\n--- UI ---")
        status, body = get("/")
        check("GET / → 200", status == 200, f"got {status}")
        check("GET / returns HTML", isinstance(body, bytes) and b"<html" in body.lower())
        check("GET / includes 3D viewer",
              isinstance(body, bytes) and b"three.module.min.js" in body)

        status, body = get("/static/vendor/three.module.min.js")
        check("GET Three.js asset → 200", status == 200, f"got {status}")
        check("Three.js asset is JavaScript",
              isinstance(body, bytes) and b"WebGLRenderer" in body)
        check("Three.js module declares its core dependency",
              isinstance(body, bytes) and b'from"./three.core.min.js"' in body)

        status, body = get("/static/vendor/three.core.min.js")
        check("GET Three.js core asset → 200", status == 200, f"got {status}")
        check("Three.js core asset is JavaScript",
              isinstance(body, bytes) and b"REVISION" in body)

        print("\n--- API ---")
        status, body = get("/api/subjects")
        check("GET /api/subjects → 200", status == 200, f"got {status}")
        listing = json.loads(body) if status == 200 else []
        check("subject list is non-empty", bool(listing))
        check("water is seeded", any(s["id"] == "water" for s in listing))
        check("Singapore Oceanarium is seeded",
              any(s["id"] == "singapore-oceanarium" for s in listing))

        status, body = get("/api/subjects/water")
        check("GET /api/subjects/water → 200", status == 200, f"got {status}")
        subject = json.loads(body) if status == 200 else {}
        check("subject has nodes", len(subject.get("nodes", [])) > 0)
        check("subject has edges", len(subject.get("edges", [])) > 0)
        check("zoom_level derived on every node",
              all("zoom_level" in n for n in subject.get("nodes", [])))
        check("root node is zoom level 0",
              any(n["zoom_level"] == 0 for n in subject.get("nodes", [])))

        status, body = get("/api/subjects/singapore-oceanarium")
        check("GET /api/subjects/singapore-oceanarium → 200",
              status == 200, f"got {status}")
        oceanarium = json.loads(body) if status == 200 else {}
        oceanarium_nodes = oceanarium.get("nodes", [])
        check("Oceanarium has a habitat-to-animal hierarchy",
              len(oceanarium_nodes) >= 60 and
              max((n.get("zoom_level", 0) for n in oceanarium_nodes), default=0) >= 3)
        check("Oceanarium animal content is source-checked",
              all(n.get("sources") for n in oceanarium_nodes))
        catalogue = [n for n in oceanarium_nodes
                     if n.get("catalogue") == "animals-a-z"]
        check("Oceanarium includes all 43 official A–Z entries",
              len(catalogue) == 43, f"got {len(catalogue)}")
        check("every A–Z entry has a complete animal profile",
              all(all(n.get("animal", {}).get(field)
                      for field in ("type", "habitat", "zone", "diet", "presentation"))
                  for n in catalogue))
        check("every A–Z entry has a real-photo path",
              all(isinstance(n.get("visual"), dict) or n.get("visual_query")
                  for n in catalogue))
        check("non-live A–Z displays are labelled",
              any("Replica" in n["animal"]["presentation"] for n in catalogue) and
              any("Preserved" in n["animal"]["presentation"] for n in catalogue))
        check("Oceanarium includes internal predator/prey links",
              sum(e.get("type") == "preys-on"
                  for e in oceanarium.get("edges", [])) >= 2)
        check("viewer includes licensed visual lookup",
              b"Wikimedia Commons" in get("/")[1])
        viewer = get("/")[1]
        check("viewer includes official Oceanarium filters",
              all(term in viewer for term in
                  (b"Animal Type", b"Natural Habitat", b"Zone")))
        check("viewer removes the duplicate Oceanarium journey list",
              b'$("browse-label").hidden = oceanarium' in viewer and
              b'$("place-list").hidden = oceanarium' in viewer and
              b"state.animalBrowseMode = isOceanarium()" in viewer)
        check("viewer uses compact shape-neutral globe pins",
              b"pin-photo" not in viewer and b"loadPinVisual" not in viewer and
              b'<span class="pin-orb"></span>' in viewer)
        check("selected pin centres in a 0.2 second turn",
              all(term in viewer for term in
                  (b"function centerPin", b"rotationTween",
                   b"duration: 200", b'slerpQuaternions')))
        check("selection greys peers and globe click resumes rotation",
              b'pin.classList.toggle("unselected"' in viewer and
              b"shouldResume" in viewer and
              b"state.autoRotate = !state.reducedMotion" in viewer)
        check("viewer supports a resizable reading drawer",
              b"resizingPanel" in viewer and b"--panel-width" in viewer)
        check("viewer projects a subject theme on the globe",
              b"uThemeMap" in viewer and b"createSubjectTexture" in viewer)
        check("Oceanarium surface has accessible water animation",
              all(term in viewer for term in
                  (b"causticField", b"rippleRing", b"waterWarp", b"waveShadow",
                   b"state.reducedMotion ? 0")))

        print("\n--- Input validation ---")
        status, _ = get("/api/subjects/nope")
        check("unknown subject → 404", status == 404, f"got {status}")
        status, _ = get("/api/subjects/..%2f..%2fetc%2fpasswd")
        check("path traversal → 404", status == 404, f"got {status}")
        status, _ = get("/static/../server.py")
        check("static path traversal → 404", status == 404, f"got {status}")

finally:
    if proc:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        if stderr.strip():
            print(f"\n--- Server stderr ---\n{stderr.strip()}")

print(f"\n{'='*50}")
print(f"Results: {len(PASSED)} passed, {len(FAILED)} failed")
if FAILED:
    print(f"Failed: {', '.join(FAILED)}")
    sys.exit(1)
else:
    print("All checks passed.")
