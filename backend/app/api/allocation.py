"""Saved joint purchasing allocations; individual recommendations remain immutable."""

import csv
import io
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import InventoryAllocation, InventoryPlan
from backend.app.db.session import get_session
from backend.app.errors import AppError
from backend.app.inventory.allocation import allocate
from backend.app.schemas.inventory import AllocationRequest

router = APIRouter(prefix="/inventory", tags=["inventory allocation"])


@router.post("/allocate", status_code=201)
def create_allocation(body: AllocationRequest, session: Session = Depends(get_session)) -> dict:
    plans = list(
        session.scalars(
            select(InventoryPlan).where(InventoryPlan.id.in_([item.plan_id for item in body.items]))
        )
    )
    if len(plans) != len(body.items):
        raise AppError("A selected inventory plan was not found.", 404)
    result = allocate([p.result for p in plans], body)
    now = datetime.now(timezone.utc)
    result.update(
        allocation_id=str(uuid4()), created_at=now.isoformat(), configuration=body.model_dump()
    )
    session.add(
        InventoryAllocation(
            id=result["allocation_id"],
            dataset_id=body.dataset_id,
            created_at=now,
            configuration=body.model_dump(),
            result=result,
        )
    )
    session.commit()
    return result


@router.get("/allocations")
def list_allocations(
    dataset_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> list[dict]:
    query = select(InventoryAllocation).where(InventoryAllocation.dataset_id == dataset_id)
    rows = session.scalars(
        query.order_by(InventoryAllocation.created_at.desc(), InventoryAllocation.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return [
        {
            "allocation_id": row.id,
            "created_at": row.created_at.isoformat(),
            "location_id": row.result["location_id"],
            "purchase_cost": row.result["purchase_cost"],
            "currency": row.result["currency"],
            "solver_status": row.result["solver_status"],
        }
        for row in rows
    ]


@router.get("/allocations/{allocation_id}")
def allocation_detail(allocation_id: str, session: Session = Depends(get_session)) -> dict:
    row = session.get(InventoryAllocation, allocation_id)
    if row is None:
        raise AppError("Allocation not found.", 404)
    return row.result


@router.get("/allocations/{allocation_id}/export")
def export_allocation(allocation_id: str, session: Session = Depends(get_session)) -> Response:
    result = allocation_detail(allocation_id, session)
    columns = [
        "sku_id",
        "store_id",
        "location_id",
        "plan_id",
        "requested_quantity",
        "allocated_quantity",
        "deferred_quantity",
        "priority_weight",
        "unit_cost",
        "purchase_cost",
        "currency",
        "capacity_used",
        "capacity_unit",
        "status",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    for item in result["items"]:
        row = {**item, "currency": result["currency"], "capacity_unit": result["capacity_unit"]}
        writer.writerow(
            {
                key: "'" + str(row[key])
                if isinstance(row[key], str) and row[key].startswith(("=", "+", "-", "@"))
                else row[key]
                for key in columns
            }
        )
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="allocation-{allocation_id}.csv"',
        },
    )
