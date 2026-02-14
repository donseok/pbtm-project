"""Run 간 비교(diff) 기능."""

from __future__ import annotations

from pathlib import Path
import sqlite3

from pb_analyzer.common import DiffItem, DiffResult, UserInputError


def diff_runs(db_path: Path, run_id_old: str, run_id_new: str) -> DiffResult:
    """두 run_id 간의 객체/관계/SQL 차이를 비교한다."""

    if not db_path.exists():
        raise UserInputError(f"DB file not found: {db_path}")

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row

        _validate_run_id(conn, run_id_old)
        _validate_run_id(conn, run_id_new)

        items: list[DiffItem] = []
        items.extend(_diff_objects(conn, run_id_old, run_id_new))
        items.extend(_diff_relations(conn, run_id_old, run_id_new))
        items.extend(_diff_sql_statements(conn, run_id_old, run_id_new))
        items.extend(_diff_data_windows(conn, run_id_old, run_id_new))

    return DiffResult(
        run_id_old=run_id_old,
        run_id_new=run_id_new,
        items=tuple(items),
    )


def _validate_run_id(conn: sqlite3.Connection, run_id: str) -> None:
    row = conn.execute(
        "SELECT run_id FROM runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    if row is None:
        raise UserInputError(f"Run not found: {run_id}")


def _diff_objects(
    conn: sqlite3.Connection, run_id_old: str, run_id_new: str,
) -> list[DiffItem]:
    old_objects = _query_object_set(conn, run_id_old)
    new_objects = _query_object_set(conn, run_id_new)

    items: list[DiffItem] = []
    for key in sorted(new_objects - old_objects):
        items.append(DiffItem(category="object", name=key, change_type="added"))
    for key in sorted(old_objects - new_objects):
        items.append(DiffItem(category="object", name=key, change_type="removed"))
    return items


def _diff_relations(
    conn: sqlite3.Connection, run_id_old: str, run_id_new: str,
) -> list[DiffItem]:
    old_rels = _query_relation_set(conn, run_id_old)
    new_rels = _query_relation_set(conn, run_id_new)

    items: list[DiffItem] = []
    for key in sorted(new_rels - old_rels):
        items.append(DiffItem(
            category="relation",
            name=key,
            change_type="added",
        ))
    for key in sorted(old_rels - new_rels):
        items.append(DiffItem(
            category="relation",
            name=key,
            change_type="removed",
        ))
    return items


def _diff_sql_statements(
    conn: sqlite3.Connection, run_id_old: str, run_id_new: str,
) -> list[DiffItem]:
    old_sqls = _query_sql_set(conn, run_id_old)
    new_sqls = _query_sql_set(conn, run_id_new)

    items: list[DiffItem] = []
    for key in sorted(new_sqls - old_sqls):
        items.append(DiffItem(
            category="sql_statement",
            name=key,
            change_type="added",
        ))
    for key in sorted(old_sqls - new_sqls):
        items.append(DiffItem(
            category="sql_statement",
            name=key,
            change_type="removed",
        ))
    return items


def _diff_data_windows(
    conn: sqlite3.Connection, run_id_old: str, run_id_new: str,
) -> list[DiffItem]:
    old_dws = _query_dw_set(conn, run_id_old)
    new_dws = _query_dw_set(conn, run_id_new)

    items: list[DiffItem] = []
    for key in sorted(new_dws - old_dws):
        items.append(DiffItem(
            category="data_window",
            name=key,
            change_type="added",
        ))
    for key in sorted(old_dws - new_dws):
        items.append(DiffItem(
            category="data_window",
            name=key,
            change_type="removed",
        ))
    return items


def _query_object_set(conn: sqlite3.Connection, run_id: str) -> set[str]:
    rows = conn.execute(
        "SELECT type || ':' || name AS key FROM objects WHERE run_id = ?",
        (run_id,),
    ).fetchall()
    return {str(row["key"]) for row in rows}


def _query_relation_set(conn: sqlite3.Connection, run_id: str) -> set[str]:
    rows = conn.execute(
        """
        SELECT src.name || '->' || dst.name || ':' || r.relation_type AS key
        FROM relations r
        JOIN objects src ON src.id = r.src_id AND src.run_id = r.run_id
        JOIN objects dst ON dst.id = r.dst_id AND dst.run_id = r.run_id
        WHERE r.run_id = ?
        """,
        (run_id,),
    ).fetchall()
    return {str(row["key"]) for row in rows}


def _query_sql_set(conn: sqlite3.Connection, run_id: str) -> set[str]:
    rows = conn.execute(
        """
        SELECT o.name || ':' || ss.sql_kind || ':' || ss.sql_text_norm AS key
        FROM sql_statements ss
        JOIN objects o ON o.id = ss.owner_id AND o.run_id = ss.run_id
        WHERE ss.run_id = ?
        """,
        (run_id,),
    ).fetchall()
    return {str(row["key"]) for row in rows}


def _query_dw_set(conn: sqlite3.Connection, run_id: str) -> set[str]:
    rows = conn.execute(
        """
        SELECT o.name || ':' || dw.dw_name || ':' || COALESCE(dw.base_table, '') AS key
        FROM data_windows dw
        JOIN objects o ON o.id = dw.object_id AND o.run_id = dw.run_id
        WHERE dw.run_id = ?
        """,
        (run_id,),
    ).fetchall()
    return {str(row["key"]) for row in rows}
