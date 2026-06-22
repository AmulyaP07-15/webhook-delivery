"""A deliberately flaky webhook receiver, for demoing retries and recovery.

It verifies every delivery's signature with the webhook_receiver library, then fails
the first N requests (HTTP 503) before succeeding (200). Point the delivery service at
it and watch the worker retry with growing backoff and finally succeed.

Usage:
    pip install -e client                       # install the verify library once
    python examples/flaky_receiver.py --secret <ENDPOINT_SECRET> --fail-times 2

Then register http://localhost:9000/hook as an endpoint, copy the secret it returns,
pass that same secret here, and emit an event.
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from webhook_receiver import WebhookVerificationError, verify


def make_handler(secret: str, fail_times: int):
    state = {"count": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # silence default logging; we print our own

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(length)  # RAW bytes, do not parse before verifying

            try:
                payload = verify(secret, raw_body, self.headers)
            except WebhookVerificationError as exc:
                print(f"  [reject] signature failed: {exc}")
                self.send_response(401)
                self.end_headers()
                return

            state["count"] += 1
            delivery_id = self.headers.get("Webhook-Id", "?")
            if state["count"] <= fail_times:
                print(f"  [fail {state['count']}/{fail_times}] verified ok, returning 503 "
                      f"(delivery {delivery_id})")
                self.send_response(503)
                self.end_headers()
            else:
                print(f"  [accept] verified ok, returning 200 "
                      f"(delivery {delivery_id}, event {payload.get('type')})")
                self.send_response(200)
                self.end_headers()

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--secret", required=True, help="the endpoint's signing secret")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--fail-times", type=int, default=2,
                        help="how many initial requests to fail before succeeding")
    args = parser.parse_args()

    handler = make_handler(args.secret, args.fail_times)
    server = HTTPServer(("127.0.0.1", args.port), handler)
    print(f"flaky receiver on http://127.0.0.1:{args.port}/hook "
          f"(will fail the first {args.fail_times} deliveries, then accept)")
    server.serve_forever()


if __name__ == "__main__":
    main()
