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
<html lang=\"ko\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>__TITLE__</title>
  <style>
    :root {
      --bg: #f7fafc;
      --surface: #ffffff;
      --text: #1f2937;
      --muted: #6b7280;
      --line: #e5e7eb;
      --accent: #0f766e;
      --accent-soft: #ccfbf1;
      --call: #0ea5e9;
      --open: #f59e0b;
    }
    body {
      margin: 0;
      background: radial-gradient(circle at 20% 0%, #e6fffa, transparent 35%), var(--bg);
      color: var(--text);
      font-family: "Pretendard", "Noto Sans KR", sans-serif;
    }
    .container {
      max-width: 1280px;
      margin: 0 auto;
      padding: 24px;
    }
    .header {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 16px;
    }
    h1 { margin: 0; font-size: 28px; }
    .sub { color: var(--muted); margin-top: 4px; font-size: 14px; }
    .controls {
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
    }
    .filter-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 8px;
      margin-bottom: 12px;
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 10px;
    }
    .filter-item {
      display: flex;
      flex-direction: column;
      gap: 6px;
      font-size: 12px;
      color: var(--muted);
    }
    select, input, button {
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 8px 10px;
      font-size: 14px;
      background: #fff;
      color: var(--text);
    }
    button {
      cursor: pointer;
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
    }
    .btn-subtle {
      background: #fff;
      color: var(--text);
      border-color: var(--line);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }
    .card {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
    }
    .card .label { color: var(--muted); font-size: 12px; }
    .card .value { font-size: 22px; font-weight: 700; margin-top: 6px; }
    .two-col {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-bottom: 12px;
    }
    @media (max-width: 960px) {
      .two-col { grid-template-columns: 1fr; }
    }
    .panel {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
      margin-bottom: 12px;
    }
    .panel h2 { margin: 0 0 10px 0; font-size: 16px; }
    .table-wrap { overflow: auto; max-height: 360px; }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      border-bottom: 1px solid var(--line);
      text-align: left;
      padding: 7px;
      white-space: nowrap;
    }
    th { background: #f9fafb; position: sticky; top: 0; }
    .pill {
      display: inline-block;
      background: var(--accent-soft);
      color: #134e4a;
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
      margin-right: 4px;
      margin-bottom: 4px;
    }
    #status { color: var(--muted); font-size: 13px; margin-bottom: 10px; }
    .legend {
      display: flex;
      gap: 14px;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 8px;
      flex-wrap: wrap;
    }
    .legend-item {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .legend-line {
      width: 20px;
      height: 3px;
      border-radius: 2px;
      display: inline-block;
    }
    .legend-line.calls { background: var(--call); }
    .legend-line.opens { background: var(--open); }
    #graphSvg {
      width: 100%;
      height: 460px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: #fcfeff;
    }
  </style>
</head>
<body>
  <div class=\"container\">
    <div class=\"header\">
      <div>
        <h1>__TITLE__</h1>
        <div class=\"sub\">IR DB 기반 영향분석 조회</div>
      </div>
      <div class=\"controls\">
        <label for=\"runSelect\">run_id</label>
        <select id=\"runSelect\"></select>
        <label for=\"limitInput\">limit</label>
        <input id=\"limitInput\" type=\"number\" value=\"200\" min=\"10\" max=\"2000\" />
        <button id=\"reloadBtn\">새로고침</button>
      </div>
    </div>

    <div class=\"filter-grid\">
      <label class=\"filter-item\">검색어
        <input id=\"searchInput\" type=\"text\" placeholder=\"이름/모듈/경로/관계\" />
      </label>
      <label class=\"filter-item\">객체명
        <input id=\"objectInput\" type=\"text\" placeholder=\"예: w_main\" />
      </label>
      <label class=\"filter-item\">테이블명
        <input id=\"tableInput\" type=\"text\" placeholder=\"예: TB_ORDER\" />
      </label>
      <label class=\"filter-item\">관계 타입
        <select id=\"relationSelect\">
          <option value=\"\">(전체)</option>
          <option value=\"calls\">calls</option>
          <option value=\"opens\">opens</option>
          <option value=\"uses_dw\">uses_dw</option>
          <option value=\"reads_table\">reads_table</option>
          <option value=\"writes_table\">writes_table</option>
          <option value=\"triggers_event\">triggers_event</option>
        </select>
      </label>
      <div class=\"controls\" style=\"align-items:flex-end;\">
        <button id=\"applyFilterBtn\">필터 적용</button>
        <button id=\"clearFilterBtn\" class=\"btn-subtle\">필터 초기화</button>
      </div>
    </div>

    <div id=\"status\">loading...</div>

    <div class=\"grid\" id=\"summaryGrid\"></div>

    <div class=\"two-col\">
      <div class=\"panel\">
        <h2>Relation Breakdown</h2>
        <div id=\"relationPills\"></div>
      </div>
      <div class=\"panel\">
        <h2>Run Info</h2>
        <div id=\"runInfo\"></div>
      </div>
    </div>

    <div class=\"panel\">
      <h2>화면 이동/호출 그래프 시각화</h2>
      <div class=\"legend\">
        <span class=\"legend-item\"><span class=\"legend-line calls\"></span>calls</span>
        <span class=\"legend-item\"><span class=\"legend-line opens\"></span>opens</span>
      </div>
      <svg id=\"graphSvg\" viewBox=\"0 0 1000 460\" role=\"img\"></svg>
    </div>

    <div class=\"panel\">
      <h2>화면 인벤토리</h2>
      <div class=\"table-wrap\" id=\"inventoryTable\"></div>
    </div>

    <div class=\"panel\">
      <h2>이벤트-함수 맵</h2>
      <div class=\"table-wrap\" id=\"eventMapTable\"></div>
    </div>

    <div class=\"panel\">
      <h2>테이블 영향도</h2>
      <div class=\"table-wrap\" id=\"tableImpactTable\"></div>
    </div>

    <div class=\"panel\">
      <h2>화면 이동/호출 그래프(Edge)</h2>
      <div class=\"table-wrap\" id=\"graphTable\"></div>
    </div>

    <div class=\"panel\">
      <h2>미사용 객체 후보</h2>
      <div class=\"table-wrap\" id=\"unusedTable\"></div>
    </div>
  </div>

  <script>
    const statusEl = document.getElementById('status');
    const runSelectEl = document.getElementById('runSelect');
    const limitInputEl = document.getElementById('limitInput');
    const reloadBtn = document.getElementById('reloadBtn');
    const applyFilterBtn = document.getElementById('applyFilterBtn');
    const clearFilterBtn = document.getElementById('clearFilterBtn');
    const searchInputEl = document.getElementById('searchInput');
    const objectInputEl = document.getElementById('objectInput');
    const tableInputEl = document.getElementById('tableInput');
    const relationSelectEl = document.getElementById('relationSelect');

    function escapeHtml(value) {
      return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
    }

    function readFilters() {
      return {
        search: searchInputEl.value.trim(),
        object_name: objectInputEl.value.trim(),
        table_name: tableInputEl.value.trim(),
        relation_type: relationSelectEl.value.trim(),
      };
    }

    function clearFilters() {
      searchInputEl.value = '';
      objectInputEl.value = '';
      tableInputEl.value = '';
      relationSelectEl.value = '';
    }

    async function fetchJson(url) {
      const response = await fetch(url);
      if (!response.ok) {
        const fallback = `request failed (${response.status})`;
        let body = null;
        try { body = await response.json(); } catch (_) {}
        throw new Error((body && body.error) ? body.error : fallback);
      }
      return await response.json();
    }

    function renderTable(containerId, rows) {
      const container = document.getElementById(containerId);
      if (!rows || rows.length === 0) {
        container.innerHTML = '<div class="sub">데이터 없음</div>';
        return;
      }

      const headers = Object.keys(rows[0]);
      const thead = `<thead><tr>${headers.map(h => `<th>${escapeHtml(h)}</th>`).join('')}</tr></thead>`;
      const bodyRows = rows.map(row => {
        const cells = headers.map(h => `<td>${escapeHtml(row[h])}</td>`).join('');
        return `<tr>${cells}</tr>`;
      }).join('');
      container.innerHTML = `<table>${thead}<tbody>${bodyRows}</tbody></table>`;
    }

    function renderSummary(summary) {
      const pairs = [
        ['App Objects', summary.app_objects],
        ['Table Objects', summary.table_objects],
        ['Relations', summary.relations],
        ['SQL Statements', summary.sql_statements],
        ['SQL Tables', summary.sql_tables],
      ];

      document.getElementById('summaryGrid').innerHTML = pairs.map(([label, value]) => (
        `<div class="card"><div class="label">${escapeHtml(label)}</div><div class="value">${escapeHtml(value)}</div></div>`
      )).join('');
    }

    function renderRelationPills(items) {
      const container = document.getElementById('relationPills');
      if (!items || items.length === 0) {
        container.innerHTML = '<div class="sub">데이터 없음</div>';
        return;
      }
      container.innerHTML = items.map(item => (
        `<span class="pill">${escapeHtml(item.relation_type)}: ${escapeHtml(item.count)}</span>`
      )).join('');
    }

    function renderRunInfo(run) {
      const container = document.getElementById('runInfo');
      if (!run) {
        container.innerHTML = '<div class="sub">데이터 없음</div>';
        return;
      }
      container.innerHTML = `
        <div><strong>run_id:</strong> ${escapeHtml(run.run_id)}</div>
        <div><strong>status:</strong> ${escapeHtml(run.status)}</div>
        <div><strong>started_at:</strong> ${escapeHtml(run.started_at || '-')}</div>
        <div><strong>finished_at:</strong> ${escapeHtml(run.finished_at || '-')}</div>
        <div><strong>source_version:</strong> ${escapeHtml(run.source_version || '-')}</div>
      `;
    }

    function buildGraphLayout(graphData) {
      const nodes = graphData.nodes || [];
      const edges = graphData.edges || [];
      const width = 1000;
      const height = 460;
      const centerX = width / 2;
      const centerY = height / 2;
      const radius = Math.max(120, Math.min(width, height) / 2 - 70);

      const positionedNodes = nodes.map((node, index) => {
        const angle = (Math.PI * 2 * index) / Math.max(nodes.length, 1);
        return {
          ...node,
          x: centerX + radius * Math.cos(angle),
          y: centerY + radius * Math.sin(angle),
        };
      });

      const nodePos = new Map(positionedNodes.map(node => [node.id, node]));
      const positionedEdges = edges.map(edge => ({
        ...edge,
        srcNode: nodePos.get(edge.src),
        dstNode: nodePos.get(edge.dst),
      })).filter(edge => edge.srcNode && edge.dstNode);

      return { width, height, nodes: positionedNodes, edges: positionedEdges };
    }

    function renderGraph(graphData) {
      const svg = document.getElementById('graphSvg');
      const { width, height, nodes, edges } = buildGraphLayout(graphData || { nodes: [], edges: [] });

      if (!nodes.length || !edges.length) {
        svg.innerHTML = `<text x="20" y="30" fill="#6b7280" font-size="14">그래프 데이터가 없습니다.</text>`;
        svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
        return;
      }

      const defs = `
        <defs>
          <marker id="arrow-call" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
            <polygon points="0 0, 7 3.5, 0 7" fill="#0ea5e9"></polygon>
          </marker>
          <marker id="arrow-open" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
            <polygon points="0 0, 7 3.5, 0 7" fill="#f59e0b"></polygon>
          </marker>
        </defs>
      `;

      const edgeSvg = edges.map(edge => {
        const color = edge.relation_type === 'opens' ? '#f59e0b' : '#0ea5e9';
        const marker = edge.relation_type === 'opens' ? 'url(#arrow-open)' : 'url(#arrow-call)';
        return `
          <line
            x1="${edge.srcNode.x}" y1="${edge.srcNode.y}"
            x2="${edge.dstNode.x}" y2="${edge.dstNode.y}"
            stroke="${color}" stroke-width="2" stroke-opacity="0.75"
            marker-end="${marker}">
            <title>${escapeHtml(edge.src)} -> ${escapeHtml(edge.dst)} (${escapeHtml(edge.relation_type)})</title>
          </line>
        `;
      }).join('');

      const nodeSvg = nodes.map(node => {
        const r = 10 + Math.min(10, Number(node.degree || 0));
        return `
          <g>
            <circle cx="${node.x}" cy="${node.y}" r="${r}" fill="#0f766e" fill-opacity="0.9" stroke="#0b4f49" stroke-width="1.5">
              <title>${escapeHtml(node.name)} (in=${escapeHtml(node.in_degree)} out=${escapeHtml(node.out_degree)})</title>
            </circle>
            <text x="${node.x}" y="${node.y - r - 6}" text-anchor="middle" fill="#374151" font-size="11">
              ${escapeHtml(node.name)}
            </text>
          </g>
        `;
      }).join('');

      svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
      svg.innerHTML = defs + edgeSvg + nodeSvg;
    }

    async function loadRuns() {
      const runPayload = await fetchJson('/api/runs');
      const runs = runPayload.runs || [];

      runSelectEl.innerHTML = runs.map(run => (
        `<option value="${escapeHtml(run.run_id)}">${escapeHtml(run.run_id)} (${escapeHtml(run.status)})</option>`
      )).join('');

      return runs;
    }

    function appendFilters(params, filters) {
      Object.entries(filters).forEach(([key, value]) => {
        if (value) {
          params.set(key, value);
        }
      });
    }

    async function loadDashboard() {
      const selectedRun = runSelectEl.value;
      const limit = Number(limitInputEl.value || 200);
      const filters = readFilters();

      const params = new URLSearchParams();
      if (selectedRun) params.set('run_id', selectedRun);
      params.set('limit', String(limit));
      appendFilters(params, filters);

      statusEl.textContent = 'loading...';
      const payload = await fetchJson(`/api/all?${params.toString()}`);

      renderSummary(payload.summary || {});
      renderRelationPills(payload.relation_counts || []);
      renderRunInfo(payload.run || null);
      renderGraph(payload.graph_data || { nodes: [], edges: [] });
      renderTable('inventoryTable', payload.screen_inventory || []);
      renderTable('eventMapTable', payload.event_function_map || []);
      renderTable('tableImpactTable', payload.table_impact || []);
      renderTable('graphTable', payload.screen_call_graph || []);
      renderTable('unusedTable', payload.unused_object_candidates || []);

      const filterText = Object.entries(payload.filters || {})
        .filter(([, value]) => value)
        .map(([key, value]) => `${key}=${value}`)
        .join(', ');
      const suffix = filterText ? ` | filters: ${filterText}` : '';
      statusEl.textContent = `run_id=${payload.run.run_id} | rows_limit=${payload.limit}${suffix}`;
    }

    async function boot() {
      try {
        const runs = await loadRuns();
        if (runs.length === 0) {
          statusEl.textContent = 'No runs found in DB';
          return;
        }
        await loadDashboard();
      } catch (error) {
        statusEl.textContent = `error: ${error.message}`;
      }
    }

    reloadBtn.addEventListener('click', () => {
      loadDashboard().catch(error => {
        statusEl.textContent = `error: ${error.message}`;
      });
    });

    applyFilterBtn.addEventListener('click', () => {
      loadDashboard().catch(error => {
        statusEl.textContent = `error: ${error.message}`;
      });
    });

    clearFilterBtn.addEventListener('click', () => {
      clearFilters();
      loadDashboard().catch(error => {
        statusEl.textContent = `error: ${error.message}`;
      });
    });

    runSelectEl.addEventListener('change', () => {
      loadDashboard().catch(error => {
        statusEl.textContent = `error: ${error.message}`;
      });
    });

    boot();
  </script>
</body>
</html>
"""

    return html.replace("__TITLE__", escape("PB Analyzer Dashboard"))
