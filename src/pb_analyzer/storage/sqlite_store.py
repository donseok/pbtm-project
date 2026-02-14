"""SQLite storage implementation for PB Analyzer IR."""

from __future__ import annotations

from pathlib import Path
import sqlite3

from pb_analyzer.common import AnalysisResult, PersistResult, RunContext, UserInputError


def persist_analysis(db_path: Path, run_context: RunContext, analysis: AnalysisResult) -> PersistResult:
    """Persists analysis records into SQLite."""

    _validate_db_path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        _initialize_schema(conn)

        conn.execute(
            """
            INSERT INTO runs (run_id, started_at, finished_at, status, source_version)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                run_context.run_id,
                run_context.started_at,
                run_context.finished_at,
                run_context.status,
                run_context.source_version,
            ),
        )

        object_name_to_id: dict[str, int] = {}
        objects_count = 0
        for object_item in analysis.objects:
            cursor = conn.execute(
                """
                INSERT INTO objects (run_id, type, name, module, source_path)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    run_context.run_id,
                    object_item.object_type,
                    object_item.name,
                    object_item.module,
                    object_item.source_path,
                ),
            )
            if cursor.lastrowid is None:
                continue
            object_id = cursor.lastrowid
            object_name_to_id.setdefault(object_item.name.lower(), object_id)
            objects_count += 1

        events_count = 0
        for event_item in analysis.events:
            ev_object_id = object_name_to_id.get(event_item.object_name.lower())
            if ev_object_id is None:
                continue
            conn.execute(
                """
                INSERT INTO events (run_id, object_id, event_name, script_ref)
                VALUES (?, ?, ?, ?)
                """,
                (run_context.run_id, ev_object_id, event_item.event_name, event_item.script_ref),
            )
            events_count += 1

        functions_count = 0
        for function_item in analysis.functions:
            fn_object_id = object_name_to_id.get(function_item.object_name.lower())
            if fn_object_id is None:
                continue
            conn.execute(
                """
                INSERT INTO functions (run_id, object_id, function_name, signature)
                VALUES (?, ?, ?, ?)
                """,
                (
                    run_context.run_id,
                    fn_object_id,
                    function_item.function_name,
                    function_item.signature,
                ),
            )
            functions_count += 1

        relations_count = 0
        for relation_item in analysis.relations:
            src_id = object_name_to_id.get(relation_item.src_name.lower())
            dst_id = object_name_to_id.get(relation_item.dst_name.lower())
            if src_id is None or dst_id is None:
                continue
            conn.execute(
                """
                INSERT INTO relations (run_id, src_id, dst_id, relation_type, confidence)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    run_context.run_id,
                    src_id,
                    dst_id,
                    relation_item.relation_type,
                    relation_item.confidence,
                ),
            )
            relations_count += 1

        sql_statements_count = 0
        sql_tables_count = 0
        for statement_item in analysis.sql_statements:
            owner_id = object_name_to_id.get(statement_item.owner_name.lower())
            if owner_id is None:
                continue

            cursor = conn.execute(
                """
                INSERT INTO sql_statements (run_id, owner_id, sql_text_norm, sql_kind)
                VALUES (?, ?, ?, ?)
                """,
                (
                    run_context.run_id,
                    owner_id,
                    statement_item.sql_text_norm,
                    statement_item.sql_kind,
                ),
            )
            if cursor.lastrowid is None:
                continue
            sql_id = cursor.lastrowid
            sql_statements_count += 1

            for usage in statement_item.table_usages:
                conn.execute(
                    """
                    INSERT INTO sql_tables (run_id, sql_id, table_name, rw_type)
                    VALUES (?, ?, ?, ?)
                    """,
                    (run_context.run_id, sql_id, usage.table_name, usage.rw_type),
                )
                sql_tables_count += 1

        data_windows_count = 0
        for dw_item in analysis.data_windows:
            dw_object_id = object_name_to_id.get(dw_item.object_name.lower())
            if dw_object_id is None:
                continue
            conn.execute(
                """
                INSERT OR IGNORE INTO data_windows
                    (run_id, object_id, dw_name, base_table, sql_select)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    run_context.run_id,
                    dw_object_id,
                    dw_item.dw_name,
                    dw_item.base_table,
                    dw_item.sql_select,
                ),
            )
            data_windows_count += 1

        conn.commit()

    return PersistResult(
        objects_count=objects_count,
        events_count=events_count,
        functions_count=functions_count,
        relations_count=relations_count,
        sql_statements_count=sql_statements_count,
        sql_tables_count=sql_tables_count,
        data_windows_count=data_windows_count,
    )


def _validate_db_path(db_path: Path) -> None:
    db_string = str(db_path)
    if db_string.startswith("postgresql://") or db_string.startswith("postgres://"):
        raise UserInputError(
            "PostgreSQL persistence is not implemented in this MVP. Use a SQLite file path."
        )


def _initialize_schema(conn: sqlite3.Connection) -> None:
    root_dir = Path(__file__).resolve().parents[3]
    schema_file = root_dir / "sql" / "schema" / "001_init.sql"
    index_file = root_dir / "sql" / "indexes" / "002_indexes.sql"

    if not schema_file.exists() or not index_file.exists():
        raise UserInputError(
            "SQL schema files not found. Expected sql/schema/001_init.sql and sql/indexes/002_indexes.sql"
        )

    conn.executescript(schema_file.read_text(encoding="utf-8"))
    conn.executescript(index_file.read_text(encoding="utf-8"))
