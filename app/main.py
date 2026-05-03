import uuid
import os
from datetime import datetime
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
import redis.asyncio as aioredis
from app.database import query_logs, query_error_rate, query_top_errors, query_trends, count_logs

load_dotenv()

app = FastAPI(title="Log Ingestion API")

redis_client = None


@app.on_event("startup")
async def startup():
    global redis_client
    redis_client = aioredis.from_url(os.getenv("REDIS_URL"))


@app.on_event("shutdown")
async def shutdown():
    await redis_client.aclose()


class LogEvent(BaseModel):
    service_name: str
    log_level: str
    message: str
    timestamp: datetime


@app.post("/logs", status_code=202)
async def ingest_log(log: LogEvent):
    log_id = str(uuid.uuid4())

    payload = {
        "log_id": log_id,
        "service_name": log.service_name,
        "log_level": log.log_level,
        "message": log.message,
        "timestamp": log.timestamp.isoformat(),
        "ingested_at": datetime.utcnow().isoformat(),
    }

    try:
        await redis_client.xadd("logs:stream", payload)
    except Exception as e:
        raise HTTPException(status_code=503, detail="Queue unavailable")

    return {"status": "queued", "log_id": log_id}


@app.get("/health")
async def health():
    try:
        await redis_client.ping()
        redis_status = "ok"
    except Exception:
        redis_status = "error"
    return {"api": "ok", "redis": redis_status}


@app.get("/internal/metrics")
async def internal_metrics():
    try:
        queue_depth = await redis_client.xlen("logs:stream")
        redis_status = "ok"
    except Exception:
        queue_depth = -1
        redis_status = "error"

    try:
        total_logs = count_logs()
        db_status = "ok"
    except Exception:
        total_logs = -1
        db_status = "error"

    return {
        "queue_depth":      queue_depth,
        "total_logs_in_db": total_logs,
        "redis_status":     redis_status,
        "db_status":        db_status,
    }


@app.get("/logs")
async def get_logs(
    service_name: Optional[str] = Query(None),
    log_level: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    limit: int = Query(100),
):
    return {"logs": query_logs(service_name, log_level, start_time, end_time, limit)}


@app.get("/analytics/error-rate")
async def error_rate(window_seconds: int = Query(60)):
    return {"window_seconds": window_seconds, "services": query_error_rate(window_seconds)}


@app.get("/analytics/top-errors")
async def top_errors():
    return {"top_services": query_top_errors()}


@app.get("/analytics/trends")
async def trends(window_minutes: int = Query(10)):
    return {"window_minutes": window_minutes, "buckets": query_trends(window_minutes)}
