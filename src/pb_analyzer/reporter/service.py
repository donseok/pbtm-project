"""Reporter service for CSV/JSON/HTML outputs."""

from __future__ import annotations

import csv
from html import escape
import json
from pathlib import Path
import sqlite3

from pb_analyzer.common import ReportOutcome, UserInputError

ReportData = dict[str, list[dict[str, object]]]


def generate_reports(db_path: Path, output_dir: Path, report_format: str) -> ReportOutcome:
    """Generates required reports from IR database."""

    if not db_path.exists():
        raise UserInputError(f"DB file not found: {db_path}")

    normalized_format = report_format.lower()
    if normalized_format not in {"csv", "json", "html"}:
        raise UserInputError(f"Unsupported report format: {report_format}")

    output_dir.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        report_data = _collect_report_data(conn)

    generated_files: list[Path] = []

    if normalized_format == "json":
        for report_name, rows in report_data.items():
            report_path = output_dir / f"{report_name}.json"
            report_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            generated_files.append(report_path)

    elif normalized_format == "csv":
        for report_name, rows in report_data.items():
            report_path = output_dir / f"{report_name}.csv"
            _write_csv(report_path, rows)
            generated_files.append(report_path)

    else:
        html_path = output_dir / "report.html"
        html_path.write_text(_render_html(report_data), encoding="utf-8")
        generated_files.append(html_path)

    return ReportOutcome(generated_files=tuple(generated_files))


def _collect_report_data(conn: sqlite3.Connection) -> ReportData:
    inventory = _query(
        conn,
        """
        SELECT type, name, module, source_path
        FROM objects
        ORDER BY type, name
        """,
    )

    event_function_map = _query(
        conn,
        """
        SELECT
            o.name AS object_name,
            e.event_name,
            e.script_ref,
            COALESCE(GROUP_CONCAT(DISTINCT dst.name), '') AS called_objects
        FROM events e
        JOIN objects o ON o.id = e.object_id
        LEFT JOIN relations r
            ON r.src_id = o.id
           AND r.relation_type = 'calls'
        LEFT JOIN objects dst ON dst.id = r.dst_id
        GROUP BY o.name, e.event_name, e.script_ref
        ORDER BY o.name, e.event_name
        """,
    )

    table_impact = _query(
        conn,
        """
        SELECT
            st.table_name,
            st.rw_type,
            owner.name AS owner_object,
            ss.sql_kind
        FROM sql_tables st
        JOIN sql_statements ss ON ss.id = st.sql_id
        JOIN objects owner ON owner.id = ss.owner_id
        ORDER BY st.table_name, owner.name, st.rw_type
        """,
    )

    graph = _query(
        conn,
        """
        SELECT
            src.name AS src_name,
            dst.name AS dst_name,
            r.relation_type,
            r.confidence
        FROM relations r
        JOIN objects src ON src.id = r.src_id
        JOIN objects dst ON dst.id = r.dst_id
        WHERE r.relation_type IN ('opens', 'calls')
        ORDER BY src.name, dst.name, r.relation_type
        """,
    )

    unused_candidates = _query(
        conn,
        """
        SELECT
            o.type,
            o.name,
            o.module,
            o.source_path
        FROM objects o
        LEFT JOIN relations rel_src ON rel_src.src_id = o.id
        LEFT JOIN relations rel_dst ON rel_dst.dst_id = o.id
        LEFT JOIN events e ON e.object_id = o.id
        LEFT JOIN functions f ON f.object_id = o.id
        WHERE rel_src.id IS NULL
          AND rel_dst.id IS NULL
          AND e.id IS NULL
          AND f.id IS NULL
          AND o.type <> 'Table'
        GROUP BY o.id, o.type, o.name, o.module, o.source_path
        ORDER BY o.type, o.name
        """,
    )

    return {
        "screen_inventory": inventory,
        "event_function_map": event_function_map,
        "table_impact": table_impact,
        "screen_call_graph": graph,
        "unused_object_candidates": unused_candidates,
    }


def _query(conn: sqlite3.Connection, sql: str) -> list[dict[str, object]]:
    rows = conn.execute(sql).fetchall()
    return [dict(row) for row in rows]


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames: list[str]
    if rows:
        first_keys = list(rows[0].keys())
        extra_keys = sorted({key for row in rows for key in row.keys()} - set(first_keys))
        fieldnames = first_keys + extra_keys
    else:
        fieldnames = ["empty"]
        rows = [{"empty": ""}]

    with path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _render_html(report_data: ReportData) -> str:
    sections: list[str] = []

    for report_name, rows in report_data.items():
        title = report_name.replace("_", " ").title()
        sections.append(f"<h2>{escape(title)}</h2>")
        sections.append(_render_html_table(rows))

    body = "\n".join(sections)
    return (
        "<!doctype html>\n"
        "<html lang='en'>\n"
        "<head>\n"
        "  <meta charset='utf-8' />\n"
        "  <title>PB Analyzer Report</title>\n"
        "  <style>\n"
        "    body { font-family: sans-serif; margin: 24px; }\n"
        "    table { border-collapse: collapse; width: 100%; margin-bottom: 24px; }\n"
        "    th, td { border: 1px solid #ccc; padding: 8px; text-align: left; }\n"
        "    th { background: #f5f5f5; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        "  <h1>PB Analyzer Report</h1>\n"
        f"  {body}\n"
        "</body>\n"
        "</html>\n"
    )


def _render_html_table(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "<p>No data.</p>"

    headers = list(rows[0].keys())
    header_html = "".join(f"<th>{escape(header)}</th>" for header in headers)

    row_html_parts: list[str] = []
    for row in rows:
        cells = "".join(f"<td>{escape(str(row.get(header, '')))}</td>" for header in headers)
        row_html_parts.append(f"<tr>{cells}</tr>")

    rows_html = "".join(row_html_parts)
    return (
        "<table>"
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table>"
    )
