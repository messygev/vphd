#!/usr/bin/env bash
set -euo pipefail

python - <<'PY'
import json, threading, subprocess, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib import request

class ExpertHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', '0'))
        payload = json.loads(self.rfile.read(length).decode())
        name = payload.get('name', 'expert')
        prompt = payload.get('prompt', '')
        response = json.dumps({'response': f'{name}::ok::{prompt[:40]}'}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, *_):
        return

servers = []
for port in range(9001, 9009):
    srv = HTTPServer(('127.0.0.1', port), ExpertHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    servers.append(srv)

planner = subprocess.Popen(['java', '-cp', 'out', 'com.example.tenthman.TenthManPlannerServer'])
time.sleep(1.0)

try:
    req_body = {
        'problem': 'Soll ein neues KI-Produkt eingeführt werden?',
        'rounds': 7,
        'externalMode': 'NONE',
        'experts': [
            {'id': i, 'name': f'E{i}', 'role': 'pro', 'endpoint': f'http://127.0.0.1:{9000+i}/expert'}
            for i in range(1, 8)
        ],
        'challenger': {
            'id': 8,
            'name': 'Doubter',
            'role': 'contra',
            'endpoint': 'http://127.0.0.1:9008/expert'
        }
    }

    req = request.Request(
        'http://127.0.0.1:8080/api/v1/tenth-man/plan',
        data=json.dumps(req_body).encode(),
        headers={'Content-Type': 'application/json'}
    )
    with request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode())

    assert result['rounds'] == 7
    assert len(result['protocol']) == 7
    assert 'Entscheidungsempfehlung' in result['markdownProtocol']
    print('Smoke test OK: 7 Runden erfolgreich erzeugt.')
finally:
    planner.terminate()
    try:
        planner.wait(timeout=5)
    except Exception:
        planner.kill()
    for srv in servers:
        srv.shutdown()
PY
