ALTER TABLE market.agent_run_log
    ADD COLUMN IF NOT EXISTS resumed_from_run_id uuid REFERENCES market.agent_run_log(run_id);

ALTER TABLE market.agent_run_log
    ADD COLUMN IF NOT EXISTS resume_completed_steps integer NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_agent_run_log_resumed_from
    ON market.agent_run_log (resumed_from_run_id);
