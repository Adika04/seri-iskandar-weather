"""Tiny stand-in for Turso's /v2/pipeline endpoint (batch steps + conditions),
backed by an in-memory SQLite database. For tests only."""
import json
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

TOKEN = "test-token"


def _decode_arg(arg):
    t = arg["type"]
    if t == "null":
        return None
    if t == "integer":
        return int(arg["value"])
    if t == "float":
        return float(arg["value"])
    return arg["value"]


def _encode_cell(v):
    if v is None:
        return {"type": "null"}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        return {"type": "float", "value": v}
    return {"type": "text", "value": v}


class FakeTurso:
    def __init__(self):
        self.db = sqlite3.connect(":memory:", check_same_thread=False,
                                  isolation_level=None)  # we send BEGIN/COMMIT ourselves
        self.requests_seen = 0
        self.fail_next = 0  # number of upcoming requests to answer with HTTP 503
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                outer.requests_seen += 1
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if outer.fail_next > 0:
                    outer.fail_next -= 1
                    return self._send(503, {"error": "unavailable"})
                if self.headers.get("Authorization") != "Bearer " + TOKEN:
                    return self._send(401, {"error": "bad token"})
                results = []
                for req in body["requests"]:
                    if req["type"] == "batch":
                        results.append({"type": "ok", "response": {
                            "type": "batch", "result": outer._batch(req["batch"]["steps"])}})
                    else:
                        results.append({"type": "ok", "response": {"type": "close"}})
                self._send(200, {"baton": None, "base_url": None, "results": results})

            def _send(self, code, obj):
                raw = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def _cond_ok(self, cond, results, errors):
        if cond is None:
            return True
        if cond["type"] == "ok":
            return results[cond["step"]] is not None
        if cond["type"] == "not":
            return not self._cond_ok(cond["cond"], results, errors)
        raise AssertionError("unsupported condition " + cond["type"])

    def _batch(self, steps):
        results, errors = [], []
        for step in steps:
            if not self._cond_ok(step.get("condition"), results, errors):
                results.append(None)
                errors.append(None)
                continue
            try:
                args = [_decode_arg(a) for a in step["stmt"].get("args", [])]
                cur = self.db.execute(step["stmt"]["sql"], args)
                rows = [[_encode_cell(c) for c in row] for row in cur.fetchall()]
                results.append({"rows": rows, "cols": [], "affected_row_count": 0})
                errors.append(None)
            except sqlite3.Error as exc:
                results.append(None)
                errors.append({"message": str(exc)})
        return {"step_results": results, "step_errors": errors}

    def stop(self):
        self.server.shutdown()
