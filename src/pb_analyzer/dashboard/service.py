"""Web dashboard service for PB Analyzer results."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
from typing import Any
from urllib.parse import parse_qs, urlparse

from pb_analyzer.common import UserInputError

RunItem = dict[str, Any]
DashboardPayload = dict[str, Any]

_MAX_API_LIMIT = 2000
_DEFAULT_API_LIMIT = 200

_VALID_RELATION_TYPES = {
    "calls",
    "opens",
    "uses_dw",
    "reads_table",
    "writes_table",
    "triggers_event",
}


@dataclass(frozen=True)
class DashboardFilters:
    search: str | None = None
    object_name: str | None = None
    table_name: str | None = None
    relation_type: str | None = None



def run_dashboard(
    db_path: Path,
    host: str = "127.0.0.1",
    port: int = 8787,
    run_id: str | None = None,
    limit: int = _DEFAULT_API_LIMIT,
) -> None:
    """Starts the dashboard web server."""

    _ensure_db_path(db_path)
    normalized_limit = _sanitize_limit(limit, _DEFAULT_API_LIMIT)

    handler_class = _build_handler(
        db_path=db_path,
        default_run_id=run_id,
        default_limit=normalized_limit,
    )

    server = ThreadingHTTPServer((host, port), handler_class)
    print(f"[OK] dashboard_url=http://{host}:{port}")
    print("[OK] press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()



def list_runs(db_path: Path, limit: int = 20) -> list[RunItem]:
    """Returns recent analysis runs from DB."""

    _ensure_db_path(db_path)
    normalized_limit = _sanitize_limit(limit, 20)

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT run_id, started_at, finished_at, status, source_version
            FROM runs
            ORDER BY started_at DESC, rowid DESC
            LIMIT ?
            """,
            (normalized_limit,),
        ).fetchall()

    return [dict(row) for row in rows]



def get_dashboard_payload(
    db_path: Path,
    run_id: str | None = None,
    limit: int = _DEFAULT_API_LIMIT,
    filters: DashboardFilters | None = None,
) -> DashboardPayload:
    """Returns dashboard data for one run."""

    _ensure_db_path(db_path)
    normalized_limit = _sanitize_limit(limit, _DEFAULT_API_LIMIT)
    normalized_filters = _normalize_filters(filters)

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        resolved_run_id = _resolve_run_id(conn, run_id)

        run_row = conn.execute(
            """
            SELECT run_id, started_at, finished_at, status, source_version
            FROM runs
            WHERE run_id = ?
            LIMIT 1
            """,
            (resolved_run_id,),
        ).fetchone()

        if run_row is None:
            raise UserInputError(f"Run not found: {resolved_run_id}")

        summary = _query_summary(conn, resolved_run_id)
        relation_counts = _query_relation_counts(conn, resolved_run_id, normalized_filters)
        screen_inventory = _query_screen_inventory(
            conn,
            resolved_run_id,
            normalized_limit,
            normalized_filters,
        )
        event_function_map = _query_event_function_map(
            conn,
            resolved_run_id,
            normalized_limit,
            normalized_filters,
        )
        table_impact = _query_table_impact(
            conn,
            resolved_run_id,
            normalized_limit,
            normalized_filters,
        )
        screen_call_graph = _query_screen_call_graph(
            conn,
            resolved_run_id,
            normalized_limit,
            normalized_filters,
        )
        unused_candidates = _query_unused_candidates(
            conn,
            resolved_run_id,
            normalized_limit,
            normalized_filters,
        )

    graph_data = _build_graph_data(screen_call_graph)

    return {
        "run": dict(run_row),
        "summary": summary,
        "relation_counts": relation_counts,
        "screen_inventory": screen_inventory,
        "event_function_map": event_function_map,
        "table_impact": table_impact,
        "screen_call_graph": screen_call_graph,
        "graph_data": graph_data,
        "unused_object_candidates": unused_candidates,
        "limit": normalized_limit,
        "filters": {
            "search": normalized_filters.search,
            "object_name": normalized_filters.object_name,
            "table_name": normalized_filters.table_name,
            "relation_type": normalized_filters.relation_type,
        },
        "filtered_counts": {
            "screen_inventory": len(screen_inventory),
            "event_function_map": len(event_function_map),
            "table_impact": len(table_impact),
            "screen_call_graph": len(screen_call_graph),
            "unused_object_candidates": len(unused_candidates),
        },
    }



def _ensure_db_path(db_path: Path) -> None:
    if not db_path.exists():
        raise UserInputError(f"DB file not found: {db_path}")



def _sanitize_limit(limit: int, default_value: int) -> int:
    if limit <= 0:
        return default_value
    return min(limit, _MAX_API_LIMIT)



def _normalize_filter_value(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized if normalized else None



def _normalize_filters(filters: DashboardFilters | None) -> DashboardFilters:
    if filters is None:
        return DashboardFilters()

    relation_type = _normalize_filter_value(filters.relation_type)
    if relation_type is not None:
        relation_type = relation_type.lower()
        if relation_type not in _VALID_RELATION_TYPES:
            raise UserInputError(f"Unsupported relation_type filter: {relation_type}")

    return DashboardFilters(
        search=_normalize_filter_value(filters.search),
        object_name=_normalize_filter_value(filters.object_name),
        table_name=_normalize_filter_value(filters.table_name),
        relation_type=relation_type,
    )



def _resolve_run_id(conn: sqlite3.Connection, run_id: str | None) -> str:
    if run_id is not None and run_id.strip():
        candidate = run_id.strip()
        row = conn.execute(
            "SELECT run_id FROM runs WHERE run_id = ? LIMIT 1",
            (candidate,),
        ).fetchone()
        if row is None:
            raise UserInputError(f"Run not found: {candidate}")
        return str(row["run_id"])

    row = conn.execute(
        """
        SELECT run_id
        FROM runs
        ORDER BY started_at DESC, rowid DESC
        LIMIT 1
        """
    ).fetchone()

    if row is None:
        raise UserInputError("No analysis run found in DB. Run analyze or run-all first.")

    return str(row["run_id"])



def _query_summary(conn: sqlite3.Connection, run_id: str) -> dict[str, int]:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total_objects,
            SUM(CASE WHEN type = 'Table' THEN 1 ELSE 0 END) AS table_objects,
            SUM(CASE WHEN type <> 'Table' THEN 1 ELSE 0 END) AS app_objects
        FROM objects
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()

    if row is None:
        return {
            "total_objects": 0,
            "table_objects": 0,
            "app_objects": 0,
            "relations": 0,
            "sql_statements": 0,
            "sql_tables": 0,
        }

    relations = _count(conn, "SELECT COUNT(*) FROM relations WHERE run_id = ?", run_id)
    sql_statements = _count(conn, "SELECT COUNT(*) FROM sql_statements WHERE run_id = ?", run_id)
    sql_tables = _count(conn, "SELECT COUNT(*) FROM sql_tables WHERE run_id = ?", run_id)

    return {
        "total_objects": int(row["total_objects"] or 0),
        "table_objects": int(row["table_objects"] or 0),
        "app_objects": int(row["app_objects"] or 0),
        "relations": relations,
        "sql_statements": sql_statements,
        "sql_tables": sql_tables,
    }



def _query_relation_counts(
    conn: sqlite3.Connection,
    run_id: str,
    filters: DashboardFilters,
) -> list[dict[str, Any]]:
    clauses = ["r.run_id = ?"]
    params: list[Any] = [run_id]

    if filters.relation_type is not None:
        clauses.append("r.relation_type = ?")
        params.append(filters.relation_type)

    if filters.object_name is not None:
        like_value = _like(filters.object_name)
        clauses.append("(src.name LIKE ? OR dst.name LIKE ?)")
        params.extend([like_value, like_value])

    if filters.search is not None:
        like_value = _like(filters.search)
        clauses.append("(src.name LIKE ? OR dst.name LIKE ? OR r.relation_type LIKE ?)")
        params.extend([like_value, like_value, like_value])

    sql = f"""
        SELECT r.relation_type, COUNT(*) AS count
        FROM relations r
        JOIN objects src
          ON src.run_id = r.run_id
         AND src.id = r.src_id
        JOIN objects dst
          ON dst.run_id = r.run_id
         AND dst.id = r.dst_id
        WHERE {' AND '.join(clauses)}
        GROUP BY r.relation_type
        ORDER BY count DESC, r.relation_type
    """

    rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]



