"""
Report generation service -- JSON and PDF test project reports.

Generates comprehensive reports that include test case results,
Jira bug status summaries, and completion statistics.
All queries are tenant-scoped via ``tenant_filter``.
"""
import io
import logging
from datetime import datetime, timezone

from database.models import TestProject, TestCase, TestResult, JiraIssueLink
from middleware.tenant import tenant_filter, get_tenant_id

logger = logging.getLogger(__name__)

# Jira status groupings for summary statistics
_OPEN_STATUSES = frozenset(('open', 'to do', 'new'))
_IN_PROGRESS_STATUSES = frozenset(('in progress', 'in review'))
_RESOLVED_STATUSES = frozenset(('resolved', 'done', 'closed'))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_project_report(db, project_id, fmt='json'):
    """Generate a test project report with Jira bug status.

    Parameters
    ----------
    db : Session
        SQLAlchemy database session.
    project_id : int
        The test project ID.
    fmt : str
        ``'json'`` returns a dict; ``'pdf'`` returns raw PDF bytes.

    Returns
    -------
    tuple
        ``(report_data_or_pdf_bytes, None)`` on success, or
        ``(None, error_message)`` on failure.
    """
    # 1. Get project (tenant-scoped)
    project = (
        tenant_filter(db.query(TestProject), TestProject)
        .filter_by(id=project_id)
        .first()
    )
    if not project:
        return None, 'Project not found'

    # 2. Get test cases assigned to this project
    cases = (
        tenant_filter(db.query(TestCase), TestCase)
        .filter(TestCase.test_project_id == project_id)
        .order_by(TestCase.id.asc())
        .all()
    )

    # 3. Get test results for this project
    results = (
        db.query(TestResult)
        .filter(TestResult.project_id == project_id)
        .all()
    )
    results_map = {r.test_case_id: r for r in results}

    # 4. Get Jira issue links for the test results in this project
    jira_links = []
    if results:
        result_ids = [r.id for r in results]
        tenant_id = get_tenant_id()
        jira_links = (
            db.query(JiraIssueLink)
            .filter(
                JiraIssueLink.tenant_id == tenant_id,
                JiraIssueLink.test_result_id.in_(result_ids),
            )
            .all()
        )

    # 5. Group Jira links by test_case_id (via their test_result)
    result_id_to_case_id = {r.id: r.test_case_id for r in results}
    jira_by_case = {}
    for link in jira_links:
        case_id = result_id_to_case_id.get(link.test_result_id)
        if case_id is not None:
            jira_by_case.setdefault(case_id, []).append(link)

    # 6. Jira summary statistics
    jira_summary = _compute_jira_summary(jira_links)

    # 7. Build case detail list
    case_details = _build_case_details(cases, results_map, jira_by_case)

    # 8. Compute stats
    stats = _compute_report_stats(case_details)

    report_data = {
        'project': {
            'name': project.name,
            'description': project.description,
            'status': project.status,
            'start_time': project.start_time.isoformat() if project.start_time else None,
            'end_time': project.end_time.isoformat() if project.end_time else None,
        },
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'stats': stats,
        'jira_summary': jira_summary,
        'test_cases': case_details,
    }

    if fmt == 'pdf':
        pdf_bytes = generate_pdf(report_data)
        return pdf_bytes, None

    return report_data, None


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

