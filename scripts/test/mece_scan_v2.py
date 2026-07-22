#!/usr/bin/env python3
"""Static architecture scan for the vNext single-agent pipeline."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
failures = []

required = [
    ROOT / "scripts/orchestrate/ppt_pipeline.py",
    ROOT / "scripts/orchestrate/make_stage_task.py",
    ROOT / "scripts/orchestrate/finalize_stage.py",
    ROOT / "references/workflow/00_pipeline_controller.md",
    ROOT / "references/contracts/stage_task_contract.md",
    ROOT / "references/contracts/svg_stage_contract.md",
]
for path in required:
    if not path.is_file():
        failures.append(f"missing vNext authority: {path.relative_to(ROOT)}")

retired_paths = [
    "scripts/orchestrate/ppt_parent.py",
    "scripts/orchestrate/make_agent_task.py",
    "scripts/orchestrate/collect_agent_results.py",
    "references/workflow/00_parent_orchestrator.md",
    "references/contracts/agent_task_contract.md",
    "references/contracts/agent_result_contract.md",
]
for rel in retired_paths:
    if (ROOT / rel).exists():
        failures.append(f"retired path remains: {rel}")

production_files = [ROOT / "SKILL.md", ROOT / "agents/openai.yaml"]
production_files += list((ROOT / "references/workflow").glob("*.md"))
production_files += list((ROOT / "references/contracts").glob("*.md"))
production_files += list((ROOT / "scripts/orchestrate").glob("*.py"))
retired_terms = [
    "agent_result.json", "worker_agent_affinity", "bind-agent", "confirm-execution",
    "resume_then_send", "spawn_then_bind", "collect-results", "collect_agent_results.py",
    "make_agent_task.py", "ppt_parent.py",
]
for path in production_files:
    text = path.read_text(encoding="utf-8")
    for term in retired_terms:
        if term in text:
            failures.append(f"retired term {term!r} remains in {path.relative_to(ROOT)}")

maker = (ROOT / "scripts/orchestrate/make_stage_task.py").read_text(encoding="utf-8")
for forbidden in ("generated_at", "output_template", "worker_run_id", "started_at", "completed_at", "agent_result_path"):
    if forbidden in maker:
        failures.append(f"model bookkeeping remains in stage task builder: {forbidden}")

svg = (ROOT / "references/workflow/04_svg_stage.md").read_text(encoding="utf-8")
for forbidden in ("完整profile", "完整registry", "components.svg", "未选canvas"):
    if forbidden not in svg:
        failures.append(f"SVG minimum-context prohibition missing: {forbidden}")

if failures:
    print("MECE scan failed:")
    for item in failures:
        print("-", item)
    raise SystemExit(1)
print("MECE scan passed")
