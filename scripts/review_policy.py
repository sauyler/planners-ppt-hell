"""Single-source review gates and deterministic feedback routing."""

import re


BLOCKING_WARNING_CODES = frozenset({"TEXT_OVERFLOW_MAJOR", "FOOTER_ZONE_INVASION"})
LAYOUT_FEEDBACK_RE = re.compile(r"重做|重新设计|整页|整体|版式|布局|结构|重排|换版", re.IGNORECASE)


def blocking_warning_issues(report):
    """Return warnings that block both review generation and stage finalization."""
    found = []
    reports = report.get("reports", []) if isinstance(report, dict) else []
    for page_report in reports:
        if not isinstance(page_report, dict):
            continue
        page = str(page_report.get("file", ""))
        for item in page_report.get("issues", []):
            if (isinstance(item, dict) and item.get("severity") == "warning"
                    and item.get("code") in BLOCKING_WARNING_CODES):
                found.append({**item, "page": page})
    return found


def visual_feedback_requires_layout(page_feedback):
    """Route structural/global visual requests back to Layout, not local SVG repair."""
    if not isinstance(page_feedback, dict):
        return False
    text_parts = [str(page_feedback.get("custom_feedback", ""))]
    for action in page_feedback.get("selected_review_actions", []):
        if isinstance(action, dict):
            text_parts.extend(str(action.get(key, "")) for key in ("title", "desc", "request"))
        else:
            text_parts.append(str(action))
    for annotation in page_feedback.get("annotations", []):
        if not isinstance(annotation, dict):
            continue
        text_parts.append(str(annotation.get("text", "")))
        try:
            if float(annotation.get("w", 0)) * float(annotation.get("h", 0)) >= 0.40:
                return True
        except (TypeError, ValueError):
            pass
    return bool(LAYOUT_FEEDBACK_RE.search(" ".join(text_parts)))


def layout_reroute_pages(feedback):
    pages = feedback.get("pages", {}) if isinstance(feedback, dict) else {}
    return sorted(
        key for key, value in pages.items()
        if isinstance(value, dict) and not value.get("approved") and visual_feedback_requires_layout(value)
    )
