#!/usr/bin/env python3
"""Tiny deploy-webhook server (standard library only) that runs on the EC2 host.

POST /deploy with a valid  X-Hub-Signature-256  header  ->  runs deploy.sh
The signature is an HMAC-SHA256 of the request body using WEBHOOK_SECRET.
GitHub's own webhooks use the same scheme, so you can also point a normal
GitHub webhook (Settings -> Webhooks) at http://<EC2_IP>:9000/deploy .
"""
import hashlib
import hmac
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

SECRET = os.environ["WEBHOOK_SECRET"].encode()
DEPLOY = os.environ.get("DEPLOY_SCRIPT", "/opt/webscout/deploy/deploy.sh")
BRANCH = os.environ.get("DEPLOY_REF", "refs/heads/main")
lock = threading.Lock()


def run_deploy():
    if not lock.acquire(blocking=False):
        print("deploy already running, skipping", flush=True)
        return
    try:
        print("deploy started", flush=True)
        r = subprocess.run(["/bin/bash", DEPLOY], capture_output=True, text=True)
        print(r.stdout[-2000:], r.stderr[-2000:], f"exit={r.returncode}", flush=True)
    finally:
        lock.release()


class Handler(BaseHTTPRequestHandler):
    def _reply(self, code, msg):
        self.send_response(code)
        self.end_headers()
        self.wfile.write(msg.encode())

    def do_GET(self):
        if self.path == "/health":
            self._reply(200, "ok")
        else:
            self._reply(404, "not found")

    def do_POST(self):
        if self.path != "/deploy":
            return self._reply(404, "not found")
        length = min(int(self.headers.get("Content-Length", 0)), 1_000_000)
        body = self.rfile.read(length)
        sent = self.headers.get("X-Hub-Signature-256", "")
        good = "sha256=" + hmac.new(SECRET, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sent, good):
            return self._reply(401, "bad signature")
        try:
            ref = json.loads(body or b"{}").get("ref", BRANCH)
        except Exception:
            ref = BRANCH
        if ref != BRANCH:
            return self._reply(200, f"ignored ref {ref}")
        threading.Thread(target=run_deploy, daemon=True).start()
        self._reply(202, "deploy started")

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)


if __name__ == "__main__":
    print("webhook listener on :9000", flush=True)
    HTTPServer(("0.0.0.0", 9000), Handler).serve_forever()
