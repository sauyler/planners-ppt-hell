import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path

INTERNAL_ROOT = "_internal"

CANONICAL_DIRS = [
    f"{INTERNAL_ROOT}/00_project",
    f"{INTERNAL_ROOT}/01_content",
    f"{INTERNAL_ROOT}/01_layout_plan",
    f"{INTERNAL_ROOT}/02_svg_source",
    f"{INTERNAL_ROOT}/03_png_preview",
    f"{INTERNAL_ROOT}/04_validation",
    f"{INTERNAL_ROOT}/04_validation/batches",
    f"{INTERNAL_ROOT}/05_review/versions",
    f"{INTERNAL_ROOT}/06_ppt_output",
    f"{INTERNAL_ROOT}/ref",
]

STARTER_FILES = {
    f"{INTERNAL_ROOT}/01_content/page_content.json": json.dumps(
        {"project": "", "source_path": "", "pages": []}, ensure_ascii=False, indent=2
    ),
    f"{INTERNAL_ROOT}/01_layout_plan/layout_plan.json": json.dumps(
        {"project": "", "layout_version": 1, "pages": []}, ensure_ascii=False, indent=2
    ),
    f"{INTERNAL_ROOT}/00_project/page_manifest.json": json.dumps(
        {
            "project": "", "version": "4.0", "batch_size": 3,
            "template_intake": {"status": "pending", "mode": "", "origin": "", "source_files": [], "confirmed_at": ""},
            "creative_direction": {"approved_rules": []},
            "batch_config": {}, "pages": [],
        },
        ensure_ascii=False, indent=2,
    ),
    f"{INTERNAL_ROOT}/00_project/flow_events.jsonl": "",
}


def main():
    parser = argparse.ArgumentParser(
        description="Initialize a Planner's PPT Hell project scaffold."
    )
    parser.add_argument("project_dir", help="Project output directory")
    parser.add_argument("--source", required=True, help="Source markdown path")
    args = parser.parse_args()
    source = Path(args.source).expanduser().resolve()
    if not source.is_file():
        parser.error(f"source Markdown not found: {source}")
    try:
        source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        parser.error(f"source Markdown must be readable UTF-8 text: {source}: {exc}")
    source_path = str(source)

    root = Path(args.project_dir).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        parser.error(f"project directory is not empty; resume it instead of re-initializing: {root}")
    root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{root.name}.init-", dir=str(root.parent)))

    try:
        for dir_path in CANONICAL_DIRS:
            (staging / dir_path).mkdir(parents=True, exist_ok=True)

        for rel_path, content in STARTER_FILES.items():
            if rel_path == f"{INTERNAL_ROOT}/01_content/page_content.json":
                content = json.dumps(
                    {"project": "", "source_path": source_path, "pages": []},
                    ensure_ascii=False,
                    indent=2,
                )
            (staging / rel_path).write_text(content, encoding="utf-8")

        if root.exists():
            root.rmdir()
        os.replace(staging, root)
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    print(f"Initialized project at: {root.resolve()}")
    print("User-facing deliverables:")
    print("  01_layout_direction.html")
    print("  02_visual_review.html")
    print("  final_deck.pptx")
    print("Internal workspace:")
    for d in CANONICAL_DIRS:
        print(f"  {d}/")
    for rel_path in STARTER_FILES:
        print(f"  {rel_path}")


if __name__ == "__main__":
    main()