def _query_screen_inventory(
    conn: sqlite3.Connection,
    run_id: str,
    limit: int,
    filters: DashboardFilters,
) -> list[dict[str, Any]]:
    clauses = ["o.run_id = ?", "o.type <> 'Table'"]
    params: list[Any] = [run_id]

    if filters.object_name is not None:
        clauses.append("o.name LIKE ?")
        params.append(_like(filters.object_name))

    if filters.search is not None:
        like_value = _like(filters.search)
        clauses.append("(o.type LIKE ? OR o.name LIKE ? OR o.module LIKE ? OR o.source_path LIKE ?)")
        params.extend([like_value, like_value, like_value, like_value])

    sql = f"""
        SELECT o.type, o.name, o.module, o.source_path
        FROM objects o
        WHERE {' AND '.join(clauses)}
        ORDER BY o.type, o.name
        LIMIT ?
    """
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]



def _query_event_function_map(
    conn: sqlite3.Connection,
    run_id: str,
    limit: int,
    filters: DashboardFilters,
) -> list[dict[str, Any]]:
    if filters.relation_type is not None and filters.relation_type != "calls":
        return []

    clauses = ["e.run_id = ?"]
    params: list[Any] = [run_id]

    if filters.object_name is not None:
        clauses.append("o.name LIKE ?")
        params.append(_like(filters.object_name))

    if filters.search is not None:
        like_value = _like(filters.search)
        clauses.append("(o.name LIKE ? OR e.event_name LIKE ? OR e.script_ref LIKE ?)")
        params.extend([like_value, like_value, like_value])

    sql = f"""
        SELECT
            o.name AS object_name,
            e.event_name,
            e.script_ref,
            COALESCE(GROUP_CONCAT(DISTINCT dst.name), '') AS called_objects
        FROM events e
        JOIN objects o
          ON o.run_id = e.run_id
         AND o.id = e.object_id
        LEFT JOIN relations r
          ON r.run_id = e.run_id
         AND r.src_id = o.id
         AND r.relation_type = 'calls'
        LEFT JOIN objects dst
          ON dst.run_id = o.run_id
         AND dst.id = r.dst_id
        WHERE {' AND '.join(clauses)}
        GROUP BY o.name, e.event_name, e.script_ref
        ORDER BY o.name, e.event_name
        LIMIT ?
    """
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]



def _query_table_impact(
    conn: sqlite3.Connection,
    run_id: str,
    limit: int,
    filters: DashboardFilters,
) -> list[dict[str, Any]]:
    if filters.relation_type is not None and filters.relation_type not in {
        "reads_table",
        "writes_table",
    }:
        return []

    clauses = ["st.run_id = ?"]
    params: list[Any] = [run_id]

    if filters.table_name is not None:
        clauses.append("st.table_name LIKE ?")
        params.append(_like(filters.table_name))

    if filters.object_name is not None:
        clauses.append("owner.name LIKE ?")
        params.append(_like(filters.object_name))

    if filters.relation_type == "reads_table":
        clauses.append("st.rw_type = 'READ'")
    elif filters.relation_type == "writes_table":
        clauses.append("st.rw_type = 'WRITE'")

    if filters.search is not None:
        like_value = _like(filters.search)
        clauses.append("(st.table_name LIKE ? OR owner.name LIKE ? OR ss.sql_kind LIKE ?)")
        params.extend([like_value, like_value, like_value])

    sql = f"""
        SELECT
            st.table_name,
            st.rw_type,
            owner.name AS owner_object,
            ss.sql_kind
        FROM sql_tables st
        JOIN sql_statements ss
          ON ss.run_id = st.run_id
         AND ss.id = st.sql_id
        JOIN objects owner
          ON owner.run_id = ss.run_id
         AND owner.id = ss.owner_id
        WHERE {' AND '.join(clauses)}
        ORDER BY st.table_name, owner.name, st.rw_type
        LIMIT ?
    """
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]



def _query_screen_call_graph(
    conn: sqlite3.Connection,
    run_id: str,
    limit: int,
    filters: DashboardFilters,
) -> list[dict[str, Any]]:
    clauses = ["r.run_id = ?", "r.relation_type IN ('opens', 'calls')"]
    params: list[Any] = [run_id]

    if filters.relation_type is not None:
        if filters.relation_type not in {"opens", "calls"}:
            return []
        clauses.append("r.relation_type = ?")
        params.append(filters.relation_type)

    if filters.object_name is not None:
        like_value = _like(filters.object_name)
        clauses.append("(src.name LIKE ? OR dst.name LIKE ?)")
        params.extend([like_value, like_value])

    if filters.search is not None:
        like_value = _like(filters.search)
        clauses.append("(src.name LIKE ? OR dst.name LIKE ? OR r.relation_type LIKE ?)")
        params.extend([like_value, like_value, like_value])

    sql = f"""
        SELECT
            src.name AS src_name,
            dst.name AS dst_name,
            r.relation_type,
            r.confidence
        FROM relations r
        JOIN objects src
          ON src.run_id = r.run_id
         AND src.id = r.src_id
        JOIN objects dst
          ON dst.run_id = r.run_id
         AND dst.id = r.dst_id
        WHERE {' AND '.join(clauses)}
        ORDER BY src.name, dst.name, r.relation_type
        LIMIT ?
    """
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]



def _query_unused_candidates(
    conn: sqlite3.Connection,
    run_id: str,
    limit: int,
    filters: DashboardFilters,
) -> list[dict[str, Any]]:
    clauses = [
        "o.run_id = ?",
        "rel_src.id IS NULL",
        "rel_dst.id IS NULL",
        "e.id IS NULL",
        "f.id IS NULL",
        "o.type <> 'Table'",
    ]
    params: list[Any] = [run_id]

    if filters.object_name is not None:
        clauses.append("o.name LIKE ?")
        params.append(_like(filters.object_name))

    if filters.search is not None:
        like_value = _like(filters.search)
        clauses.append("(o.type LIKE ? OR o.name LIKE ? OR o.module LIKE ? OR o.source_path LIKE ?)")
        params.extend([like_value, like_value, like_value, like_value])

    sql = f"""
        SELECT
            o.type,
            o.name,
            o.module,
            o.source_path
        FROM objects o
        LEFT JOIN relations rel_src
          ON rel_src.run_id = o.run_id
         AND rel_src.src_id = o.id
        LEFT JOIN relations rel_dst
          ON rel_dst.run_id = o.run_id
         AND rel_dst.dst_id = o.id
        LEFT JOIN events e
          ON e.run_id = o.run_id
         AND e.object_id = o.id
        LEFT JOIN functions f
          ON f.run_id = o.run_id
         AND f.object_id = o.id
        WHERE {' AND '.join(clauses)}
        GROUP BY o.id, o.type, o.name, o.module, o.source_path
        ORDER BY o.type, o.name
        LIMIT ?
    """
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]



def _build_graph_data(edges: list[dict[str, Any]]) -> dict[str, Any]:
    node_map: dict[str, dict[str, Any]] = {}
    graph_edges: list[dict[str, Any]] = []

    for edge in edges:
        src_name = str(edge.get("src_name", ""))
        dst_name = str(edge.get("dst_name", ""))
        relation_type = str(edge.get("relation_type", ""))
        confidence = float(edge.get("confidence", 0.0) or 0.0)

        if not src_name or not dst_name:
            continue

        src_node = node_map.setdefault(
            src_name,
            {
                "id": src_name,
                "name": src_name,
                "in_degree": 0,
                "out_degree": 0,
                "degree": 0,
            },
        )
        dst_node = node_map.setdefault(
            dst_name,
            {
                "id": dst_name,
                "name": dst_name,
                "in_degree": 0,
                "out_degree": 0,
                "degree": 0,
            },
        )

        src_node["out_degree"] += 1
        dst_node["in_degree"] += 1

        graph_edges.append(
            {
                "src": src_name,
                "dst": dst_name,
                "relation_type": relation_type,
                "confidence": confidence,
            }
        )

    nodes = sorted(node_map.values(), key=lambda item: str(item["name"]).lower())
    for node in nodes:
        node["degree"] = int(node["in_degree"]) + int(node["out_degree"])

    return {
        "nodes": nodes,
        "edges": graph_edges,
        "node_count": len(nodes),
        "edge_count": len(graph_edges),
    }



def _count(conn: sqlite3.Connection, sql: str, run_id: str) -> int:
    row = conn.execute(sql, (run_id,)).fetchone()
    if row is None:
        return 0
    return int(row[0])



def _like(value: str) -> str:
    return f"%{value}%"



