"""Read-only HTTP API + viewer for Knowledge Globe (DESIGN_v0.1.md §4)."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import subjects

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


class Handler(BaseHTTPRequestHandler):
    server_version = "KnowledgeGlobe/0.1"

    def do_GET(self):
        path = self.path.split("?", 1)[0].rstrip("/") or "/"

        if path == "/":
            return self._send_viewer()
        if path == "/api/subjects":
            return self._send_json(200, subjects.list_subjects())
        if path.startswith("/api/subjects/"):
            subject_id = path[len("/api/subjects/"):]
            try:
                return self._send_json(200, subjects.get_subject(subject_id))
            except subjects.SubjectError:
                return self._send_json(404, {"error": "unknown subject"})

        self._send_json(404, {"error": "not found"})

    def _send_viewer(self):
        with open(os.path.join(STATIC_DIR, "index.html"), "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
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
