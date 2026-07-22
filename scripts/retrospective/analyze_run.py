#!/usr/bin/env python3
"""
Run retrospective analysis for Planner's PPT Hell.

Analyzes flow events, feedback, validation warnings, repair history,
and template profile to generate:
  - run_summary.json
  - default_suggestions.md
  - memory_candidates.json

Usage:
  python3 analyze_run.py <project_dir>
  python3 analyze_run.py <project_dir> --output <output_dir>
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

INTERNAL = "_internal"


def load_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def load_jsonl(path):
    """Read a JSONL file into a list of events."""
    path = Path(path)
    events = []
    if not path.exists():
        return events
    try:
        for line in path.read_text(encoding="utf-8").strip().split("\n"):
            if line.strip():
                events.append(json.loads(line))
    except (json.JSONDecodeError, Exception):
        pass
    return events


def analyze_flow_events(events):
    """Analyze flow events for timing and state transitions."""
    if not events:
        return {"total_events": 0, "state_transitions": [], "total_states": [], "stage_durations_ms": {}, "failed_commands": [], "stage_failures": []}

    states = []
    for e in events:
        state = e.get("details", {}).get("state", "")
        if state:
            states.append(state)

    transitions = []
    for i in range(1, len(states)):
        if states[i] != states[i - 1]:
            transitions.append(f"{states[i-1]} → {states[i]}")

    stage_durations = {}
    failed_commands = []
    stage_failures = []
    command_counts = {}
    for event in events:
        event_type = event.get("type", "")
        details = event.get("details", {}) if isinstance(event, dict) else {}
        if event_type == "stage_completed":
            key = details.get("step", "") + (":" + details.get("batch", "") if details.get("batch") else "")
            stage_durations[key] = stage_durations.get(key, 0) + int(details.get("duration_ms", 0) or 0)
        elif event_type == "stage_failed":
            stage_failures.append({"step": details.get("step", ""), "batch": details.get("batch", ""), "issues": details.get("issues", [])})
        elif event_type == "pipeline_command_failed":
            failed_commands.append({"command": details.get("command", ""), "step": details.get("step", ""), "batch": details.get("batch", ""), "duration_ms": details.get("duration_ms", 0)})
        if event_type == "pipeline_command_started":
            key = ":".join(str(details.get(name, "")) for name in ("command", "step", "batch"))
            command_counts[key] = command_counts.get(key, 0) + 1
    repeated_commands = {key: count for key, count in command_counts.items() if count > 1}

    return {
        "total_events": len(events),
        "state_transitions": transitions,
        "total_states": list(dict.fromkeys(states)),
        "stage_durations_ms": stage_durations,
        "failed_commands": failed_commands,
        "stage_failures": stage_failures,
        "repeated_commands": repeated_commands,
    }


def analyze_layout_feedback(feedback):
    """Analyze layout direction feedback for user preferences."""
    if not feedback:
        return {"has_feedback": False, "approved_pages": 0, "rejected_pages": 0, "feedback_themes": []}

    pages = feedback.get("pages", {})
    approved = sum(1 for p in pages.values() if isinstance(p, dict) and p.get("approved"))
    rejected = sum(1 for p in pages.values() if isinstance(p, dict) and not p.get("approved"))

    themes = []
    # Collect feedback themes from page comments
    for pk, page in pages.items():
        if isinstance(page, dict):
            notes = page.get("notes", "")
            if notes:
                themes.append({"page_key": pk, "note": notes[:200]})

    return {
        "has_feedback": True,
        "approved_pages": approved,
        "rejected_pages": rejected,
        "all_approved": feedback.get("all_approved", False),
        "feedback_themes": themes[:10],
    }


def analyze_validation(validation):
    """Analyze validation warnings for common patterns."""
    if not validation:
        return {"has_validation": False, "total_reports": 0, "common_warnings": []}

    reports = validation.get("reports", [])
    warning_counts = {}
    error_counts = {}

    for report in reports:
        for issue in report.get("issues", []):
            if not isinstance(issue, dict):
                continue
            code = issue.get("code", "UNKNOWN")
            severity = issue.get("severity", "info")
            if severity == "warning":
                warning_counts[code] = warning_counts.get(code, 0) + 1
            elif severity == "error":
                error_counts[code] = error_counts.get(code, 0) + 1

    common_warnings = sorted(warning_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    common_errors = sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "has_validation": True,
        "total_reports": len(reports),
        "common_warnings": [{"code": c, "count": n} for c, n in common_warnings],
        "common_errors": [{"code": c, "count": n} for c, n in common_errors],
        "total_warnings": sum(warning_counts.values()),
        "total_errors": sum(error_counts.values()),
    }


def analyze_repair_history(revision_notes):
    """Analyze repair loop history."""
    if not revision_notes:
        return {"repairs_attempted": 0, "repair_rounds": 0}

    pages = revision_notes.get("pages", {})
    rounds = revision_notes.get("repair_round", 0)

    return {
        "repairs_attempted": len(pages),
        "repair_rounds": rounds,
        "pages_repaired": list(pages.keys()),
    }


def analyze_template_profile(profile):
    """Summarize template profile for retrospective."""
    if not profile:
        return {"template_used": False}

    return {
        "template_used": True,
        "source_file": profile.get("source_file", ""),
        "confidence": profile.get("confidence", {}).get("overall", "unknown"),
        "style_tendencies": profile.get("style_tendencies", {}),
    }


def generate_default_suggestions(run_data):
    """Generate candidate default settings based on run analysis."""
    suggestions = []
    lines = [
        "# Default Settings Suggestions",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## ⚠ 以下为候选建议，需用户确认后才可写回默认设置。",
        "",
    ]

    # Batch size suggestion
    manifest = load_json(Path(run_data.get("project_dir", "")) / INTERNAL / "00_project" / "page_manifest.json", {})
    batch_size = manifest.get("batch_size", 3)
    total_pages = len(manifest.get("pages", []))

    lines.append("## 批次大小")
    if total_pages > 0 and batch_size > 0:
        suggestions.append({
            "field": "batch_size",
            "current": batch_size,
            "suggested": batch_size,
            "reason": f"当前 batch_size={batch_size}，共 {total_pages} 页，分为 {manifest.get('batch_config', {})} 批次。",
        })
        lines.append(f"- 当前 batch_size: {batch_size}")
        lines.append(f"- 总页数: {total_pages}")
        lines.append(f"- 建议: 保留 batch_size={batch_size}，除非用户反馈批次数过多或过少。")

    # Layout preferences
    layout_feedback = run_data.get("layout_analysis", {})
    if layout_feedback.get("has_feedback"):
        lines.append("")
        lines.append("## 版式偏好")
        approved = layout_feedback.get("approved_pages", 0)
        rejected = layout_feedback.get("rejected_pages", 0)
        lines.append(f"- 批准页面: {approved}")
        lines.append(f"- 拒绝页面: {rejected}")
        if rejected > 0:
            suggestions.append({
                "field": "layout_preferences",
                "current": "N/A",
                "suggested": "需要更多版式方向",
                "reason": f"{rejected} 页版式被拒绝。",
            })
            lines.append("- ⚠ 有页面版式被拒绝，建议在下次运行时提供更多版式方向选择。")

    # Common warnings
    validation = run_data.get("validation_analysis", {})
    if validation.get("common_warnings"):
        lines.append("")
        lines.append("## 常见 SVG Warning")
        for w in validation["common_warnings"][:5]:
            lines.append(f"- `{w['code']}`: {w['count']} 次")
            suggestions.append({
                "field": f"svg_warning.{w['code']}",
                "current": "N/A",
                "suggested": f"在 SVG rules 中添加 {w['code']} 的预防指引",
                "reason": f"发生了 {w['count']} 次。",
            })

    # Repair cost
    repair = run_data.get("repair_analysis", {})
    if repair.get("repairs_attempted", 0) > 0:
        lines.append("")
        lines.append("## 修复成本")
        lines.append(f"- 修复轮次: {repair.get('repair_rounds', 0)}")
        lines.append(f"- 修复页面数: {repair.get('repairs_attempted', 0)}")
        if repair.get("repair_rounds", 0) >= 2:
            suggestions.append({
                "field": "repair_loop_limit",
                "current": 2,
                "suggested": 2,
                "reason": "修复达到上限，可能需要更早的人工介入或更严格的 SVG 规则。",
            })

    # Template preferences
    template = run_data.get("template_analysis", {})
    if template.get("template_used"):
        lines.append("")
        lines.append("## 模板偏好")
        lines.append(f"- 模板文件: {template.get('source_file', 'N/A')}")
        lines.append(f"- 置信度: {template.get('confidence', 'N/A')}")
        suggestions.append({
            "field": "template_preference",
            "current": template.get("source_file", ""),
            "suggested": f"继续使用 {Path(template.get('source_file', '')).name} 作为风格参考",
            "reason": f"用户提供了此模板，置信度={template.get('confidence', 'unknown')}。",
        })

    # Rules to promote/demote
    lines.append("")
    lines.append("## 规则调整建议")
    if validation.get("total_errors", 0) == 0 and validation.get("total_warnings", 0) == 0:
        lines.append("- 本轮无 validation 问题，现有规则可维持。")
    else:
        lines.append(f"- 总 warning: {validation.get('total_warnings', 0)}")
        lines.append(f"- 总 error: {validation.get('total_errors', 0)}")
        if validation.get("total_errors", 0) > 0:
            lines.append("- ⚠ 存在error级别问题，建议加强SVG阶段的preflight检查规则。")
            suggestions.append({
                "field": "rules.promote",
                "current": "N/A",
                "suggested": "加强 SVG pre-flight 检查",
                "reason": f"存在 {validation.get('total_errors', 0)} 个 error。",
            })

    lines.append("")
    lines.append("---")
    lines.append("**以上所有建议均为候选，需用户确认后才可写回默认设置。**")

    return "\n".join(lines), suggestions


def analyze_run(project_dir, output_dir=None):
    """Main analysis function."""
    root = Path(project_dir).resolve()
    internal = root / INTERNAL

    if not internal.is_dir():
        print(f"ERROR: _internal/ not found in {root}. Not a valid project.", file=sys.stderr)
        sys.exit(1)

    out = Path(output_dir) if output_dir else internal / "07_retrospective"
    out.mkdir(parents=True, exist_ok=True)

    # Gather data
    events = load_jsonl(internal / "00_project" / "flow_events.jsonl")
    layout_feedback = load_json(internal / "01_layout_plan" / "layout_feedback.json", {})
    visual_feedback = load_json(internal / "05_review" / "feedback.json", {})
    validation = load_json(internal / "04_validation" / "validation_summary.json", {})
    revision_notes = load_json(internal / "05_review" / "revision_notes.json", {})
    template_profile = load_json(internal / "00_project" / "template_profile.json", {})
    manifest = load_json(internal / "00_project" / "page_manifest.json", {})

    # Analyze
    flow_analysis = analyze_flow_events(events)
    layout_analysis = analyze_layout_feedback(layout_feedback)
    validation_analysis = analyze_validation(validation)
    repair_analysis = analyze_repair_history(revision_notes)
    template_analysis = analyze_template_profile(template_profile)

    run_data = {
        "project_dir": str(root),
        "flow_analysis": flow_analysis,
        "layout_analysis": layout_analysis,
        "validation_analysis": validation_analysis,
        "repair_analysis": repair_analysis,
        "template_analysis": template_analysis,
    }

    # Generate run_summary.json
    run_summary = {
        "project": manifest.get("project", "Unknown"),
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "total_pages": len(manifest.get("pages", [])),
        "batches": len(manifest.get("batch_config", {})),
        "flow_summary": {
            "states_visited": flow_analysis.get("total_states", []),
            "transitions": flow_analysis.get("state_transitions", []),
        },
        "layout_summary": {
            "pages_approved": layout_analysis.get("approved_pages", 0),
            "pages_rejected": layout_analysis.get("rejected_pages", 0),
        },
        "validation_summary": {
            "total_warnings": validation_analysis.get("total_warnings", 0),
            "total_errors": validation_analysis.get("total_errors", 0),
            "common_warnings": validation_analysis.get("common_warnings", []),
        },
        "repair_summary": {
            "rounds": repair_analysis.get("repair_rounds", 0),
            "pages_repaired": repair_analysis.get("pages_repaired", []),
        },
        "template_summary": {
            "used": template_analysis.get("template_used", False),
            "confidence": template_analysis.get("confidence", "N/A"),
        },
    }

    run_summary_path = out / "run_summary.json"
    run_summary_path.write_text(json.dumps(run_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Written: {run_summary_path}")

    # Generate default_suggestions.md
    suggestions_md, suggestions_list = generate_default_suggestions(run_data)
    suggestions_path = out / "default_suggestions.md"
    suggestions_path.write_text(suggestions_md, encoding="utf-8")
    print(f"Written: {suggestions_path}")

    # Generate memory_candidates.json
    memory_candidates = {
        "requires_user_confirmation": True,
        "confirmation_required_before": "任何写回 SKILL.md、references 或 memory 的操作",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidates": suggestions_list,
        "summary": f"本次运行共产生 {len(suggestions_list)} 条候选建议。请逐条确认后手动应用。",
        "safe_to_apply_automatically": [],
        "needs_user_review": suggestions_list,
    }

    memory_path = out / "memory_candidates.json"
    memory_path.write_text(json.dumps(memory_candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Written: {memory_path}")

    print(f"\nRetrospective complete. {len(suggestions_list)} suggestion(s) generated.")
    print("⚠ All suggestions require user confirmation before being written back.")

    return run_summary, suggestions_md, memory_candidates


def main():
    parser = argparse.ArgumentParser(
        description="Run retrospective analysis for a Planner's PPT Hell project."
    )
    parser.add_argument("project_dir", help="Project root directory")
    parser.add_argument("--output", default=None, help="Output directory (default: _internal/07_retrospective/)")
    args = parser.parse_args()

    analyze_run(args.project_dir, args.output)


if __name__ == "__main__":
    main()
