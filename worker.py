import os
import redis
import pg8000.native
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

STREAM    = "logs:stream"
GROUP     = "log-workers"
CONSUMER  = "worker-1"
THRESHOLD = float(os.getenv("ALERT_THRESHOLD_PCT", 20))
WINDOW    = int(os.getenv("ALERT_WINDOW_SECONDS", 60))


def create_group(r):
    try:
        r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
        print("Consumer group created.")
    except Exception as e:
        if "BUSYGROUP" not in str(e):
            raise


def get_db():
    return pg8000.native.Connection(
        host="localhost", port=5434,
        user="loguser", password="logpass", database="logsdb",
    )


def insert_batch(conn, messages):
    rows = []
    for message_id, fields in messages:
        try:
            ingested = datetime.fromisoformat(fields[b"ingested_at"].decode())
            latency = int((datetime.utcnow() - ingested).total_seconds() * 1000)
        except Exception:
            latency = None

        rows.append((
            fields[b"log_id"].decode(),
            fields[b"service_name"].decode(),
            fields[b"log_level"].decode(),
            fields[b"message"].decode(),
            fields[b"timestamp"].decode(),
            fields[b"ingested_at"].decode(),
            latency,
        ))

    for row in rows:
        conn.run(
            """
            INSERT INTO logs (log_id, service_name, log_level, message, timestamp, ingested_at, latency_ms)
            VALUES (:log_id, :service, :level, :msg, :ts::timestamptz, :ingested::timestamptz, :latency)
            ON CONFLICT (log_id) DO NOTHING
            """,
            log_id=row[0], service=row[1], level=row[2],
            msg=row[3], ts=row[4], ingested=row[5], latency=row[6],
        )

    print(f"Inserted {len(rows)} log(s) into DB.")


def check_alerts(conn):
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
        window=WINDOW,
    )

    for r in rows:
        service, total, errors = r[0], r[1], r[2]
        if total == 0:
            continue
        rate = (errors / total) * 100
        if rate > THRESHOLD:
            print(
                f"[ALERT] {service} error rate {rate:.1f}% "
                f"exceeds threshold {THRESHOLD}% "
                f"(window={WINDOW}s, errors={errors}/{total})"
            )


def run_worker(r):
    print("Worker started. Waiting for logs...")
    while True:
        results = r.xreadgroup(
            groupname=GROUP,
            consumername=CONSUMER,
            streams={STREAM: ">"},
            count=10,
            block=2000,
        )

        if not results:
            continue

        conn = get_db()
        for stream_name, messages in results:
            insert_batch(conn, messages)
            ids = [msg_id for msg_id, _ in messages]
            r.xack(STREAM, GROUP, *ids)

        check_alerts(conn)
        conn.close()


def main():
    r = redis.from_url(os.getenv("REDIS_URL"))
    create_group(r)
    run_worker(r)


if __name__ == "__main__":
    main()
