CREATE TABLE IF NOT EXISTS logs (
    id           BIGSERIAL PRIMARY KEY,
    log_id       UUID NOT NULL UNIQUE,
    service_name VARCHAR(100) NOT NULL,
    log_level    VARCHAR(20) NOT NULL,
    message      TEXT NOT NULL,
    timestamp    TIMESTAMPTZ NOT NULL,
    ingested_at  TIMESTAMPTZ NOT NULL,
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    latency_ms   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_logs_service   ON logs (service_name);
CREATE INDEX IF NOT EXISTS idx_logs_level     ON logs (log_level);
CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs (timestamp DESC);
