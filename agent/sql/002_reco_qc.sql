CREATE TABLE IF NOT EXISTS market.reco_qc_log (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trade_date date NOT NULL,
    strategy_name text NOT NULL,
    check_name text NOT NULL,
    status text NOT NULL,
    detail_json jsonb,
    threshold_json jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reco_qc_trade_strategy_check
    ON market.reco_qc_log (trade_date, strategy_name, check_name);
