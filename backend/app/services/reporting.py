from __future__ import annotations

from html import escape

from weasyprint import HTML
from typing import Any

from sqlalchemy.orm import Session

from app.services.case_builder import get_case_detail


def _markdown_value(value: Any) -> str:
    if value is None:
        return "Not recorded"

    return str(value)


def build_case_markdown(
    db: Session,
    case_id: Any,
) -> str | None:
    case = get_case_detail(db, case_id)

    if not case:
        return None

    lines: list[str] = [
        "# GrantScope Investigation Case Report",
        "",
        f"**Case ID:** `{case['id']}`",
        f"**Status:** {case['status']}",
        f"**Severity:** {case['severity'].upper()}",
        f"**Confidence:** {case['confidence'].upper()}",
        f"**Disposition:** {case['disposition']}",
        "",
        "## Executive Assessment",
        "",
        case["summary"] or "No summary was generated.",
        "",
        "## Findings",
        "",
    ]

    for finding in case["findings"]:
        lines.extend(
            [
                f"### [{finding['severity'].upper()}] {finding['title']}",
                "",
                finding["rationale"],
                "",
                f"- Rule ID: `{finding['rule_id']}`",
                f"- Confidence: {finding['confidence']}",
                f"- Subject: `{finding['subject_external_id']}`",
                "",
            ]
        )

    lines.extend(
        [
            "## Timeline",
            "",
            "| Time (UTC) | Evidence | Detail | Correlation ID |",
            "|---|---|---|---|",
        ]
    )

    if case["timeline"]:
        for event in case["timeline"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _markdown_value(event["observed_at"]),
                        _markdown_value(event["label"]).replace("|", "\\|"),
                        _markdown_value(event["detail"]).replace("|", "\\|"),
                        _markdown_value(event["correlation_id"]),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| Not recorded | No timestamped evidence | Not recorded | Not recorded |")

    lines.extend(
        [
            "",
            "## Evidence Index",
            "",
        ]
    )

    for evidence in case["evidence"]:
        lines.extend(
            [
                f"- **{evidence['label']}**",
                f"  - Source: `{evidence['source_table']}`",
                f"  - Source ID: `{_markdown_value(evidence['source_external_id'])}`",
                f"  - Detail: {_markdown_value(evidence['detail'])}",
            ]
        )

    lines.extend(
        [
            "",
            "## What Would Make This Benign?",
            "",
        ]
    )

    if case["what_would_make_this_benign"]:
        for step in case["what_would_make_this_benign"]:
            lines.append(f"- {step}")
    else:
        lines.append("- No benign-validation checklist was generated.")

    lines.extend(
        [
            "",
            "## Recommended Human Review Actions",
            "",
        ]
    )

    for recommendation in case["recommended_human_review_actions"]:
        lines.append(f"- {recommendation}")

    lines.extend(
        [
            "",
            "## Missing-Data Notes",
            "",
        ]
    )

    if case["missing_data_notes"]:
        for note in case["missing_data_notes"]:
            lines.append(f"- {note}")
    else:
        lines.append("- No material missing-data note was generated.")

    lines.extend(
        [
            "",
            "---",
            "",
            "GrantScope is an evidence-driven triage workbench. This report does not classify an application as malicious solely from publisher or permission metadata.",
        ]
    )

    return "\n".join(lines)


def _list_items(items: list[str]) -> str:
    if not items:
        return "<li>Not recorded</li>"

    return "".join(f"<li>{escape(item)}</li>" for item in items)


def build_case_html(
    db: Session,
    case_id: Any,
) -> str | None:
    case = get_case_detail(db, case_id)

    if not case:
        return None

    findings_html = "".join(
        f"""
        <article class="finding">
          <div class="finding-header">
            <span class="badge {escape(finding['severity'])}">
              {escape(finding['severity'].upper())}
            </span>
            <span class="confidence">Confidence: {escape(finding['confidence'].upper())}</span>
          </div>
          <h3>{escape(finding['title'])}</h3>
          <p>{escape(finding['rationale'])}</p>
          <dl>
            <dt>Rule ID</dt><dd>{escape(finding['rule_id'])}</dd>
            <dt>Subject</dt><dd>{escape(finding['subject_external_id'])}</dd>
          </dl>
        </article>
        """
        for finding in case["findings"]
    )

    timeline_rows = "".join(
        f"""
        <tr>
          <td>{escape(event['observed_at'])}</td>
          <td>{escape(event['label'])}</td>
          <td>{escape(event['detail'] or 'Not recorded')}</td>
          <td>{escape(event['correlation_id'] or 'Not recorded')}</td>
        </tr>
        """
        for event in case["timeline"]
    )

    if not timeline_rows:
        timeline_rows = """
        <tr>
          <td>Not recorded</td>
          <td>No timestamped evidence</td>
          <td>Not recorded</td>
          <td>Not recorded</td>
        </tr>
        """

    evidence_rows = "".join(
        f"""
        <tr>
          <td>{escape(evidence['label'])}</td>
          <td>{escape(evidence['source_table'])}</td>
          <td>{escape(evidence['source_external_id'] or 'Not recorded')}</td>
          <td>{escape(evidence['detail'] or 'Not recorded')}</td>
        </tr>
        """
        for evidence in case["evidence"]
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>GrantScope Case Report - {escape(case['id'])}</title>
  <style>
    body {{
      font-family: Arial, Helvetica, sans-serif;
      margin: 0;
      background: #f5f7fb;
      color: #172033;
      line-height: 1.5;
    }}
    .page {{
      width: min(1100px, calc(100% - 48px));
      margin: 32px auto;
      background: #ffffff;
      padding: 42px;
      box-shadow: 0 10px 28px rgba(30, 52, 88, 0.10);
    }}
    h1, h2, h3 {{
      color: #12264d;
    }}
    h1 {{
      margin-bottom: 4px;
    }}
    h2 {{
      border-bottom: 1px solid #dce4f2;
      padding-bottom: 8px;
      margin-top: 36px;
    }}
    .meta {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 12px;
      margin: 24px 0;
    }}
    .meta-card {{
      border: 1px solid #dce4f2;
      border-radius: 8px;
      padding: 12px;
      background: #f9fbff;
    }}
    .meta-card strong {{
      display: block;
      font-size: 12px;
      text-transform: uppercase;
      color: #5d6b82;
      letter-spacing: 0.04em;
    }}
    .finding {{
      border: 1px solid #dce4f2;
      border-left: 5px solid #315a9b;
      border-radius: 8px;
      padding: 18px;
      margin: 16px 0;
    }}
    .finding-header {{
      display: flex;
      gap: 12px;
      align-items: center;
    }}
    .badge {{
      display: inline-block;
      padding: 4px 8px;
      border-radius: 4px;
      font-weight: 700;
      font-size: 12px;
    }}
    .badge.critical {{ background: #fee2e2; color: #991b1b; }}
    .badge.high {{ background: #ffedd5; color: #9a3412; }}
    .badge.medium {{ background: #fef3c7; color: #92400e; }}
    .badge.low {{ background: #dbeafe; color: #1e40af; }}
    .badge.informational {{ background: #e5e7eb; color: #374151; }}
    .confidence {{
      color: #5d6b82;
      font-size: 13px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      border: 1px solid #dce4f2;
      padding: 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      background: #edf3ff;
    }}
    dl {{
      display: grid;
      grid-template-columns: 120px 1fr;
      gap: 6px 12px;
      font-size: 14px;
    }}
    dt {{
      font-weight: 700;
      color: #485873;
    }}
    dd {{
      margin: 0;
    }}
    .footer {{
      margin-top: 36px;
      padding-top: 18px;
      border-top: 1px solid #dce4f2;
      color: #5d6b82;
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <main class="page">
    <h1>GrantScope Investigation Case Report</h1>
    <p>Evidence-driven Entra OAuth and service-principal triage packet.</p>

    <section class="meta">
      <div class="meta-card"><strong>Case ID</strong>{escape(case['id'])}</div>
      <div class="meta-card"><strong>Status</strong>{escape(case['status'])}</div>
      <div class="meta-card"><strong>Severity</strong>{escape(case['severity'].upper())}</div>
      <div class="meta-card"><strong>Confidence</strong>{escape(case['confidence'].upper())}</div>
      <div class="meta-card"><strong>Disposition</strong>{escape(case['disposition'])}</div>
    </section>

    <h2>Executive Assessment</h2>
    <p>{escape(case['summary'] or 'No summary was generated.')}</p>

    <h2>Findings</h2>
    {findings_html}

    <h2>Timeline</h2>
    <table>
      <thead>
        <tr>
          <th>Time (UTC)</th>
          <th>Evidence</th>
          <th>Detail</th>
          <th>Correlation ID</th>
        </tr>
      </thead>
      <tbody>
        {timeline_rows}
      </tbody>
    </table>

    <h2>Evidence Index</h2>
    <table>
      <thead>
        <tr>
          <th>Evidence</th>
          <th>Source Table</th>
          <th>Source ID</th>
          <th>Detail</th>
        </tr>
      </thead>
      <tbody>
        {evidence_rows}
      </tbody>
    </table>

    <h2>What Would Make This Benign?</h2>
    <ul>
      {_list_items(case['what_would_make_this_benign'])}
    </ul>

    <h2>Recommended Human Review Actions</h2>
    <ul>
      {_list_items(case['recommended_human_review_actions'])}
    </ul>

    <h2>Missing-Data Notes</h2>
    <ul>
      {_list_items(case['missing_data_notes'])}
    </ul>

    <p class="footer">
      GrantScope does not classify an application as malicious solely from
      publisher reputation or permission metadata. This report is intended to
      support analyst review and evidence preservation.
    </p>
  </main>
</body>
</html>
"""


def build_case_report_bundle(
    db: Session,
    case_id: Any,
) -> dict[str, str] | None:
    markdown_report = build_case_markdown(db, case_id)
    html_report = build_case_html(db, case_id)

    if markdown_report is None or html_report is None:
        return None

    return {
        "markdown": markdown_report,
        "html": html_report,
    }

def build_case_pdf(
    db: Session,
    case_id: Any,
) -> bytes | None:
    html_report = build_case_html(
        db=db,
        case_id=case_id,
    )

    if html_report is None:
        return None

    return HTML(
        string=html_report,
        base_url="http://localhost",
    ).write_pdf()