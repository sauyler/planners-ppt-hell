#!/usr/bin/env python3
"""Behavioral smoke suite for the vNext single-agent PPT pipeline."""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))
from review_server import validate_template_decisions  # noqa: E402
PIPELINE = SCRIPTS / "orchestrate" / "ppt_pipeline.py"
TASKS = SCRIPTS / "orchestrate" / "make_stage_task.py"
FINALIZE = SCRIPTS / "orchestrate" / "finalize_stage.py"
passed = 0


def run(*args, ok=True):
    result = subprocess.run([sys.executable, *map(str, args)], cwd=SKILL, text=True, capture_output=True)
    if ok and result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    return result


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def check(name, fn):
    global passed
    fn()
    passed += 1
    print(f"PASS {passed:02d}: {name}")


def new_project(base, name="project"):
    source = base / f"{name}.md"
    source.write_text("# 测试\n\n事实、判断与行动建议。", encoding="utf-8")
    project = base / name
    run(SCRIPTS / "init_svg_project.py", project, "--source", source)
    return project, source


def one_page_content(project, source):
    return {
        "project": "vnext-smoke",
        "source_path": str(source),
        "pages": [{
            "page_key": "page_01",
            "action_title": "三种力量正在改写服务边界",
            "core_message": "这是一个不匹配任何专用模型的真实关系页。",
            "body_blocks": ["监管变化", "渠道摩擦", "服务承诺"],
            "speaker_notes": ["完整背景保留在备注。"],
        }],
    }


def test_authority_surface():
    required = [PIPELINE, TASKS, FINALIZE, SKILL / "references/workflow/00_pipeline_controller.md"]
    retired = [
        SCRIPTS / "orchestrate/ppt_parent.py",
        SCRIPTS / "orchestrate/make_agent_task.py",
        SCRIPTS / "orchestrate/collect_agent_results.py",
    ]
    assert all(path.is_file() for path in required)
    assert not any(path.exists() for path in retired)
    help_text = run(PIPELINE, "--help").stdout
    assert "make-task" in help_text and "finalize-stage" in help_text
    assert "bind-agent" not in help_text and "collect-results" not in help_text


def test_init_and_template_intake():
    with tempfile.TemporaryDirectory(prefix="ppt-vnext-smoke-") as raw:
        project, _ = new_project(Path(raw))
        state = read_from_stdout(run(PIPELINE, project, "next").stdout)
        assert state["state"] == "TEMPLATE_INTAKE"
        ids = [item["id"] for item in state["do"]["choices"]]
        assert "library:planner-simple-default" in ids and "none" in ids and "extract" in ids
        assert state["do"]["requires_new_user_response"] is True
        assert state["do"]["auto_selection_forbidden"] is True
        assert all("--user-confirmed" in item["command"]["argv"] for item in state["do"]["choices"])
        manifest = read(project / "_internal/00_project/page_manifest.json")
        assert manifest["version"] == "4.0" and "execution" not in manifest


def read_from_stdout(text):
    return json.loads(text[text.find("{"):])


def test_default_template_routes_directly_to_content():
    with tempfile.TemporaryDirectory(prefix="ppt-vnext-smoke-") as raw:
        project, _ = new_project(Path(raw))
        blocked = run(PIPELINE, project, "confirm-template", "--status", "provided", "--library", "planner-simple-default", ok=False)
        assert blocked.returncode != 0 and "explicit user reply" in (blocked.stdout + blocked.stderr)
        run(PIPELINE, project, "confirm-template", "--user-confirmed", "--status", "provided", "--library", "planner-simple-default")
        state = read_from_stdout(run(PIPELINE, project, "next").stdout)
        assert state["state"] == "CONTENT"
        stage = state["do"]["stage"]
        assert stage["step"] == "content" and stage["mode"] == "initial"
        assert "primary Agent" not in stage["instruction"]


def test_task_is_minimal_hashed_and_repeatable():
    with tempfile.TemporaryDirectory(prefix="ppt-vnext-smoke-") as raw:
        project, _ = new_project(Path(raw))
        run(TASKS, project, "--step", "content")
        path = project / "_internal/00_project/tasks/content_task.json"
        first = path.read_bytes()
        task = read(path)
        assert set(task["input_files"]) == set(task["input_hashes"])
        assert task["executor"] == "primary_agent"
        forbidden = {"generated_at", "agent_result_path", "output_template", "worker_run_id", "started_at", "completed_at"}
        assert not forbidden.intersection(task)
        run(TASKS, project, "--step", "content")
        assert first == path.read_bytes()