def _build_handler(
    db_path: Path,
    default_run_id: str | None,
    default_limit: int,
) -> type[BaseHTTPRequestHandler]:
    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "PBAnalyzerDashboard/0.2"

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            endpoint = parsed.path or "/"
            params = parse_qs(parsed.query)

            try:
                if endpoint == "/":
                    self._send_html(_render_dashboard_html())
                    return

                if endpoint == "/health":
                    self._send_json({"status": "ok"})
                    return

                run_id = _get_query_param(params, "run_id") or default_run_id
                limit = _parse_limit_param(params, default_limit)
                filters = _parse_filters(params)

                if endpoint == "/api/runs":
                    self._send_json({"runs": list_runs(db_path, limit=min(limit, 100))})
                    return

                if endpoint == "/api/all":
                    payload = get_dashboard_payload(
                        db_path=db_path,
                        run_id=run_id,
                        limit=limit,
                        filters=filters,
                    )
                    self._send_json(payload)
                    return

                if endpoint == "/api/summary":
                    payload = get_dashboard_payload(
                        db_path=db_path,
                        run_id=run_id,
                        limit=limit,
                        filters=filters,
                    )
                    self._send_json(
                        {
                            "run": payload["run"],
                            "summary": payload["summary"],
                            "relation_counts": payload["relation_counts"],
                            "filters": payload["filters"],
                        }
                    )
                    return

                if endpoint == "/api/graph":
                    payload = get_dashboard_payload(
                        db_path=db_path,
                        run_id=run_id,
                        limit=limit,
                        filters=filters,
                    )
                    self._send_json(
                        {
                            "run": payload["run"],
                            "graph_data": payload["graph_data"],
                            "filters": payload["filters"],
                        }
                    )
                    return

                if endpoint == "/api/screen-inventory":
                    payload = get_dashboard_payload(
                        db_path=db_path,
                        run_id=run_id,
                        limit=limit,
                        filters=filters,
                    )
                    self._send_json({"items": payload["screen_inventory"]})
                    return

                if endpoint == "/api/event-function-map":
                    payload = get_dashboard_payload(
                        db_path=db_path,
                        run_id=run_id,
                        limit=limit,
                        filters=filters,
                    )
                    self._send_json({"items": payload["event_function_map"]})
                    return

                if endpoint == "/api/table-impact":
                    payload = get_dashboard_payload(
                        db_path=db_path,
                        run_id=run_id,
                        limit=limit,
                        filters=filters,
                    )
                    self._send_json({"items": payload["table_impact"]})
                    return

                if endpoint == "/api/screen-call-graph":
                    payload = get_dashboard_payload(
                        db_path=db_path,
                        run_id=run_id,
                        limit=limit,
                        filters=filters,
                    )
                    self._send_json({"items": payload["screen_call_graph"]})
                    return

                if endpoint == "/api/unused-object-candidates":
                    payload = get_dashboard_payload(
                        db_path=db_path,
                        run_id=run_id,
                        limit=limit,
                        filters=filters,
                    )
                    self._send_json({"items": payload["unused_object_candidates"]})
                    return

                self._send_json({"error": f"Not found: {endpoint}"}, status=404)
            except UserInputError as exc:
                self._send_json({"error": str(exc)}, status=400)
            except Exception as exc:  # pragma: no cover
                self._send_json({"error": f"dashboard error: {exc}"}, status=500)

        def log_message(self, fmt: str, *args: object) -> None:
            return

        def _send_html(self, payload: str, status: int = 200) -> None:
            data = payload.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return DashboardHandler



def _get_query_param(params: dict[str, list[str]], key: str) -> str | None:
    values = params.get(key)
    if not values:
        return None
    value = values[0].strip()
    return value or None



def _parse_limit_param(params: dict[str, list[str]], default_limit: int) -> int:
    raw_limit = _get_query_param(params, "limit")
    if raw_limit is None:
        return default_limit
    try:
        parsed = int(raw_limit)
    except ValueError:
        return default_limit
    return _sanitize_limit(parsed, default_limit)



def _parse_filters(params: dict[str, list[str]]) -> DashboardFilters:
    return DashboardFilters(
        search=_get_query_param(params, "search"),
        object_name=_get_query_param(params, "object_name"),
        table_name=_get_query_param(params, "table_name"),
        relation_type=_get_query_param(params, "relation_type"),
    )



