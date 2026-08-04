#!/usr/bin/env python3
"""Create immutable stage tasks for the single-agent PPT pipeline."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

INTERNAL = "_internal"


def load_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, data):
    """Validate serialisation, then atomically replace the UTF-8 JSON file."""
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


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_file(root, source, destination):
    """Freeze a prior output as immutable revision input."""
    source = Path(source)
    if not source.is_file():
        raise ValueError(f"revision input is missing: {source}")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return str(destination.relative_to(root))


def template_style(profile):
    direction = (profile or {}).get("design_direction", {})
    return {
        "color_roles": direction.get("color_roles", {}),
        "type_hierarchy": direction.get("type_hierarchy", {}),
        "title_entry": direction.get("title_entry", {}),
        "component_language": direction.get("component_language", {}),
    }


def task_sha256(task):
    payload = dict(task)
    payload.pop("task_sha256", None)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def deterministic_input_hashes(task, root):
    """Hash every concrete task input using its declared path as the stable key."""
    hashes = {}
    reference_root = Path(task["reference_root"])
    for key in task.get("input_files", []):
        candidate = Path(key)
        paths = [candidate] if candidate.is_absolute() else [root / candidate, reference_root / candidate]
        path = next((item for item in paths if item.is_file()), None)
        if path:
            hashes[key] = sha256_file(path)
    if not hashes:
        raise ValueError("task has no hashable input files")
    return hashes


def base_task(root, step, contract, inputs, outputs):
    overlap = sorted(set(inputs) & set(outputs))
    if overlap:
        raise ValueError(f"task input/output paths overlap: {', '.join(overlap)}")
    task_id = f"{step}_task"
    return {
        "task_id": task_id,
        "step": step,
        "project_dir": str(root),
        "reference_root": str(Path(__file__).resolve().parents[2]),
        "contract": contract,
        "input_files": inputs,
        "output_files": outputs,
        "executor": "primary_agent",
        "constraints": {"encoding": "utf-8", "atomic_json_writes": True},
    }


def make_content(root, internal):
    content_stub = load_json(internal / "01_content" / "page_content.json", {})
    source = str(content_stub.get("source_path", "")).strip()
    if not source:
        raise ValueError("source_path is missing; initialize the project with --source <markdown-or-docx>")
    source_path = Path(source).expanduser()
    if not source_path.is_absolute():
        source_path = (root / source_path).resolve()
    if not source_path.is_file():
        raise ValueError(f"normalized source Markdown not found: {source_path}")
    assets_manifest = internal / "00_project" / "source" / "source_assets.json"
    source_inputs = [str(source_path)]
    source_summary = {"has_images": False, "image_count": 0, "assets": []}
    if assets_manifest.is_file():
        source_summary = load_json(assets_manifest, source_summary)
        source_inputs.append(str(assets_manifest.relative_to(root)))
        for asset in source_summary.get("assets", []):
            rel = str(asset.get("normalized_path", "")).strip()
            if rel and (root / rel).is_file():
                source_inputs.append(rel)
    task = base_task(
        root, "content", "references/contracts/page_content_contract.md",
        [*source_inputs, "references/workflow/02_content_stage.md", "references/contracts/page_content_contract.md"],
        ["_internal/01_content/page_content.json"],
    )
    task["source_asset_handoff"] = {
        "has_images": source_summary.get("has_images") is True,
        "image_count": int(source_summary.get("image_count", 0) or 0),
        "manifest": "_internal/00_project/source/source_assets.json",
        "instruction": "Preserve source image references and state explicitly in every downstream handoff when images exist.",
    }
    task["constraints"]["forbidden_writes"] = ["_internal/01_layout_plan/**", "_internal/02_svg_source/**"]
    return task, "content_task.json"


def make_layout(root, internal, revision=False, feedback_source="layout"):
    if not (internal / "01_content" / "page_content.json").exists():
        raise ValueError("page_content.json is required before layout")
    layout_plan = internal / "01_layout_plan" / "layout_plan.json"
    existing_layout = load_json(layout_plan, {}) if layout_plan.exists() else {}
    if not revision and not existing_layout.get("pages"):
        completed = subprocess.run([
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "scaffold_layout_plan.py"),
            str(root),
            "--force",
        ], capture_output=True, text=True)
        if completed.returncode:
            raise ValueError(completed.stderr or completed.stdout or "Layout scaffold generation failed")
    inputs = [
        "_internal/01_content/page_content.json",
        "references/workflow/03_layout_stage.md",
        "references/domain/layout_taxonomy.md",
        "references/contracts/layout_plan_contract.md",
    ]
    scaffold_input = ""
    previous_plan = ""
    if not revision:
        scaffold_input = snapshot_file(
            root,
            layout_plan,
            internal / "00_project" / "tasks" / "inputs" / "layout_scaffold" / "layout_plan.json",
        )
        inputs.append(scaffold_input)
    assets_manifest = internal / "00_project" / "source" / "source_assets.json"
    source_assets = load_json(assets_manifest, {}) if assets_manifest.is_file() else {}
    if assets_manifest.is_file():
        inputs.append(str(assets_manifest.relative_to(root)))
        inputs.extend(
            str(asset.get("normalized_path"))
            for asset in source_assets.get("assets", [])
            if asset.get("normalized_path") and (root / str(asset["normalized_path"])).is_file()
        )
    if (internal / "00_project" / "template_profile.json").exists():
        inputs.append("_internal/00_project/template_profile.json")
    capacity = internal / "01_layout_plan" / "layout_capacity_report.json"
    if capacity.is_file() and any(
        page.get("status") == "overfull" for page in load_json(capacity, {}).get("pages", {}).values()
    ):
        inputs.append("_internal/01_layout_plan/layout_capacity_report.json")
    fidelity = internal / "00_project" / "fidelity_template" / "template_registry.json"
    if fidelity.exists():
        inputs.append(str(fidelity.relative_to(root)))
    if revision:
        feedback = (
            internal / "05_review" / "feedback.json"
            if feedback_source == "visual"
            else internal / "01_layout_plan" / "layout_feedback.json"
        )
        if not feedback.is_file():
            raise ValueError(f"layout revision requires {feedback.name} from {feedback_source} review")
        snapshot = internal / "00_project" / "tasks" / "inputs" / f"layout_from_{feedback_source}_feedback.json"
        save_json(snapshot, load_json(feedback, {}))
        previous_plan = snapshot_file(
            root,
            internal / "01_layout_plan" / "layout_plan.json",
            internal / "00_project" / "tasks" / "inputs" / "layout_previous" / "layout_plan.json",
        )
        inputs.extend([str(snapshot.relative_to(root)), previous_plan])
        feedback_data = load_json(feedback, {})
        for page_feedback in feedback_data.get("pages", {}).values():
            for upload in (page_feedback or {}).get("asset_uploads", []):
                rel = str(upload.get("path", "")).strip()
                if rel and (root / rel).is_file():
                    inputs.append(rel)
    task = base_task(root, "layout", "references/contracts/layout_plan_contract.md", inputs,
                     ["_internal/01_layout_plan/layout_plan.json"])
    task["mode"] = "revision" if revision else "initial"
    task["constraints"]["layout_scaffold"] = {
        "source_path": scaffold_input or previous_plan,
        "output_path": "_internal/01_layout_plan/layout_plan.json",
        "status_field": "scaffold_status",
        "completion": "Set the top-level and every page scaffold_status to completed after page-specific judgment; incomplete scaffolds fail validation.",
        "rule": "Edit the deterministic scaffold in place. Do not regenerate the full page array with ad hoc Python or hand-write a replacement JSON document.",
    }
    task["source_asset_handoff"] = {
        "has_images": source_assets.get("has_images") is True,
        "image_count": int(source_assets.get("image_count", 0) or 0),
        "manifest": "_internal/00_project/source/source_assets.json",
        "instruction": "Place existing images deliberately; select a non-distorting fit and an explicit crop ratio/anchor for every image slot.",
    }
    task["constraints"]["forbidden_writes"] = [
        "_internal/00_project/page_manifest.json",
        "_internal/00_project/flow_events.jsonl",
        "_internal/01_layout_plan/layout_capacity_report.json",
        "_internal/01_layout_plan/layout_feedback.json",
        "_internal/02_svg_source/**",
        "_internal/05_review/feedback.json",
    ]
    if revision:
        task["constraints"]["revision_feedback_sha256"] = sha256_file(feedback)
        task["constraints"]["revision_feedback_source"] = feedback_source
        feedback_data = load_json(feedback, {})
        required_feedback = []
        global_feedback = str(feedback_data.get("global_feedback", "")).strip()
        if global_feedback:
            required_feedback.append({"scope": "global", "page_key": "", "request": global_feedback})
        for page_key, page_feedback in feedback_data.get("pages", {}).items():
            if not isinstance(page_feedback, dict):
                continue
            custom = str(page_feedback.get("custom_feedback", "")).strip()
            if custom:
                required_feedback.append({"scope": "page", "page_key": page_key, "request": custom})
            for annotation in page_feedback.get("annotations", []):
                if not isinstance(annotation, dict):
                    continue
                text = str(annotation.get("text", "")).strip()
                if not text:
                    continue
                required_feedback.append({
                    "scope": "page_region",
                    "page_key": page_key,
                    "region": {
                        "x": annotation.get("x"), "y": annotation.get("y"),
                        "w": annotation.get("w"), "h": annotation.get("h"),
                        "coordinate_space": "normalized_slide_0_to_1",
                    },
                    "request": text,
                })
            for suggestion in page_feedback.get("selected_suggestions", []):
                text = str(suggestion).strip()
                if text:
                    required_feedback.append({"scope": "page", "page_key": page_key, "request": text})
            for action in page_feedback.get("selected_review_actions", []):
                if isinstance(action, dict):
                    text = str(action.get("request") or action.get("desc") or action.get("title") or "").strip()
                else:
                    text = str(action).strip()
                if text:
                    required_feedback.append({"scope": "page", "page_key": page_key, "request": text})
            for upload in page_feedback.get("asset_uploads", []):
                if not isinstance(upload, dict) or upload.get("changed") is not True:
                    continue
                is_new = upload.get("is_new") is True or upload.get("operation") == "add"
                verb = "Add as a new image slot and redesign the wireframe around" if is_new else "Apply"
                required_feedback.append({
                    "scope": "page",
                    "page_key": page_key,
                    "request": (
                        f"{verb} image asset {upload.get('path', '')} at slot {upload.get('slot_label', '')}; "
                        f"fit={upload.get('fit', '')}, crop_ratio={upload.get('crop_ratio', '')}, "
                        f"crop_anchor={upload.get('crop_anchor', '')}. Preserve aspect ratio; never stretch."
                    ),
                })
        task["constraints"]["required_feedback_items"] = required_feedback
        task["constraints"]["previous_layout_plan"] = previous_plan
    return task, "layout_task.json"


def make_template(root, internal, revision=False):
    visual_manifest = internal / "00_project" / "template_visuals" / "visual_manifest.json"
    if not visual_manifest.exists():
        raise ValueError("prepare_visual_references.py must run before the Template stage")
    visual_data = load_json(visual_manifest, {})
    page_inputs = []
    for item in visual_data.get("pages", []):
        image = str(item.get("image", "")).strip() if isinstance(item, dict) else ""
        if not image:
            continue
        declared = Path(image)
        candidates = [declared] if declared.is_absolute() else [root / declared, visual_manifest.parent / declared]
        page_path = next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)
        if page_path is None:
            raise ValueError(f"visual manifest page image is missing: {image}")
        try:
            page_inputs.append(str(page_path.relative_to(root)))
        except ValueError:
            page_inputs.append(str(page_path))
    if not page_inputs:
        raise ValueError("visual manifest has no rendered page images")
    mode = load_json(internal / "00_project" / "page_manifest.json", {}).get("template_intake", {}).get("mode", "reference")
    outputs = [
        "_internal/00_project/template_profile.json",
        "_internal/00_project/template_asset_registry.json",
    ]
    if mode == "fidelity":
        outputs.extend([
            "_internal/00_project/template_worker_result.json",
            "_internal/00_project/fidelity_template/template_registry.json",
            "_internal/00_project/fidelity_template/components.svg",
            "_internal/00_project/fidelity_template/canvas_previews/png_manifest.json",
            "_internal/00_project/template_canvas_self_review.json",
        ])
    inputs = [
        "_internal/00_project/template_visuals/visual_manifest.json",
        "_internal/00_project/template_visuals/contact_sheet.png",
        *page_inputs,
        "references/workflow/01_template_intake.md",
        "references/contracts/template_profile_contract.md",
    ]
    if revision:
        feedback = internal / "00_project" / "template_feedback.json"
        if not feedback.is_file():
            raise ValueError("template revision requires template_feedback.json")
        snapshot = internal / "00_project" / "tasks" / "inputs" / "template_feedback.json"
        save_json(snapshot, load_json(feedback, {}))
        previous_outputs = {}
        for rel in outputs:
            source = root / rel
            if source.is_file():
                frozen = snapshot_file(
                    root, source,
                    internal / "00_project" / "tasks" / "inputs" / "template_previous" / rel,
                )
                previous_outputs[rel] = frozen
        inputs.extend([str(snapshot.relative_to(root)), *previous_outputs.values()])
    task = base_task(
        root, "template", "references/contracts/template_profile_contract.md",
        inputs,
        outputs,
    )
    task["mode"] = "revision" if revision else "initial"
    task["method"] = "visual_only"
    task["template_mode"] = mode
    task["constraints"]["write_root"] = str(root)
    task["constraints"]["estimated_duration_minutes"] = 15
    task["constraints"]["visual_input_rule"] = (
        "input_files explicitly lists the contact sheet and every rendered source page; inspect all of them."
    )
    task["constraints"]["required_source_page_ids"] = [Path(item).stem for item in page_inputs]
    task["constraints"]["fidelity_completion_rule"] = (
        "Every fidelity layout has non-empty required_components. template_asset_registry.reviewed_source_ids must "
        "exactly cover all structural candidates. Elements are only candidates: visual source-vs-canvas judgment decides "
        "what is usable. Layout canvases must originate from actual source page archetypes, never generic taxonomy placeholders."
    )
    if mode == "fidelity":
        task["constraints"]["fidelity_builder_argv"] = [
            sys.executable, str(Path(__file__).resolve().parents[1] / "template" / "build_fidelity_template.py"),
            "--project", str(root), "--decision", str(internal / "00_project" / "template_worker_result.json"),
        ]
        task["constraints"]["canvas_render_argv"] = [
            sys.executable, str(Path(__file__).resolve().parents[1] / "render_svg_png.py"),
            str(internal / "00_project" / "fidelity_template" / "layout_canvases"),
            str(internal / "00_project" / "fidelity_template" / "canvas_previews"),
        ]
        task["constraints"]["canvas_self_review_path"] = "_internal/00_project/template_canvas_self_review.json"
        task["constraints"]["visual_comparison_required"] = (
            "Run builder_argv, then canvas_render_argv. View source and canvas contact sheets plus every source/canvas PNG. "
            "Identify repeated identity features, page archetypes, typography, color, geometry, card/emphasis language. "
            "If a canvas is generic, incomplete, wrongly scaled, or not recognizably from its source pages, revise the same "
            "template_worker_result and rerun build/render. Maximum two repair rounds; unresolved layouts stay unusable/partial."
        )
        task["constraints"]["max_canvas_repair_rounds"] = 2
        task["constraints"]["visual_recovery_policy"] = {
            "on_permission_error": "request escalated permission and rerun the exact canvas_render_argv",
            "if_primary_agent_cannot_escalate": "stop this stage with visual_render_blocked and ask the host/user to render or provide PNGs",
            "alternatives": [
                "Host runs the exact canvas_render_argv and returns previews to this stage",
                "User reviews/provides source and canvas PNGs; feedback is frozen into a revision task",
            ],
        }
    task["constraints"]["forbidden_writes"] = ["project paths outside project_dir", "_internal/01_content/**", "_internal/01_layout_plan/**", "_internal/02_svg_source/**"]
    if revision:
        task["constraints"]["revision_feedback_sha256"] = sha256_file(feedback)
        task["constraints"]["layout_decision_rule"] = (
            "For every feedback.layouts entry: pass keeps the layout; discard removes its registry entry and canvas; "
            "revise implements custom_feedback/overall_feedback. If content_base is discarded, rebuild a valid content_base "
            "in the same revision because the runtime fallback is mandatory."
        )
        task["constraints"]["previous_output_snapshots"] = previous_outputs
    return task, "template_task.json"


def make_svg(root, internal, batch_id, revision=False):
    if not batch_id:
        raise ValueError("--batch is required for SVG work")
    manifest = load_json(internal / "00_project" / "page_manifest.json", {})
    batch = manifest.get("batch_config", {}).get(batch_id)
    if not isinstance(batch, dict) or not batch.get("pages"):
        raise ValueError(f"unknown or empty batch: {batch_id}")
    page_keys = batch["pages"]
    content = load_json(internal / "01_content" / "page_content.json", {})
    layout = load_json(internal / "01_layout_plan" / "layout_plan.json", {})
    content_by_key = {p.get("page_key"): p for p in content.get("pages", []) if isinstance(p, dict)}
    layout_by_key = {p.get("page_key"): p for p in layout.get("pages", []) if isinstance(p, dict)}
    missing = [key for key in page_keys if key not in content_by_key or key not in layout_by_key]
    if missing:
        raise ValueError(f"batch inputs missing content/layout for: {', '.join(missing)}")

    inputs_dir = internal / "00_project" / "tasks" / "inputs"
    batch_input = inputs_dir / f"svg_{batch_id}_input.json"
    profile = load_json(internal / "00_project" / "template_profile.json", {})
    selected_layout_ids = []
    for key in page_keys:
        layout_id = layout_by_key[key].get("template_layout_id")
        if layout_id and layout_id not in selected_layout_ids:
            selected_layout_ids.append(layout_id)
    fidelity = internal / "00_project" / "fidelity_template" / "template_registry.json"
    selected_canvases = []
    scoped_runtime = None
    if fidelity.exists():
        registry = load_json(fidelity, {})
        layouts = registry.get("layouts", {})
        missing_layout_ids = [key for key in page_keys if not layout_by_key[key].get("template_layout_id")]
        if missing_layout_ids:
            raise ValueError(
                "fidelity pages missing template_layout_id: " + ", ".join(missing_layout_ids)
            )
        selected_layouts = {}
        for layout_id in selected_layout_ids:
            entry = layouts.get(layout_id)
            if not entry or not entry.get("canvas_file"):
                raise ValueError(f"layout plan selects unknown fidelity layout or canvas: {layout_id}")
            canvas = internal / "00_project" / "fidelity_template" / entry["canvas_file"]
            if not canvas.is_file():
                raise ValueError(f"selected fidelity canvas is missing: {entry['canvas_file']}")
            selected_canvases.append(str(canvas.relative_to(root)))
            scoped_entry = dict(entry)
            scoped_entry["canvas_file"] = os.path.relpath(canvas, inputs_dir)
            selected_layouts[layout_id] = scoped_entry
        component_ids = {
            component_id
            for entry in selected_layouts.values()
            for component_id in entry.get("required_components", []) + entry.get("optional_components", [])
        }
        components = [
            component for component in registry.get("components", [])
            if isinstance(component, dict) and component.get("component_id") in component_ids
        ]
        if {item.get("component_id") for item in components} != component_ids:
            raise ValueError("selected fidelity layouts reference missing components")
        scoped_runtime = inputs_dir / f"svg_{batch_id}_template_runtime.json"
        save_json(scoped_runtime, {
            "schema": registry.get("schema", "planner.fidelity-template.v2"),
            "mode": "batch_scoped",
            "batch_id": batch_id,
            "canvas": registry.get("canvas", {"width": 1920, "height": 1080}),
            "layouts": selected_layouts,
            "components": components,
        })
    save_json(batch_input, {
        "batch_id": batch_id,
        "pages": page_keys,
        "content": [content_by_key[key] for key in page_keys],
        "layout": [layout_by_key[key] for key in page_keys],
        "template_style": template_style(profile),
        "template_layout_ids": selected_layout_ids,
        "source_content": "_internal/01_content/page_content.json",
        "source_layout": "_internal/01_layout_plan/layout_plan.json",
    })
    inputs = [
        str(batch_input.relative_to(root)),
        "references/workflow/04_svg_stage.md",
        "references/domain/style_system.md",
        "references/domain/svg_rules.md",
        "references/contracts/svg_stage_contract.md",
    ]
    if fidelity.exists():
        inputs.append(str(scoped_runtime.relative_to(root)))
        inputs.extend(selected_canvases)
    referenced_assets = []
    for key in page_keys:
        strategy = layout_by_key[key].get("visual_asset_strategy", {})
        candidates = strategy.get("assets", []) if isinstance(strategy.get("assets"), list) else [strategy]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            rel = str(item.get("path") or item.get("normalized_path") or "").strip()
            if rel and (root / rel).is_file() and rel not in referenced_assets:
                referenced_assets.append(rel)
    inputs.extend(referenced_assets)
    layout_feedback = internal / "01_layout_plan" / "layout_feedback.json"
    scoped_layout_approval = None
    if layout_feedback.is_file():
        approval = load_json(layout_feedback, {})
        scoped_layout_approval = inputs_dir / f"svg_{batch_id}_layout_approval.json"
        save_json(scoped_layout_approval, {
            "all_approved": approval.get("all_approved") is True,
            "global_feedback": approval.get("global_feedback", ""),
            "pages": {
                key: approval.get("pages", {}).get(key, {}) for key in page_keys
            },
            "provenance": approval.get("provenance", {}),
        })
        inputs.append(str(scoped_layout_approval.relative_to(root)))
    feedback = internal / "05_review" / "feedback.json"
    previous_svgs = {}
    required_revision_feedback = []
    if revision:
        if not feedback.is_file():
            raise ValueError("SVG revision requires feedback.json")
        feedback_data = load_json(feedback, {})
        feedback_snapshot = inputs_dir / f"svg_{batch_id}_feedback.json"
        save_json(feedback_snapshot, feedback_data)
        inputs.append(str(feedback_snapshot.relative_to(root)))
        global_feedback = str(feedback_data.get("global_feedback", "")).strip()
        if global_feedback:
            required_revision_feedback.append({"scope": "global", "page_key": "", "request": global_feedback})
        for key in page_keys:
            page_feedback = feedback_data.get("pages", {}).get(key, {})
            if not isinstance(page_feedback, dict):
                continue
            custom = str(page_feedback.get("custom_feedback", "")).strip()
            if custom:
                required_revision_feedback.append({"scope": "page", "page_key": key, "request": custom})
            for annotation in page_feedback.get("annotations", []):
                if not isinstance(annotation, dict) or not str(annotation.get("text", "")).strip():
                    continue
                required_revision_feedback.append({
                    "scope": "page_region", "page_key": key,
                    "region": {
                        "x": annotation.get("x"), "y": annotation.get("y"),
                        "w": annotation.get("w"), "h": annotation.get("h"),
                        "coordinate_space": "normalized_slide_0_to_1",
                    },
                    "request": str(annotation.get("text", "")).strip(),
                })
            for action in page_feedback.get("selected_review_actions", []):
                if isinstance(action, dict) and str(action.get("label", "")).strip():
                    required_revision_feedback.append({
                        "scope": "page", "page_key": key,
                        "request": str(action.get("label", "")).strip(),
                    })
        for key in page_keys:
            frozen = snapshot_file(
                root,
                internal / "02_svg_source" / f"{key}.svg",
                inputs_dir / f"svg_{batch_id}_previous" / f"{key}.svg",
            )
            previous_svgs[key] = frozen
        inputs.extend(previous_svgs.values())

    outputs = [f"_internal/02_svg_source/{key}.svg" for key in page_keys]
    outputs += [
        f"_internal/04_validation/batches/{batch_id}.json",
        f"_internal/04_validation/batches/{batch_id}_self_review.json",
    ]
    task = base_task(root, "svg", "references/contracts/svg_stage_contract.md", inputs, outputs)
    task.update({"task_id": f"svg_{batch_id}_task", "batch_id": batch_id, "pages": page_keys,
                 "mode": "revision" if revision else "initial", "executor": "one_shot_subagent_preferred"})
    task["source_asset_handoff"] = {
        "has_images": bool(referenced_assets),
        "image_count": len(referenced_assets),
        "asset_files": referenced_assets,
        "instruction": (
            "This batch contains existing images. Preserve aspect ratio; use SVG preserveAspectRatio meet/slice "
            "as approved by Layout and never force-stretch width and height."
        ),
    }
    task["constraints"].update({
        "layout_plan_sha256": sha256_file(internal / "01_layout_plan" / "layout_plan.json"),
        "validator_required": True,
        "fidelity_template_contract": (
            "When a batch-scoped template runtime exists, start each page from the exact selected SVG named by "
            "template_layout_id.canvas_file. The runtime contains only this batch's selected layouts and reachable components. "
            "Preserve every data-template-lock layer byte-equivalently "
            "in structure/style, replace only data-template-content-layer=replace, and keep data-template-component."
        ),
        "visual_inspection": (
            "Run the initial validator and visual render before making any quality repair. Merge validator issues and PNG findings "
            "into one repair list, make at most one concentrated SVG repair pass, then rerun both validator and visual inspection."
        ),
        "visual_review_required": True,
        "max_combined_repair_rounds": 1,
        "combined_quality_gate": {
            "required": True,
            "sequence": [
                "initial_validator", "initial_visual_render_and_inspection", "combined_findings",
                "zero_or_one_concentrated_repair", "final_validator", "final_visual_recheck",
            ],
            "forbidden": "Do not repair immediately after validator and then start a second independent visual repair loop.",
            "self_review_fields": [
                "initial_validator_checked", "initial_visual_checked", "combined_findings",
                "repair_passes", "final_validator_rechecked", "final_visual_rechecked",
            ],
        },
        "visual_recovery_policy": {
            "version": 1,
            "permission_error_markers": [
                "Mach port permission denied", "permission denied", "sandbox", "browser launch failed",
            ],
            "on_permission_error": "request escalated permission and rerun the exact visual_render_argv",
            "if_primary_agent_cannot_escalate": "stop this stage with visual_render_blocked",
            "alternatives": [
                "Host runs the exact visual_render_argv into visual_preview_dir",
                "User supplies this batch's PNG pages/contact sheet for the current task",
            ],
            "completion_rule": "no validator hard errors, no visual must_fix, and all visual findings fixed or classified",
        },
        "forbidden_writes": [
            "_internal/00_project/page_manifest.json", "_internal/00_project/flow_events.jsonl",
            "_internal/01_layout_plan/layout_feedback.json", "_internal/05_review/feedback.json",
            "SVG files outside this batch",
        ],
    })
    if revision:
        task["constraints"]["required_feedback_items"] = required_revision_feedback
    if scoped_layout_approval:
        task["constraints"]["approved_layout_feedback_sha256"] = sha256_file(scoped_layout_approval)
    if fidelity.exists():
        start_commands = {}
        for key in page_keys:
            final_copy = layout_by_key[key].get("copy_handling", {}).get("final_on_slide", {})
            title = final_copy.get("title", "") if isinstance(final_copy, dict) else ""
            if not str(title).strip():
                raise ValueError(f"layout plan final_on_slide.title is required for canvas start: {key}")
            start_commands[key] = [
                sys.executable,
                str(Path(__file__).resolve().parents[1] / "template" / "apply_fidelity_template.py"),
                "--project", str(root), "--page-key", key,
                "--layout-id", str(layout_by_key[key]["template_layout_id"]),
                "--title", str(title),
            ]
        task["constraints"]["canvas_start_argv_by_page"] = start_commands
    validator_argv = [
        sys.executable,
        str(Path(__file__).resolve().parents[1] / "validate_svg_layout.py"),
        str(internal / "02_svg_source"),
        "--manifest", str(internal / "00_project" / "page_manifest.json"),
        "--batch", batch_id,
        "--layout-plan", str(internal / "01_layout_plan" / "layout_plan.json"),
        "--output", str(internal / "04_validation" / "batches" / f"{batch_id}.json"),
    ]
    if fidelity.exists():
        validator_argv.extend(["--fidelity-template", str(scoped_runtime)])
    task["constraints"]["validator_argv"] = validator_argv
    preview_key = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:12]
    preview_dir = Path(tempfile.gettempdir()) / "planners-ppt-hell" / preview_key / batch_id
    task["constraints"]["visual_preview_dir"] = str(preview_dir)
    task["constraints"]["visual_render_argv"] = [
        sys.executable,
        str(Path(__file__).resolve().parents[1] / "render_svg_png.py"),
        str(internal / "02_svg_source"),
        str(preview_dir),
        "--manifest", str(internal / "00_project" / "page_manifest.json"),
        "--batch", batch_id,
    ]
    if revision:
        task["constraints"]["revision_feedback_sha256"] = sha256_file(feedback)
        task["constraints"]["previous_svg_by_page"] = previous_svgs
    return task, f"svg_{batch_id}_task.json"


def main():
    parser = argparse.ArgumentParser(description="Create a minimal immutable stage task")
    parser.add_argument("project_dir")
    parser.add_argument("--step", required=True, choices=["template", "content", "layout", "svg"])
    parser.add_argument("--batch", default="")
    parser.add_argument("--revision", action="store_true")
    parser.add_argument("--feedback-source", default="layout", choices=["layout", "visual"])
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    root = Path(args.project_dir).resolve()
    internal = root / INTERNAL
    if not internal.is_dir():
        parser.error(f"project is not initialized: {root}")
    makers = {"template": make_template, "content": make_content}
    try:
        if args.step == "svg":
            task, filename = make_svg(root, internal, args.batch, args.revision)
        elif args.step == "layout":
            task, filename = make_layout(root, internal, args.revision, args.feedback_source)
        else:
            task, filename = make_template(root, internal, args.revision) if args.step == "template" else makers[args.step](root, internal)
    except (ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    task["finalize_argv"] = [
        sys.executable,
        str(Path(__file__).resolve().parent / "finalize_stage.py"),
        str(root),
        "--step", args.step,
    ]
    if args.batch:
        task["finalize_argv"].extend(["--batch", args.batch])
    task["input_hashes"] = deterministic_input_hashes(task, root)
    task["task_sha256"] = task_sha256(task)
    output_dir = Path(args.output).resolve() if args.output else internal / "00_project" / "tasks"
    output_path = output_dir / filename
    save_json(output_path, task)
    print(output_path)


if __name__ == "__main__":
    main()
