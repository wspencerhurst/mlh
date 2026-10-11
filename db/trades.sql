-- Trade blotter for the mock Checker desk. Idempotent; run with psql -f (not inside a transaction).
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS trades (
	id uuid NOT NULL DEFAULT gen_random_uuid(),
	executed_at timestamptz NOT NULL DEFAULT now(),
	instrument text NOT NULL,
	side text NOT NULL,
	quantity double precision NOT NULL,
	reference_price double precision NOT NULL,
	scenario text NOT NULL,
	ok boolean NOT NULL,
	error_code text,
	error_step text,
	provider text,
	order_status text,
	payment_status text,
	filled_quantity double precision NOT NULL DEFAULT 0,
	notional_usd double precision,
	sentry_event_id text,
	result jsonb NOT NULL,
	PRIMARY KEY (id, executed_at)
);

SELECT create_hypertable('trades', 'executed_at', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS trades_instrument_time_idx ON trades (instrument, executed_at DESC);

CREATE MATERIALIZED VIEW IF NOT EXISTS trades_daily
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT
	time_bucket('1 day', executed_at) AS day,
	instrument,
	count(*) AS trades,
	count(*) FILTER (WHERE NOT ok) AS failures,
	sum(filled_quantity) AS filled_quantity,
	sum(notional_usd) AS notional_usd
FROM trades
GROUP BY 1, 2
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
	'trades_daily',
	start_offset => INTERVAL '3 days',
	end_offset => INTERVAL '1 hour',
	schedule_interval => INTERVAL '1 hour',
	if_not_exists => TRUE
);
