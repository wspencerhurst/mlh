-- Snowflake schema for the Goldmine warehouse. Idempotent; applied by qp_hedge/warehouse.py.
CREATE DATABASE IF NOT EXISTS goldmine;
USE SCHEMA goldmine.public;

CREATE TABLE IF NOT EXISTS cme_settlements (
    trade_date DATE NOT NULL,
    product_id STRING NOT NULL,
    ym INT NOT NULL,
    settle FLOAT,
    volume FLOAT,
    oi FLOAT
);

CREATE TABLE IF NOT EXISTS backtest_episodes (
    market STRING NOT NULL,
    policy STRING NOT NULL,
    delivery INT NOT NULL,
    elected STRING,
    elect_date STRING,
    pnl FLOAT,
    pnl_unit FLOAT,
    physical_unit FLOAT,
    futures_unit FLOAT,
    costs_unit FLOAT,
    financing_unit FLOAT
);

CREATE TABLE IF NOT EXISTS recommendations (
    market STRING NOT NULL,
    asof DATE NOT NULL,
    qp STRING NOT NULL,
    qp_month STRING,
    qp_ym INT,
    hedged_value FLOAT,
    is_best BOOLEAN,
    declare_now BOOLEAN,
    unit STRING
);

-- front settle and the 2nd/3rd listed contracts vs the front (M+1 / M+2 / M+3 QP choice)
CREATE OR REPLACE VIEW curve_spreads AS
WITH ranked AS (
    SELECT trade_date, product_id, ym, settle,
           ROW_NUMBER() OVER (PARTITION BY product_id, trade_date ORDER BY ym) AS rn
    FROM cme_settlements
    WHERE settle IS NOT NULL
)
SELECT trade_date, product_id,
       MAX(IFF(rn = 1, ym, NULL)) AS front_ym,
       MAX(IFF(rn = 1, settle, NULL)) AS front_settle,
       MAX(IFF(rn = 2, settle, NULL)) - MAX(IFF(rn = 1, settle, NULL)) AS spread_2,
       MAX(IFF(rn = 3, settle, NULL)) - MAX(IFF(rn = 1, settle, NULL)) AS spread_3
FROM ranked
WHERE rn <= 3
GROUP BY trade_date, product_id;

-- per market and policy: realized value per unit over the walk-forward test period
CREATE OR REPLACE VIEW policy_scorecard AS
SELECT market, policy,
       COUNT(*) AS cargoes,
       AVG(pnl_unit) AS mean_unit,
       STDDEV(pnl_unit) AS std_unit,
       MIN(pnl_unit) AS worst_unit,
       PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY pnl_unit) AS p5_unit,
       SUM(pnl) / 1e6 AS total_pnl_musd
FROM backtest_episodes
GROUP BY market, policy;

-- which QP each policy elected, by market
CREATE OR REPLACE VIEW qp_elections AS
SELECT market, policy, elected, COUNT(*) AS cargoes,
       RATIO_TO_REPORT(COUNT(*)) OVER (PARTITION BY market, policy) AS share
FROM backtest_episodes
GROUP BY market, policy, elected;

CREATE STAGE IF NOT EXISTS app;
