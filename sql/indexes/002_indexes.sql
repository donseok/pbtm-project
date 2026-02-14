CREATE INDEX IF NOT EXISTS idx_relations_type_src_dst
    ON relations (relation_type, src_id, dst_id);

CREATE INDEX IF NOT EXISTS idx_sql_tables_table_name
    ON sql_tables (table_name);

CREATE INDEX IF NOT EXISTS idx_objects_run_type_name
    ON objects (run_id, type, name);

CREATE INDEX IF NOT EXISTS idx_events_run_object
    ON events (run_id, object_id);

CREATE INDEX IF NOT EXISTS idx_functions_run_object
    ON functions (run_id, object_id);

CREATE INDEX IF NOT EXISTS idx_runs_started_at
    ON runs (started_at);

CREATE INDEX IF NOT EXISTS idx_sql_statements_owner
    ON sql_statements (run_id, owner_id);

CREATE INDEX IF NOT EXISTS idx_relations_run_id
    ON relations (run_id);

CREATE INDEX IF NOT EXISTS idx_data_windows_run_object
    ON data_windows (run_id, object_id);
