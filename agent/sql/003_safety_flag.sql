ALTER TABLE market.agent_run_log
    ADD COLUMN IF NOT EXISTS safety_flag boolean DEFAULT false;
