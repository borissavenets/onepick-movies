"""Application entrypoint for FastAPI and bot startup."""

import asyncio
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from aiogram import Dispatcher
from aiogram.types import Update
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from app.config import config
from app.logging import get_logger, setup_logging
from app.bot.instance import bot
from app.bot.router import setup_routers
from app.jobs import setup_all_jobs, shutdown_scheduler, start_scheduler

setup_logging(config.log_level)
logger = get_logger(__name__)

dp = Dispatcher()

setup_routers(dp)


async def verify_admin_token(
    authorization: str | None = Header(None, alias="Authorization"),
) -> None:
    """Verify admin token for protected endpoints.

    Args:
        authorization: Authorization header value

    Raises:
        HTTPException: If token is invalid or missing
    """
    if not config.admin_token:
        raise HTTPException(
            status_code=503,
            detail="Admin endpoints not configured (ADMIN_TOKEN not set)",
        )

    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    # Support "Bearer <token>" or just "<token>"
    token = authorization
    if authorization.startswith("Bearer "):
        token = authorization[7:]

    if token != config.admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown events."""
    logger.info("Starting application")

    # Ensure all tables exist (dev convenience — idempotent)
    from app.storage.db import Base, get_engine
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured")

    # Start scheduler and setup jobs
    start_scheduler()
    setup_all_jobs()

    if config.bot_mode == "webhook":
        webhook_full_url = f"{config.webhook_url}{config.webhook_path}"
        logger.info(f"Setting webhook to {webhook_full_url}")
        await bot.set_webhook(
            url=webhook_full_url,
            drop_pending_updates=True,
        )
        logger.info("Webhook registered successfully")

    yield

    logger.info("Shutting down application")

    # Shutdown scheduler
    shutdown_scheduler()

    if config.bot_mode == "webhook":
        await bot.delete_webhook()
        logger.info("Webhook deleted")

    await bot.session.close()
    logger.info("Bot session closed")


app = FastAPI(
    title="OnePick Movies Bot",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"ok": True}


@app.post(config.webhook_path)
async def telegram_webhook(request: Request) -> JSONResponse:
    """Handle incoming Telegram webhook updates."""
    if config.bot_mode != "webhook":
        return JSONResponse(
            status_code=400,
            content={"error": "Webhook mode is not enabled"},
        )

    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot=bot, update=update)
        return JSONResponse(content={"ok": True})
    except Exception as e:
        logger.exception(f"Error processing webhook update: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"},
        )


@app.post("/admin/tmdb/sync")
async def trigger_tmdb_sync(
    _: None = Depends(verify_admin_token),
) -> dict:
    """Trigger an immediate TMDB sync run.

    Requires admin token in Authorization header.

    Returns:
        Sync statistics including counts and duration
    """
    from app.jobs import run_tmdb_sync

    logger.info("Admin triggered TMDB sync")

    try:
        stats = await run_tmdb_sync()
        return {
            "ok": True,
            "fetched": stats.total_fetched,
            "upserted": stats.total_upserted,
            "errors": stats.errors,
            "duration_seconds": stats.duration_seconds,
            "sources_processed": stats.sources_processed,
        }
    except Exception as e:
        logger.exception(f"Admin TMDB sync failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Sync failed: {str(e)[:200]}",
        )


@app.get("/admin/stats")
async def get_stats(
    _: None = Depends(verify_admin_token),
) -> dict:
    """Get application statistics.

    Requires admin token in Authorization header.

    Returns:
        Statistics about items, users, etc.
    """
    from app.storage import ItemsRepo, UsersRepo, get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as session:
        items_repo = ItemsRepo(session)
        users_repo = UsersRepo(session)

        total_items = await items_repo.count_items()
        curated_items = await items_repo.count_items(source="curated")
        tmdb_items = await items_repo.count_items(source="tmdb")

        # Count users (simple query)
        from sqlalchemy import func, select
        from app.storage.models import User
        result = await session.execute(select(func.count()).select_from(User))
        total_users = result.scalar() or 0

    return {
        "items": {
            "total": total_items,
            "curated": curated_items,
            "tmdb": tmdb_items,
        },
        "users": {
            "total": total_users,
        },
    }


@app.post("/admin/channel/post")
async def trigger_channel_post(
    _: None = Depends(verify_admin_token),
) -> dict:
    """Trigger an immediate channel post for testing."""
    from app.jobs.publish_posts import run_publish_post

    logger.info("Admin triggered channel post")

    try:
        result = await run_publish_post(slot_index=0)
        return {
            "ok": result.ok,
            "post_id": result.post_id,
            "format_id": result.format_id,
            "error": result.error,
        }
    except Exception as e:
        logger.exception(f"Admin channel post failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Channel post failed: {str(e)[:200]}",
        )


class MetricsIngestPayload(BaseModel):
    """Payload for manual metrics ingestion."""

    post_id: str
    captured_at: str  # ISO-8601
    views: int = 0
    reactions: int = 0
    forwards: int = 0
    unsub_delta: int = 0


@app.post("/admin/metrics/ingest")
async def ingest_metrics(
    payload: MetricsIngestPayload,
    _: None = Depends(verify_admin_token),
) -> dict:
    """Manually ingest a post_metrics snapshot."""
    from datetime import datetime, timezone

    from app.storage import EventsRepo, MetricsRepo, get_session_factory

    logger.info(f"Admin metrics ingest for post {payload.post_id}")

    try:
        captured_at = datetime.fromisoformat(payload.captured_at)
        if captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid captured_at format")

    session_factory = get_session_factory()
    async with session_factory() as session:
        metrics_repo = MetricsRepo(session)

        # Preserve existing bot_clicks if a snapshot already exists
        existing = await metrics_repo.get_latest_snapshot(payload.post_id)
        bot_clicks = existing.bot_clicks if existing else 0

        metric = await metrics_repo.insert_snapshot(
            post_id=payload.post_id,
            captured_at=captured_at,
            views=payload.views,
            reactions=payload.reactions,
            forwards=payload.forwards,
            bot_clicks=bot_clicks,
            unsub_delta=payload.unsub_delta,
        )

        events_repo = EventsRepo(session)
        await events_repo.log_event(
            event_name="metrics_ingested",
            post_id=payload.post_id,
            payload={
                "captured_at": captured_at.isoformat(),
                "views": payload.views,
                "reactions": payload.reactions,
                "forwards": payload.forwards,
                "unsub_delta": payload.unsub_delta,
            },
        )

    return {"ok": True, "metric_id": metric.id}


@app.get("/admin/posts/recent")
async def get_recent_posts(
    _: None = Depends(verify_admin_token),
) -> dict:
    """Return last 20 posts with computed score and bot_clicks."""
    import json

    from app.storage import MetricsRepo, PostsRepo, get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as session:
        posts_repo = PostsRepo(session)
        metrics_repo = MetricsRepo(session)

        posts = await posts_repo.list_recent_posts(days=30, limit=20)

        items = []
        for post in posts:
            snap = await metrics_repo.get_latest_snapshot(post.post_id)
            try:
                meta = json.loads(post.meta_json) if post.meta_json else {}
            except (json.JSONDecodeError, TypeError):
                meta = {}

            items.append({
                "post_id": post.post_id,
                "format_id": post.format_id,
                "hypothesis_id": post.hypothesis_id,
                "variant_id": post.variant_id,
                "published_at": post.published_at.isoformat() if post.published_at else None,
                "score": snap.score if snap else None,
                "bot_clicks": snap.bot_clicks if snap else 0,
                "views": snap.views if snap else 0,
                "reactions": snap.reactions if snap else 0,
                "text_preview": post.text[:80] if post.text else "",
                "deeplink": meta.get("deeplink"),
            })

    return {"ok": True, "posts": items}


@app.get("/admin/metrics/daily")
async def get_daily_metrics(
    days: int = 7,
    metric_name: str | None = None,
    _: None = Depends(verify_admin_token),
) -> dict:
    """Return daily metrics for the last N days."""
    from app.storage import DailyMetricsRepo, get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as session:
        repo = DailyMetricsRepo(session)
        metrics = await repo.list_metrics(metric_name=metric_name, days=days)

    return {
        "ok": True,
        "metrics": [
            {
                "date": m.date,
                "metric_name": m.metric_name,
                "value": m.value,
            }
            for m in metrics
        ],
    }


@app.get("/admin/metrics/latest")
async def get_latest_metrics(
    _: None = Depends(verify_admin_token),
) -> dict:
    """Return the latest value for each metric."""
    from app.storage import DailyMetricsRepo, get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as session:
        repo = DailyMetricsRepo(session)
        # Get all metrics from recent days, then deduplicate by name
        all_metrics = await repo.list_metrics(days=7)

    seen: dict[str, dict] = {}
    for m in all_metrics:
        if m.metric_name not in seen:
            seen[m.metric_name] = {
                "metric_name": m.metric_name,
                "value": m.value,
                "date": m.date,
            }

    return {"ok": True, "metrics": list(seen.values())}


@app.get("/admin/alerts")
async def get_alerts(
    unresolved_only: bool = True,
    limit: int = 50,
    _: None = Depends(verify_admin_token),
) -> dict:
    """Return recent alerts."""
    from app.storage import AlertsRepo, get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as session:
        repo = AlertsRepo(session)
        alerts = await repo.list_alerts(
            unresolved_only=unresolved_only,
            limit=limit,
        )

    return {
        "ok": True,
        "alerts": [
            {
                "id": a.id,
                "alert_type": a.alert_type,
                "severity": a.severity,
                "message": a.message,
                "created_at": a.created_at.isoformat(),
                "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
            }
            for a in alerts
        ],
    }


@app.get("/admin/slo/ttfr")
async def get_ttfr(
    date: str | None = None,
    _: None = Depends(verify_admin_token),
) -> dict:
    """Compute and return TTFR p50/p90 for a given date."""
    from app.observability.slo import compute_ttfr

    try:
        result = await compute_ttfr(date)
        return {"ok": True, **result}
    except Exception as e:
        logger.exception(f"TTFR computation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"TTFR computation failed: {str(e)[:200]}",
        )


@app.post("/admin/metrics/compute")
async def trigger_daily_metrics(
    date: str | None = None,
    _: None = Depends(verify_admin_token),
) -> dict:
    """Trigger immediate daily metrics computation."""
    from app.observability.runner import run_daily_metrics

    logger.info(f"Admin triggered daily metrics for {date or 'yesterday'}")

    try:
        result = await run_daily_metrics(date)
        return {"ok": True, **result}
    except Exception as e:
        logger.exception(f"Daily metrics computation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Metrics computation failed: {str(e)[:200]}",
        )


@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(token: str = "") -> HTMLResponse:
    """Serve the admin dashboard HTML page.

    The page itself is unprotected static HTML.
    All data fetches use the token passed via query param.
    """
    return HTMLResponse(content=_DASHBOARD_HTML.replace("__TOKEN__", token))


_DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>OnePick Movies — Панель керування</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0f1117;--surface:#1a1d27;--surface2:#242733;--border:#2e3140;
--text:#e1e4ed;--text2:#9399ad;--accent:#6c8cff;--accent2:#4ecdc4;
--green:#2ecc71;--yellow:#f39c12;--red:#e74c3c;--orange:#e67e22}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
background:var(--bg);color:var(--text);line-height:1.5;padding:16px 24px}
h1{font-size:1.5rem;font-weight:700;margin-bottom:4px}
.header{display:flex;justify-content:space-between;align-items:center;
margin-bottom:20px;padding-bottom:12px;border-bottom:1px solid var(--border)}
.header-left{display:flex;align-items:center;gap:12px}
.status{font-size:.8rem;color:var(--text2)}
.status .dot{display:inline-block;width:8px;height:8px;border-radius:50%;
background:var(--green);margin-right:4px;vertical-align:middle}
.section{margin-bottom:24px}
.section-title{font-size:1rem;font-weight:600;color:var(--text2);
margin-bottom:10px;text-transform:uppercase;letter-spacing:.5px;font-size:.8rem}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;
padding:14px 16px;transition:border-color .2s}
.card:hover{border-color:var(--accent)}
.card .label{font-size:.75rem;color:var(--text2);margin-bottom:4px;text-transform:uppercase;letter-spacing:.3px}
.card .value{font-size:1.5rem;font-weight:700;color:var(--text)}
.card .value.accent{color:var(--accent)}
.card .value.green{color:var(--green)}
.card .value.yellow{color:var(--yellow)}
.card .value.red{color:var(--red)}
.card .sub{font-size:.7rem;color:var(--text2);margin-top:2px}
table{width:100%;border-collapse:collapse;background:var(--surface);
border-radius:10px;overflow:hidden;border:1px solid var(--border)}
th{background:var(--surface2);font-size:.7rem;text-transform:uppercase;
letter-spacing:.5px;color:var(--text2);padding:10px 12px;text-align:left;font-weight:600}
td{padding:8px 12px;border-top:1px solid var(--border);font-size:.85rem}
tr:hover td{background:var(--surface2)}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.7rem;
font-weight:600;text-transform:uppercase}
.badge-critical{background:rgba(231,76,60,.15);color:var(--red)}
.badge-warning{background:rgba(243,156,18,.15);color:var(--yellow)}
.badge-info{background:rgba(108,140,255,.15);color:var(--accent)}
.badge-resolved{background:rgba(46,204,113,.15);color:var(--green)}
.badge-open{background:rgba(231,76,60,.15);color:var(--red)}
.error-banner{background:rgba(231,76,60,.1);border:1px solid var(--red);
border-radius:8px;padding:10px 14px;color:var(--red);font-size:.85rem;margin-bottom:16px;display:none}
.empty{color:var(--text2);font-style:italic;padding:20px;text-align:center}
.refresh-btn{background:var(--surface);border:1px solid var(--border);color:var(--text2);
padding:6px 14px;border-radius:6px;cursor:pointer;font-size:.8rem;transition:all .2s}
.refresh-btn:hover{border-color:var(--accent);color:var(--accent)}
@media(max-width:768px){body{padding:10px 12px}.cards{grid-template-columns:1fr 1fr}
table{font-size:.75rem}th,td{padding:6px 8px}}
</style>
</head>
<body>
<div class="header">
 <div class="header-left">
  <h1>OnePick Movies</h1>
  <span class="status"><span class="dot"></span>Панель керування</span>
 </div>
 <div>
  <span class="status" id="last-update"></span>
  <button class="refresh-btn" onclick="loadAll()">Оновити</button>
 </div>
</div>
<div class="error-banner" id="error-banner"></div>

<div class="section" id="s-system">
 <div class="section-title">Система</div>
 <div class="cards" id="system-cards"></div>
</div>

<div class="section" id="s-bot">
 <div class="section-title">Бот — метрики</div>
 <div class="cards" id="bot-cards"></div>
</div>

<div class="section" id="s-channel">
 <div class="section-title">Канал — метрики</div>
 <div class="cards" id="channel-cards"></div>
</div>

<div class="section" id="s-slo">
 <div class="section-title">TTFR SLO</div>
 <div class="cards" id="slo-cards"></div>
</div>

<div class="section" id="s-posts">
 <div class="section-title">Останні пости</div>
 <div id="posts-table"></div>
</div>

<div class="section" id="s-alerts">
 <div class="section-title">Сповіщення</div>
 <div id="alerts-table"></div>
</div>

<script>
const TOKEN = "__TOKEN__";
const BASE = window.location.origin;

function authHeaders() {
  return { "Authorization": "Bearer " + TOKEN };
}

async function api(path) {
  const r = await fetch(BASE + path, { headers: authHeaders() });
  if (!r.ok) throw new Error(path + " → " + r.status);
  return r.json();
}

function card(label, value, cls, sub) {
  return '<div class="card"><div class="label">' + esc(label) + '</div>' +
    '<div class="value ' + (cls||'') + '">' + esc(String(value)) + '</div>' +
    (sub ? '<div class="sub">' + esc(sub) + '</div>' : '') + '</div>';
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function timeAgo(iso) {
  if (!iso) return "—";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return Math.round(diff) + " сек тому";
  if (diff < 3600) return Math.round(diff / 60) + " хв тому";
  if (diff < 86400) return Math.round(diff / 3600) + " год тому";
  return Math.round(diff / 86400) + " дн тому";
}

function severityBadge(s) {
  const cls = s === 'critical' ? 'badge-critical' : s === 'warning' ? 'badge-warning' : 'badge-info';
  return '<span class="badge ' + cls + '">' + esc(s) + '</span>';
}

function showError(msg) {
  const el = document.getElementById('error-banner');
  el.textContent = msg;
  el.style.display = 'block';
}

function clearError() {
  document.getElementById('error-banner').style.display = 'none';
}

async function loadSystem() {
  try {
    const data = await api('/admin/stats');
    const el = document.getElementById('system-cards');
    el.innerHTML =
      card('Всього контенту', data.items?.total ?? '—', 'accent') +
      card('Курований', data.items?.curated ?? '—', '') +
      card('TMDB', data.items?.tmdb ?? '—', '') +
      card('Користувачів', data.users?.total ?? '—', 'accent');
  } catch (e) { showError('Система: ' + e.message); }
}

async function loadBotMetrics() {
  try {
    const data = await api('/admin/metrics/latest');
    const el = document.getElementById('bot-cards');
    const m = {};
    (data.metrics || []).forEach(function(x) { m[x.metric_name] = x; });
    el.innerHTML =
      card('DAU', m.dau?.value ?? '—', 'accent', m.dau?.date || '') +
      card('Сесії', m.sessions?.value ?? '—', '', m.sessions?.date || '') +
      card('Hit rate', m.hit_rate?.value != null ? (m.hit_rate.value * 100).toFixed(1) + '%' : '—',
           (m.hit_rate?.value ?? 0) > 0.5 ? 'green' : 'yellow', m.hit_rate?.date || '') +
      card('Miss rate', m.miss_rate?.value != null ? (m.miss_rate.value * 100).toFixed(1) + '%' : '—',
           (m.miss_rate?.value ?? 0) > 0.3 ? 'red' : 'green', m.miss_rate?.date || '') +
      card('Обрані', m.favorites?.value ?? '—', '', m.favorites?.date || '') +
      card('Поділились', m.shares?.value ?? '—', '', m.shares?.date || '');
  } catch (e) { showError('Бот: ' + e.message); }
}

async function loadChannelMetrics() {
  try {
    const data = await api('/admin/metrics/latest');
    const el = document.getElementById('channel-cards');
    const m = {};
    (data.metrics || []).forEach(function(x) { m[x.metric_name] = x; });
    el.innerHTML =
      card('Опубліковано постів', m.posts_published?.value ?? '—', 'accent',
           m.posts_published?.date || '') +
      card('Середній score', m.avg_score?.value != null ? Number(m.avg_score.value).toFixed(1) : '—',
           '', m.avg_score?.date || '') +
      card('Bot clicks', m.bot_clicks?.value ?? '—', 'accent', m.bot_clicks?.date || '') +
      card('Реакцій', m.reactions?.value ?? '—', '', m.reactions?.date || '') +
      card('Пересилань', m.forwards?.value ?? '—', '', m.forwards?.date || '');
  } catch (e) { showError('Канал: ' + e.message); }
}

async function loadSLO() {
  try {
    const data = await api('/admin/slo/ttfr');
    const el = document.getElementById('slo-cards');
    el.innerHTML =
      card('TTFR p50', data.p50 != null ? data.p50.toFixed(2) + ' с' : '—',
           (data.p50 ?? 99) < 3 ? 'green' : 'red') +
      card('TTFR p90', data.p90 != null ? data.p90.toFixed(2) + ' с' : '—',
           (data.p90 ?? 99) < 5 ? 'green' : 'yellow') +
      card('Вибірка', data.sample_count ?? '—', '', data.date || '');
  } catch (e) { showError('SLO: ' + e.message); }
}

async function loadPosts() {
  try {
    const data = await api('/admin/posts/recent');
    const el = document.getElementById('posts-table');
    const posts = data.posts || [];
    if (!posts.length) { el.innerHTML = '<div class="empty">Постів поки немає</div>'; return; }
    let h = '<table><thead><tr><th>ID</th><th>Формат</th><th>Варіант</th>' +
            '<th>Опубліковано</th><th>Score</th><th>Реакції</th><th>Перегляди</th>' +
            '<th>Bot clicks</th></tr></thead><tbody>';
    posts.forEach(function(p) {
      h += '<tr><td>' + esc(p.post_id || '') + '</td>' +
        '<td>' + esc(p.format_id || '') + '</td>' +
        '<td>' + esc(p.variant_id || '') + '</td>' +
        '<td>' + (p.published_at ? timeAgo(p.published_at) : '—') + '</td>' +
        '<td>' + (p.score != null ? Number(p.score).toFixed(1) : '—') + '</td>' +
        '<td>' + (p.reactions ?? 0) + '</td>' +
        '<td>' + (p.views ?? 0) + '</td>' +
        '<td>' + (p.bot_clicks ?? 0) + '</td></tr>';
    });
    h += '</tbody></table>';
    el.innerHTML = h;
  } catch (e) { showError('Пости: ' + e.message); }
}

async function loadAlerts() {
  try {
    const data = await api('/admin/alerts?unresolved_only=false&limit=20');
    const el = document.getElementById('alerts-table');
    const alerts = data.alerts || [];
    if (!alerts.length) { el.innerHTML = '<div class="empty">Сповіщень немає</div>'; return; }
    let h = '<table><thead><tr><th>Тип</th><th>Рівень</th><th>Повідомлення</th>' +
            '<th>Створено</th><th>Статус</th></tr></thead><tbody>';
    alerts.forEach(function(a) {
      const resolved = a.resolved_at != null;
      h += '<tr><td>' + esc(a.alert_type || '') + '</td>' +
        '<td>' + severityBadge(a.severity || 'info') + '</td>' +
        '<td>' + esc(a.message || '') + '</td>' +
        '<td>' + timeAgo(a.created_at) + '</td>' +
        '<td><span class="badge ' + (resolved ? 'badge-resolved' : 'badge-open') + '">' +
        (resolved ? 'Вирішено' : 'Відкрито') + '</span></td></tr>';
    });
    h += '</tbody></table>';
    el.innerHTML = h;
  } catch (e) { showError('Сповіщення: ' + e.message); }
}

async function loadAll() {
  clearError();
  await Promise.allSettled([
    loadSystem(),
    loadBotMetrics(),
    loadChannelMetrics(),
    loadSLO(),
    loadPosts(),
    loadAlerts(),
  ]);
  document.getElementById('last-update').textContent =
    'Оновлено: ' + new Date().toLocaleTimeString('uk-UA');
}

// Initial load
loadAll();

// Auto-refresh every 60s
setInterval(loadAll, 60000);
</script>
</body>
</html>
"""


async def run_polling() -> None:
    """Run the bot in polling mode."""
    logger.info("Starting bot in polling mode")

    # Ensure all tables exist
    from app.storage.db import Base, get_engine
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured")

    # Start scheduler and setup jobs
    start_scheduler()
    setup_all_jobs()

    try:
        await dp.start_polling(
            bot,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query", "message_reaction_count"],
        )
    finally:
        shutdown_scheduler()
        await bot.session.close()
        logger.info("Polling stopped, bot session closed")


def main() -> None:
    """Main entrypoint supporting both polling and webhook modes."""
    if len(sys.argv) > 1 and sys.argv[1] == "polling":
        asyncio.run(run_polling())
    elif config.bot_mode == "polling" and len(sys.argv) == 1:
        asyncio.run(run_polling())
    else:
        logger.info(f"Starting FastAPI server on {config.host}:{config.port}")
        uvicorn.run(
            "app.main:app",
            host=config.host,
            port=config.port,
            reload=False,
        )


if __name__ == "__main__":
    main()
