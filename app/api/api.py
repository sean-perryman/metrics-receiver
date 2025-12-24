from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.ingest import get_endpoint_by_token, ingest_snapshot

router = APIRouter()


@router.post("/v1/ingest")
async def ingest(request: Request, db: AsyncSession = Depends(get_db)):
        # Accept either X-API-Key header (recommended for agents) or Authorization: Bearer <token>
    token = (request.headers.get("x-api-key") or "").strip()
    if not token:
        auth = request.headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API token")
    endpoint = await get_endpoint_by_token(db, token)
    if not endpoint:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    body = await request.json()
    # Accept either a single object or a one-element list.
    if isinstance(body, list):
        if len(body) != 1 or not isinstance(body[0], dict):
            raise HTTPException(status_code=400, detail="Expected a single snapshot object or a one-element array")
        payload = body[0]
    elif isinstance(body, dict):
        payload = body
    else:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    try:
        snap_id = await ingest_snapshot(db, endpoint, payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {"ok": True, "snapshot_id": snap_id}
