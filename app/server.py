"""Read-only HTTP API + viewer for Knowledge Globe (DESIGN_v0.1.md §4)."""
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import geography, graph, subjects

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
            return self._send_viewer()
        if path.startswith("/static/"):
            return self._send_static(path[len("/static/"):])
        if path.startswith("/earth/"):
            name = path[len("/earth/"):]
            cache = "no-cache" if name == "manifest.json" else FOREVER
            return self._send_file(EARTH_DIR, name, cache)
        if path == "/explore":
            return self._send_viewer("explore.html")
        if path == "/api/graph":
            return self._send_json(200, graph.build(geo=geography.load(EARTH_DIR)))
        if path == "/api/subjects":
            return self._send_json(200, subjects.list_subjects())
        if path.startswith("/api/subjects/"):
            subject_id = path[len("/api/subjects/"):]
            try:
                return self._send_json(200, subjects.get_subject(subject_id))
            except subjects.SubjectError:
                return self._send_json(404, {"error": "unknown subject"})

        self._send_json(404, {"error": "not found"})

    def _send_viewer(self, name="index.html"):
        with open(os.path.join(STATIC_DIR, name), "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
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

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}")


def serve(port):
    # Binds all interfaces by design: the viewer is used from other machines on
    # the LAN. Kept off the public internet at the network edge, not here.
    host = os.environ.get("HOST", "0.0.0.0")  # nosec B104
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Knowledge Globe listening on http://{host}:{port}")
    httpd.serve_forever()