def test_finalizer_aggregates_failures_and_does_not_complete():
    with tempfile.TemporaryDirectory(prefix="ppt-vnext-smoke-") as raw:
        project, source = new_project(Path(raw))
        run(TASKS, project, "--step", "content")
        source.write_text("# 输入已改变", encoding="utf-8")
        (project / "_internal/01_content/page_content.json").unlink()
        result = run(FINALIZE, project, "--step", "content", ok=False)
        assert result.returncode == 1
        payload = read_from_stdout(result.stdout)
        codes = {item["code"] for item in payload["issues"]}
        assert {"input.stale", "output.missing"}.issubset(codes)
        events = (project / "_internal/00_project/flow_events.jsonl").read_text(encoding="utf-8")
        assert '"type": "stage_failed"' in events and '"type": "stage_completed"' not in events


def test_successful_content_finalize_owns_manifest_and_log():
    with tempfile.TemporaryDirectory(prefix="ppt-vnext-smoke-") as raw:
        project, source = new_project(Path(raw))
        run(TASKS, project, "--step", "content")
        write(project / "_internal/01_content/page_content.json", one_page_content(project, source))
        result = run(FINALIZE, project, "--step", "content")
        payload = read_from_stdout(result.stdout)
        assert payload["status"] == "pass" and payload["output_sha256"]
        manifest = read(project / "_internal/00_project/page_manifest.json")
        assert manifest["batch_config"] == {"batch_01": {"pages": ["page_01"]}}
        event = json.loads((project / "_internal/00_project/flow_events.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        assert event["type"] == "stage_completed" and event["details"]["duration_ms"] >= 0
        sys.path.insert(0, str(SCRIPTS / "orchestrate"))
        from ppt_pipeline import stage_completed
        assert stage_completed(project, "content") is True
        output = project / "_internal/01_content/page_content.json"
        original = output.read_text(encoding="utf-8")
        output.write_text(original + " ", encoding="utf-8")
        assert stage_completed(project, "content") is False


def test_default_content_base_is_safe():
    package = SKILL / "assets/template_library/planner-simple-default/fidelity_template"
    registry = read(package / "template_registry.json")
    layout = registry["layouts"]["content_base"]
    assert layout["required_components"] and layout["canvas_file"].endswith("content_base.svg")
    canvas = package / layout["canvas_file"]
    root = ET.parse(canvas).getroot()
    replace_layers = [node for node in root.iter() if node.get("data-template-content-layer") == "replace"]
    assert len(replace_layers) == 1 and len(list(replace_layers[0])) == 0
    text = canvas.read_text(encoding="utf-8").lower()
    assert "placeholder" not in text and "#333333" not in text and "#666666" not in text


def prepare_layout_project(base):
    project, source = new_project(base)
    run(SCRIPTS / "template/template_library.py", "apply", project, "--template-id", "planner-simple-default")
    internal = project / "_internal"
    write(internal / "01_content/page_content.json", one_page_content(project, source))
    manifest = read(internal / "00_project/page_manifest.json")
    manifest["pages"] = [{"page_key": "page_01", "batch_id": "batch_01", "svg_path": "_internal/02_svg_source/page_01.svg", "png_path": "_internal/03_png_preview/pages/page_01.png"}]
    manifest["batch_config"] = {"batch_01": {"pages": ["page_01"]}}
    write(internal / "00_project/page_manifest.json", manifest)
    write(internal / "01_layout_plan/layout_plan.json", {"project": "vnext-smoke", "pages": [{
        "page_key": "page_01", "layout_id": "L04", "template_layout_id": "content_base",
        "page_mode": "rational", "visual_density": "balanced", "grid": "single",
        "wireframe": [{"label": "title", "zone": "header", "x": 140, "y": 100, "w": 1600, "h": 120}, {"label": "body", "zone": "body", "x": 140, "y": 270, "w": 1600, "h": 600}],
        "copy_handling": {"final_on_slide": {"title": "三种力量正在改写服务边界", "body": ["监管变化 × 渠道摩擦 × 服务承诺"]}, "kept_on_slide": [], "compression_rationale": [], "compressed": False, "moved_to_notes": []},
        "visual_asset_strategy": {"asset_need": "none"}, "layout_reason": "无精确专用模型匹配，使用 content_base。",
    }]})
    return project


def test_svg_task_contains_only_selected_canvas_and_runtime():
    with tempfile.TemporaryDirectory(prefix="ppt-vnext-smoke-") as raw:
        project = prepare_layout_project(Path(raw))
        run(TASKS, project, "--step", "svg", "--batch", "batch_01")
        task = read(project / "_internal/00_project/tasks/svg_batch_01_task.json")
        canvas_inputs = [item for item in task["input_files"] if "/layout_canvases/" in item]
        assert len(canvas_inputs) == 1 and canvas_inputs[0].endswith("content_base.svg")
        assert not any(item.endswith("components.svg") or item.endswith("template_profile.json") for item in task["input_files"])
        runtime_path = next(item for item in task["input_files"] if item.endswith("_template_runtime.json"))
        runtime = read(project / runtime_path)
        assert set(runtime["layouts"]) == {"content_base"}
        assert all(name not in json.dumps(runtime) for name in ("funnel", "table", "three_card", "process"))
        assert task["executor"] == "one_shot_subagent_preferred"
        assert set(task["constraints"]["canvas_start_argv_by_page"]) == {"page_01"}
        pipeline_source = PIPELINE.read_text(encoding="utf-8")
        assert "one_shot_subagent" in pipeline_source and "subagent_prompt" in pipeline_source
        assert "announce_before_start" in pipeline_source


def test_review_decisions_are_tri_state_without_weakening_approval():
    html_source = (SCRIPTS / "generate_template_review_html.py").read_text(encoding="utf-8")
    server_source = (SCRIPTS / "review_server.py").read_text(encoding="utf-8")
    for label in ("通过", "舍弃", "返修", "提交批次反馈", "全部通过"):
        assert label in html_source
    assert "approveAll()" in html_source and "input[value=\"pass\"]" in html_source
    assert 'action not in {"submit_batch", "approve_all"}' in server_source
    assert 'get("decision") in {"pass", "discard", "revise"}' in server_source
    assert "template_name" in server_source and "validate_template_decisions" in server_source
    assert "discarded_layouts" in server_source and "revision_layouts" in server_source
    mixed = {
        "submission_action": "submit_batch", "approved": False, "all_approved": False,
        "overall_feedback": "", "layouts": {
            "cover": {"approved": True, "decision": "pass", "custom_feedback": ""},
            "content_base": {"approved": False, "decision": "revise", "custom_feedback": "放大安全区"},
            "table": {"approved": False, "decision": "discard", "custom_feedback": ""},
        },
    }
    error, summary = validate_template_decisions(mixed, {"cover", "content_base", "table"})
    assert not error
    assert summary == {"all_pass": False, "discarded_layouts": ["table"], "revision_layouts": ["content_base"]}
    mixed["layouts"]["content_base"]["custom_feedback"] = ""
    error, _ = validate_template_decisions(mixed, {"cover", "content_base", "table"})
    assert "requires" in error


def test_layout_revision_cannot_drop_feedback():
    with tempfile.TemporaryDirectory(prefix="ppt-vnext-smoke-") as raw:
        project = prepare_layout_project(Path(raw))
        feedback = {
            "all_approved": False,
            "pages": {"page_01": {"approved": False, "selected_suggestions": [], "custom_feedback": "改成五主题折线图"}},
        }
        write(project / "_internal/01_layout_plan/layout_feedback.json", feedback)
        run(TASKS, project, "--step", "layout", "--revision")
        task = read(project / "_internal/00_project/tasks/layout_task.json")
        assert not (set(task["input_files"]) & set(task["output_files"]))
        assert task["constraints"]["previous_layout_plan"].endswith("layout_previous/layout_plan.json")
        assert task["constraints"]["required_feedback_items"] == [
            {"scope": "page", "page_key": "page_01", "request": "改成五主题折线图"}
        ]
        result = run(FINALIZE, project, "--step", "layout", ok=False)
        payload = read_from_stdout(result.stdout)
        assert "layout.feedback_unresolved" in {item["code"] for item in payload["issues"]}


def test_missing_local_image_is_a_hard_error():
    with tempfile.TemporaryDirectory(prefix="ppt-vnext-smoke-") as raw:
        project = prepare_layout_project(Path(raw))
        run(SCRIPTS / "template/apply_fidelity_template.py", "--project", project,
            "--page-key", "page_01", "--layout-id", "content_base", "--title", "测试")
        svg = project / "_internal/02_svg_source/page_01.svg"
        text = svg.read_text(encoding="utf-8").replace(
            "</svg>", '<image href="missing-background.png" x="0" y="0" width="1920" height="1080"/></svg>'
        )
        svg.write_text(text, encoding="utf-8")
        result = run(SCRIPTS / "validate_svg_layout.py", svg.parent, "--file", svg, ok=False)
        payload = read_from_stdout(result.stdout)
        codes = {issue["code"] for report in payload["reports"] for issue in report["issues"]}
        assert "MISSING_IMAGE_FILE" in codes


def test_template_initial_task_does_not_hash_its_output():
    maker = TASKS.read_text(encoding="utf-8")
    assert "profile_path.is_file()" not in maker
    assert "previous_output_snapshots" in maker
    assert 'inputs.extend([str(snapshot.relative_to(root)), *outputs])' not in maker


def test_svg_revision_uses_frozen_previous_outputs():
    with tempfile.TemporaryDirectory(prefix="ppt-vnext-smoke-") as raw:
        project = prepare_layout_project(Path(raw))
        run(SCRIPTS / "template/apply_fidelity_template.py", "--project", project,
            "--page-key", "page_01", "--layout-id", "content_base", "--title", "测试")
        write(project / "_internal/05_review/feedback.json", {
            "approved": False, "pages": {"page_01": {"custom_feedback": "调整正文层级"}}
        })
        run(TASKS, project, "--step", "svg", "--batch", "batch_01", "--revision")
        task = read(project / "_internal/00_project/tasks/svg_batch_01_task.json")
        assert not (set(task["input_files"]) & set(task["output_files"]))
        frozen = task["constraints"]["previous_svg_by_page"]["page_01"]
        assert frozen.endswith("svg_batch_01_previous/page_01.svg") and (project / frozen).is_file()


def test_wireframe_trace_reports_one_structural_repair():
    with tempfile.TemporaryDirectory(prefix="ppt-vnext-smoke-") as raw:
        project = prepare_layout_project(Path(raw))
        run(SCRIPTS / "template/apply_fidelity_template.py", "--project", project,
            "--page-key", "page_01", "--layout-id", "content_base", "--title", "测试")
        svg = project / "_internal/02_svg_source/page_01.svg"
        result = run(SCRIPTS / "validate_svg_layout.py", svg.parent, "--file", svg,
                     "--layout-plan", project / "_internal/01_layout_plan/layout_plan.json", ok=False)
        payload = read_from_stdout(result.stdout)
        issues = [item for report in payload["reports"] for item in report["issues"]
                  if item["code"] == "WIREFRAME_REGION_MISSING"]
        assert len(issues) == 1 and "body" in issues[0]["message"]


def test_svg_completion_short_circuit_is_hash_bound():
    with tempfile.TemporaryDirectory(prefix="ppt-vnext-smoke-") as raw:
        project = prepare_layout_project(Path(raw))
        run(SCRIPTS / "template/apply_fidelity_template.py", "--project", project,
            "--page-key", "page_01", "--layout-id", "content_base", "--title", "测试")
        run(TASKS, project, "--step", "svg", "--batch", "batch_01")
        task = read(project / "_internal/00_project/tasks/svg_batch_01_task.json")
        for rel in task["output_files"]:
            path = project / rel
            if not path.exists():
                write(path, {"status": "pass"})
        preview = project / "_internal/03_png_preview"
        (preview / "pages").mkdir(parents=True, exist_ok=True)
        (preview / "pages/page_01.png").write_bytes(b"png")
        (preview / "full_deck_contact_sheet.png").write_bytes(b"sheet")
        sys.path.insert(0, str(SCRIPTS / "orchestrate"))
        from finalize_stage import file_hash, svg_completion_is_current
        event = {
            "task_sha256": task["task_sha256"], "feedback_sha256": "", "issues": [],
            "output_sha256": {rel: file_hash(project / rel) for rel in task["output_files"]},
        }
        assert svg_completion_is_current(project, task, event, "batch_01") is True
        (project / task["output_files"][0]).write_text("changed", encoding="utf-8")
        assert svg_completion_is_current(project, task, event, "batch_01") is False


def test_layout_review_uses_semantic_renderer():
    source = (SCRIPTS / "generate_layout_html.py").read_text(encoding="utf-8")
    assert "renderSemanticValue" in source and "flattenVisible" not in source
    assert "value.every(function(item)" in source and "objectRows" in source


def test_locked_layers_and_required_components_remain_hard_gates():
    validator = (SCRIPTS / "validate_svg_layout.py").read_text(encoding="utf-8")
    library = (SCRIPTS / "template/template_library.py").read_text(encoding="utf-8")
    assert "locked_sha256" in validator and "required_components" in validator
    assert "validate_component_references" in library and "template_canvas_review_issues" in library


def test_export_keeps_strict_controller_gate():
    pipeline = PIPELINE.read_text(encoding="utf-8")
    converter = (SCRIPTS / "native_svg_to_ppt.py").read_text(encoding="utf-8")
    assert "SMART_SVG_EXPORT_APPROVED_BY_PIPELINE" in pipeline
    assert "SMART_SVG_EXPORT_APPROVED_BY_PIPELINE" in converter
    assert "--strict-missing-images" in pipeline and "--notes" in pipeline


def test_no_model_owned_completion_metadata():
    maker = TASKS.read_text(encoding="utf-8")
    finalizer = FINALIZE.read_text(encoding="utf-8")
    assert "generated_at" not in maker and "agent_result" not in maker
    assert 'append_event(root, "stage_failed" if problems else "stage_completed"' in finalizer
    assert "duration_ms" in finalizer and "output_sha256" in finalizer


def test_machine_hash_matches_declared_task():
    with tempfile.TemporaryDirectory(prefix="ppt-vnext-smoke-") as raw:
        project, _ = new_project(Path(raw))
        run(TASKS, project, "--step", "content")
        task = read(project / "_internal/00_project/tasks/content_task.json")
        declared = task.pop("task_sha256")
        encoded = json.dumps(task, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        assert declared == hashlib.sha256(encoded).hexdigest()


def main():
    check("single authority surface", test_authority_surface)
    check("atomic init and explicit template intake", test_init_and_template_intake)
    check("approved default template routes to Content", test_default_template_routes_directly_to_content)
    check("minimal hashed repeatable stage task", test_task_is_minimal_hashed_and_repeatable)
    check("finalizer aggregates failures", test_finalizer_aggregates_failures_and_does_not_complete)
    check("content finalizer owns manifest and log", test_successful_content_finalize_owns_manifest_and_log)
    check("content_base canvas is safe", test_default_content_base_is_safe)
    check("SVG task is batch-scoped and minimal", test_svg_task_contains_only_selected_canvas_and_runtime)
    check("template review has revise/discard/approve", test_review_decisions_are_tri_state_without_weakening_approval)
    check("layout revision cannot drop frozen feedback", test_layout_revision_cannot_drop_feedback)
    check("missing local image is a hard error", test_missing_local_image_is_a_hard_error)
    check("template initial task excludes mutable output", test_template_initial_task_does_not_hash_its_output)
    check("SVG revision freezes previous outputs", test_svg_revision_uses_frozen_previous_outputs)
    check("wireframe trace is a single structural repair", test_wireframe_trace_reports_one_structural_repair)
    check("SVG finalize idempotency is hash-bound", test_svg_completion_short_circuit_is_hash_bound)
    check("layout review uses semantic rendering", test_layout_review_uses_semantic_renderer)
    check("locked layers and required components remain gates", test_locked_layers_and_required_components_remain_hard_gates)
    check("export remains controller-gated and strict", test_export_keeps_strict_controller_gate)
    check("completion metadata is machine-owned", test_no_model_owned_completion_metadata)
    check("task hash is valid", test_machine_hash_matches_declared_task)
    print(f"All {passed} vNext smoke checks passed")


if __name__ == "__main__":
    main()
