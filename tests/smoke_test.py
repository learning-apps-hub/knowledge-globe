#!/usr/bin/env python3
"""
Smoke test — Knowledge Globe

Verifies the app starts and key endpoints respond.
Run from project root: python3 tests/smoke_test.py
"""
import subprocess
import time
import urllib.request
import urllib.error
import sys
import os

PORT = 8110
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

        # TODO: add project-specific endpoint checks here

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