def _render_dashboard_html() -> str:
    html = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>__TITLE__</title>
  <style>
    :root {
      --bg: #f8fafc;
      --surface: #ffffff;
      --surface-hover: #f1f5f9;
      --text: #0f172a;
      --text-secondary: #475569;
      --muted: #94a3b8;
      --border: #e2e8f0;
      --accent: #0d9488;
      --accent-light: #ccfbf1;
      --accent-dark: #115e59;
      --accent-hover: #0f766e;
      --calls: #3b82f6;
      --calls-light: #dbeafe;
      --opens: #f59e0b;
      --opens-light: #fef3c7;
      --read: #22c55e;
      --read-light: #dcfce7;
      --write: #ef4444;
      --write-light: #fee2e2;
      --uses-dw: #8b5cf6;
      --uses-dw-light: #ede9fe;
      --triggers: #ec4899;
      --triggers-light: #fce7f3;
      --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
      --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.07), 0 2px 4px -2px rgba(0,0,0,0.05);
      --radius: 12px;
      --radius-sm: 8px;
      --radius-xs: 6px;
      --transition: 0.2s ease;
    }
    *, *::before, *::after { box-sizing: border-box; }
    body {
      margin: 0; background: var(--bg); color: var(--text);
      font-family: "Pretendard","Noto Sans KR",-apple-system,sans-serif;
      font-size: 14px; line-height: 1.5; -webkit-font-smoothing: antialiased;
    }
    .container { max-width: 1400px; margin: 0 auto; padding: 20px 24px; }

    /* Header */
    .header {
      display: flex; flex-wrap: wrap; align-items: center;
      justify-content: space-between; gap: 12px; margin-bottom: 16px;
    }
    .header h1 { margin: 0; font-size: 24px; font-weight: 700; }
    .header .sub { color: var(--text-secondary); font-size: 13px; margin-top: 2px; }
    .header-controls {
      display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
    }
    .header-controls label {
      font-size: 12px; color: var(--text-secondary); font-weight: 500;
    }

    /* Form Elements */
    select, input[type="text"], input[type="number"] {
      border: 1px solid var(--border); border-radius: var(--radius-xs);
      padding: 6px 10px; font-size: 13px; background: var(--surface);
      color: var(--text); transition: border-color var(--transition); outline: none;
    }
    select:focus, input:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(13,148,136,0.1);
    }
    button {
      border: 1px solid var(--accent); border-radius: var(--radius-xs);
      padding: 6px 14px; font-size: 13px; font-weight: 500;
      background: var(--accent); color: #fff; cursor: pointer;
      transition: all var(--transition);
    }
    button:hover { background: var(--accent-hover); }
    .btn-subtle {
      background: var(--surface); color: var(--text-secondary);
      border-color: var(--border);
    }
    .btn-subtle:hover { background: var(--surface-hover); }
    .btn-icon {
      background: none; border: 1px solid var(--border);
      color: var(--text-secondary); padding: 6px 10px;
      display: inline-flex; align-items: center; gap: 4px;
    }
    .btn-icon:hover { background: var(--surface-hover); color: var(--text); }

    /* Filter Bar */
    .filter-bar {
      background: var(--surface); border: 1px solid var(--border);
      border-radius: var(--radius); margin-bottom: 16px; overflow: hidden;
    }
    .filter-toggle {
      display: flex; align-items: center; justify-content: space-between;
      padding: 10px 16px; cursor: pointer; user-select: none;
      font-size: 13px; font-weight: 500; color: var(--text-secondary);
    }
    .filter-toggle:hover { background: var(--surface-hover); }
    .filter-toggle .arrow {
      transition: transform var(--transition); font-size: 10px;
    }
    .filter-toggle .arrow.open { transform: rotate(180deg); }
    .filter-content { display: none; padding: 0 16px 14px; }
    .filter-content.open { display: block; }
    .filter-grid {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px; align-items: end;
    }
    .filter-item { display: flex; flex-direction: column; gap: 4px; }
    .filter-item label {
      font-size: 11px; font-weight: 500; color: var(--muted);
      text-transform: uppercase; letter-spacing: 0.5px;
    }
    .filter-actions { display: flex; gap: 6px; align-items: flex-end; }
    .active-filters {
      display: flex; flex-wrap: wrap; gap: 6px; padding: 0 16px 10px;
    }
    .active-filters:empty { display: none; padding: 0; }
    .filter-tag {
      display: inline-flex; align-items: center; gap: 4px;
      background: var(--accent-light); color: var(--accent-dark);
      padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 500;
    }
    .filter-tag .remove { cursor: pointer; font-weight: 700; opacity: 0.6; }
    .filter-tag .remove:hover { opacity: 1; }

    /* Tab Navigation */
    .tab-bar {
      display: flex; gap: 0; border-bottom: 2px solid var(--border);
      margin-bottom: 20px; overflow-x: auto;
      -webkit-overflow-scrolling: touch; scrollbar-width: none;
    }
    .tab-bar::-webkit-scrollbar { display: none; }
    .tab-btn {
      position: relative; padding: 10px 20px; font-size: 14px;
      font-weight: 500; color: var(--muted); background: none;
      border: none; cursor: pointer; white-space: nowrap;
      transition: color var(--transition);
    }
    .tab-btn:hover { color: var(--text-secondary); }
    .tab-btn.active { color: var(--accent); font-weight: 600; }
    .tab-btn.active::after {
      content: ''; position: absolute; bottom: -2px; left: 0; right: 0;
      height: 2px; background: var(--accent); border-radius: 1px 1px 0 0;
    }
    .tab-content { display: none; }
    .tab-content.active { display: block; animation: fadeIn 0.25s ease; }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(4px); }
      to { opacity: 1; transform: translateY(0); }
    }

    /* Status */
    #status {
      color: var(--text-secondary); font-size: 12px; margin-bottom: 12px;
      padding: 6px 12px; background: var(--surface);
      border: 1px solid var(--border); border-radius: var(--radius-xs);
    }

    /* Metric Cards */
    .metric-grid {
      display: grid; grid-template-columns: repeat(6, 1fr);
      gap: 12px; margin-bottom: 20px;
    }
    @media (max-width: 1200px) { .metric-grid { grid-template-columns: repeat(3, 1fr); } }
    @media (max-width: 768px) { .metric-grid { grid-template-columns: repeat(2, 1fr); } }
    .metric-card {
      background: var(--surface); border: 1px solid var(--border);
      border-left: 4px solid var(--accent); border-radius: var(--radius-sm);
      padding: 16px; transition: all var(--transition); cursor: default;
    }
    .metric-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-md); }
    .metric-card .metric-label {
      font-size: 11px; font-weight: 500; color: var(--muted);
      text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;
    }
    .metric-card .metric-value {
      font-size: 28px; font-weight: 700; color: var(--text); line-height: 1.2;
    }
    .metric-card .metric-sub {
      font-size: 11px; color: var(--text-secondary); margin-top: 2px;
    }
    .metric-card.blue { border-left-color: var(--calls); }
    .metric-card.amber { border-left-color: var(--opens); }
    .metric-card.green { border-left-color: var(--read); }
    .metric-card.red { border-left-color: var(--write); }
    .metric-card.violet { border-left-color: var(--uses-dw); }
    .metric-card.gray { border-left-color: var(--muted); }

    /* Panels */
    .panel {
      background: var(--surface); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 20px; margin-bottom: 16px;
    }
    .panel-header {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 14px; flex-wrap: wrap; gap: 8px;
    }
    .panel-title { font-size: 15px; font-weight: 600; color: var(--text); margin: 0; }
    .panel-actions { display: flex; gap: 6px; align-items: center; }

    /* Layout */
    .two-col {
      display: grid; grid-template-columns: 1fr 1fr;
      gap: 16px; margin-bottom: 16px;
    }
    @media (max-width: 960px) { .two-col { grid-template-columns: 1fr; } }
    .three-col {
      display: grid; grid-template-columns: 1fr 1fr 1fr;
      gap: 16px; margin-bottom: 16px;
    }
    @media (max-width: 960px) { .three-col { grid-template-columns: 1fr; } }

    /* Horizontal Bar Chart */
    .bar-chart { display: flex; flex-direction: column; gap: 8px; }
    .bar-row { display: flex; align-items: center; gap: 10px; }
    .bar-label {
      width: 110px; font-size: 12px; font-weight: 500;
      color: var(--text-secondary); text-align: right; flex-shrink: 0;
    }
    .bar-track {
      flex: 1; height: 22px; background: var(--surface-hover);
      border-radius: 4px; overflow: hidden;
    }
    .bar-fill {
      height: 100%; border-radius: 4px;
      transition: width 0.6s ease; min-width: 2px;
    }
    .bar-fill.calls { background: var(--calls); }
    .bar-fill.opens { background: var(--opens); }
    .bar-fill.uses_dw { background: var(--uses-dw); }
    .bar-fill.reads_table { background: var(--read); }
    .bar-fill.writes_table { background: var(--write); }
    .bar-fill.triggers_event { background: var(--triggers); }
    .bar-count {
      width: 50px; font-size: 12px; font-weight: 600;
      color: var(--text); flex-shrink: 0;
    }

    /* Tables */
    .table-wrap { overflow-x: auto; max-height: 450px; overflow-y: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    thead th {
      background: #f8fafc; position: sticky; top: 0; z-index: 1;
      border-bottom: 2px solid var(--border); text-align: left;
      padding: 8px 10px; font-weight: 600; font-size: 12px;
      color: var(--text-secondary); text-transform: uppercase;
      letter-spacing: 0.3px; cursor: pointer; user-select: none;
      white-space: nowrap;
    }
    thead th:hover { background: var(--surface-hover); }
    thead th .sort-icon { margin-left: 4px; font-size: 10px; opacity: 0.4; }
    thead th.sorted .sort-icon { opacity: 1; color: var(--accent); }
    tbody td {
      border-bottom: 1px solid var(--border); padding: 7px 10px;
      white-space: nowrap;
    }
    tbody tr:nth-child(even) { background: #fafbfc; }
    tbody tr:hover { background: #f0f9ff; }

    /* Badges */
    .badge {
      display: inline-block; padding: 2px 8px; border-radius: 999px;
      font-size: 11px; font-weight: 600; white-space: nowrap;
    }
    .badge-calls { background: var(--calls-light); color: #1d4ed8; }
    .badge-opens { background: var(--opens-light); color: #b45309; }
    .badge-uses_dw { background: var(--uses-dw-light); color: #6d28d9; }
    .badge-reads_table, .badge-read { background: var(--read-light); color: #15803d; }
    .badge-writes_table, .badge-write { background: var(--write-light); color: #b91c1c; }
    .badge-triggers_event { background: var(--triggers-light); color: #be185d; }
    .badge-type { background: var(--accent-light); color: var(--accent-dark); }
    .badge-count {
      background: var(--surface-hover); color: var(--text);
      font-size: 12px; padding: 3px 10px; border: 1px solid var(--border);
    }

    /* Clickable & Mono */
    .clickable {
      color: var(--accent); cursor: pointer;
      font-family: "Cascadia Code","Fira Code",monospace; font-size: 12px;
    }
    .clickable:hover { text-decoration: underline; }
    .mono { font-family: "Cascadia Code","Fira Code",monospace; font-size: 12px; }

    /* Graph */
    .graph-container {
      border: 1px solid var(--border); border-radius: var(--radius-sm);
      background: #fcfeff; overflow: hidden; position: relative;
    }
    .graph-container svg { width: 100%; display: block; }
    .graph-container.mini svg { height: 280px; }
    .graph-container.full svg { height: 550px; }
    @media (max-width: 960px) { .graph-container.full svg { height: 450px; } }
    @media (max-width: 640px) {
      .graph-container.mini svg { height: 200px; }
      .graph-container.full svg { height: 300px; }
    }
    .graph-legend {
      display: flex; gap: 16px; font-size: 12px;
      color: var(--text-secondary); margin-bottom: 10px; flex-wrap: wrap;
    }
    .graph-legend .legend-item {
      display: inline-flex; align-items: center; gap: 6px;
    }
    .legend-dot {
      width: 10px; height: 10px; border-radius: 50%; display: inline-block;
    }
    .legend-line {
      width: 20px; height: 3px; border-radius: 2px; display: inline-block;
    }
    .graph-tooltip {
      position: absolute; background: var(--surface);
      border: 1px solid var(--border); border-radius: var(--radius-xs);
      padding: 8px 12px; font-size: 12px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.08);
      pointer-events: none; opacity: 0; transition: opacity 0.15s;
      z-index: 100; max-width: 250px;
    }
    .graph-tooltip.visible { opacity: 1; }

    /* Toggle Group */
    .toggle-group {
      display: inline-flex; border: 1px solid var(--border);
      border-radius: var(--radius-xs); overflow: hidden;
    }
    .toggle-btn {
      padding: 5px 12px; font-size: 12px; font-weight: 500;
      border: none; border-right: 1px solid var(--border);
      background: var(--surface); color: var(--text-secondary);
      cursor: pointer; transition: all var(--transition);
    }
    .toggle-btn:last-child { border-right: none; }
    .toggle-btn:hover { background: var(--surface-hover); }
    .toggle-btn.active { background: var(--accent); color: #fff; }

    /* Run Info */
    .run-info {
      display: grid; grid-template-columns: 1fr 1fr;
      gap: 6px 20px; font-size: 13px;
    }
    .run-info dt {
      color: var(--muted); font-size: 11px; font-weight: 500;
      text-transform: uppercase; letter-spacing: 0.3px;
    }
    .run-info dd { margin: 0 0 8px 0; font-weight: 500; color: var(--text); }

    /* Empty State */
    .empty-state { text-align: center; padding: 40px 20px; color: var(--muted); }
    .empty-state .icon { font-size: 32px; margin-bottom: 8px; }
    .empty-state .msg { font-size: 14px; }

    /* Type Distribution */
    .type-dist { display: flex; flex-wrap: wrap; gap: 8px; }
    .type-chip {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 6px 12px; background: var(--surface);
      border: 1px solid var(--border); border-radius: var(--radius-xs);
      font-size: 13px; font-weight: 500; cursor: default;
      transition: all var(--transition);
    }
    .type-chip:hover { transform: translateY(-1px); box-shadow: var(--shadow-sm); }
    .type-chip .count {
      background: var(--accent-light); color: var(--accent-dark);
      padding: 1px 6px; border-radius: 999px; font-size: 12px; font-weight: 600;
    }
  </style>
</head>
<body>
  <div class="container">
    <!-- Header -->
    <div class="header">
      <div>
        <h1>__TITLE__</h1>
        <div class="sub">IR DB 기반 영향분석 조회</div>
      </div>
      <div class="header-controls">
        <label for="runSelect">run_id</label>
        <select id="runSelect"></select>
        <label for="limitInput">limit</label>
        <input id="limitInput" type="number" value="200" min="10" max="2000" style="width:80px"/>
        <button id="reloadBtn">새로고침</button>
      </div>
    </div>

    <!-- Filter Bar -->
    <div class="filter-bar">
      <div class="filter-toggle" id="filterToggle">
        <span>필터</span>
        <span class="arrow" id="filterArrow">&#9660;</span>
      </div>
      <div id="activeFilters" class="active-filters"></div>
      <div class="filter-content" id="filterContent">
        <div class="filter-grid">
          <div class="filter-item">
            <label>검색어</label>
            <input id="searchInput" type="text" placeholder="이름/모듈/경로" />
          </div>
          <div class="filter-item">
            <label>객체명</label>
            <input id="objectInput" type="text" placeholder="예: w_main" />
          </div>
          <div class="filter-item">
            <label>테이블명</label>
            <input id="tableInput" type="text" placeholder="예: TB_ORDER" />
          </div>
          <div class="filter-item">
            <label>관계 타입</label>
            <select id="relationSelect">
              <option value="">(전체)</option>
              <option value="calls">calls</option>
              <option value="opens">opens</option>
              <option value="uses_dw">uses_dw</option>
              <option value="reads_table">reads_table</option>
              <option value="writes_table">writes_table</option>
              <option value="triggers_event">triggers_event</option>
            </select>
          </div>
          <div class="filter-actions">
            <button id="applyFilterBtn">적용</button>
            <button id="clearFilterBtn" class="btn-subtle">초기화</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Status -->
    <div id="status">loading...</div>

    <!-- Tab Navigation -->
    <div class="tab-bar" id="tabBar">
      <button class="tab-btn active" data-tab="overview">개요</button>
      <button class="tab-btn" data-tab="dependencies">의존관계</button>
      <button class="tab-btn" data-tab="table-impact">테이블 영향도</button>
      <button class="tab-btn" data-tab="inventory">인벤토리</button>
    </div>

    <!-- Tab: 개요 -->
    <div class="tab-content active" id="tab-overview">
      <div class="metric-grid" id="metricGrid"></div>
      <div class="two-col">
        <div class="panel">
          <div class="panel-header"><h2 class="panel-title">관계 분포</h2></div>
          <div id="relationBar" class="bar-chart"></div>
        </div>
        <div class="panel">
          <div class="panel-header"><h2 class="panel-title">Run 정보</h2></div>
          <dl id="runInfo" class="run-info"></dl>
        </div>
      </div>
      <div class="panel">
        <div class="panel-header">
          <h2 class="panel-title">의존관계 미리보기</h2>
          <button class="btn-subtle btn-icon" id="goFullGraphBtn">전체 보기 &#8594;</button>
        </div>
        <div class="graph-legend">
          <span class="legend-item"><span class="legend-line" style="background:var(--calls)"></span>calls</span>
          <span class="legend-item"><span class="legend-line" style="background:var(--opens)"></span>opens</span>
        </div>
        <div class="graph-container mini" id="miniGraphContainer">
          <svg id="miniGraphSvg"></svg>
        </div>
      </div>
    </div>

    <!-- Tab: 의존관계 -->
    <div class="tab-content" id="tab-dependencies">
      <div class="panel">
        <div class="panel-header">
          <h2 class="panel-title">화면 이동/호출 그래프</h2>
          <div class="panel-actions">
            <div class="toggle-group" id="graphFilter">
              <button class="toggle-btn active" data-filter="all">전체</button>
              <button class="toggle-btn" data-filter="calls">calls</button>
              <button class="toggle-btn" data-filter="opens">opens</button>
            </div>
          </div>
        </div>
        <div class="graph-legend">
          <span class="legend-item"><span class="legend-line" style="background:var(--calls)"></span>calls</span>
          <span class="legend-item"><span class="legend-line" style="background:var(--opens)"></span>opens</span>
          <span class="legend-item"><span class="legend-dot" style="background:var(--accent)"></span>노드 (크기=연결수)</span>
        </div>
        <div class="graph-container full" id="fullGraphContainer">
          <svg id="fullGraphSvg"></svg>
          <div class="graph-tooltip" id="graphTooltip"></div>
        </div>
      </div>
      <div class="two-col">
        <div class="panel">
          <div class="panel-header"><h2 class="panel-title">이벤트-함수 맵</h2></div>
          <div class="table-wrap" id="eventMapTable"></div>
        </div>
        <div class="panel">
          <div class="panel-header"><h2 class="panel-title">호출 엣지</h2></div>
          <div class="table-wrap" id="graphEdgeTable"></div>
        </div>
      </div>
    </div>

    <!-- Tab: 테이블 영향도 -->
    <div class="tab-content" id="tab-table-impact">
      <div class="three-col" id="tableImpactSummary"></div>
      <div class="panel">
        <div class="panel-header">
          <h2 class="panel-title">테이블 영향도 상세</h2>
          <div class="panel-actions">
            <div class="toggle-group" id="rwFilter">
              <button class="toggle-btn active" data-filter="all">ALL</button>
              <button class="toggle-btn" data-filter="READ">READ</button>
              <button class="toggle-btn" data-filter="WRITE">WRITE</button>
            </div>
          </div>
        </div>
        <div class="table-wrap" id="tableImpactDetail"></div>
      </div>
    </div>

    <!-- Tab: 인벤토리 -->
    <div class="tab-content" id="tab-inventory">
      <div class="panel">
        <div class="panel-header"><h2 class="panel-title">객체 타입별 분포</h2></div>
        <div id="typeDist" class="type-dist"></div>
      </div>
      <div class="panel">
        <div class="panel-header"><h2 class="panel-title">화면 인벤토리</h2></div>
        <div class="table-wrap" id="inventoryTable"></div>
      </div>
      <div class="panel">
        <div class="panel-header">
          <h2 class="panel-title">미사용 객체 후보</h2>
          <span class="badge badge-count" id="unusedCount">0</span>
        </div>
        <div class="table-wrap" id="unusedTable"></div>
      </div>
    </div>
  </div>

  <script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
  <script>
    /* ===== State ===== */
    var currentData = null;
    var currentGraphFilter = 'all';
    var currentRwFilter = 'all';
    var fullSimulation = null;

    /* ===== DOM Refs ===== */
    var statusEl = document.getElementById('status');
    var runSelectEl = document.getElementById('runSelect');
    var limitInputEl = document.getElementById('limitInput');
    var searchInputEl = document.getElementById('searchInput');
    var objectInputEl = document.getElementById('objectInput');
    var tableInputEl = document.getElementById('tableInput');
    var relationSelectEl = document.getElementById('relationSelect');

    /* ===== Utilities ===== */
    function esc(v) {
      return String(v == null ? '' : v)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    function fmt(n) { return Number(n || 0).toLocaleString(); }

    function readFilters() {
      return {
        search: searchInputEl.value.trim(),
        object_name: objectInputEl.value.trim(),
        table_name: tableInputEl.value.trim(),
        relation_type: relationSelectEl.value.trim()
      };
    }

    function clearFilters() {
      searchInputEl.value = '';
      objectInputEl.value = '';
      tableInputEl.value = '';
      relationSelectEl.value = '';
      renderActiveFilters({});
    }

    function handleErr(e) { statusEl.textContent = 'error: ' + e.message; }

    async function fetchJson(url) {
      var r = await fetch(url);
      if (!r.ok) {
        var body = null;
        try { body = await r.json(); } catch(_) {}
        throw new Error((body && body.error) || 'request failed (' + r.status + ')');
      }
      return r.json();
    }

    function badgeHtml(type, label) {
      return '<span class="badge badge-' + esc(type).replace(/ +/g,'_') + '">' + esc(label || type) + '</span>';
    }

    /* ===== Filter Bar ===== */
    var filterToggle = document.getElementById('filterToggle');
    var filterContent = document.getElementById('filterContent');
    var filterArrow = document.getElementById('filterArrow');
    filterToggle.addEventListener('click', function() {
      filterContent.classList.toggle('open');
      filterArrow.classList.toggle('open');
    });

    function renderActiveFilters(filters) {
      var c = document.getElementById('activeFilters');
      var tags = [];
      for (var k in filters) {
        if (filters[k]) {
          tags.push('<span class="filter-tag">' + esc(k) + '=' + esc(filters[k]) +
            ' <span class="remove" data-fkey="' + esc(k) + '">&times;</span></span>');
        }
      }
      c.innerHTML = tags.join('');
    }

    document.getElementById('activeFilters').addEventListener('click', function(e) {
      var rm = e.target.closest('.remove');
      if (!rm) return;
      var key = rm.getAttribute('data-fkey');
      var map = {search: searchInputEl, object_name: objectInputEl,
                 table_name: tableInputEl, relation_type: relationSelectEl};
      if (map[key]) map[key].value = '';
      loadDashboard().catch(handleErr);
    });

    /* ===== Tab Navigation ===== */
    function switchTab(tabId) {
      document.querySelectorAll('.tab-btn').forEach(function(b) {
        b.classList.toggle('active', b.getAttribute('data-tab') === tabId);
      });
      document.querySelectorAll('.tab-content').forEach(function(c) {
        c.classList.toggle('active', c.id === 'tab-' + tabId);
      });
      if (tabId === 'dependencies' && currentData) renderFullGraph(currentData.graph_data);
      if (tabId === 'overview' && currentData) renderMiniGraph(currentData.graph_data);
    }

    document.getElementById('tabBar').addEventListener('click', function(e) {
      var btn = e.target.closest('.tab-btn');
      if (btn) switchTab(btn.getAttribute('data-tab'));
    });

    document.getElementById('goFullGraphBtn').addEventListener('click', function() {
      switchTab('dependencies');
    });

    /* Cross-tab navigation: click object name -> dependencies tab with filter */
    function navToObject(name) {
      objectInputEl.value = name;
      loadDashboard().then(function() { switchTab('dependencies'); }).catch(handleErr);
    }

    /* Event delegation for clickable elements */
    document.addEventListener('click', function(e) {
      var el = e.target.closest('[data-nav]');
      if (el) navToObject(el.getAttribute('data-nav'));
    });

    /* ===== Sortable Table Renderer ===== */
    function renderSortableTable(containerId, rows, columns) {
      var container = document.getElementById(containerId);
      if (!rows || !rows.length) {
        container.innerHTML = '<div class="empty-state"><div class="msg">데이터 없음</div></div>';
        return;
      }
      var sortCol = null, sortAsc = true;

      function render() {
        var sorted = rows.slice();
        if (sortCol !== null) {
          sorted.sort(function(a, b) {
            var va = a[sortCol], vb = b[sortCol];
            if (va == null) va = '';
            if (vb == null) vb = '';
            var cmp = typeof va === 'number' ? va - vb : String(va).localeCompare(String(vb));
            return sortAsc ? cmp : -cmp;
          });
        }
        var ths = columns.map(function(c) {
          var icon = sortCol === c.key ? (sortAsc ? '&#9650;' : '&#9660;') : '&#8597;';
          var cls = sortCol === c.key ? 'sorted' : '';
          return '<th class="' + cls + '" data-col="' + esc(c.key) + '">' +
                 esc(c.label) + ' <span class="sort-icon">' + icon + '</span></th>';
        }).join('');
        var trs = sorted.map(function(row) {
          var tds = columns.map(function(c) {
            var val = row[c.key];
            if (c.render) return '<td>' + c.render(val, row) + '</td>';
            return '<td>' + esc(val) + '</td>';
          }).join('');
          return '<tr>' + tds + '</tr>';
        }).join('');
        container.innerHTML = '<table><thead><tr>' + ths + '</tr></thead><tbody>' + trs + '</tbody></table>';
        container.querySelectorAll('th').forEach(function(th) {
          th.addEventListener('click', function() {
            var col = th.getAttribute('data-col');
            if (sortCol === col) sortAsc = !sortAsc;
            else { sortCol = col; sortAsc = true; }
            render();
          });
        });
      }
      render();
    }

    /* ===== Overview Tab ===== */
    function renderMetrics(summary, unusedCount) {
      var cards = [
        {label:'App Objects', value:summary.app_objects, color:'', sub:'애플리케이션 객체'},
        {label:'Table Objects', value:summary.table_objects, color:'green', sub:'DB 테이블'},
        {label:'Relations', value:summary.relations, color:'blue', sub:'관계 연결'},
        {label:'SQL Statements', value:summary.sql_statements, color:'violet', sub:'SQL 문'},
        {label:'SQL Tables', value:summary.sql_tables, color:'amber', sub:'참조 테이블'},
        {label:'Unused', value:unusedCount, color:'gray', sub:'미사용 후보'}
      ];
      document.getElementById('metricGrid').innerHTML = cards.map(function(c) {
        return '<div class="metric-card ' + c.color + '">' +
          '<div class="metric-label">' + esc(c.label) + '</div>' +
          '<div class="metric-value">' + fmt(c.value) + '</div>' +
          '<div class="metric-sub">' + esc(c.sub) + '</div></div>';
      }).join('');
    }

    function renderRelationBar(counts) {
      var el = document.getElementById('relationBar');
      if (!counts || !counts.length) {
        el.innerHTML = '<div class="empty-state"><div class="msg">데이터 없음</div></div>';
        return;
      }
      var max = Math.max.apply(null, counts.map(function(c) { return c.count; }).concat([1]));
      el.innerHTML = counts.map(function(c) {
        var pct = (c.count / max * 100).toFixed(1);
        return '<div class="bar-row">' +
          '<span class="bar-label">' + esc(c.relation_type) + '</span>' +
          '<div class="bar-track"><div class="bar-fill ' + c.relation_type + '" style="width:' + pct + '%"></div></div>' +
          '<span class="bar-count">' + fmt(c.count) + '</span></div>';
      }).join('');
    }

    function renderRunInfo(run) {
      var el = document.getElementById('runInfo');
      if (!run) { el.innerHTML = '<div class="empty-state"><div class="msg">데이터 없음</div></div>'; return; }
      el.innerHTML =
        '<dt>Run ID</dt><dd class="mono">' + esc(run.run_id) + '</dd>' +
        '<dt>Status</dt><dd>' + esc(run.status) + '</dd>' +
        '<dt>Started</dt><dd>' + esc(run.started_at || '-') + '</dd>' +
        '<dt>Finished</dt><dd>' + esc(run.finished_at || '-') + '</dd>' +
        '<dt>Source Version</dt><dd class="mono">' + esc(run.source_version || '-') + '</dd>';
    }

    /* ===== Mini Graph (Overview) ===== */
    function renderMiniGraph(graphData) {
      var svg = d3.select('#miniGraphSvg');
      svg.selectAll('*').remove();
      if (!graphData || !graphData.nodes || !graphData.nodes.length) {
        svg.append('text').attr('x',20).attr('y',30).attr('fill','#94a3b8').attr('font-size',13).text('그래프 데이터 없음');
        return;
      }
      var topNodes = graphData.nodes.slice().sort(function(a,b) { return (b.degree||0)-(a.degree||0); }).slice(0,20);
      var nodeSet = {};
      topNodes.forEach(function(n) { nodeSet[n.id] = true; });
      var edges = graphData.edges.filter(function(e) { return nodeSet[e.src] && nodeSet[e.dst]; });

      var container = document.getElementById('miniGraphContainer');
      var width = container.clientWidth || 600;
      var height = 280;
      svg.attr('viewBox', '0 0 ' + width + ' ' + height);

      var defs = svg.append('defs');
      ['calls','opens'].forEach(function(t) {
        defs.append('marker').attr('id','mini-arrow-'+t)
          .attr('viewBox','0 0 10 10').attr('refX',20).attr('refY',5)
          .attr('markerWidth',6).attr('markerHeight',6).attr('orient','auto')
          .append('path').attr('d','M 0 0 L 10 5 L 0 10 z')
          .attr('fill', t === 'calls' ? '#3b82f6' : '#f59e0b');
      });

      var nodes = topNodes.map(function(n) { return Object.assign({}, n); });
      var links = edges.map(function(e) { return {source:e.src, target:e.dst, type:e.relation_type}; });

      var sim = d3.forceSimulation(nodes)
        .force('link', d3.forceLink(links).id(function(d){return d.id;}).distance(60))
        .force('charge', d3.forceManyBody().strength(-120))
        .force('center', d3.forceCenter(width/2, height/2))
        .force('collision', d3.forceCollide().radius(function(d){return 8+Math.min(10,d.degree||0)+5;}))
        .stop();
      for (var i=0; i<150; i++) sim.tick();
      nodes.forEach(function(n) {
        n.x = Math.max(30, Math.min(width-30, n.x));
        n.y = Math.max(30, Math.min(height-30, n.y));
      });

      svg.selectAll('line.edge').data(links).join('line').attr('class','edge')
        .attr('x1',function(d){return d.source.x;}).attr('y1',function(d){return d.source.y;})
        .attr('x2',function(d){return d.target.x;}).attr('y2',function(d){return d.target.y;})
        .attr('stroke',function(d){return d.type==='opens'?'#f59e0b':'#3b82f6';})
        .attr('stroke-width',1.5).attr('stroke-opacity',0.5)
        .attr('marker-end',function(d){return 'url(#mini-arrow-'+d.type+')';});

      var g = svg.selectAll('g.node').data(nodes).join('g').attr('class','node')
        .attr('transform',function(d){return 'translate('+d.x+','+d.y+')';});
      g.append('circle')
        .attr('r',function(d){return 4+Math.min(8,(d.degree||0)*0.8);})
        .attr('fill','#0d9488').attr('fill-opacity',0.85).attr('stroke','#115e59').attr('stroke-width',1);
      g.append('text').text(function(d){return d.name;})
        .attr('y',function(d){return -(6+Math.min(8,(d.degree||0)*0.8));})
        .attr('text-anchor','middle').attr('font-size',9).attr('fill','#475569');
    }

    /* ===== Full Interactive Graph (Dependencies) ===== */
    function renderFullGraph(graphData) {
      var svgEl = document.getElementById('fullGraphSvg');
      var svg = d3.select(svgEl);
      svg.selectAll('*').remove();
      if (fullSimulation) { fullSimulation.stop(); fullSimulation = null; }

      if (!graphData || !graphData.nodes || !graphData.nodes.length) {
        svg.append('text').attr('x',20).attr('y',30).attr('fill','#94a3b8').attr('font-size',13).text('그래프 데이터 없음');
        return;
      }

      var container = document.getElementById('fullGraphContainer');
      var width = container.clientWidth || 900;
      var height = parseInt(getComputedStyle(svgEl).height) || 550;

      var filteredEdges = graphData.edges;
      if (currentGraphFilter !== 'all') {
        filteredEdges = graphData.edges.filter(function(e) { return e.relation_type === currentGraphFilter; });
      }
      var nodeIds = {};
      filteredEdges.forEach(function(e) { nodeIds[e.src] = true; nodeIds[e.dst] = true; });
      var filteredNodes = graphData.nodes.filter(function(n) { return nodeIds[n.id]; });

      if (!filteredNodes.length) {
        svg.append('text').attr('x',20).attr('y',30).attr('fill','#94a3b8').attr('font-size',13).text('선택된 관계 타입의 데이터 없음');
        return;
      }

      svg.attr('viewBox', '0 0 ' + width + ' ' + height);

      var defs = svg.append('defs');
      ['calls','opens'].forEach(function(t) {
        defs.append('marker').attr('id','full-arrow-'+t)
          .attr('viewBox','0 0 10 10').attr('refX',20).attr('refY',5)
          .attr('markerWidth',6).attr('markerHeight',6).attr('orient','auto')
          .append('path').attr('d','M 0 0 L 10 5 L 0 10 z')
          .attr('fill', t==='calls'?'#3b82f6':'#f59e0b');
      });

      var nodes = filteredNodes.map(function(n) { return Object.assign({}, n); });
      var links = filteredEdges.map(function(e) {
        return {source:e.src, target:e.dst, type:e.relation_type, confidence:e.confidence};
      });

      var gRoot = svg.append('g');
      var zoom = d3.zoom().scaleExtent([0.3, 5]).on('zoom', function(event) {
        gRoot.attr('transform', event.transform);
      });
      svg.call(zoom);

      var linkSel = gRoot.selectAll('line.edge').data(links).join('line').attr('class','edge')
        .attr('stroke',function(d){return d.type==='opens'?'#f59e0b':'#3b82f6';})
        .attr('stroke-width',1.5).attr('stroke-opacity',0.4)
        .attr('marker-end',function(d){return 'url(#full-arrow-'+d.type+')';});

      var nodeSel = gRoot.selectAll('g.node').data(nodes).join('g').attr('class','node').style('cursor','pointer');
      var circles = nodeSel.append('circle')
        .attr('r',function(d){return 6+Math.min(14,(d.degree||0)*0.7);})
        .attr('fill','#0d9488').attr('fill-opacity',0.85).attr('stroke','#115e59').attr('stroke-width',1.5);
      var labels = nodeSel.append('text').text(function(d){return d.name;})
        .attr('dy',function(d){return -(8+Math.min(14,(d.degree||0)*0.7));})
        .attr('text-anchor','middle').attr('font-size',10).attr('fill','#475569').attr('pointer-events','none');

      var tooltip = document.getElementById('graphTooltip');

      nodeSel.on('mouseenter', function(event, d) {
        tooltip.innerHTML = '<strong>' + esc(d.name) + '</strong><br>In: ' + d.in_degree + ' / Out: ' + d.out_degree + ' / Total: ' + d.degree;
        tooltip.classList.add('visible');
        var rect = container.getBoundingClientRect();
        tooltip.style.left = (event.clientX - rect.left + 12) + 'px';
        tooltip.style.top = (event.clientY - rect.top - 10) + 'px';
        var connected = {};
        connected[d.id] = true;
        links.forEach(function(l) {
          var sId = typeof l.source === 'object' ? l.source.id : l.source;
          var tId = typeof l.target === 'object' ? l.target.id : l.target;
          if (sId === d.id) connected[tId] = true;
          if (tId === d.id) connected[sId] = true;
        });
        circles.attr('fill-opacity', function(n) { return connected[n.id] ? 1 : 0.15; });
        linkSel.attr('stroke-opacity', function(l) {
          var sId = typeof l.source === 'object' ? l.source.id : l.source;
          var tId = typeof l.target === 'object' ? l.target.id : l.target;
          return (sId === d.id || tId === d.id) ? 0.8 : 0.05;
        });
        labels.attr('fill-opacity', function(n) { return connected[n.id] ? 1 : 0.15; });
      }).on('mouseleave', function() {
        tooltip.classList.remove('visible');
        circles.attr('fill-opacity', 0.85);
        linkSel.attr('stroke-opacity', 0.4);
        labels.attr('fill-opacity', 1);
      }).on('click', function(event, d) {
        navToObject(d.name);
      });

      nodeSel.call(d3.drag()
        .on('start', function(event, d) {
          if (!event.active) fullSimulation.alphaTarget(0.3).restart();
          d.fx = d.x; d.fy = d.y;
        })
        .on('drag', function(event, d) { d.fx = event.x; d.fy = event.y; })
        .on('end', function(event, d) {
          if (!event.active) fullSimulation.alphaTarget(0);
          d.fx = null; d.fy = null;
        })
      );

      fullSimulation = d3.forceSimulation(nodes)
        .force('link', d3.forceLink(links).id(function(d){return d.id;}).distance(70))
        .force('charge', d3.forceManyBody().strength(-150))
        .force('center', d3.forceCenter(width/2, height/2))
        .force('collision', d3.forceCollide().radius(function(d){return 8+Math.min(14,(d.degree||0)*0.7)+4;}))
        .on('tick', function() {
          linkSel.attr('x1',function(d){return d.source.x;}).attr('y1',function(d){return d.source.y;})
                 .attr('x2',function(d){return d.target.x;}).attr('y2',function(d){return d.target.y;});
          nodeSel.attr('transform',function(d){return 'translate('+d.x+','+d.y+')';});
        });
    }

    /* Graph filter toggle */
    document.getElementById('graphFilter').addEventListener('click', function(e) {
      var btn = e.target.closest('.toggle-btn');
      if (!btn) return;
      document.querySelectorAll('#graphFilter .toggle-btn').forEach(function(b) { b.classList.remove('active'); });
      btn.classList.add('active');
      currentGraphFilter = btn.getAttribute('data-filter');
      if (currentData) renderFullGraph(currentData.graph_data);
    });

    /* ===== Dependencies Tab Tables ===== */
    function renderEventMap(data) {
      renderSortableTable('eventMapTable', data, [
        {key:'object_name', label:'객체명', render: function(v) {
          return '<span class="clickable" data-nav="'+esc(v)+'">'+esc(v)+'</span>';
        }},
        {key:'event_name', label:'이벤트', render: function(v) {
          return '<span class="mono">'+esc(v)+'</span>';
        }},
        {key:'script_ref', label:'스크립트', render: function(v) {
          return '<span class="mono">'+esc(v)+'</span>';
        }},
        {key:'called_objects', label:'호출 대상', render: function(v) {
          if (!v) return '<span style="color:var(--muted)">-</span>';
          return v.split(',').map(function(o) {
            var t = o.trim();
            return '<span class="clickable" data-nav="'+esc(t)+'">'+esc(t)+'</span>';
          }).join(', ');
        }}
      ]);
    }

    function renderGraphEdges(data) {
      renderSortableTable('graphEdgeTable', data, [
        {key:'src_name', label:'Source', render: function(v) {
          return '<span class="clickable" data-nav="'+esc(v)+'">'+esc(v)+'</span>';
        }},
        {key:'dst_name', label:'Target', render: function(v) {
          return '<span class="clickable" data-nav="'+esc(v)+'">'+esc(v)+'</span>';
        }},
        {key:'relation_type', label:'관계', render: function(v) { return badgeHtml(v, v); }},
        {key:'confidence', label:'신뢰도', render: function(v) {
          return '<span style="font-weight:600">' + ((v||0)*100).toFixed(0) + '%</span>';
        }}
      ]);
    }

    /* ===== Table Impact Tab ===== */
    function renderTableImpactSummary(data) {
      var reads = 0, writes = 0, tableSet = {};
      (data||[]).forEach(function(d) {
        if (d.rw_type === 'READ') reads++;
        if (d.rw_type === 'WRITE') writes++;
        tableSet[d.table_name] = true;
      });
      var tables = Object.keys(tableSet).length;
      var cards = [
        {label:'READ', value:reads, color:'green'},
        {label:'WRITE', value:writes, color:'red'},
        {label:'Tables', value:tables, color:'amber'}
      ];
      document.getElementById('tableImpactSummary').innerHTML = cards.map(function(c) {
        return '<div class="metric-card '+c.color+'">' +
          '<div class="metric-label">'+esc(c.label)+'</div>' +
          '<div class="metric-value">'+fmt(c.value)+'</div></div>';
      }).join('');
    }

    function renderTableImpactDetail(data) {
      var filtered = data;
      if (currentRwFilter !== 'all') {
        filtered = data.filter(function(d) { return d.rw_type === currentRwFilter; });
      }
      renderSortableTable('tableImpactDetail', filtered, [
        {key:'table_name', label:'테이블', render: function(v) {
          return '<span class="mono" style="font-weight:600">'+esc(v)+'</span>';
        }},
        {key:'rw_type', label:'R/W', render: function(v) {
          return badgeHtml(v.toLowerCase(), v);
        }},
        {key:'owner_object', label:'참조 객체', render: function(v) {
          return '<span class="clickable" data-nav="'+esc(v)+'">'+esc(v)+'</span>';
        }},
        {key:'sql_kind', label:'SQL 종류', render: function(v) {
          return '<span class="mono">'+esc(v)+'</span>';
        }}
      ]);
    }

    /* RW filter toggle */
    document.getElementById('rwFilter').addEventListener('click', function(e) {
      var btn = e.target.closest('.toggle-btn');
      if (!btn) return;
      document.querySelectorAll('#rwFilter .toggle-btn').forEach(function(b) { b.classList.remove('active'); });
      btn.classList.add('active');
      currentRwFilter = btn.getAttribute('data-filter');
      if (currentData) renderTableImpactDetail(currentData.table_impact);
    });

    /* ===== Inventory Tab ===== */
    function renderTypeDist(data) {
      var counts = {};
      (data||[]).forEach(function(d) { counts[d.type] = (counts[d.type]||0) + 1; });
      var el = document.getElementById('typeDist');
      var sorted = Object.entries(counts).sort(function(a,b) { return b[1]-a[1]; });
      if (!sorted.length) {
        el.innerHTML = '<div class="empty-state"><div class="msg">데이터 없음</div></div>';
        return;
      }
      el.innerHTML = sorted.map(function(e) {
        return '<div class="type-chip">' + badgeHtml('type', e[0]) +
          ' <span class="count">' + fmt(e[1]) + '</span></div>';
      }).join('');
    }

    function renderInventory(data) {
      renderSortableTable('inventoryTable', data, [
        {key:'type', label:'타입', render: function(v) { return badgeHtml('type', v); }},
        {key:'name', label:'객체명', render: function(v) {
          return '<span class="clickable" data-nav="'+esc(v)+'">'+esc(v)+'</span>';
        }},
        {key:'module', label:'모듈', render: function(v) {
          return '<span class="mono">'+esc(v||'-')+'</span>';
        }},
        {key:'source_path', label:'경로', render: function(v) {
          return '<span class="mono" style="color:var(--text-secondary)">'+esc(v||'-')+'</span>';
        }}
      ]);
    }

    function renderUnused(data) {
      document.getElementById('unusedCount').textContent = fmt(data.length);
      renderSortableTable('unusedTable', data, [
        {key:'type', label:'타입', render: function(v) { return badgeHtml('type', v); }},
        {key:'name', label:'객체명', render: function(v) {
          return '<span class="clickable" data-nav="'+esc(v)+'">'+esc(v)+'</span>';
        }},
        {key:'module', label:'모듈', render: function(v) {
          return '<span class="mono">'+esc(v||'-')+'</span>';
        }},
        {key:'source_path', label:'경로', render: function(v) {
          return '<span class="mono" style="color:var(--text-secondary)">'+esc(v||'-')+'</span>';
        }}
      ]);
    }

    /* ===== Main Data Load ===== */
    async function loadRuns() {
      var data = await fetchJson('/api/runs');
      var runs = data.runs || [];
      runSelectEl.innerHTML = runs.map(function(r) {
        return '<option value="'+esc(r.run_id)+'">'+esc(r.run_id)+' ('+esc(r.status)+')</option>';
      }).join('');
      return runs;
    }

    async function loadDashboard() {
      var selectedRun = runSelectEl.value;
      var limit = Number(limitInputEl.value || 200);
      var filters = readFilters();
      var params = new URLSearchParams();
      if (selectedRun) params.set('run_id', selectedRun);
      params.set('limit', String(limit));
      for (var k in filters) { if (filters[k]) params.set(k, filters[k]); }

      statusEl.textContent = 'loading...';
      var payload = await fetchJson('/api/all?' + params.toString());
      currentData = payload;

      renderActiveFilters(payload.filters || {});

      /* Overview */
      renderMetrics(payload.summary || {}, (payload.unused_object_candidates || []).length);
      renderRelationBar(payload.relation_counts || []);
      renderRunInfo(payload.run || null);
      renderMiniGraph(payload.graph_data);

      /* Dependencies */
      renderEventMap(payload.event_function_map || []);
      renderGraphEdges(payload.screen_call_graph || []);

      /* Table Impact */
      renderTableImpactSummary(payload.table_impact || []);
      renderTableImpactDetail(payload.table_impact || []);

      /* Inventory */
      renderTypeDist(payload.screen_inventory || []);
      renderInventory(payload.screen_inventory || []);
      renderUnused(payload.unused_object_candidates || []);

      /* Render full graph only if dependencies tab is active */
      var depTab = document.getElementById('tab-dependencies');
      if (depTab.classList.contains('active')) renderFullGraph(payload.graph_data);

      /* Status */
      var parts = [];
      var f = payload.filters || {};
      for (var fk in f) { if (f[fk]) parts.push(fk + '=' + f[fk]); }
      var suffix = parts.length ? ' | filters: ' + parts.join(', ') : '';
      statusEl.textContent = 'run_id=' + payload.run.run_id + ' | limit=' + payload.limit + suffix;
    }

    async function boot() {
      try {
        var runs = await loadRuns();
        if (!runs.length) { statusEl.textContent = 'No runs found in DB'; return; }
        await loadDashboard();
      } catch(e) { handleErr(e); }
    }

    /* ===== Event Handlers ===== */
    document.getElementById('reloadBtn').addEventListener('click', function() { loadDashboard().catch(handleErr); });
    document.getElementById('applyFilterBtn').addEventListener('click', function() { loadDashboard().catch(handleErr); });
    document.getElementById('clearFilterBtn').addEventListener('click', function() { clearFilters(); loadDashboard().catch(handleErr); });
    runSelectEl.addEventListener('change', function() { loadDashboard().catch(handleErr); });

    [searchInputEl, objectInputEl, tableInputEl].forEach(function(el) {
      el.addEventListener('keydown', function(ev) {
        if (ev.key === 'Enter') loadDashboard().catch(handleErr);
      });
    });

    boot();
  </script>
</body>
</html>
"""

    return html.replace("__TITLE__", escape("PB Analyzer Dashboard"))
