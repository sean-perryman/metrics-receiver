from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_

from app.api.templating import templates
from app.core.auth import get_current_user, require_admin
from app.core.security import verify_password, hash_password, generate_token, hash_token
from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.endpoint import Endpoint
from app.models.snapshot import Snapshot, DiskPhysical, DiskVolume, NetworkInterface, LoggedInUser
from app.models.setting import Setting

router = APIRouter()


@router.get("/")
async def home(request: Request, user: User = Depends(get_current_user)):
    return RedirectResponse(url="/dashboard", status_code=302)


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login(request: Request, db: AsyncSession = Depends(get_db), email: str = Form(...), password: str = Form(...)):
    q = await db.execute(select(User).where(User.email == email.lower(), User.is_active.is_(True)))
    user = q.scalars().first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"}, status_code=401)

    request.session["user_id"] = user.id
    return RedirectResponse(url="/dashboard", status_code=302)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


async def _get_global_settings(db: AsyncSession) -> dict:
    q = await db.execute(select(Setting).where(Setting.key == "global"))
    row = q.scalars().first()
    return row.value if row else {}


@router.get("/dashboard")
async def dashboard(request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    # Summary across all hosts using latest snapshot per endpoint
    subq = select(Snapshot.endpoint_id, func.max(Snapshot.timestamp_utc).label("max_ts")).group_by(Snapshot.endpoint_id).subquery()

    q = await db.execute(
        select(Endpoint, Snapshot)
        .join(subq, Endpoint.id == subq.c.endpoint_id)
        .join(Snapshot, and_(Snapshot.endpoint_id == subq.c.endpoint_id, Snapshot.timestamp_utc == subq.c.max_ts))
        .where(Endpoint.is_active.is_(True))
        .order_by(Endpoint.hostname.asc())
    )
    rows = q.all()

    # Top offenders
    top_cpu = sorted([r for r in rows if r[1].cpu_utilization_pct is not None], key=lambda x: x[1].cpu_utilization_pct, reverse=True)[:5]
    top_mem = sorted([r for r in rows if r[1].mem_used_pct is not None], key=lambda x: x[1].mem_used_pct, reverse=True)[:5]

    # Low disk table (free_pct < X) across latest snapshots
    cfg = await _get_global_settings(db)
    low_disk_threshold = float(((cfg.get("alerts") or {}).get("low_disk_free_pct_threshold", 10.0)))

    q = await db.execute(
        select(Endpoint.hostname, Endpoint.machine_id, DiskVolume.mount, DiskVolume.free_pct, DiskVolume.free_bytes, DiskVolume.total_bytes)
        .join(Snapshot, Snapshot.endpoint_id == Endpoint.id)
        .join(DiskVolume, DiskVolume.snapshot_id == Snapshot.id)
        .join(subq, and_(Snapshot.endpoint_id == subq.c.endpoint_id, Snapshot.timestamp_utc == subq.c.max_ts))
        .where(DiskVolume.free_pct < low_disk_threshold)
        .order_by(DiskVolume.free_pct.asc())
        .limit(50)
    )
    low_disk_rows = q.all()

    now = datetime.now(timezone.utc)
    host_cards = []
    for ep, snap in rows:
        last_seen = ep.last_seen
        seconds_ago = int((now - last_seen).total_seconds()) if last_seen else None
        host_cards.append({
            "hostname": ep.hostname,
            "machine_id": ep.machine_id,
            "endpoint_id": ep.id,
            "last_seen": last_seen,
            "seconds_ago": seconds_ago,
            "cpu": snap.cpu_utilization_pct,
            "mem": snap.mem_used_pct,
            "ts": snap.timestamp_utc,
        })

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "host_cards": host_cards,
            "top_cpu": top_cpu,
            "top_mem": top_mem,
            "low_disk_threshold": low_disk_threshold,
            "low_disk_rows": low_disk_rows,
        },
    )


@router.get("/hosts")
async def hosts(request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user), q: str | None = None):
    stmt = select(Endpoint).where(Endpoint.is_active.is_(True))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Endpoint.hostname.ilike(like), Endpoint.machine_id.ilike(like)))
    stmt = stmt.order_by(Endpoint.hostname.asc())
    res = await db.execute(stmt)
    endpoints = res.scalars().all()
    return templates.TemplateResponse("hosts.html", {"request": request, "user": user, "endpoints": endpoints, "q": q or ""})


