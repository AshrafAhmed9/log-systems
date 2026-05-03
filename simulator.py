import asyncio
import httpx
import random
import time
from datetime import datetime, timezone

API_URL  = "http://localhost:8000/logs"
SERVICES = ["auth-service", "payment-service", "recommendation-service"]
LEVELS   = ["INFO", "INFO", "INFO", "WARNING", "ERROR"]
MESSAGES = {
    "INFO":    ["Request processed", "User logged in", "Cache hit", "Health check ok"],
    "WARNING": ["High memory usage", "Slow query detected", "Retry attempt"],
    "ERROR":   ["Connection timeout", "Transaction failed", "Model error", "DB write failed"],
}

TARGET_RPS     = 500
DURATION_SEC   = 30
CONCURRENCY    = 50


async def send_log(client: httpx.AsyncClient, start_times: list):
    service = random.choice(SERVICES)
    level   = random.choice(LEVELS)
    message = random.choice(MESSAGES[level])

    payload = {
        "service_name": service,
        "log_level":    level,
        "message":      message,
        "timestamp":    datetime.now(timezone.utc).isoformat(),
    }

    t0 = time.perf_counter()
    try:
        r = await client.post(API_URL, json=payload, timeout=5.0)
        latency_ms = (time.perf_counter() - t0) * 1000
        if r.status_code == 202:
            start_times.append(latency_ms)
    except Exception:
        pass


async def run():
    latencies = []
    sent      = 0
    start     = time.perf_counter()
    delay     = 1.0 / TARGET_RPS

    async with httpx.AsyncClient() as client:
        tasks = []
        while time.perf_counter() - start < DURATION_SEC:
            task = asyncio.create_task(send_log(client, latencies))
            tasks.append(task)
            sent += 1

            if len(tasks) >= CONCURRENCY:
                await asyncio.gather(*tasks)
                tasks = []

            await asyncio.sleep(delay)

        if tasks:
            await asyncio.gather(*tasks)

    elapsed = time.perf_counter() - start
    rps     = sent / elapsed

    latencies.sort()
    p50 = latencies[int(len(latencies) * 0.50)] if latencies else 0
    p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0

    print(f"\n--- Load Test Results ---")
    print(f"Duration:      {elapsed:.1f}s")
    print(f"Logs sent:     {sent}")
    print(f"Throughput:    {rps:.0f} logs/sec")
    print(f"Latency P50:   {p50:.1f}ms")
    print(f"Latency P99:   {p99:.1f}ms")
    print(f"Success count: {len(latencies)}")


if __name__ == "__main__":
    asyncio.run(run())
