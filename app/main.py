"""FastAPI application. Wires the routers together and creates tables on startup."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import init_db
from app.queue import DeliveryQueue
from app.routers import deliveries, endpoints, events


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Webhook Delivery System", version="0.1.0", lifespan=lifespan)
app.include_router(endpoints.router)
app.include_router(events.router)
app.include_router(deliveries.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "queue_depth": DeliveryQueue().size()}