@router.get("/hosts/{endpoint_id}")
async def host_detail(request: Request, endpoint_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    q = await db.execute(select(Endpoint).where(Endpoint.id == endpoint_id))
    ep = q.scalars().first()
    if not ep:
        raise HTTPException(status_code=404, detail="Host not found")

    # last 24h snapshot count
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    q = await db.execute(select(func.count()).select_from(Snapshot).where(Snapshot.endpoint_id == endpoint_id, Snapshot.timestamp_utc >= since))
    count_24h = q.scalar_one()

    return templates.TemplateResponse(
        "host_detail.html",
        {"request": request, "user": user, "endpoint": ep, "count_24h": count_24h},
    )


@router.get("/api/ui/host/{endpoint_id}/timeseries")
async def host_timeseries(endpoint_id: int, metric: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    # metric: cpu, mem, disk_queue, disk_read_lat, disk_write_lat, vol_free, nic_bps, nic_err
    since_hours = 24
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)

    if metric == "cpu":
        q = await db.execute(select(Snapshot.timestamp_utc, Snapshot.cpu_utilization_pct).where(Snapshot.endpoint_id == endpoint_id, Snapshot.timestamp_utc >= since).order_by(Snapshot.timestamp_utc.asc()))
        rows = q.all()
        return {"labels": [r[0].isoformat() for r in rows], "series": [{"name": "CPU Util %", "data": [r[1] for r in rows]}]}

    if metric == "mem":
        q = await db.execute(select(Snapshot.timestamp_utc, Snapshot.mem_used_pct).where(Snapshot.endpoint_id == endpoint_id, Snapshot.timestamp_utc >= since).order_by(Snapshot.timestamp_utc.asc()))
        rows = q.all()
        return {"labels": [r[0].isoformat() for r in rows], "series": [{"name": "Memory Used %", "data": [r[1] for r in rows]}]}

    if metric in ("disk_queue", "disk_read_lat", "disk_write_lat"):
        q = await db.execute(
            select(Snapshot.timestamp_utc, DiskPhysical.instance, DiskPhysical.avg_queue_length, DiskPhysical.read_latency_ms, DiskPhysical.write_latency_ms)
            .join(DiskPhysical, DiskPhysical.snapshot_id == Snapshot.id)
            .where(Snapshot.endpoint_id == endpoint_id, Snapshot.timestamp_utc >= since)
            .order_by(Snapshot.timestamp_utc.asc())
        )
        rows = q.all()
        # group by instance
        labels = sorted({r[0] for r in rows})
        label_str = [t.isoformat() for t in labels]
        by_inst = {}
        for ts, inst, ql, rl, wl in rows:
            by_inst.setdefault(inst, {})[ts] = (ql, rl, wl)
        series = []
        for inst, data in by_inst.items():
            vals = []
            for ts in labels:
                ql, rl, wl = data.get(ts, (None, None, None))
                if metric == "disk_queue":
                    vals.append(ql)
                elif metric == "disk_read_lat":
                    vals.append(rl)
                else:
                    vals.append(wl)
            name = f"{inst}"
            series.append({"name": name, "data": vals})
        title = {"disk_queue": "Disk Avg Queue Length", "disk_read_lat": "Disk Read Latency (ms)", "disk_write_lat": "Disk Write Latency (ms)"}[metric]
        return {"labels": label_str, "series": [{"name": f"{title} - {s['name']}", "data": s["data"]} for s in series]}

    if metric == "vol_free":
        q = await db.execute(
            select(Snapshot.timestamp_utc, DiskVolume.mount, DiskVolume.free_pct)
            .join(DiskVolume, DiskVolume.snapshot_id == Snapshot.id)
            .where(Snapshot.endpoint_id == endpoint_id, Snapshot.timestamp_utc >= since)
            .order_by(Snapshot.timestamp_utc.asc())
        )
        rows = q.all()
        labels = sorted({r[0] for r in rows})
        label_str = [t.isoformat() for t in labels]
        by_mount = {}
        for ts, mount, free_pct in rows:
            by_mount.setdefault(mount, {})[ts] = free_pct
        series = []
        for mount, data in by_mount.items():
            series.append({"name": f"{mount} Free %", "data": [data.get(ts) for ts in labels]})
        return {"labels": label_str, "series": series}

    if metric in ("nic_bps", "nic_err"):
        q = await db.execute(
            select(Snapshot.timestamp_utc, NetworkInterface.name, NetworkInterface.bits_total_per_sec, NetworkInterface.packets_in_errors, NetworkInterface.packets_out_errors)
            .join(NetworkInterface, NetworkInterface.snapshot_id == Snapshot.id)
            .where(Snapshot.endpoint_id == endpoint_id, Snapshot.timestamp_utc >= since)
            .order_by(Snapshot.timestamp_utc.asc())
        )
        rows = q.all()
        labels = sorted({r[0] for r in rows})
        label_str = [t.isoformat() for t in labels]
        by_name = {}
        for ts, name, bps, ein, eout in rows:
            by_name.setdefault(name, {})[ts] = (bps, ein, eout)
        series = []
        for name, data in by_name.items():
            if metric == "nic_bps":
                series.append({"name": f"{name} bps", "data": [data.get(ts, (None, None, None))[0] for ts in labels]})
            else:
                series.append({"name": f"{name} in_err", "data": [data.get(ts, (None, None, None))[1] for ts in labels]})
                series.append({"name": f"{name} out_err", "data": [data.get(ts, (None, None, None))[2] for ts in labels]})
        return {"labels": label_str, "series": series}

    raise HTTPException(status_code=400, detail="Unknown metric")


@router.get("/search")
async def global_search(request: Request, q: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    like = f"%{q}%"
    endpoints = (await db.execute(select(Endpoint).where(or_(Endpoint.hostname.ilike(like), Endpoint.machine_id.ilike(like))).limit(25))).scalars().all()
    users = (await db.execute(select(LoggedInUser.username, Snapshot.endpoint_id).join(Snapshot, LoggedInUser.snapshot_id == Snapshot.id).where(LoggedInUser.username.ilike(like)).order_by(LoggedInUser.username.asc()).limit(25))).all()
    return templates.TemplateResponse("search.html", {"request": request, "user": user, "q": q, "endpoints": endpoints, "user_hits": users})


@router.get("/admin/endpoints")
async def admin_endpoints(request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)):
    eps = (await db.execute(select(Endpoint).order_by(Endpoint.created_at.desc()))).scalars().all()
    # show newly created token exactly once
    new_token = request.session.pop("new_endpoint_token", None)
    return templates.TemplateResponse("admin_endpoints.html", {"request": request, "user": user, "endpoints": eps, "new_token": new_token})


@router.post("/admin/endpoints/new")
async def admin_endpoints_new(request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_admin), hostname: str = Form(...), machine_id: str = Form(...)):
    token = generate_token(32)
    ep = Endpoint(hostname=hostname, machine_id=machine_id, token_hash=hash_token(token), is_active=True)
    db.add(ep)
    await db.commit()
    # Show token once
    request.session["new_endpoint_token"] = token
    return RedirectResponse(url="/admin/endpoints", status_code=302)


