"""The delayed queue, built on a Redis sorted set (ZSET).

This is the primitive that makes "try again in 5 minutes" work. Each delivery id
is a member of the sorted set, scored by the unix timestamp at which it next
becomes due. The worker repeatedly asks "give me everything whose score is <= now"
and processes those.

claim_due uses ZREM to remove each id as it pulls it. ZREM is atomic and returns 1
only to the caller that actually removed it, so even if two workers fetch the same
id, only one "wins" the claim. That keeps a delivery from being processed twice by
concurrent workers. (A Lua-script claim would be tighter under heavy contention;
noted as a Day-2 refinement.)
"""

import time

import redis

from app.config import settings


class DeliveryQueue:
    def __init__(self, url: str | None = None, key: str | None = None):
        self.client = redis.from_url(url or settings.redis_url, decode_responses=True)
        self.key = key or settings.queue_key

    def enqueue(self, delivery_id: str, due_at: float | None = None) -> None:
        """Add or reschedule a delivery to fire at due_at (unix seconds)."""
        score = due_at if due_at is not None else time.time()
        self.client.zadd(self.key, {delivery_id: score})

    def claim_due(self, limit: int) -> list[str]:
        """Return up to `limit` delivery ids that are due now, claiming each so no
        other worker also processes it."""
        now = time.time()
        candidates = self.client.zrangebyscore(self.key, "-inf", now, start=0, num=limit)
        claimed = []
        for delivery_id in candidates:
            if self.client.zrem(self.key, delivery_id) == 1:
                claimed.append(delivery_id)
        return claimed

    def size(self) -> int:
        return self.client.zcard(self.key)