def generate_pdf(report_data):
    """Generate a PDF document from the report data using reportlab.

    Returns raw PDF bytes suitable for HTTP response.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    )
    from reportlab.lib.units import inch, cm

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
    )
    elements = []
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Title'],
        fontSize=18,
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        'ReportSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.grey,
        spaceAfter=12,
    )
    heading2_style = styles['Heading2']
    heading4_style = styles['Heading4']
    normal_style = styles['Normal']

    # -- Title ----------------------------------------------------------------
    elements.append(Paragraph(report_data['project']['name'], title_style))

    description = report_data['project'].get('description') or ''
    if description:
        elements.append(Paragraph(description, subtitle_style))

    generated_at = report_data.get('generated_at', '')
    elements.append(Paragraph(f"Generated: {generated_at}", subtitle_style))
    elements.append(Spacer(1, 12))

    # -- Stats summary table --------------------------------------------------
    stats = report_data['stats']
    stats_data = [
        ['Total', 'Pass', 'Fail', 'Blocked', 'Not Tested', 'Completion'],
        [
            str(stats['total']),
            str(stats['pass_count']),
            str(stats['fail_count']),
            str(stats['blocked_count']),
            str(stats['not_tested_count']),
            f"{stats['completion_rate']}%",
        ],
    ]
    col_width = (A4[0] - 3 * cm) / 6  # Distribute across page width
    stats_table = Table(stats_data, colWidths=[col_width] * 6)
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#333333')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
    ]))
    elements.append(stats_table)
    elements.append(Spacer(1, 16))

    # -- Jira Bug Summary -----------------------------------------------------
    jira = report_data['jira_summary']
    if jira['total'] > 0:
        elements.append(Paragraph('Jira Bug Summary', heading2_style))
        jira_data = [
            ['Open', 'In Progress', 'Resolved', 'Total'],
            [
                str(jira['open_count']),
                str(jira['in_progress_count']),
                str(jira['resolved_count']),
                str(jira['total']),
            ],
        ]
        jira_col_width = (A4[0] - 3 * cm) / 4
        jira_table = Table(jira_data, colWidths=[jira_col_width] * 4)
        jira_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#333333')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ]))
        elements.append(jira_table)
        elements.append(Spacer(1, 16))

    # -- Test case results ----------------------------------------------------
    elements.append(Paragraph('Test Case Results', heading2_style))
    elements.append(Spacer(1, 6))

    status_labels = {
        'pass': 'PASS',
        'fail': 'FAIL',
        'blocked': 'BLOCKED',
        'not_tested': 'NOT TESTED',
    }

    for case in report_data['test_cases']:
        status_text = status_labels.get(case['result_status'], case['result_status'])
        elements.append(Paragraph(
            f"<b>{case['tc_id']}</b> | {case['title']} | <b>{status_text}</b>",
            heading4_style,
        ))

        if case.get('notes'):
            elements.append(Paragraph(f"Notes: {case['notes']}", normal_style))
        if case.get('blocked_reason'):
            elements.append(Paragraph(
                f"Blocked Reason: {case['blocked_reason']}", normal_style,
            ))
        if case.get('known_issues'):
            elements.append(Paragraph(
                f"Known Issues: {case['known_issues']}", normal_style,
            ))

        # Jira issues for this case
        for jira_issue in case.get('jira_issues', []):
            jira_text = f"Bug: {jira_issue['key']} ({jira_issue['status']}"
            if jira_issue.get('assignee'):
                jira_text += f", {jira_issue['assignee']}"
            jira_text += ")"
            elements.append(Paragraph(jira_text, normal_style))

        elements.append(Spacer(1, 6))

    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compute_jira_summary(jira_links):
    """Calculate Jira issue status summary from a list of JiraIssueLink objects."""
    open_count = 0
    in_progress_count = 0
    resolved_count = 0

    for link in jira_links:
        status_lower = (link.jira_status or '').lower()
        if status_lower in _OPEN_STATUSES:
            open_count += 1
        elif status_lower in _IN_PROGRESS_STATUSES:
            in_progress_count += 1
        elif status_lower in _RESOLVED_STATUSES:
            resolved_count += 1

    return {
        'open_count': open_count,
        'in_progress_count': in_progress_count,
        'resolved_count': resolved_count,
        'total': len(jira_links),
    }


def _build_case_details(cases, results_map, jira_by_case):
    """Build the list of case detail dicts for the report."""
    case_details = []
    for case in cases:
        result = results_map.get(case.id)
        case_jira = jira_by_case.get(case.id, [])

        case_details.append({
            'tc_id': case.tc_id,
            'title': case.title,
            'user_role': case.user_role,
            'feature_description': case.feature_description,
            'priority': case.priority,
            'result_status': result.status if result else 'not_tested',
            'notes': result.notes if result else None,
            'known_issues': result.known_issues if result else None,
            'blocked_reason': result.blocked_reason if result else None,
            'jira_issues': [
                {
                    'key': j.jira_issue_key,
                    'summary': j.jira_issue_summary,
                    'status': j.jira_status,
                    'assignee': j.jira_assignee,
                    'priority': j.jira_priority,
                }
                for j in case_jira
            ],
        })

    return case_details


def _compute_report_stats(case_details):
    """Compute pass/fail/blocked/not_tested statistics from case details."""
    total = len(case_details)
    pass_count = sum(1 for c in case_details if c['result_status'] == 'pass')
    fail_count = sum(1 for c in case_details if c['result_status'] == 'fail')
    blocked_count = sum(1 for c in case_details if c['result_status'] == 'blocked')
    not_tested_count = sum(1 for c in case_details if c['result_status'] == 'not_tested')

    completion_rate = (
        round((total - not_tested_count) / total * 100, 1) if total > 0 else 0.0
    )

    return {
        'total': total,
        'pass_count': pass_count,
        'fail_count': fail_count,
        'blocked_count': blocked_count,
        'not_tested_count': not_tested_count,
        'completion_rate': completion_rate,
    }