@router.get("/admin/endpoints/{endpoint_id}/config")
async def download_endpoint_config(endpoint_id: int, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)):
    q = await db.execute(select(Endpoint).where(Endpoint.id == endpoint_id))
    ep = q.scalars().first()
    if not ep:
        raise HTTPException(status_code=404)

    token = request.session.get("new_endpoint_token")
    # If we don't have the plaintext token (i.e., old endpoint), generate a new one and replace.
    if not token:
        token = generate_token(32)
        ep.token_hash = hash_token(token)
        await db.commit()

    cfg = {
        "server_url": str(request.base_url).rstrip('/') + '/api/v1/ingest',
        "bearer_token": token,
        "interval_seconds": 30,
        "enable": {
            "cpu": True,
            "memory": True,
            "disk": True,
            "network": True,
            "users": True,
        },
    }

    data = json.dumps(cfg, indent=2).encode("utf-8")
    filename = f"metricsagent-config-{ep.hostname}.json"
    return Response(content=data, media_type="application/json", headers={"Content-Disposition": f"attachment; filename={filename}"})


@router.get("/admin/users")
async def admin_users(request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)):
    users = (await db.execute(select(User).order_by(User.created_at.desc()))).scalars().all()
    return templates.TemplateResponse("admin_users.html", {"request": request, "user": user, "users": users, "roles": list(UserRole)})


@router.post("/admin/users/new")
async def admin_users_new(request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_admin), email: str = Form(...), password: str = Form(...), role: str = Form(...)):
    db.add(User(email=email.lower(), password_hash=hash_password(password), role=UserRole(role)))
    await db.commit()
    return RedirectResponse(url="/admin/users", status_code=302)


@router.get("/admin/settings")
async def admin_settings(request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_admin)):
    cfg = await _get_global_settings(db)
    return templates.TemplateResponse("admin_settings.html", {"request": request, "user": user, "cfg": json.dumps(cfg, indent=2)})


@router.post("/admin/settings")
async def admin_settings_save(request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(require_admin), cfg_json: str = Form(...)):
    try:
        cfg = json.loads(cfg_json) if cfg_json.strip() else {}
    except Exception:
        return templates.TemplateResponse("admin_settings.html", {"request": request, "user": user, "cfg": cfg_json, "error": "Invalid JSON"}, status_code=400)

    q = await db.execute(select(Setting).where(Setting.key == "global"))
    row = q.scalars().first()
    if not row:
        row = Setting(key="global", value=cfg)
        db.add(row)
    else:
        row.value = cfg
    await db.commit()
    return RedirectResponse(url="/admin/settings", status_code=302)