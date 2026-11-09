#!/usr/bin/env python3
"""route_server.py: a stand-in webhook route for the relay, on 127.0.0.1 only. Every POST body is one JSON line in the
log file ({"at", "path", "authorized", "body"}) and gets a 200, so the flusher delivers and the evals read what
reached the "bot". Nothing leaves the machine.

    python3 route_server.py --port 8765 --log received.jsonl
"""
import argparse, json, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--log', required=True)
    a = p.parse_args(argv)
    log = Path(a.log)
    log.parent.mkdir(parents=True, exist_ok=True)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get('Content-Length') or 0))
            try:
                body = json.loads(raw)
            except ValueError:
                body = raw.decode('utf-8', 'replace')
            row = {'at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'path': self.path,
                   'authorized': self.headers.get('Authorization', '').startswith('Bearer '), 'body': body}
            with log.open('a') as out:
                out.write(json.dumps(row) + '\n')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"ok":true}\n')

        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'route stand-in\n')

        def log_message(self, *args):
            pass

    ThreadingHTTPServer(('127.0.0.1', a.port), Handler).serve_forever()


if __name__ == '__main__':
    main(sys.argv[1:])
