# webhook-receiver

A tiny, dependency-free library for verifying webhooks delivered by the
[webhook-delivery](../) service. One function, `verify()`.

## Install

```bash
pip install webhook-receiver
```

(Local, from this repo: `pip install -e client`.)

## Use

```python
from webhook_receiver import verify, WebhookVerificationError

# `body` must be the RAW request body, not parsed-and-re-serialized JSON.
try:
    payload = verify(secret, raw_body, request_headers)
except WebhookVerificationError:
    ...  # reject the request (400)

# payload is the trusted, parsed event
```

`verify()` does three things: confirms the `Webhook-Signature` matches an
HMAC-SHA256 of the body computed with your secret, rejects deliveries whose
`Webhook-Timestamp` is older than the tolerance window (replay protection, default
5 minutes), and returns the parsed JSON payload. Any failure raises
`WebhookVerificationError`.

## The one rule

Verify over the **raw** body bytes exactly as received. If you parse the JSON and
re-serialize it before verifying, key order or whitespace can change, the bytes
change, and the signature no longer matches. Every framework gives you a way to read
the raw body before parsing (`await request.body()` in FastAPI, `request.get_data()`
in Flask, `req.rawBody` patterns in Node). Use it.

## Deduplicate

Delivery is at-least-once, so the same event can arrive twice (for example, your 200
came back after the sender's timeout and it retried). Each delivery carries a unique
`Webhook-Id`. Record the ids you have processed and skip repeats.
