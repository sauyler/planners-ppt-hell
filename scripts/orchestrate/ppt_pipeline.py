#!/usr/bin/env python3
"""Deterministic control plane for the single-agent PPT pipeline."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "template"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from layout_canvas import registry_canvases_ready  # noqa: E402
from template_visual_gate import review_complete as template_canvas_review_complete  # noqa: E402
from review_policy import layout_reroute_pages  # noqa: E402

INTERNAL = "_internal"
HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
TEMPLATE_LIBRARY = SCRIPTS.parent / "assets" / "template_library"
TEMPLATE_STAGE_PROMPT = (
    "执行 Template 阶段。结构元素只是候选，视觉判断决定能否复用。先看源 contact sheet 和全部源页；"
    "Fidelity 模式按真实源页原型生成 canvas，运行 task 的 builder/render argv，再逐页对照源图与 canvas。"
    "模板只固定视觉身份和页面边界；replace layer 必须为空，不得固定标题、正文或内容结构。"
    "通用灰框或凭 taxonomy 臆造 layout 必须返修。"
    "revision时逐Layout执行冻结反馈：通过的保留，舍弃的从registry/canvas删除，返修的按意见重做；"
    "content_base如被舍弃必须重建为可用默认基础页。"
    "所有输出必须位于 task.project_dir。只写语义产物，完成后运行 task 指定的 finalize 命令。"
)
CONTENT_STAGE_PROMPT = (
    "执行 Content 阶段。只读取 task.input_files，只做事实整理、分页内容与素材角色判断。"
    "按 task.contract 写 task.output_files；不得选择模板 layout、设计 wireframe 或生成 SVG。完成后运行 finalize。"
)
LAYOUT_STAGE_PROMPT = (
    "执行 Layout 阶段。Controller 已生成完整页集合的确定性 layout_plan.json scaffold；逐页在原文件上完成内容结构、最终上屏文案、wireframe 与 canvas 判断。"
    "不得另写临时 Python 生成器、不得手写替换整份 JSON；完成一页即把该页 scaffold_status 设为 completed，全部完成后设置顶层 completed。"
    "专用 canvas 仅在精确匹配时选择，否则必须选择 content_base。按 task.contract 写输出，不得生成 SVG 或写 forbidden_writes。"
)
SVG_STAGE_PROMPT = (
    "执行一个 SVG batch。只读取 task.input_files，按 task.contract 与 constraints 写 task.output_files。"
    "先原样执行 canvas_start_argv_by_page；validator_argv、visual_render_argv 和 finalize 也必须直接执行 task 中的 argv，不得手抄或重组路径。"
    "不得改变已批准的 final_on_slide、wireframe、素材角色或 "
    "template_layout_id；存在 layout canvas 时必须以它为每页起始 SVG，只替换 content layer，不得重画 locked layer。"
    "Layout Plan 每个非 background wireframe 区域必须在对应 SVG 元素或分组上保留相同的 data-wireframe-label，作为结构执行追踪。"
    "不得跨 batch 写入。视觉渲染首次失败不得直接降级；按 visual_recovery_policy "
    "恢复渲染，并用视觉发现实际优化 SVG；完成后运行 finalize。"
)


def load_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    json.loads(payload)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def append_event(root, event_type, **details):
    path = root / INTERNAL / "00_project" / "flow_events.jsonl"
    if not path.parent.is_dir():
        return
    event = {"time": datetime.now(timezone.utc).isoformat(), "type": event_type, "details": details}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def provenance_ok(data, route):
    p = data.get("provenance", {}) if isinstance(data, dict) else {}
    return p.get("source") == "review_server" and p.get("route") == route and bool(p.get("session_id"))


def review_artifact_current(root, data, route):
    if not provenance_ok(data, route):
        return False
    provenance = data.get("provenance", {})
    html_rel = {
        "/template-feedback": "00_template_review.html",
        "/layout-feedback": "01_layout_direction.html",
        "/review-feedback": "02_visual_review.html",
    }.get(route, "")
    html_path = root / html_rel
    if not html_path.is_file() or provenance.get("html_sha256") != sha256(html_path):
        return False
    if route == "/layout-feedback":
        plan = root / INTERNAL / "01_layout_plan" / "layout_plan.json"
        return plan.is_file() and provenance.get("layout_plan_sha256") == sha256(plan)
    if route in {"/review-feedback", "/template-feedback"}:
        approved_hashes = provenance.get("png_sha256", {})
        if route == "/template-feedback":
            visuals = root / INTERNAL / "00_project" / "template_visuals"
            current = {path.name: sha256(path) for path in visuals.glob("*.png")}
            package_root = root / INTERNAL / "00_project" / "fidelity_template"
            package_files = [package_root / "template_registry.json"]
            package_files += sorted((package_root / "layout_canvases").glob("*.svg"))
            package_files += sorted((package_root / "canvas_previews" / "pages").glob("*.png"))
            package_files += [package_root / "canvas_previews" / "full_deck_contact_sheet.png"]
            package_current = {
                str(path.relative_to(root)): sha256(path) for path in package_files if path.is_file()
            }
            return (bool(current) and approved_hashes == current
                    and bool(package_current)
                    and provenance.get("template_package_sha256") == package_current)
        data_manifest = manifest(root)
        return bool(approved_hashes) and all(
            (root / page.get("png_path", "")).is_file()
            and approved_hashes.get(Path(page.get("png_path", "")).name) == sha256(root / page["png_path"])
            for page in data_manifest.get("pages", [])
        )
    return True


def manifest(root):
    return load_json(root / INTERNAL / "00_project" / "page_manifest.json", {})


def local_templates():
    items = []
    if TEMPLATE_LIBRARY.is_dir():
        for path in sorted(TEMPLATE_LIBRARY.glob("*/manifest.json")):
            data = load_json(path, {})
            if data.get("status") == "approved":
                items.append({"template_id": data.get("template_id", path.parent.name),
                              "name": data.get("name", path.parent.name),
                              "mode": data.get("mode", "reference"),
                              "is_default": data.get("is_default") is True})
    return sorted(items, key=lambda item: (not item.get("is_default"), item.get("name", "")))


def template_visual_review_complete(root):
    """Require complete visual evidence, full page coverage, and visual conclusions."""
    internal = root / INTERNAL
    profile = load_json(internal / "00_project" / "template_profile.json", {})
    visual_manifest = load_json(internal / "00_project" / "template_visuals" / "visual_manifest.json", {})
    intake = manifest(root).get("template_intake", {})
    fidelity_registry = load_json(internal / "00_project" / "fidelity_template" / "template_registry.json", {})
    fidelity_dir = internal / "00_project" / "fidelity_template"
    if intake.get("origin") == "library":
        source = load_json(internal / "00_project" / "template_library_source.json", {})
        return (
            source.get("status") == "approved"
            and source.get("template_id") == intake.get("library_template_id")
            and bool(profile)
            and (internal / "00_project" / "template_asset_registry.json").is_file()
            and (source.get("mode") != "fidelity" or (
                "content_base" in fidelity_registry.get("layouts", {})
                and registry_canvases_ready(fidelity_registry, fidelity_dir)
            ))
        )
    mode = intake.get("mode", "reference")
    asset_registry = load_json(internal / "00_project" / "template_asset_registry.json", {})
    expected = {
        Path(page.get("image", "")).stem
        for page in visual_manifest.get("pages", [])
        if isinstance(page, dict) and page.get("image")
    }
    reviewed = set(profile.get("pages_reviewed", [])) if isinstance(profile, dict) else set()
    direction = profile.get("design_direction", {}) if isinstance(profile, dict) else {}
    facts = profile.get("structural_extraction", {}) if isinstance(profile, dict) else {}
    candidate_ids = {
        item.get("asset_id") for item in facts.get("assets", []) if isinstance(item, dict) and item.get("asset_id")
    } | {
        item.get("candidate_id") for item in facts.get("native_shapes", []) if isinstance(item, dict) and item.get("candidate_id")
    }
    reviewed_source_ids = set(asset_registry.get("reviewed_source_ids", []))
    return (
        bool(expected)
        and reviewed == expected
        and stage_completed(root, "template")
        and bool(str(direction.get("overall_character", {}).get("value", "")).strip())
        and bool(direction.get("color_roles"))
        and bool(direction.get("type_hierarchy"))
        and (
            isinstance(asset_registry.get("assets", asset_registry.get("approved_assets")), list)
            or isinstance(asset_registry.get("approved"), list)
        )
        and (not candidate_ids or reviewed_source_ids == candidate_ids)
        and (mode != "fidelity" or (
            bool(fidelity_registry.get("layouts"))
            and "content_base" in fidelity_registry.get("layouts", {})
            and all(layout.get("required_components") for layout in fidelity_registry.get("layouts", {}).values())
            and registry_canvases_ready(fidelity_registry, fidelity_dir)
            and template_canvas_review_complete(root)
        ))
    )


def action(script, root, *args):
    """Return the only executable action format exposed by the controller."""
    return {"argv": [sys.executable, str(script), str(root), *map(str, args)]}


def batch_ids(data):
    return [key for key, value in sorted(data.get("batch_config", {}).items())
            if isinstance(value, dict) and value.get("pages")]


def latest_stage_event(root, step, batch=""):
    """Read the latest machine-owned completion/failure event for a stage."""
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
        if (
            event.get("type") in {"stage_completed", "stage_failed"}
            and details.get("step") == step
            and details.get("batch", "") == batch
        ):
            latest = details
    return latest


def latest_svg_evidence_event(root, batch=""):
    """Return the latest event that can accept or reject SVG visual evidence."""
    path = root / INTERNAL / "00_project" / "flow_events.jsonl"
    latest = {"event_type": ""}
    if not path.is_file():
        return latest
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        details = event.get("details", {}) if isinstance(event, dict) else {}
        if (
            event.get("type") in {"stage_completed", "stage_failed", "stage_evidence_sealed", "stage_evidence_failed"}
            and details.get("step") == "svg"
            and details.get("batch", "") == batch
        ):
            latest = {**details, "event_type": event.get("type", "")}
    return latest


def task_is_current(task, event):
    if not task or task.get("task_sha256") != event.get("task_sha256"):
        return False
    payload = dict(task)
    declared_task_hash = payload.pop("task_sha256", "")
    calculated_task_hash = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return declared_task_hash == calculated_task_hash


def split_svg_outputs(task):
    outputs = task.get("output_files", []) if isinstance(task, dict) else []
    evidence = [rel for rel in outputs if rel.endswith("_self_review.json")]
    artifacts = [rel for rel in outputs if rel not in evidence]
    return artifacts, evidence


def hashes_current(root, files, recorded):
    return bool(files) and set(recorded) == set(files) and all(
        (root / rel).is_file() and sha256(root / rel) == recorded[rel] for rel in files
    )


def svg_artifacts_completed(root, batch="", feedback_sha256=""):
    event = latest_stage_event(root, "svg", batch)
    if not event or event.get("issues") or not event.get("output_sha256"):
        return False
    if feedback_sha256 and event.get("feedback_sha256") != feedback_sha256:
        return False
    task = load_json(root / INTERNAL / "00_project" / "tasks" / f"svg_{batch}_task.json", {})
    if not task_is_current(task, event):
        return False
    layout_plan = root / INTERNAL / "01_layout_plan" / "layout_plan.json"
    if (not layout_plan.is_file()
            or task.get("constraints", {}).get("layout_plan_sha256") != sha256(layout_plan)):
        return False
    artifact_files, _ = split_svg_outputs(task)
    recorded = event.get("artifact_sha256") or {
        rel: event.get("output_sha256", {}).get(rel)
        for rel in artifact_files if event.get("output_sha256", {}).get(rel)
    }
    if not hashes_current(root, artifact_files, recorded):
        return False
    preview_pages = root / INTERNAL / "03_png_preview" / "pages"
    return (
        all((preview_pages / f"{key}.png").is_file() for key in task.get("pages", []))
        and (root / INTERNAL / "03_png_preview" / "full_deck_contact_sheet.png").is_file()
    )


def svg_evidence_sealed(root, batch="", feedback_sha256=""):
    event = latest_svg_evidence_event(root, batch)
    if event.get("event_type") not in {"stage_completed", "stage_evidence_sealed"} or event.get("issues"):
        return False
    if feedback_sha256 and event.get("feedback_sha256") != feedback_sha256:
        return False
    task = load_json(root / INTERNAL / "00_project" / "tasks" / f"svg_{batch}_task.json", {})
    if not task_is_current(task, event):
        return False
    _, evidence_files = split_svg_outputs(task)
    recorded = event.get("evidence_sha256") or {
        rel: event.get("output_sha256", {}).get(rel)
        for rel in evidence_files if event.get("output_sha256", {}).get(rel)
    }
    return hashes_current(root, evidence_files, recorded)


def stage_completed(root, step, batch="", feedback_sha256=""):
    if step == "svg":
        return (
            svg_artifacts_completed(root, batch, feedback_sha256)
            and svg_evidence_sealed(root, batch, feedback_sha256)
        )
    event = latest_stage_event(root, step, batch)
    if not event or event.get("issues") or not event.get("output_sha256"):
        return False
    if feedback_sha256 and event.get("feedback_sha256") != feedback_sha256:
        return False
    task_name = f"svg_{batch}_task.json" if step == "svg" else f"{step}_task.json"
    task = load_json(root / INTERNAL / "00_project" / "tasks" / task_name, {})
    if not task_is_current(task, event):
        return False
    expected_outputs = task.get("output_files", [])
    recorded = event.get("output_sha256", {})
    if set(recorded) != set(expected_outputs):
        return False
    return all((root / rel).is_file() and sha256(root / rel) == recorded[rel] for rel in expected_outputs)


def stage_action(root, step, batch="", revision=False, feedback_source="layout"):
    task_name = f"svg_{batch}_task.json" if step == "svg" else f"{step}_task.json"
    prompts = {
        "template": TEMPLATE_STAGE_PROMPT,
        "content": CONTENT_STAGE_PROMPT,
        "layout": LAYOUT_STAGE_PROMPT,
        "svg": SVG_STAGE_PROMPT,
    }
    make_args = ["make-task", "--step", step]
    finalize_args = ["finalize-stage", "--step", step]
    if batch:
        make_args += ["--batch", batch]
        finalize_args += ["--batch", batch]
    if revision:
        make_args.append("--revision")
        if step == "layout" and feedback_source != "layout":
            make_args += ["--feedback-source", feedback_source]
    stage = {
        "step": step,
        "batch_id": batch,
        "mode": "revision" if revision else "initial",
        "feedback_source": feedback_source if revision else "",
        "prepare": action(Path(__file__).resolve(), root, *make_args),
        "task": f"_internal/00_project/tasks/{task_name}",
        "instruction": prompts[step],
        "finalize": action(Path(__file__).resolve(), root, *finalize_args),
    }
    if step == "svg":
        stage["execution_policy"] = {
            "preferred_executor": "one_shot_subagent",
            "fallback_executor": "primary_agent_serial",
            "announce_before_start": True,
            "user_notice": (
                f"即将为 {batch} 启动一个一次性 SVG 子 Agent。"
                "它只读冻结 task，不与其他 batch 通信，完成 finalize 后立即退出。"
                "若宿主没有子 Agent 能力，必须先告知用户，再由主 Agent 串行执行同一 task。"
            ),
            "join_policy": "one completion join; no intermediate messages, resume, affinity, or polling loop",
        }
        stage["subagent_prompt"] = (
            f"使用当前 Planner PPT Skill 执行唯一 SVG batch {batch}。"
            f"准备后只读取 {stage['task']}的 input_files，只写 output_files。"
            "必须原样执行 task 内的 canvas_start_argv_by_page、validator_argv 和 visual_render_argv；"
            "不得手抄、缩写或重组路径。首次 Validator 后不得立即修图；必须先完成首次视觉渲染与检查，"
            "把两类发现合成一个清单后最多集中修复一次，再同时复跑 Validator 与视觉检查，然后运行 finalize。"
            "不跨 batch 写入，不修改批准文案、wireframe、canvas 选择或 locked layer。"
            "每个非 background wireframe 区域都要在对应 SVG 元素或分组上写入相同的 data-wireframe-label。"
        )
    return stage


def report_has_hard_errors(report):
    if not isinstance(report, dict):
        return True
    if report.get("status") == "fail":
        return True
    if report.get("summary", {}).get("errors", 0):
        return True
    return any(issue.get("severity") == "error" for issue in report.get("issues", []) if isinstance(issue, dict))


def visual_self_review_complete(review, page_keys):
    if not isinstance(review, dict):
        return False
    if review.get("visual_review_status") not in (None, "completed"):
        return False
    pages = review.get("pages", {})
    if not isinstance(pages, dict) or any(key not in pages for key in page_keys):
        return False
    if review.get("vision_available") is True:
        reviewed = all(isinstance(pages[key], dict) and pages[key].get("png_reviewed") is True for key in page_keys)
    else:
        reviewed = (
            review.get("review_mode") == "external_feedback"
            and bool(str(review.get("external_feedback_source", "")).strip())
            and all(pages[key].get("external_feedback_applied") is True for key in page_keys)
        )
    no_must_fix = all(not pages[key].get("must_fix") for key in page_keys if isinstance(pages[key], dict))
    return reviewed and no_must_fix


def export_is_current(root, data):
    output = root / "final_deck.pptx"
    report_path = root / INTERNAL / "06_ppt_output" / "ppt_conversion_report.json"
    report = load_json(report_path, {})
    pages = data.get("pages", [])
    svg_paths = [root / page.get("svg_path", "") for page in pages]
    if not output.is_file() or report.get("status") != "ok" or report.get("page_count") != len(pages):
        return False
    if not svg_paths or not all(path.is_file() for path in svg_paths):
        return False
    recorded = report.get("input_svg_sha256")
    if isinstance(recorded, dict):
        return all(recorded.get(path.name) == sha256(path) for path in svg_paths)
    return output.stat().st_mtime >= max(path.stat().st_mtime for path in svg_paths)


def derive(root):
    internal = root / INTERNAL
    common = {"required_inputs": [], "allowed_writers": [], "forbidden_writes": [], "checks": {}}
    if not internal.is_dir():
        return {**common, "state": "PROJECT_MISSING",
                "next_action": "Initialize the project, then ask the user about a template before content work.",
                "do": {"actions": [{"argv": [sys.executable, str(SCRIPTS / "init_svg_project.py"), "<dir>",
                                               "--source", "<source-markdown>"],
                                      "completion": "project scaffold exists"}]}}

    data = manifest(root)
    intake = data.get("template_intake", {})
    intake_status = intake.get("status", "pending")
    if intake_status not in {"provided", "none"}:
        templates = local_templates()
        return {**common, "state": "TEMPLATE_INTAKE", "next_action": "Show the template question and wait for a new user reply. A template path in the initial request is availability, not consent to extract it.",
                "do": {"user_question": "请确认本次模板方案：使用内置模板、提取用户提供的新模板，还是不使用模板？即使初始请求已经给出 PPTX/PDF/图片路径，也必须等待用户新的明确回复，不得自动提取。",
                       "requires_new_user_response": True,
                       "auto_selection_forbidden": True,
                       "input_template_path_is_not_consent": True,
                       "choices": [
                           *[{"id": f"library:{item['template_id']}",
                              "label": (f"使用默认模板（推荐）：{item['name']}" if item.get("is_default") else f"使用模板：{item['name']}"),
                              "command": action(Path(__file__).resolve(), root, "confirm-template", "--user-confirmed", "--status", "provided", "--library", item["template_id"])} for item in templates],
                           {"id": "extract", "label": "提取新模板（约 15 分钟）",
                            "command": action(Path(__file__).resolve(), root, "confirm-template", "--user-confirmed", "--status", "provided", "--mode", "fidelity", "--source", "<uploaded-path>")},
                           {"id": "none", "label": "不使用模板",
                            "command": action(Path(__file__).resolve(), root, "confirm-template", "--user-confirmed", "--status", "none")},
                       ],
                       "available_templates": templates},
                "allowed_writers": ["controller → page_manifest.json.template_intake"]}

    content = load_json(internal / "01_content" / "page_content.json", {})
    pages = content.get("pages", []) if isinstance(content, dict) else []
    content_ready = bool(pages)
    profile = internal / "00_project" / "template_profile.json"
    visual_manifest = internal / "00_project" / "template_visuals" / "visual_manifest.json"
    if intake_status == "provided" and not template_visual_review_complete(root):
        decision = load_json(internal / "00_project" / "template_worker_result.json", {})
        if intake.get("mode") == "fidelity" and decision.get("status") == "completed" and not decision.get("approved_components"):
            source = intake.get("source_files", [""])[0]
            feedback = load_json(internal / "00_project" / "template_feedback.json", {})
            if review_artifact_current(root, feedback, "/template-feedback") and feedback.get("approved") is not True:
                return {
                    **common, "state": "TEMPLATE_REVISION",
                    "next_action": "Revise the failed extraction from the frozen feedback task.",
                    "do": {"stage": stage_action(root, "template", revision=True)},
                }
            return {
                **common,
                "state": "TEMPLATE_REVIEW",
                "next_action": "Human-review the failed fidelity extraction before choosing revision or an alternative.",
                "do": {
                    "actions": [action(SCRIPTS / "generate_template_review_html.py", root),
                                action(Path(__file__).resolve(), root, "start-review", "--stage", "template")],
                    "alternatives": [
                        {
                            "id": "reference",
                            "label": "改为参考模式",
                            "command": action(Path(__file__).resolve(), root, "confirm-template", "--user-confirmed", "--status", "provided", "--mode", "reference", "--source", source),
                        },
                        {
                            "id": "replace",
                            "label": "更换模板",
                            "command": action(Path(__file__).resolve(), root, "confirm-template", "--user-confirmed", "--status", "provided", "--mode", "fidelity", "--source", "<replacement-template>"),
                        },
                    ],
                },
            }
        actions = []
        if not visual_manifest.exists():
            source = intake.get("source_files", [""])[0]
            source_path = Path(source)
            prepared_source = source
            if source_path.suffix.lower() == ".pptx":
                rendered_dir = internal / "00_project" / "template_rendered_pages"
                rendered_pages = [
                    path for path in rendered_dir.glob("*")
                    if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
                ]
                if not rendered_pages:
                    return {
                        **common,
                        "state": "TEMPLATE_RENDER_REQUIRED",
                        "next_action": "Obtain ordered page images before template analysis.",
                        "do": {
                            "host_actions": [{
                                "type": "render_presentation_pages",
                                "source": source,
                                "output_dir": str(rendered_dir),
                                "required_output": "one PNG/JPEG per visible slide",
                                "completion": "rendered page count is non-zero and pages preserve source order",
                            }],
                            "user_choices": [
                                {
                                    "id": "host_render",
                                    "label": "让当前宿主演示文稿能力渲染全部页面",
                                    "completion": f"将逐页图片写入 {rendered_dir}",
                                },
                                {
                                    "id": "upload_images",
                                    "label": "请用户上传按页码排序的 PNG/JPEG 图片或图片目录",
                                    "command": action(Path(__file__).resolve(), root, "confirm-template", "--user-confirmed", "--status", "provided", "--mode", intake.get("mode", "reference"), "--source", "<image-or-directory>"),
                                },
                                {
                                    "id": "provide_pdf",
                                    "label": "请用户提供同一模板导出的 PDF",
                                    "command": action(Path(__file__).resolve(), root, "confirm-template", "--user-confirmed", "--status", "provided", "--mode", intake.get("mode", "reference"), "--source", "<template.pdf>"),
                                },
                            ],
                        },
                        "required_inputs": [source],
                        "allowed_writers": ["host renderer → template_rendered_pages/"],
                    }
                prepared_source = str(rendered_dir)
            actions.append({"argv": [sys.executable, str(SCRIPTS / "template" / "prepare_visual_references.py"), prepared_source,
                                      "--project", str(root)]})
        # Structural extraction only supplies candidates for the Template stage.
        profile_data = load_json(profile, {})
        source_files = data.get("template_intake", {}).get("source_files", [])
        if not isinstance(profile_data.get("structural_extraction"), dict):
            for src in (source_files or []):
                if isinstance(src, str) and src.lower().endswith(".pptx"):
                    actions.append({
                        "argv": [sys.executable, str(SCRIPTS / "template" / "extract_template_assets.py"),
                                 src, "--project", str(root)],
                        "description": "Extract structural candidates for the Template stage",
                        "timeout_seconds": 300,
                        "allowed_writers": [
                            "extract_template_assets → template_profile.json (candidates only)",
                            "extract_template_assets → template_media/",
                        ],
                    })
                    break
        return {**common, "state": "TEMPLATE", "next_action": "Prepare template evidence, then execute the Template stage.",
                "do": {"actions": actions, "stage": stage_action(root, "template")},
                "required_inputs": intake.get("source_files", []),
                "allowed_writers": [
                    "primary Agent → task-scoped template profile/registry/decision outputs",
                    "primary Agent → fidelity canvases, canvas previews, and template_canvas_self_review.json",
                ]}

    if intake_status == "provided" and intake.get("origin") != "library":
        template_feedback = load_json(internal / "00_project" / "template_feedback.json", {})
        review_current = review_artifact_current(root, template_feedback, "/template-feedback")
        if not review_current:
            return {
                **common,
                "state": "TEMPLATE_REVIEW",
                "next_action": "Generate and open the mandatory human review for the extracted template.",
                "do": {"actions": [
                    action(SCRIPTS / "generate_template_review_html.py", root),
                    action(Path(__file__).resolve(), root, "start-review", "--stage", "template"),
                ], "completion": "current template_feedback.json is bound to the current review HTML and template package"},
                "required_inputs": ["00_template_review.html", "template visuals", "fidelity registry"],
                "allowed_writers": ["review_server.py → template_feedback.json"],
            }
        if template_feedback.get("approved") is not True:
            feedback_path = internal / "00_project" / "template_feedback.json"
            if not stage_completed(root, "template", feedback_sha256=sha256(feedback_path)):
                return {
                    **common,
                    "state": "TEMPLATE_REVISION",
                    "next_action": "Revise the template from the current frozen human feedback.",
                    "do": {"stage": stage_action(root, "template", revision=True)},
                    "allowed_writers": ["primary Agent → template outputs only"],
                }
            return {**common, "state": "TEMPLATE_REVIEW", "next_action": "Review the revised template extraction again.",
                    "do": {"actions": [action(SCRIPTS / "generate_template_review_html.py", root),
                                       action(Path(__file__).resolve(), root, "start-review", "--stage", "template")]}}
        if template_feedback.get("approved") is True and not intake.get("published_template_id"):
            return {**common, "state": "TEMPLATE_PUBLISH", "next_action": "Publish the approved extraction to the local template library.",
                    "do": {"actions": [action(Path(__file__).resolve(), root, "publish-template")]},
                    "allowed_writers": ["controller → Skill assets/template_library/<template_id>/", "controller → page_manifest.json.template_intake"]}

    if not content_ready:
        return {**common, "state": "CONTENT", "next_action": "Execute the Content stage for the full deck.",
                "do": {"stage": stage_action(root, "content")},
                "required_inputs": ["normalized source Markdown", "source_assets.json and declared images"],
                "allowed_writers": ["primary Agent → page_content.json"]}

    layout = load_json(internal / "01_layout_plan" / "layout_plan.json", {})
    layout_pages = layout.get("pages", []) if isinstance(layout, dict) else []
    capacity = load_json(internal / "01_layout_plan" / "layout_capacity_report.json", {})
    overfull = sorted(
        key for key, page in capacity.get("pages", {}).items()
        if isinstance(page, dict) and page.get("status") == "overfull"
    )
    if len(layout_pages) == len(pages) and overfull:
        return {**common, "state": "LAYOUT", "next_action": "Revise overfull Layout pages before human review.",
                "do": {"stage": stage_action(root, "layout")},
                "required_inputs": ["layout_capacity_report.json"],
                "blocking_pages": overfull,
                "allowed_writers": ["primary Agent → layout_plan.json"]}
    layout_html = root / "01_layout_direction.html"
    if len(layout_pages) != len(pages) or not layout_html.exists():
        return {**common, "state": "LAYOUT", "next_action": "Execute Layout, run the complete preflight, and generate the full layout review.",
                "do": {"stage": stage_action(root, "layout")},
                "required_inputs": ["page_content.json", "layout_taxonomy.md", "layout_plan_contract.md"],
                "allowed_writers": ["primary Agent → layout_plan.json"]}

    layout_feedback = load_json(internal / "01_layout_plan" / "layout_feedback.json", {})
    if provenance_ok(layout_feedback, "/layout-feedback") and layout_feedback.get("all_approved") is not True:
        feedback_path = internal / "01_layout_plan" / "layout_feedback.json"
        feedback_hash = sha256(feedback_path)
        if not stage_completed(root, "layout", feedback_sha256=feedback_hash):
            return {
                **common,
                "state": "LAYOUT",
                "next_action": "Revise Layout from the current frozen feedback.",
                "do": {
                    "stage": stage_action(root, "layout", revision=True),
                },
                "required_inputs": ["layout_feedback.json", "layout_plan.json"],
                "allowed_writers": ["primary Agent → layout_plan.json"],
            }
    if not (layout_feedback.get("all_approved") is True and review_artifact_current(root, layout_feedback, "/layout-feedback")):
        return {**common, "state": "LAYOUT_REVIEW", "next_action": "Show the complete layout review and wait for user approval of layout and final on-slide copy.",
                "do": {"actions": [action(Path(__file__).resolve(), root, "start-review", "--stage", "layout")],
                       "completion": "healthy review URL and layout_feedback.json all_approved for the current HTML hash"},
                "required_inputs": ["01_layout_direction.html"],
                "allowed_writers": ["review_server.py → layout_feedback.json"]}

    batches = batch_ids(data)
    task_dir = internal / "00_project" / "tasks"
    missing_tasks = []
    for bid in batches:
        task_path = task_dir / f"svg_{bid}_task.json"
        if not task_path.exists():
            missing_tasks.append(bid)
    incomplete = []
    evidence_unsealed = []
    visual_blocked = []
    for bid in batches:
        batch = data["batch_config"][bid]
        svgs = [internal / "02_svg_source" / f"{key}.svg" for key in batch["pages"]]
        validation = load_json(internal / "04_validation" / "batches" / f"{bid}.json")
        self_review = load_json(internal / "04_validation" / "batches" / f"{bid}_self_review.json", {})
        visual_ok = visual_self_review_complete(self_review, batch["pages"])
        if not visual_ok:
            visual_blocked.append(bid)
        artifact_ok = svg_artifacts_completed(root, bid)
        evidence_ok = svg_evidence_sealed(root, bid)
        if artifact_ok and visual_ok and not evidence_ok:
            evidence_unsealed.append(bid)
        if not all(path.exists() for path in svgs) or not validation or report_has_hard_errors(validation) or not artifact_ok or not visual_ok:
            incomplete.append(bid)
    if missing_tasks or incomplete:
        active = [bid for bid in batches if bid in set(missing_tasks + incomplete)]
        current = active[0]
        wave = [stage_action(root, "svg", bid) for bid in active]
        next_action = "Prepare every ready frozen SVG task, then run disjoint batches in waves of three (bounded by host concurrency)."
        return {**common, "state": "SVG_BATCH_BUILD", "next_action": next_action,
                "active_batches": active, "current_batch": current,
                "visual_blocked_batches": visual_blocked,
                "do": {"stage": wave[0],
                       "parallel_wave": {
                           "required_default": len(active) > 1,
                           "batches": active,
                           "stages": wave,
                           "max_parallel_batches": 3,
                           "concurrency": "min(3, host_available_slots, ready_batch_count)",
                           "join": "wait for the whole wave, then finalize/check every batch before deriving next state",
                       },
                       "visual_recovery": {
                           "first": "retry task visual_render_argv with escalated sandbox permission",
                           "if_escalation_unavailable": ["host renders into visual_preview_dir", "user supplies batch PNG/contact sheet for the frozen task"],
                           "completion": "visual findings applied to SVG; validator and PNG rechecked; no visual must_fix",
                       }},
                "required_inputs": ["approved layout", "style_system.md", "svg_rules.md",
                                    "batch input with compact template_style",
                                    "batch-scoped template runtime and selected canvases when fidelity"],
                "allowed_writers": ["one-shot SVG subagent, or announced primary-Agent fallback → current batch SVGs and batch validation/self-review"],
                "forbidden_writes": ["cross-batch SVG writes", "approval files", "manifest"]}

    if evidence_unsealed:
        return {
            **common,
            "state": "SVG_EVIDENCE_SEAL",
            "next_action": "Seal all ready visual-evidence versions in one controller action; stable SVG artifacts and renders are reused.",
            "active_batches": evidence_unsealed,
            "do": {
                "actions": [action(Path(__file__).resolve(), root, "seal-ready-batches", "--batches", ",".join(evidence_unsealed))],
                "completion": "every ready batch has a current stage_evidence_sealed event without re-rendering",
            },
            "required_inputs": ["stable SVG artifact hashes", "completed combined validator + visual evidence"],
            "allowed_writers": ["controller → flow_events.jsonl evidence seal events"],
            "forbidden_writes": ["SVG artifacts", "PNG previews", "validation reports"],
        }

    feedback_path = internal / "05_review" / "feedback.json"
    feedback = load_json(feedback_path, {})
    review_html = root / "02_visual_review.html"
    all_approved = feedback.get("all_approved") is True and review_artifact_current(root, feedback, "/review-feedback")
    approved_pages = all(feedback.get("pages", {}).get(p.get("page_key"), {}).get("approved") for p in data.get("pages", []))
    hashes_current = review_artifact_current(root, feedback, "/review-feedback")
    if hashes_current and not (all_approved and approved_pages):
        layout_pages = layout_reroute_pages(feedback)
        if layout_pages:
            feedback_hash = sha256(feedback_path)
            if not stage_completed(root, "layout", feedback_sha256=feedback_hash):
                return {
                    **common,
                    "state": "LAYOUT_REVISION_FROM_VISUAL",
                    "next_action": "Visual feedback changes page structure; route it back to Layout before any SVG-local repair.",
                    "affected_pages": layout_pages,
                    "do": {"stage": stage_action(root, "layout", revision=True, feedback_source="visual")},
                    "required_inputs": ["current visual feedback", "approved layout plan"],
                    "allowed_writers": ["primary Agent → layout_plan.json"],
                }
        rejected = {key for key, value in feedback.get("pages", {}).items()
                    if isinstance(value, dict) and not value.get("approved")}
        affected = [bid for bid in batches if rejected.intersection(data["batch_config"][bid]["pages"])]
        feedback_hash = sha256(feedback_path)
        pending = [bid for bid in affected if not stage_completed(root, "svg", bid, feedback_hash)]
        if pending:
            current = pending[0]
            wave = [stage_action(root, "svg", bid, revision=True) for bid in pending]
            return {**common, "state": "SVG_BATCH_BUILD", "next_action": "Revise the next affected SVG batch from frozen full-deck feedback.",
                    "active_batches": pending, "current_batch": current,
                    "do": {"stage": wave[0],
                           "parallel_wave": {
                               "required_default": len(pending) > 1,
                               "batches": pending,
                               "stages": wave,
                               "max_parallel_batches": 3,
                               "concurrency": "min(3, host_available_slots, ready_batch_count)",
                               "join": "wait for the whole revision wave, then finalize/check every affected batch",
                           }},
                    "required_inputs": ["full-deck feedback", "original batch SVGs", "style_system.md", "svg_rules.md"],
                    "allowed_writers": ["current affected batch only"]}
    if not review_html.exists() or not (all_approved and approved_pages and hashes_current):
        return {**common, "state": "VISUAL_REVIEW", "next_action": "Generate one review page for the complete deck and collect one full-deck decision.",
                "do": {"actions": [action(SCRIPTS / "generate_review_html.py", root, "--all"),
                                    action(Path(__file__).resolve(), root, "start-review", "--stage", "visual")],
                       "completion": "feedback.json approves every current page hash"},
                "required_inputs": ["all SVGs", "all PNGs", "merged validation/self-review"],
                "allowed_writers": ["review_server.py → feedback.json"]}

    if export_is_current(root, data):
        return {**common, "state": "COMPLETE", "next_action": "The approved deck has been exported and matches the current SVG inputs.",
                "do": {"actions": []}, "checks": {"complete": True, "export_ready": True}}

    return {**common, "state": "EXPORT", "next_action": "All pages are approved; export through the controller.",
            "do": {"actions": [action(Path(__file__).resolve(), root, "export")]}, "checks": {"export_ready": True}}


def run_command(command):
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.stdout:
        print(completed.stdout.strip())
    if completed.stderr:
        print(completed.stderr.strip(), file=sys.stderr)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def make_task(root, step, batch, revision, feedback_source="layout"):
    command = [sys.executable, str(HERE / "make_stage_task.py"), str(root), "--step", step]
    if batch:
        command += ["--batch", batch]
    if revision:
        command.append("--revision")
        if step == "layout" and feedback_source != "layout":
            command += ["--feedback-source", feedback_source]
    run_command(command)


def finalize_stage(root, step, batch):
    command = [sys.executable, str(HERE / "finalize_stage.py"), str(root), "--step", step]
    if batch:
        command += ["--batch", batch]
    run_command(command)


def seal_ready_batches(root, batches=""):
    requested = [item.strip() for item in str(batches).split(",") if item.strip()]
    known = batch_ids(manifest(root))
    selected = requested or known
    unknown = sorted(set(selected) - set(known))
    if unknown:
        raise SystemExit(f"unknown SVG batches: {unknown}")
    sealed = []
    for batch in selected:
        run_command([
            sys.executable, str(HERE / "finalize_stage.py"), str(root),
            "--step", "svg", "--batch", batch, "--seal-evidence-only",
        ])
        sealed.append(batch)
    print(json.dumps({"status": "sealed", "batches": sealed, "rendered": False}, ensure_ascii=False, indent=2))


def sync_manifest_from_content(root):
    """The controller owns the page/batch index; model stages never edit it."""
    internal = root / INTERNAL
    data = manifest(root)
    content = load_json(internal / "01_content" / "page_content.json", {})
    keys = [p.get("page_key") for p in content.get("pages", []) if isinstance(p, dict) and p.get("page_key")]
    if not keys:
        raise SystemExit("content collection produced no page keys")
    size = data.get("batch_size", 3)
    batches = {}
    pages = []
    for index in range(0, len(keys), size):
        bid = f"batch_{index // size + 1:02d}"
        batch_keys = keys[index:index + size]
        batches[bid] = {"pages": batch_keys}
        for key in batch_keys:
            pages.append({"page_key": key, "batch_id": bid,
                          "svg_path": f"_internal/02_svg_source/{key}.svg",
                          "png_path": f"_internal/03_png_preview/pages/{key}.png"})
    data["project"] = content.get("project", data.get("project", ""))
    data["pages"] = pages
    data["batch_config"] = batches
    save_json(internal / "00_project" / "page_manifest.json", data)


def merge_batch_reviews(root):
    internal = root / INTERNAL
    data = manifest(root)
    reports, self_pages = [], {}
    vision_available = True
    visual_review_status = "completed"
    review_modes = set()
    render_attempts = []
    external_feedback_sources = []
    reasons = []
    for bid in batch_ids(data):
        validation = load_json(internal / "04_validation" / "batches" / f"{bid}.json", {})
        reports.extend(validation.get("reports", []))
        review = load_json(internal / "04_validation" / "batches" / f"{bid}_self_review.json", {})
        self_pages.update(review.get("pages", {}))
        expected_pages = (data.get("batch_config", {}).get(bid, {}) or {}).get("pages", [])
        if not visual_self_review_complete(review, expected_pages):
            visual_review_status = "blocked"
        if review.get("review_mode"):
            review_modes.add(str(review["review_mode"]))
        render_attempts.extend(review.get("render_attempts", []))
        if review.get("external_feedback_source"):
            external_feedback_sources.append(str(review["external_feedback_source"]))
        if review.get("vision_available") is not True:
            vision_available = False
            if review.get("vision_unavailable_reason"):
                reasons.append(str(review["vision_unavailable_reason"]))
    summary = {"errors": sum(r.get("summary", {}).get("errors", 0) for r in reports),
               "warnings": sum(r.get("summary", {}).get("warnings", 0) for r in reports),
               "infos": sum(r.get("summary", {}).get("infos", 0) for r in reports)}
    save_json(internal / "04_validation" / "validation_summary.json",
              {"status": "fail" if summary["errors"] else "warning" if summary["warnings"] else "pass", "summary": summary, "reports": reports})
    review_mode = next(iter(review_modes)) if len(review_modes) == 1 else "mixed"
    save_json(internal / "04_validation" / "self_review.json",
              {"visual_review_status": visual_review_status, "review_mode": review_mode,
               "vision_available": vision_available, "vision_unavailable_reason": "; ".join(reasons),
               "external_feedback_source": "; ".join(external_feedback_sources),
               "render_attempts": render_attempts, "pages": self_pages})
    must_fix, should_fix, accepted_risks = [], [], []
    for page_key, page in self_pages.items():
        if not isinstance(page, dict):
            continue
        must_fix.extend({"page_key": page_key, "issue": item} for item in page.get("must_fix", []))
        should_fix.extend({"page_key": page_key, "issue": item} for item in page.get("should_fix", []))
        accepted = page.get("accepted_risks", page.get("accepted_warnings", []))
        accepted_risks.extend({"page_key": page_key, "issue": item} for item in accepted)
    save_json(internal / "04_validation" / "integrated_review.json", {
        "visual_review_status": visual_review_status,
        "review_mode": review_mode,
        "vision_available": vision_available,
        "must_fix": must_fix,
        "should_fix": should_fix,
        "accepted_risks": accepted_risks,
        "pages": self_pages,
    })


def clear_project_template(root):
    project_root = root / INTERNAL / "00_project"
    for name in ("template_profile.json", "template_asset_registry.json", "template_worker_result.json",
                 "template_feedback.json", "template_library_source.json"):
        (project_root / name).unlink(missing_ok=True)
    for name in ("template_visuals", "template_rendered_pages", "template_media", "fidelity_template"):
        path = project_root / name
        if path.is_dir():
            shutil.rmtree(path)
    for name in ("template_task.json",):
        (project_root / "tasks" / name).unlink(missing_ok=True)
    (root / "00_template_review.html").unlink(missing_ok=True)


def confirm_template(root, status, sources, mode="", library_id="", user_confirmed=False):
    data = manifest(root)
    if not user_confirmed:
        raise SystemExit("template choice requires a new explicit user reply and --user-confirmed")
    if library_id and status != "provided":
        raise SystemExit("--library requires --status provided")
    if status == "provided" and not sources and not library_id:
        raise SystemExit("--source is required when status=provided")
    if status == "provided" and not library_id and mode not in {"reference", "fidelity"}:
        raise SystemExit("--mode reference|fidelity is required when status=provided")
    if library_id and sources:
        raise SystemExit("--library and --source are mutually exclusive")
    if library_id:
        clear_project_template(root)
        completed = subprocess.run([
            sys.executable, str(SCRIPTS / "template" / "template_library.py"), "apply", str(root),
            "--template-id", library_id,
        ], capture_output=True, text=True)
        if completed.returncode:
            raise SystemExit(completed.stderr or completed.stdout)
        package = json.loads(completed.stdout)
        data["template_intake"] = {
            "status": "provided", "mode": package.get("mode", "reference"), "origin": "library",
            "library_template_id": library_id, "source_files": [str(TEMPLATE_LIBRARY / library_id)],
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
        }
        save_json(root / INTERNAL / "00_project" / "page_manifest.json", data)
        print(json.dumps(data["template_intake"], ensure_ascii=False, indent=2))
        return
    resolved_sources = []
    for source in sources:
        path = Path(source).expanduser().resolve()
        if not path.exists():
            raise SystemExit(f"template source not found: {path}")
        resolved_sources.append(str(path))
    old_intake = data.get("template_intake", {})
    source_changed = old_intake.get("source_files", []) != resolved_sources
    project_root = root / INTERNAL / "00_project"
    if source_changed or status == "none":
        clear_project_template(root)
    elif mode == "reference":
        (project_root / "template_worker_result.json").unlink(missing_ok=True)
        fidelity = project_root / "fidelity_template"
        if fidelity.is_dir():
            shutil.rmtree(fidelity)
    data["template_intake"] = {"status": status, "mode": mode if status == "provided" else "none",
                               "origin": "extraction" if status == "provided" else "none",
                               "source_files": resolved_sources,
                               "confirmed_at": datetime.now(timezone.utc).isoformat()}
    save_json(root / INTERNAL / "00_project" / "page_manifest.json", data)
    print(json.dumps(data["template_intake"], ensure_ascii=False, indent=2))


def publish_template(root):
    completed = subprocess.run([
        sys.executable, str(SCRIPTS / "template" / "template_library.py"), "publish", str(root),
    ], capture_output=True, text=True)
    if completed.returncode:
        raise SystemExit(completed.stderr or completed.stdout)
    package = json.loads(completed.stdout)
    data = manifest(root)
    data.setdefault("template_intake", {})["published_template_id"] = package["template_id"]
    save_json(root / INTERNAL / "00_project" / "page_manifest.json", data)
    print(json.dumps(package, ensure_ascii=False, indent=2))


def review_server_health(root, metadata=None):
    metadata = metadata or load_json(root / INTERNAL / "00_project" / "review_server.json", {})
    health_url = metadata.get("health_url")
    if not health_url:
        return None
    try:
        with urllib.request.urlopen(health_url, timeout=0.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None
    if (
        payload.get("status") == "running"
        and payload.get("project_dir") == str(root)
        and payload.get("session_id") == metadata.get("session_id")
        and payload.get("pid") == metadata.get("pid")
    ):
        return payload
    return None


def open_review_url(url):
    """Open the review immediately; a printed URL is not a human-review handoff."""
    if os.environ.get("PPT_HELL_REVIEW_TEST_NO_OPEN") == "1":
        return {"opened": False, "open_skipped_for_test": True}
    if sys.platform == "darwin":
        command = ["open", url]
    elif os.name == "nt":
        command = ["cmd", "/c", "start", "", url]
    else:
        command = ["xdg-open", url]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"REVIEW OPEN FAILED: {exc}") from exc
    if completed.returncode:
        details = (completed.stderr or completed.stdout or "").strip()
        raise SystemExit(f"REVIEW OPEN FAILED: {details or command[0]}")
    return {"opened": True}


def start_review(root, stage):
    html_rel = {"template": "00_template_review.html", "layout": "01_layout_direction.html", "visual": "02_visual_review.html"}[stage]
    if not (root / html_rel).is_file():
        raise SystemExit(f"REVIEW SERVER BLOCKED: missing {html_rel}")
    metadata_path = root / INTERNAL / "00_project" / "review_server.json"
    metadata = load_json(metadata_path, {})
    key = {"template": "template_review_url", "layout": "layout_url", "visual": "visual_review_url"}[stage]
    if review_server_health(root, metadata) and metadata.get(key):
        opened = open_review_url(metadata[key])
        print(json.dumps({"status": "ready", "reused": True, **opened, **metadata}, ensure_ascii=False, indent=2))
        return
    if review_server_health(root, metadata):
        stop_review(root)
        metadata = {}
    if metadata_path.exists():
        metadata_path.unlink()
    log_path = root / INTERNAL / "00_project" / "review_server.log"
    log_handle = log_path.open("a", encoding="utf-8")
    try:
        subprocess.Popen(
            [sys.executable, str(SCRIPTS / "review_server.py"), str(root)],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        log_handle.close()
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        time.sleep(0.1)
        metadata = load_json(metadata_path, {})
        if review_server_health(root, metadata):
            key = {"template": "template_review_url", "layout": "layout_url", "visual": "visual_review_url"}[stage]
            opened = open_review_url(metadata[key])
            print(json.dumps({"status": "ready", "reused": False, **opened, **metadata}, ensure_ascii=False, indent=2))
            return
    raise SystemExit(f"REVIEW SERVER FAILED: not healthy within 3 seconds; inspect {log_path}")


def stop_review(root):
    metadata_path = root / INTERNAL / "00_project" / "review_server.json"
    metadata = load_json(metadata_path, {})
    if review_server_health(root, metadata):
        request = urllib.request.Request(
            f"http://127.0.0.1:{metadata['port']}/shutdown", data=b"{}", method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(request, timeout=1).read()
        except OSError:
            pass
    deadline = time.monotonic() + 2.0
    while metadata_path.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    if metadata_path.exists() and not review_server_health(root, metadata):
        metadata_path.unlink()
    print(json.dumps({"status": "stopped"}, ensure_ascii=False))


def export(root):
    state = derive(root)
    if state.get("state") != "EXPORT":
        raise SystemExit("EXPORT BLOCKED: " + state.get("next_action", "workflow incomplete"))
    data = manifest(root)
    svg_files = [str(root / page["svg_path"]) for page in data.get("pages", [])]
    output = root / "final_deck.pptx"
    report = root / INTERNAL / "06_ppt_output" / "ppt_conversion_report.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    content = load_json(root / INTERNAL / "01_content" / "page_content.json", {})
    layout = load_json(root / INTERNAL / "01_layout_plan" / "layout_plan.json", {})
    content_by_key = {page.get("page_key"): page for page in content.get("pages", []) if isinstance(page, dict)}
    layout_by_key = {page.get("page_key"): page for page in layout.get("pages", []) if isinstance(page, dict)}
    notes = {}
    for page in data.get("pages", []):
        key = page.get("page_key")
        parts = []
        speaker = content_by_key.get(key, {}).get("speaker_notes")
        moved = layout_by_key.get(key, {}).get("copy_handling", {}).get("moved_to_notes")
        for value in (speaker, moved):
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
            elif isinstance(value, list):
                parts.extend(str(item).strip() for item in value if str(item).strip())
        if parts:
            notes[Path(page["svg_path"]).name] = "\n".join(parts)
    notes_path = report.parent / "speaker_notes.json"
    save_json(notes_path, notes)
    env = os.environ.copy()
    env["SMART_SVG_EXPORT_APPROVED_BY_PIPELINE"] = "1"
    subprocess.run([sys.executable, str(SCRIPTS / "native_svg_to_ppt.py"), *svg_files,
                    "-o", str(output), "--report", str(report), "--auto-size", "--match-aspect",
                    "--strict-missing-images", "--notes", str(notes_path)], check=True, env=env)
    report_data = load_json(report, {})
    report_data["input_svg_sha256"] = {Path(path).name: sha256(path) for path in svg_files}
    report_data["output_sha256"] = sha256(output)
    save_json(report, report_data)
    print(output)


def main():
    parser = argparse.ArgumentParser(description="Planner PPT deterministic pipeline controller")
    parser.add_argument("project_dir")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "next"):
        p = sub.add_parser(name)
        p.add_argument("--json", action="store_true")
    p = sub.add_parser("confirm-template")
    p.add_argument("--user-confirmed", action="store_true")
    p.add_argument("--status", required=True, choices=["provided", "none"])
    p.add_argument("--mode", default="", choices=["reference", "fidelity"])
    p.add_argument("--source", action="append", default=[])
    p.add_argument("--library", default="")
    p = sub.add_parser("start-review")
    p.add_argument("--stage", required=True, choices=["template", "layout", "visual"])
    sub.add_parser("stop-review")
    p = sub.add_parser("make-task")
    p.add_argument("--step", required=True, choices=["template", "content", "layout", "svg"])
    p.add_argument("--batch", default="")
    p.add_argument("--revision", action="store_true")
    p.add_argument("--feedback-source", default="layout", choices=["layout", "visual"])
    p = sub.add_parser("finalize-stage")
    p.add_argument("--step", required=True, choices=["template", "content", "layout", "svg"])
    p.add_argument("--batch", default="")
    p = sub.add_parser("seal-ready-batches")
    p.add_argument("--batches", default="", help="Comma-separated batch ids; default is all manifest batches")
    sub.add_parser("export")
    sub.add_parser("publish-template")
    args = parser.parse_args()
    root = Path(args.project_dir).resolve()
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    event_details = {
        "command": args.command,
        "step": getattr(args, "step", ""),
        "batch": getattr(args, "batch", ""),
        "started_at": started_at,
    }
    append_event(root, "pipeline_command_started", **event_details)
    try:
        if args.command in {"status", "next"}:
            print(json.dumps(derive(root), ensure_ascii=False, indent=2))
        elif args.command == "confirm-template":
            confirm_template(root, args.status, args.source, args.mode, args.library, args.user_confirmed)
        elif args.command == "start-review":
            start_review(root, args.stage)
        elif args.command == "stop-review":
            stop_review(root)
        elif args.command == "make-task":
            make_task(root, args.step, args.batch, args.revision, args.feedback_source)
        elif args.command == "finalize-stage":
            finalize_stage(root, args.step, args.batch)
        elif args.command == "seal-ready-batches":
            seal_ready_batches(root, args.batches)
        elif args.command == "export":
            export(root)
        elif args.command == "publish-template":
            publish_template(root)
    except BaseException as exc:
        append_event(
            root, "pipeline_command_failed", **event_details,
            completed_at=datetime.now(timezone.utc).isoformat(),
            duration_ms=round((time.monotonic() - started) * 1000),
            exit_code=exc.code if isinstance(exc, SystemExit) and isinstance(exc.code, int) else 1,
            error_type=type(exc).__name__,
        )
        raise
    append_event(
        root, "pipeline_command_completed", **event_details,
        completed_at=datetime.now(timezone.utc).isoformat(),
        duration_ms=round((time.monotonic() - started) * 1000),
        exit_code=0,
    )


if __name__ == "__main__":
    main()
