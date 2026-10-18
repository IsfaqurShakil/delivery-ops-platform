# app/routes.py
# The API endpoints. Each one receives a request, calls a service function, and maps errors to HTTP status codes.
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import services
from app.deps import get_db
from app.models import Shipment
from app.schemas import ShipmentCreate, ShipmentOut, StatusChange
from app.state_machine import IllegalTransition

router = APIRouter(prefix="/shipments", tags=["shipments"])


@router.post("", response_model=ShipmentOut, status_code=201)
def create_shipment(data: ShipmentCreate, db: Session = Depends(get_db)):
    try:
        return services.create_shipment(db, data)
    except services.NotFound as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.get("/{shipment_id}", response_model=ShipmentOut)
def get_shipment(shipment_id: int, db: Session = Depends(get_db)):
    shipment = db.get(Shipment, shipment_id)
    if shipment is None:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return shipment


@router.post("/{shipment_id}/status", response_model=ShipmentOut)
def change_shipment_status(shipment_id: int, change: StatusChange, db: Session = Depends(get_db)):
    try:
        return services.change_status(db, shipment_id, change)
    except services.NotFound as error:
        raise HTTPException(status_code=404, detail=str(error))
    except IllegalTransition as error:
        raise HTTPException(status_code=409, detail=str(error))
    except services.RuleViolation as error:
        raise HTTPException(status_code=422, detail=str(error))
