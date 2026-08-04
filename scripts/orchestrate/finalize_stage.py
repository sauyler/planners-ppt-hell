#!/usr/bin/env python3
"""Deterministically validate and close one pipeline stage.

The model writes semantic outputs only. This command owns timestamps, hashes,
completion state, issue aggregation, and automatic run logging.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
INTERNAL = "_internal"

sys.path.insert(0, str(SCRIPTS / "template"))
sys.path.insert(0, str(SCRIPTS))
from template_visual_gate import review_issues as template_review_issues  # noqa: E402
from ppt_pipeline import merge_batch_reviews, sync_manifest_from_content  # noqa: E402
from review_policy import blocking_warning_issues  # noqa: E402


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def task_hash(task):
    payload = dict(task)
    payload.pop("task_sha256", None)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def split_output_files(task):
    outputs = task.get("output_files", []) if isinstance(task, dict) else []
    evidence = [rel for rel in outputs if rel.endswith("_self_review.json")]
    artifacts = [rel for rel in outputs if rel not in evidence]
    return artifacts, evidence


def append_event(root, event_type, **details):
    path = root / INTERNAL / "00_project" / "flow_events.jsonl"
    event = {
        "time": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
        "details": details,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def latest_success(root, step, batch):
    path = root / INTERNAL / "00_project" / "flow_events.jsonl"
    latest = {}
    if not path.is_file():
        return latest
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        details = event.get("details", {}) if isinstance(event, dict) else {}
        if (event.get("type") == "stage_completed" and details.get("step") == step
                and details.get("batch", "") == batch):
            latest = details
    return latest


def svg_completion_is_current(root, task, event, batch):
    """Avoid repeated validation/render/logging only when every SVG side effect is still present."""
    if not event or event.get("issues"):
        return False
    if event.get("task_sha256") != task.get("task_sha256"):
        return False
    if event.get("feedback_sha256", "") != task.get("constraints", {}).get("revision_feedback_sha256", ""):
        return False
    recorded = event.get("output_sha256", {})
    outputs = task.get("output_files", [])
    if set(recorded) != set(outputs):
        return False
    if not all((root / rel).is_file() and file_hash(root / rel) == recorded[rel] for rel in outputs):
        return False
    preview_pages = root / INTERNAL / "03_png_preview" / "pages"
    if not all((preview_pages / f"{key}.png").is_file() for key in task.get("pages", [])):
        return False
    return (root / INTERNAL / "03_png_preview" / "full_deck_contact_sheet.png").is_file()


def svg_artifacts_current_except_review(root, task, event):
    """Reuse canonical renders when only the semantic self-review evidence changed."""
    if not event or event.get("issues") or event.get("task_sha256") != task.get("task_sha256"):
        return False
    if event.get("feedback_sha256", "") != task.get("constraints", {}).get("revision_feedback_sha256", ""):
        return False
    recorded = event.get("output_sha256", {})
    stable_outputs, _ = split_output_files(task)
    if not stable_outputs or any(rel not in recorded for rel in stable_outputs):
        return False
    if not all((root / rel).is_file() and file_hash(root / rel) == recorded[rel] for rel in stable_outputs):
        return False
    preview_pages = root / INTERNAL / "03_png_preview" / "pages"
    return (
        all((preview_pages / f"{key}.png").is_file() for key in task.get("pages", []))
        and (root / INTERNAL / "03_png_preview" / "full_deck_contact_sheet.png").is_file()
    )


def seal_svg_evidence(root, batch):
    """Seal changed visual evidence without re-validating or re-rendering stable SVG artifacts."""
    path = task_path(root, "svg", batch)
    task = load_json(path)
    problems = basic_issues(root, task, path)
    previous = latest_success(root, "svg", batch)
    if isinstance(task, dict) and not svg_artifacts_current_except_review(root, task, previous):
        problems.append(issue(
            "artifact.stale", "SVG artifact version is missing or changed; run normal finalize-stage instead.", str(path)
        ))
    if isinstance(task, dict):
        problems.extend(visual_review_issues(root, task))
    _, evidence_files = split_output_files(task or {})
    evidence_hashes = {
        rel: file_hash(root / rel) for rel in evidence_files if (root / rel).is_file()
    }
    details = {
        "step": "svg", "batch": batch,
        "task_sha256": (task or {}).get("task_sha256", ""),
        "feedback_sha256": (task or {}).get("constraints", {}).get("revision_feedback_sha256", ""),
        "artifact_sha256": previous.get("artifact_sha256") or {
            rel: previous.get("output_sha256", {}).get(rel)
            for rel in split_output_files(task or {})[0]
            if previous.get("output_sha256", {}).get(rel)
        },
        "evidence_sha256": evidence_hashes,
        "issues": problems,
    }
    append_event(root, "stage_evidence_failed" if problems else "stage_evidence_sealed", **details)
    print(json.dumps({"status": "fail" if problems else "pass", **details}, ensure_ascii=False, indent=2))
    return 1 if problems else 0


def issue(code, message, path="", severity="error", remediation=""):
    return {
        "code": code,
        "severity": severity,
        "path": path,
        "message": message,
        "remediation": remediation,
    }


def run_check(argv, code):
    started = datetime.now(timezone.utc)
    result = subprocess.run(argv, text=True, capture_output=True)
    duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    record = {
        "argv": argv,
        "exit_code": result.returncode,
        "duration_ms": duration_ms,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }
    problems = []
    if result.returncode:
        problems.append(issue(code, (result.stdout + "\n" + result.stderr).strip(), remediation="Fix all reported issues, then rerun finalize-stage."))
    return record, problems


def task_path(root, step, batch):
    name = f"svg_{batch}_task.json" if step == "svg" else f"{step}_task.json"
    return root / INTERNAL / "00_project" / "tasks" / name


def basic_issues(root, task, path):
    problems = []
    if not isinstance(task, dict):
        return [issue("task.invalid", "Stage task is missing or invalid JSON.", str(path))]
    if task.get("task_sha256") != task_hash(task):
        problems.append(issue("task.stale", "Stage task hash is invalid.", str(path)))
    finalize_argv = task.get("finalize_argv")
    if not isinstance(finalize_argv, list) or not finalize_argv or not all(
        isinstance(item, str) and item for item in finalize_argv
    ):
        problems.append(issue("task.finalize_argv", "Stage task must declare one directly executable finalize_argv.", str(path)))
    input_hashes = task.get("input_hashes", {})
    if set(input_hashes) != set(task.get("input_files", [])):
        problems.append(issue("input.set_mismatch", "input_files and input_hashes must contain the same paths.", str(path)))
    reference_root = Path(task.get("reference_root", ""))
    for key, expected in input_hashes.items():
        declared = Path(key)
        candidates = [declared] if declared.is_absolute() else [root / declared, reference_root / declared]
        source = next((candidate for candidate in candidates if candidate.is_file()), None)
        if source is None:
            problems.append(issue("input.missing", f"Missing declared input: {key}", key))
        elif file_hash(source) != expected:
            problems.append(issue("input.stale", f"Input changed after task creation: {key}", key))
    for rel in task.get("output_files", []):
        output = root / rel
        if not output.is_file():
            problems.append(issue("output.missing", f"Missing declared output: {rel}", rel))
    feedback_hash = task.get("constraints", {}).get("revision_feedback_sha256")
    if feedback_hash:
        snapshot = next((key for key in task.get("input_files", []) if key.endswith("feedback.json")), "")
        if not snapshot or not (root / snapshot).is_file() or file_hash(root / snapshot) != feedback_hash:
            problems.append(issue("feedback.stale", "Revision feedback snapshot does not match the task.", snapshot))
    return problems


def visual_review_issues(root, task):
    batch = task.get("batch_id", "")
    report_path = root / INTERNAL / "04_validation" / "batches" / f"{batch}.json"
    review_path = root / INTERNAL / "04_validation" / "batches" / f"{batch}_self_review.json"
    report = load_json(report_path, {})
    review = load_json(review_path, {})
    problems = []
    if report.get("status") == "fail" or report.get("summary", {}).get("errors", 0):
        problems.append(issue("svg.validator", "SVG validator contains hard errors.", str(report_path)))
    for warning in blocking_warning_issues(report):
        problems.append(issue(
            "svg.blocking_warning",
            f"Blocking validator warning {warning.get('code')}: {warning.get('message', '')}",
            warning.get("page") or str(report_path),
        ))
    reports = {Path(item.get("file", "")).stem: item for item in report.get("reports", []) if isinstance(item, dict)}
    expected = set(task.get("pages", []))
    if set(reports) != expected:
        problems.append(issue("svg.page_set", f"Validator pages differ: expected {sorted(expected)}, got {sorted(reports)}", str(report_path)))
    pages = review.get("pages", {}) if isinstance(review, dict) else {}
    gate = task.get("constraints", {}).get("combined_quality_gate", {})
    if gate.get("required") is True:
        evidence = review.get("combined_quality_gate", {}) if isinstance(review, dict) else {}
        required_true = (
            "initial_validator_checked", "initial_visual_checked",
            "final_validator_rechecked", "final_visual_rechecked",
        )
        for field in required_true:
            if evidence.get(field) is not True:
                problems.append(issue("quality_gate.missing", f"Combined quality gate requires {field}=true.", str(review_path)))
        findings = evidence.get("combined_findings")
        if not isinstance(findings, list):
            problems.append(issue("quality_gate.findings", "combined_findings must be an array merging validator and visual findings.", str(review_path)))
        repair_passes = evidence.get("repair_passes")
        if not isinstance(repair_passes, int) or repair_passes not in (0, 1):
            problems.append(issue("quality_gate.repair_passes", "repair_passes must be 0 or 1.", str(review_path)))
    if review.get("visual_review_status") not in (None, "completed"):
        problems.append(issue("visual.blocked", "Visual self-review is not completed.", str(review_path)))
    for key in sorted(expected):
        page = pages.get(key, {}) if isinstance(pages, dict) else {}
        reviewed = page.get("png_reviewed") is True or page.get("external_feedback_applied") is True
        if not reviewed:
            problems.append(issue("visual.missing", f"No visual evidence for {key}.", str(review_path)))
        if page.get("must_fix"):
            problems.append(issue("visual.must_fix", f"Unresolved visual must_fix for {key}: {page['must_fix']}", str(review_path)))
    return problems


def finalize(root, step, batch=""):
    started = datetime.now(timezone.utc)
    path = task_path(root, step, batch)
    task = load_json(path)
    problems = basic_issues(root, task, path)
    commands = []

    previous = {}
    reuse_svg_render = False
    if step == "svg" and isinstance(task, dict) and not problems:
        previous = latest_success(root, step, batch)
        if svg_completion_is_current(root, task, previous, batch):
            result = {"status": "pass", "already_complete": True, **previous}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        reuse_svg_render = svg_artifacts_current_except_review(root, task, previous)

    if isinstance(task, dict) and not problems:
        if step == "content":
            data = load_json(root / INTERNAL / "01_content" / "page_content.json", {})
            if not data.get("pages"):
                problems.append(issue("content.empty", "page_content.json has no pages."))
            source_assets = load_json(root / INTERNAL / "00_project" / "source" / "source_assets.json", {})
            expected_assets = {
                str(item.get("asset_id", "")).strip()
                for item in source_assets.get("assets", [])
                if isinstance(item, dict) and str(item.get("asset_id", "")).strip()
            }
            assigned_assets = {
                str(item.get("asset_id", "")).strip()
                for page in data.get("pages", [])
                if isinstance(page, dict)
                for item in page.get("source_assets", [])
                if isinstance(item, dict) and str(item.get("asset_id", "")).strip()
            }
            unknown_assets = assigned_assets - expected_assets
            missing_assets = expected_assets - assigned_assets
            if unknown_assets:
                problems.append(issue(
                    "content.source_asset_unknown",
                    f"page_content.json references unknown source assets: {sorted(unknown_assets)}",
                    str(root / INTERNAL / "01_content" / "page_content.json"),
                ))
            if missing_assets:
                problems.append(issue(
                    "content.source_asset_unassigned",
                    f"Source images were not assigned to any content page: {sorted(missing_assets)}",
                    str(root / INTERNAL / "00_project" / "source" / "source_assets.json"),
                    remediation="Inspect every source image and add it to the relevant page.source_assets before finalizing Content.",
                ))
        elif step == "layout":
            if task.get("mode") == "revision":
                plan = load_json(root / INTERNAL / "01_layout_plan" / "layout_plan.json", {})
                expected = {
                    (item.get("scope", ""), item.get("page_key", ""), item.get("request", ""))
                    for item in task.get("constraints", {}).get("required_feedback_items", [])
                    if isinstance(item, dict)
                }
                resolved = {
                    (item.get("scope", ""), item.get("page_key", ""), item.get("request", ""))
                    for item in plan.get("feedback_resolution", [])
                    if isinstance(item, dict) and str(item.get("implemented_change", "")).strip()
                }
                for missing in sorted(expected - resolved):
                    problems.append(issue(
                        "layout.feedback_unresolved",
                        f"Layout revision did not resolve frozen feedback: scope={missing[0]} page={missing[1]} request={missing[2]}",
                        str(root / INTERNAL / "01_layout_plan" / "layout_plan.json"),
                    ))
            command, found = run_check([
                sys.executable, str(SCRIPTS / "estimate_layout_capacity.py"), str(root)
            ], "layout.capacity_command")
            commands.append(command)
            problems.extend(found)
            command, found = run_check([
                sys.executable, str(SCRIPTS / "validate_contracts.py"), "project", str(root), "--stage", "plan"
            ], "layout.contract")
            commands.append(command)
            problems.extend(found)
            capacity = load_json(root / INTERNAL / "01_layout_plan" / "layout_capacity_report.json", {})
            for key, page in capacity.get("pages", {}).items():
                if isinstance(page, dict) and page.get("status") == "overfull":
                    problems.append(issue("layout.overfull", f"Layout page is overfull: {key}", str(root / INTERNAL / "01_layout_plan" / "layout_capacity_report.json")))
        elif step == "template":
            profile = root / INTERNAL / "00_project" / "template_profile.json"
            visual_manifest = root / INTERNAL / "00_project" / "template_visuals" / "visual_manifest.json"
            command, found = run_check([
                sys.executable, str(SCRIPTS / "validate_contracts.py"), "template", str(profile),
                "--visual-manifest", str(visual_manifest),
            ], "template.contract")
            commands.append(command)
            problems.extend(found)
            if task.get("template_mode") == "fidelity":
                problems.extend(issue("template.visual_gate", message) for message in template_review_issues(root))
        elif step == "svg":
            problems.extend(visual_review_issues(root, task))

    if isinstance(task, dict) and not problems:
        if step == "content":
            sync_manifest_from_content(root)
        elif step == "layout":
            command, found = run_check([
                sys.executable, str(SCRIPTS / "generate_layout_html.py"), str(root)
            ], "layout.review_html")
            commands.append(command)
            problems.extend(found)
        elif step == "template" and task.get("mode") == "revision":
            (root / INTERNAL / "00_project" / "template_feedback.json").unlink(missing_ok=True)
            (root / "00_template_review.html").unlink(missing_ok=True)
        elif step == "svg":
            merge_batch_reviews(root)
            if reuse_svg_render:
                commands.append({"code": "svg.render_reused", "duration_ms": 0, "returncode": 0})
            else:
                render_argv = [
                    sys.executable, str(SCRIPTS / "render_svg_png.py"),
                    str(root / INTERNAL / "02_svg_source"),
                    str(root / INTERNAL / "03_png_preview"),
                    "--manifest", str(root / INTERNAL / "00_project" / "page_manifest.json"),
                    "--batch", batch,
                ]
                command, found = run_check(render_argv, "svg.render")
                commands.append(command)
                problems.extend(found)
                if not problems:
                    command, found = run_check([
                        sys.executable, str(SCRIPTS / "render_svg_png.py"),
                        str(root / INTERNAL / "02_svg_source"),
                        str(root / INTERNAL / "03_png_preview"),
                        "--manifest", str(root / INTERNAL / "00_project" / "page_manifest.json"),
                        "--contact-sheet-only",
                    ], "svg.contact_sheet")
                    commands.append(command)
                    problems.extend(found)

    duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    output_hashes = {
        rel: file_hash(root / rel)
        for rel in (task or {}).get("output_files", [])
        if (root / rel).is_file()
    }
    artifact_files, evidence_files = split_output_files(task or {})
    details = {
        "step": step,
        "batch": batch,
        "task": str(path.relative_to(root)) if path.is_relative_to(root) else str(path),
        "task_sha256": (task or {}).get("task_sha256", ""),
        "feedback_sha256": (task or {}).get("constraints", {}).get("revision_feedback_sha256", ""),
        "output_sha256": output_hashes,
        "artifact_sha256": {rel: output_hashes[rel] for rel in artifact_files if rel in output_hashes},
        "evidence_sha256": {rel: output_hashes[rel] for rel in evidence_files if rel in output_hashes},
        "duration_ms": duration_ms,
        "commands": commands,
        "issues": problems,
    }
    append_event(root, "stage_failed" if problems else "stage_completed", **details)
    result = {"status": "fail" if problems else "pass", **details}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if problems else 0


def main():
    parser = argparse.ArgumentParser(description="Validate and close one pipeline stage")
    parser.add_argument("project_dir")
    parser.add_argument("--step", required=True, choices=["template", "content", "layout", "svg"])
    parser.add_argument("--batch", default="")
    parser.add_argument("--seal-evidence-only", action="store_true")
    args = parser.parse_args()
    if args.step == "svg" and not args.batch:
        parser.error("--batch is required for SVG")
    if args.seal_evidence_only:
        if args.step != "svg":
            parser.error("--seal-evidence-only requires --step svg")
        raise SystemExit(seal_svg_evidence(Path(args.project_dir).resolve(), args.batch))
    raise SystemExit(finalize(Path(args.project_dir).resolve(), args.step, args.batch))


if __name__ == "__main__":
    main()
