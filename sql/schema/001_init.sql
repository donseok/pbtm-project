PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    source_version TEXT
);

CREATE TABLE IF NOT EXISTS objects (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    module TEXT,
    source_path TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id),
    UNIQUE (run_id, type, name)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    object_id INTEGER NOT NULL,
    event_name TEXT NOT NULL,
    script_ref TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id),
    FOREIGN KEY (object_id) REFERENCES objects(id)
);

CREATE TABLE IF NOT EXISTS functions (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    object_id INTEGER NOT NULL,
    function_name TEXT NOT NULL,
    signature TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id),
    FOREIGN KEY (object_id) REFERENCES objects(id)
);

CREATE TABLE IF NOT EXISTS relations (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    src_id INTEGER NOT NULL,
    dst_id INTEGER NOT NULL,
    relation_type TEXT NOT NULL CHECK (
        relation_type IN (
            'calls',
            'opens',
            'uses_dw',
            'reads_table',
            'writes_table',
            'triggers_event'
        )
    ),
    confidence REAL NOT NULL DEFAULT 1.0 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    FOREIGN KEY (run_id) REFERENCES runs(run_id),
    FOREIGN KEY (src_id) REFERENCES objects(id),
    FOREIGN KEY (dst_id) REFERENCES objects(id)
);

CREATE TABLE IF NOT EXISTS sql_statements (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    owner_id INTEGER NOT NULL,
    sql_text_norm TEXT NOT NULL,
    sql_kind TEXT NOT NULL CHECK (sql_kind IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'MERGE', 'OTHER')),
    FOREIGN KEY (run_id) REFERENCES runs(run_id),
    FOREIGN KEY (owner_id) REFERENCES objects(id)
);

CREATE TABLE IF NOT EXISTS sql_tables (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    sql_id INTEGER NOT NULL,
    table_name TEXT NOT NULL,
    rw_type TEXT NOT NULL CHECK (rw_type IN ('READ', 'WRITE')),
    FOREIGN KEY (run_id) REFERENCES runs(run_id),
    FOREIGN KEY (sql_id) REFERENCES sql_statements(id)
);

CREATE TABLE IF NOT EXISTS data_windows (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    object_id INTEGER NOT NULL,
    dw_name TEXT NOT NULL,
    base_table TEXT,
    sql_select TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id),
    FOREIGN KEY (object_id) REFERENCES objects(id),
    UNIQUE (run_id, object_id, dw_name)
);
