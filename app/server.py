"""Read-only HTTP API + viewer for Knowledge Globe (DESIGN_v0.1.md §4)."""
import gzip
import hashlib
import json
import mimetypes
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import geography, graph, language

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The Earth's pictures are big and live outside git, in a server data folder
# shared by the dev and prod trees (scripts/build_earth.py writes it).
EARTH_DIR = os.path.join(
    os.environ.get("KG_EARTH_DIR") or os.path.join(os.path.dirname(REPO_DIR), "earth-data"), "derived")
# File names carry their version (day-4096.v1.jpg), so a browser keeps them for good.
FOREVER = "public, max-age=31536000, immutable"


class Handler(BaseHTTPRequestHandler):
    server_version = "KnowledgeGlobe/0.1"

    def do_GET(self):
        path = self.path.split("?", 1)[0].rstrip("/") or "/"

        if path == "/":
            return self._send_viewer("explore.html")
        if path.startswith("/static/"):
            return self._send_static(path[len("/static/"):])
        if path.startswith("/earth/"):
            name = path[len("/earth/"):]
            # The lists change (clouds.json every hour, ice.json every day); the pictures they name never do.
            lists = ("manifest.json", "clouds/clouds.json", "lights/lights.json", "paleo/paleo.json", "ice/ice.json")
            cache = "no-cache" if name in lists else FOREVER
            return self._send_file(EARTH_DIR, name, cache)
        if path == "/explore":
            return self._send_viewer("explore.html")
        if path == "/api/graph":
            return self._send_graph()
        if path.startswith("/api/lang/") and path.endswith(".json"):
            # The words in another language (Owner, 2026-11-17); English needs none.
            try:
                return self._send_json(200, language.build(path[len("/api/lang/"):-len(".json")]))
            except language.LanguageError:
                return self._send_json(404, {"error": "unknown language"})

        self._send_json(404, {"error": "not found"})

    def _send_viewer(self, name="index.html"):
        with open(os.path.join(STATIC_DIR, name), "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # The page itself changes with every build: a phone must ask again, never keep an old viewer.
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, relative_path):
        """Serve versioned frontend assets without exposing arbitrary files."""
        return self._send_file(STATIC_DIR, relative_path, "public, max-age=86400")

    def _send_file(self, root, relative_path, cache):
        """Serve one file from under `root`, never anything outside it."""
        target = os.path.realpath(os.path.join(root, relative_path))
        static_root = os.path.realpath(root) + os.sep
        if not target.startswith(static_root) or not os.path.isfile(target):
            return self._send_json(404, {"error": "not found"})
        with open(target, "rb") as fh:
            body = fh.read()
        content_type = mimetypes.guess_type(target)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def _send_graph(self):
        """The graph, built once per change of its inputs, sent gzipped, and not sent at all when the browser
        already holds it (the logo's fresh start was slow on a phone: 4.5 MB every time, Owner 2026-11-16)."""
        body, packed, tag = _graph_bytes()
        if tag in self.headers.get("If-None-Match", ""):
            self.send_response(304)
            self.send_header("ETag", tag)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            return
        gz = "gzip" in self.headers.get("Accept-Encoding", "")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if gz:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(packed if gz else body)))
        self.send_header("ETag", tag)
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(packed if gz else body)

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        # Every answer: the browser must not guess a different type than the one sent (audit R11).
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}")


_graph_cache = {"key": None, "value": None}
_graph_lock = threading.Lock()


def _graph_inputs():
    """Name, size and change time of every file the graph is built from: the data folder and the Earth's lists."""
    seen = []
    for top, _dirs, files in os.walk(os.path.join(REPO_DIR, "data")):
        for name in files:
            seen.append(os.path.join(top, name))
    if os.path.isdir(EARTH_DIR):
        seen += [entry.path for entry in os.scandir(EARTH_DIR) if entry.is_file()]
    stamps = []
    for name in sorted(seen):
        try:
            info = os.stat(name)
        except OSError:
            continue
        stamps.append((name, info.st_size, info.st_mtime_ns))
    return tuple(stamps)


def _graph_bytes():
    """(plain body, gzipped body, ETag), rebuilt only when an input file changes."""
    key = _graph_inputs()
    with _graph_lock:
        if _graph_cache["key"] != key:
            body = json.dumps(graph.build(geography.load(EARTH_DIR))).encode("utf-8")
            tag = '"' + hashlib.sha256(body).hexdigest()[:20] + '"'
            _graph_cache.update(key=key, value=(body, gzip.compress(body, 6), tag))
        return _graph_cache["value"]


def serve(port):
    # Binds all interfaces by design: the viewer is used from other machines on
    # the LAN. Kept off the public internet at the network edge, not here.
    host = os.environ.get("HOST", "0.0.0.0")  # nosec B104
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Knowledge Globe listening on http://{host}:{port}")
    httpd.serve_forever()
