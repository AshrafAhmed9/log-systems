import pg8000.native
import os
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    return pg8000.native.Connection(
        host="localhost",
        port=5434,
        user="loguser",
        password="logpass",
        database="logsdb",
    )


def query_logs(service_name=None, log_level=None, start_time=None, end_time=None, limit=100):
    conn = get_connection()

    filters = ["1=1"]
    params = {}

    if service_name:
        filters.append("service_name = :service")
        params["service"] = service_name
    if log_level:
        filters.append("log_level = :level")
        params["level"] = log_level
    if start_time:
        filters.append("timestamp >= :start")
        params["start"] = start_time
    if end_time:
        filters.append("timestamp <= :end")
        params["end"] = end_time

    where = " AND ".join(filters)
    sql = f"SELECT id, log_id, service_name, log_level, message, timestamp, latency_ms FROM logs WHERE {where} ORDER BY timestamp DESC LIMIT :limit"
    params["limit"] = limit

    rows = conn.run(sql, **params)
    conn.close()

    return [
        {
            "id": r[0], "log_id": str(r[1]), "service_name": r[2],
            "log_level": r[3], "message": r[4],
            "timestamp": r[5].isoformat() if r[5] else None,
            "latency_ms": r[6],
        }
        for r in rows
    ]


def query_error_rate(window_seconds=60):
    conn = get_connection()
    rows = conn.run(
        """
        SELECT
            service_name,
            COUNT(*) AS total,
            SUM(CASE WHEN log_level = 'ERROR' THEN 1 ELSE 0 END) AS errors
        FROM logs
        WHERE timestamp >= NOW() - INTERVAL '1 second' * :window
        GROUP BY service_name
        """,
        window=window_seconds,
    )
    conn.close()

    result = []
    for r in rows:
        total = r[1]
        errors = r[2]
        rate = round((errors / total) * 100, 2) if total > 0 else 0.0
        result.append({"service_name": r[0], "total": total, "errors": errors, "error_rate_pct": rate})
    return result


def query_top_errors(limit=10):
    conn = get_connection()
    rows = conn.run(
        """
        SELECT service_name, COUNT(*) AS error_count
        FROM logs
        WHERE log_level = 'ERROR'
        GROUP BY service_name
        ORDER BY error_count DESC
        LIMIT :limit
        """,
        limit=limit,
    )
    conn.close()
    return [{"service_name": r[0], "error_count": r[1]} for r in rows]


def query_trends(window_minutes=10):
    conn = get_connection()
    rows = conn.run(
        """
        SELECT
            date_trunc('minute', timestamp) AS bucket,
            COUNT(*) AS total,
            SUM(CASE WHEN log_level = 'ERROR' THEN 1 ELSE 0 END) AS errors
        FROM logs
        WHERE timestamp >= NOW() - INTERVAL '1 minute' * :window
        GROUP BY bucket
        ORDER BY bucket
        """,
        window=window_minutes,
    )
    conn.close()

    buckets = [
        {"minute": r[0].isoformat(), "total": r[1], "errors": r[2]}
        for r in rows
    ]

    if buckets:
        avg = sum(b["total"] for b in buckets) / len(buckets)
        for b in buckets:
            b["is_spike"] = b["total"] > avg * 2

    return buckets


def count_logs():
    conn = get_connection()
    result = conn.run("SELECT COUNT(*) FROM logs")
    conn.close()
    return result[0][0]
