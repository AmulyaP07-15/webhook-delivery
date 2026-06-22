"""Read access to deliveries so you can inspect state while building. The full
delivery log (per-attempt history) and the redeliver endpoint land on Day 2."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.database import get_session
from app.models import Delivery
from app.schemas import DeliveryRead

router = APIRouter(prefix="/deliveries", tags=["deliveries"])


@router.get("", response_model=list[DeliveryRead])
def list_deliveries(session: Session = Depends(get_session)):
    return session.exec(select(Delivery).order_by(Delivery.created_at.desc())).all()


@router.get("/{delivery_id}", response_model=DeliveryRead)
def get_delivery(delivery_id: str, session: Session = Depends(get_session)):
    delivery = session.get(Delivery, delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="delivery not found")
    return delivery
