"""
Payment routes:
  GET   /api/payments            — list all payments sorted by due date
  GET   /api/payments/{id}       — get a single payment record
  PATCH /api/payments/{id}/status — mark as paid / pending / overdue
  DELETE /api/payments/{id}      — remove a payment record
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.auth.middleware import get_current_uid
from backend.redis_client import redis_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments", tags=["payments"])

VALID_STATUSES = {"pending", "paid", "overdue"}


class StatusUpdate(BaseModel):
    status: str


@router.get("")
async def list_payments(uid: str = Depends(get_current_uid)) -> list[dict]:
    """Return all payments for the authenticated user, sorted by due date ascending."""
    rc = redis_client()
    return await rc.list_payments(uid)


@router.get("/{payment_id}")
async def get_payment(payment_id: str, uid: str = Depends(get_current_uid)) -> dict:
    """Return a single payment record."""
    rc = redis_client()
    payment = await rc.get_payment(uid, payment_id)
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    return payment


@router.patch("/{payment_id}/status")
async def update_status(
    payment_id: str,
    body: StatusUpdate,
    uid: str = Depends(get_current_uid),
) -> dict:
    """Update the status of a payment (paid / pending / overdue)."""
    if body.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Status must be one of: {', '.join(VALID_STATUSES)}",
        )
    rc = redis_client()
    payment = await rc.get_payment(uid, payment_id)
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    await rc.update_payment_status(uid, payment_id, body.status)
    return {"payment_id": payment_id, "status": body.status}


@router.delete("/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payment(payment_id: str, uid: str = Depends(get_current_uid)) -> None:
    """Remove a payment record and its due-date index entry."""
    rc = redis_client()
    payment = await rc.get_payment(uid, payment_id)
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    r = rc.r
    await r.delete(f"utility:{uid}:{payment_id}")
    await r.zrem(f"due:{uid}", payment_id)
    logger.info("Payment deleted: uid=%s pid=%s", uid, payment_id)
