-- Tiger Data (TimescaleDB) schema for CME futures settlements. Idempotent.
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS cme_settlements (
    trade_date date NOT NULL,
    product_id text NOT NULL,
    ym int NOT NULL,
    settle double precision,
    volume double precision,
    oi double precision,
    PRIMARY KEY (product_id, ym, trade_date)
);

SELECT create_hypertable('cme_settlements', 'trade_date', if_not_exists => TRUE);

CREATE MATERIALIZED VIEW IF NOT EXISTS cme_settlements_weekly
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 week', trade_date) AS week,
       product_id,
       ym,
       avg(settle) AS avg_settle,
       last(settle, trade_date) AS last_settle,
       sum(volume) AS volume
FROM cme_settlements
GROUP BY week, product_id, ym
WITH NO DATA;

SELECT add_continuous_aggregate_policy('cme_settlements_weekly',
    start_offset => INTERVAL '3 months',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day',
    if_not_exists => TRUE);

-- front settle and the 2nd/3rd listed contracts vs the front (M+1 / M+2 / M+3 QP choice)
CREATE OR REPLACE VIEW curve_spreads AS
WITH ranked AS (
    SELECT trade_date, product_id, ym, settle,
           row_number() OVER (PARTITION BY product_id, trade_date ORDER BY ym) AS rn
    FROM cme_settlements
    WHERE settle IS NOT NULL
)
SELECT trade_date, product_id,
       max(ym) FILTER (WHERE rn = 1) AS front_ym,
       max(settle) FILTER (WHERE rn = 1) AS front_settle,
       max(settle) FILTER (WHERE rn = 2) - max(settle) FILTER (WHERE rn = 1) AS spread_2,
       max(settle) FILTER (WHERE rn = 3) - max(settle) FILTER (WHERE rn = 1) AS spread_3
FROM ranked
WHERE rn <= 3
GROUP BY trade_date, product_id
ORDER BY trade_date, product_id;
