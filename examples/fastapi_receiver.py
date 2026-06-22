"""A realistic subscriber: a small FastAPI app that receives and verifies webhooks.

This is what integrating the delivery service looks like in practice. The subscriber
stores the secret it got at registration, reads the raw request body, and calls
verify(). On success it has a trusted, parsed payload to act on.

Run:
    pip install -e client fastapi uvicorn
    WEBHOOK_SECRET=<ENDPOINT_SECRET> uvicorn examples.fastapi_receiver:app --port 9000
"""

import os

from fastapi import FastAPI, Request, Response

from webhook_receiver import WebhookVerificationError, verify

app = FastAPI()
SECRET = os.environ.get("WEBHOOK_SECRET", "set-me")


@app.post("/hook")
async def receive(request: Request):
    raw_body = await request.body()  # RAW bytes, before any parsing

    try:
        payload = verify(SECRET, raw_body, request.headers)
    except WebhookVerificationError as exc:
        # 400 tells the sender this delivery is bad and should not be retried blindly;
        # in practice an attacker forging requests lands here.
        return Response(status_code=400, content=str(exc))

    # Verified. `payload` is the parsed event. Deduplicate on the delivery id so a
    # retried delivery is processed at most once (at-least-once delivery means you
    # can receive the same event twice).
    delivery_id = request.headers.get("Webhook-Id")
    print(f"received event {payload.get('type')} (delivery {delivery_id}): {payload.get('data')}")

    return {"ok": True}
