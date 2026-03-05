CREATE SCHEMA IF NOT EXISTS market;

CREATE TABLE IF NOT EXISTS market.agent_run_log (
    run_id uuid NOT NULL,
    session_id text,
    user_query text NOT NULL,
    plan_json jsonb,
    result_summary text,
    status text NOT NULL DEFAULT 'running',
    llm_provider text,
    total_tokens integer DEFAULT 0,
    safety_flag boolean DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    error_text text,
    CONSTRAINT agent_run_log_pkey PRIMARY KEY (run_id)
);

CREATE INDEX IF NOT EXISTS idx_agent_run_log_session_created
    ON market.agent_run_log (session_id, created_at DESC);

CREATE TABLE IF NOT EXISTS market.tool_call_log (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES market.agent_run_log(run_id),
    step_index integer NOT NULL,
    tool_name text NOT NULL,
    params_json jsonb,
    result_json jsonb,
    status text NOT NULL DEFAULT 'running',
    latency_ms integer,
    error_text text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tool_call_log_run_step
    ON market.tool_call_log (run_id, step_index);

CREATE TABLE IF NOT EXISTS market.reco_daily (
    symbol text NOT NULL,
    trade_date date NOT NULL,
    strategy_name text NOT NULL,
    score double precision,
    confidence double precision,
    rank integer,
    reason_json jsonb,
    model_version text,
    data_cutoff date,
    code_version text,
    params_hash text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT reco_daily_pkey PRIMARY KEY (symbol, trade_date, strategy_name)
);

CREATE INDEX IF NOT EXISTS idx_reco_daily_date_strategy_score
    ON market.reco_daily (trade_date, strategy_name, score DESC);

CREATE INDEX IF NOT EXISTS idx_reco_daily_symbol_trade_date
    ON market.reco_daily (symbol, trade_date DESC);
