# app/routes.py
# The API endpoints. Each one checks who is calling, runs a service function,
# and maps errors to HTTP status codes.
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import services
from app.auth_deps import get_current_user, require_roles
from app.deps import get_db
from app.models import Shipment, User, UserRole
from app.schemas import ShipmentCreate, ShipmentOut, StatusChange
from app.state_machine import IllegalTransition

router = APIRouter(prefix="/shipments", tags=["shipments"])


@router.post("", response_model=ShipmentOut, status_code=201)
def create_shipment(
    data: ShipmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DISPATCHER)),
):
    try:
        return services.create_shipment(db, data, actor=user.username)
    except services.NotFound as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.get("/{shipment_id}", response_model=ShipmentOut)
def get_shipment(
    shipment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),  # any logged-in role may read
):
    shipment = db.get(Shipment, shipment_id)
    if shipment is None:
        raise HTTPException(status_code=404, detail="Shipment not found")
    # A rider may only see shipments assigned to them. Anything else looks like "not found".
    if user.role == UserRole.RIDER and (user.rider_id is None or shipment.rider_id != user.rider_id):
        raise HTTPException(status_code=404, detail="Shipment not found")
    return shipment


@router.post("/{shipment_id}/status", response_model=ShipmentOut)
def change_shipment_status(
    shipment_id: int,
    change: StatusChange,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.ADMIN, UserRole.DISPATCHER, UserRole.RIDER)),
):
    try:
        return services.change_status(
            db,
            shipment_id,
            change,
            actor=user.username,
            actor_role=user.role,
            actor_rider_id=user.rider_id,
        )
    except services.NotFound as error:
        raise HTTPException(status_code=404, detail=str(error))
    except services.Forbidden as error:
        raise HTTPException(status_code=403, detail=str(error))
    except IllegalTransition as error:
        raise HTTPException(status_code=409, detail=str(error))
    except services.RuleViolation as error:
        raise HTTPException(status_code=422, detail=str(error))
