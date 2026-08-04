"""
Unified contract validator for Planner's PPT Hell.

Modes:
  project      Validate content/layout/manifest cross-contract consistency.
  template     Validate template_profile.json.
  self-review  Validate self_review.json.

Exit code: 0 if all error-level checks pass, 1 otherwise.
"""

import argparse
import json
import sys
from pathlib import Path

# Legacy fields that must not be used as primary page identifiers
LEGACY_ID_FIELDS = {"page", "page_number", "page_id", "layout"}

# Required fields per contract
CONTENT_REQUIRED = {"page_key", "action_title", "core_message", "body_blocks"}
LAYOUT_REQUIRED = {
    "page_key",
    "layout_id",
    "page_mode",
    "visual_density",
    "grid",
    "wireframe",
    "layout_reason",
    "copy_handling",
    "visual_asset_strategy",
}
VALID_ASSET_NEEDS = {"required", "optional", "none"}
VALID_ASSET_TYPES = {
    "real_asset",
    "data_visual",
    "editable_schematic",
    "photo_placeholder",
    "screenshot_placeholder",
    "svg_background",
    "svg_illustration",
    "generated_image",
    "chart",
    "none",
}
VALID_ASSET_PLACEMENTS = {
    "main_right",
    "full_bleed",
    "background",
    "card_visual",
    "evidence_slot",
    "inline_diagram",
    "none",
}
VALID_IMAGE_FITS = {"contain", "cover"}
VALID_CROP_RATIOS = {"original", "16:9", "4:3", "1:1", "3:4"}
VALID_CROP_ANCHORS = {"center", "top", "bottom", "left", "right"}
MANIFEST_REQUIRED = {"page_key", "batch_id", "svg_path", "png_path"}
VALID_CONFIDENCE_LEVELS = {"high", "medium", "low"}
VALID_SELF_REVIEW_STATUSES = {"pass", "revise", "blocked"}


def load_json(path):
    """Load and parse a JSON file. Returns (data, error_message)."""
    p = Path(path)
    if not p.exists():
        return None, f"File not found: {p}"
    try:
        return json.loads(p.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON in {p}: {e}"
    except Exception as e:
        return None, f"Cannot read {p}: {e}"


def _has_visible_copy(value):
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, (str, int, float)):
        return bool(str(value).strip())
    if isinstance(value, list):
        return any(_has_visible_copy(item) for item in value)
    if isinstance(value, dict):
        return any(_has_visible_copy(item) for item in value.values())
    return False


def validate_project(content_data, layout_data, manifest_data, stage="all", project_root=None):
    errors = []
    warnings = []
    infos = []

    E = errors.append
    W = warnings.append
    I = infos.append

    # ── 1. Basic file presence (pre-checked by caller) ──

    # ── 2. Top-level structure ──
    files_to_check = [
        ("page_content.json", content_data, "pages"),
        ("page_manifest.json", manifest_data, "pages"),
    ]
    if stage in ("plan", "draft", "export", "all"):
        files_to_check.append(("layout_plan.json", layout_data, "pages"))

    for name, data, expected_key in files_to_check:
        if not isinstance(data, dict):
            E(f"{name}: not a JSON object")
            continue
        if expected_key not in data:
            E(f"{name}: missing '{expected_key}' array")
        elif not isinstance(data[expected_key], list):
            E(f"{name}: '{expected_key}' is not an array")
        elif len(data[expected_key]) == 0:
            W(f"{name}: '{expected_key}' array is empty — project may not be initialized yet")

    # ── 3. Extract page keys ──
    content_pages = content_data.get("pages", []) if isinstance(content_data, dict) else []
    layout_pages = layout_data.get("pages", []) if isinstance(layout_data, dict) else []
    manifest_pages = manifest_data.get("pages", []) if isinstance(manifest_data, dict) else []

    content_page_keys = set()
    for i, p in enumerate(content_pages):
        if not isinstance(p, dict):
            E(f"page_content.json page[{i}]: not an object")
            continue
        pk = p.get("page_key")
        if pk:
            content_page_keys.add(pk)

    layout_keys = set()
    for i, p in enumerate(layout_pages):
        if not isinstance(p, dict):
            E(f"layout_plan.json page[{i}]: not an object")
            continue
        pk = p.get("page_key")
        if pk:
            layout_keys.add(pk)

    manifest_keys = set()
    for i, p in enumerate(manifest_pages):
        if not isinstance(p, dict):
            E(f"page_manifest.json page[{i}]: not an object")
            continue
        pk = p.get("page_key")
        if pk:
            manifest_keys.add(pk)

    # ── 4. Cross-contract key consistency ──
    # Every page_key in layout_plan must exist in page_content
    if stage in ("plan", "draft", "export", "all"):
        orphan_layout = layout_keys - content_page_keys
        if orphan_layout:
            E(f"layout_plan.json references page_keys not in page_content.json: {sorted(orphan_layout)}")

        # Every page_key in layout_plan must exist in page_manifest
        orphan_layout_m = layout_keys - manifest_keys
        if orphan_layout_m:
            E(f"layout_plan.json references page_keys not in page_manifest.json: {sorted(orphan_layout_m)}")

    # Every page_key in page_manifest must exist in page_content
    orphan_manifest = manifest_keys - content_page_keys
    if orphan_manifest:
        E(f"page_manifest.json references page_keys not in page_content.json: {sorted(orphan_manifest)}")

    if stage in ("plan", "draft", "export", "all"):
        # Every page_key in page_manifest must exist in layout_plan
        orphan_manifest_l = manifest_keys - layout_keys
        if orphan_manifest_l:
            E(f"page_manifest.json references page_keys not in layout_plan.json: {sorted(orphan_manifest_l)}")

    # All keys from content should be in manifest (once pages is non-empty)
    missing_from_manifest = content_page_keys - manifest_keys
    if missing_from_manifest and content_page_keys:
        E(f"page_content.json has page_keys not in page_manifest.json: {sorted(missing_from_manifest)}")

    # ── 5. page_key format and sequentiality ──
    all_keys = content_page_keys | layout_keys | manifest_keys
    for pk in sorted(all_keys):
        if not pk.startswith("page_"):
            E(f"Invalid page_key format: '{pk}' — must be 'page_NN'")
            continue
        try:
            num_part = pk.split("_")[1]
            if len(num_part) != 2 or not num_part.isdigit():
                E(f"Invalid page_key format: '{pk}' — must be 'page_NN' (two-digit zero-padded)")
        except (IndexError, ValueError):
            E(f"Invalid page_key format: '{pk}' — must be 'page_NN'")

    # Check sequentiality among content keys (defines canonical order)
    content_nums = []
    for pk in sorted(content_page_keys):
        try:
            content_nums.append(int(pk.split("_")[1]))
        except (IndexError, ValueError):
            pass
    if content_nums:
        expected_nums = list(range(1, len(content_nums) + 1))
        if content_nums != expected_nums:
            W(f"page_content.json page_keys are not sequential: got {content_nums}, expected {expected_nums}")

    # ── 6. Required fields per page ──
    # Content pages
    for i, p in enumerate(content_pages):
        if not isinstance(p, dict):
            continue
        pk = p.get("page_key", f"[index {i}]")
        # Check for legacy identifiers
        for legacy in LEGACY_ID_FIELDS:
            if legacy in p:
                W(f"page_content.json {pk}: uses legacy field '{legacy}' as identifier — use 'page_key' instead")
        # Required fields
        for field in CONTENT_REQUIRED:
            if field not in p:
                E(f"page_content.json {pk}: missing required field '{field}'")
            elif field == "body_blocks" and (not isinstance(p[field], list) or len(p[field]) == 0):
                E(f"page_content.json {pk}: 'body_blocks' is empty — full copy required")
            elif field in ("action_title", "core_message") and (not isinstance(p[field], str) or not p[field].strip()):
                E(f"page_content.json {pk}: '{field}' is empty")

    # Layout pages
    scaffold_managed = isinstance(layout_data, dict) and "scaffold_status" in layout_data
    if stage in ("plan", "draft", "export", "all") and scaffold_managed:
        if layout_data.get("scaffold_status") != "completed":
            E("layout_plan.json scaffold_status must be completed after page-specific Layout judgment")
    for i, p in enumerate(layout_pages if stage in ("plan", "draft", "export", "all") else []):
        if not isinstance(p, dict):
            continue
        pk = p.get("page_key", f"[index {i}]")
        if scaffold_managed and p.get("scaffold_status") != "completed":
            E(f"layout_plan.json {pk}: scaffold_status must be completed")
        for legacy in LEGACY_ID_FIELDS:
            if legacy in p:
                W(f"layout_plan.json {pk}: uses legacy field '{legacy}' as identifier")
        for field in LAYOUT_REQUIRED:
            if field not in p:
                E(f"layout_plan.json {pk}: missing required field '{field}'")
            elif field == "wireframe" and (not isinstance(p[field], list) or len(p[field]) == 0):
                E(f"layout_plan.json {pk}: 'wireframe' is empty — at least one zone required")
            elif field == "layout_reason" and (not isinstance(p[field], str) or not p[field].strip()):
                E(f"layout_plan.json {pk}: 'layout_reason' is empty")
            elif field == "copy_handling":
                ch = p[field]
                if not isinstance(ch, dict) or "kept_on_slide" not in ch:
                    E(f"layout_plan.json {pk}: 'copy_handling' missing 'kept_on_slide'")
                elif not ch.get("kept_on_slide"):
                    E(f"layout_plan.json {pk}: 'copy_handling.kept_on_slide' is empty")
                if isinstance(ch, dict):
                    compressed = ch.get("compressed")
                    if not isinstance(compressed, bool):
                        if isinstance(compressed, list):
                            W(f"layout_plan.json {pk}: legacy 'copy_handling.compressed' array; use a boolean")
                        else:
                            E(f"layout_plan.json {pk}: 'copy_handling.compressed' must be a boolean")
                    if not isinstance(ch.get("moved_to_notes"), list):
                        E(f"layout_plan.json {pk}: 'copy_handling.moved_to_notes' must be an array")
                    final_copy = ch.get("final_on_slide")
                    if not isinstance(final_copy, dict):
                        E(f"layout_plan.json {pk}: 'copy_handling.final_on_slide' is required")
                    else:
                        if not str(final_copy.get("title", "")).strip():
                            E(f"layout_plan.json {pk}: 'copy_handling.final_on_slide.title' is required")
                        other_values = [value for key, value in final_copy.items() if key != "title"]
                        if not any(_has_visible_copy(value) for value in other_values):
                            E(f"layout_plan.json {pk}: final_on_slide needs visible content beyond title")
                    rationale = ch.get("compression_rationale", [])
                    if not isinstance(rationale, list) or not any(str(x).strip() for x in rationale):
                        E(f"layout_plan.json {pk}: 'copy_handling.compression_rationale' is required")
            elif field == "visual_asset_strategy":
                vas = p[field]
                if not isinstance(vas, dict):
                    E(f"layout_plan.json {pk}: 'visual_asset_strategy' must be an object")
                else:
                    for vf in ("asset_need", "asset_type", "placement", "reason"):
                        if not str(vas.get(vf, "")).strip():
                            E(f"layout_plan.json {pk}: 'visual_asset_strategy' missing '{vf}'")
                    if vas.get("asset_need") and vas.get("asset_need") not in VALID_ASSET_NEEDS:
                        W(f"layout_plan.json {pk}: visual_asset_strategy.asset_need is '{vas.get('asset_need')}'")
                    if vas.get("asset_type") and vas.get("asset_type") not in VALID_ASSET_TYPES:
                        W(f"layout_plan.json {pk}: visual_asset_strategy.asset_type is '{vas.get('asset_type')}'")
                    if vas.get("placement") and vas.get("placement") not in VALID_ASSET_PLACEMENTS:
                        W(f"layout_plan.json {pk}: visual_asset_strategy.placement is '{vas.get('placement')}'")
                    if vas.get("asset_need") == "none":
                        if vas.get("asset_type") != "none" or vas.get("placement") != "none":
                            E(f"layout_plan.json {pk}: asset_need 'none' requires asset_type='none' and placement='none'")
                    if vas.get("asset_type") in ("real_asset", "photo_placeholder", "screenshot_placeholder", "generated_image"):
                        if not str(vas.get("prompt_or_source", "")).strip():
                            W(f"layout_plan.json {pk}: visual_asset_strategy.prompt_or_source should describe source/prompt")
                    assets = vas.get("assets", [])
                    if assets is not None and not isinstance(assets, list):
                        E(f"layout_plan.json {pk}: visual_asset_strategy.assets must be an array")
                        assets = []
                    labels = {
                        str(zone.get("label", "")).strip()
                        for zone in p.get("wireframe", [])
                        if isinstance(zone, dict) and str(zone.get("label", "")).strip()
                    }
                    for ai, asset in enumerate(assets):
                        target = f"layout_plan.json {pk}: visual_asset_strategy.assets[{ai}]"
                        if not isinstance(asset, dict):
                            E(f"{target} must be an object")
                            continue
                        if not str(asset.get("path", "")).strip():
                            E(f"{target} missing project-relative 'path'")
                        elif project_root is not None:
                            declared_path = Path(str(asset["path"]))
                            resolved_path = (Path(project_root) / declared_path).resolve()
                            root_path = Path(project_root).resolve()
                            if declared_path.is_absolute() or root_path not in resolved_path.parents:
                                E(f"{target} path must stay inside the project")
                            elif not resolved_path.is_file():
                                E(f"{target} path does not exist: {asset['path']}")
                        slot = str(asset.get("slot_label", "")).strip()
                        if not slot or slot not in labels:
                            E(f"{target} slot_label must match a wireframe label")
                        if asset.get("fit") not in VALID_IMAGE_FITS:
                            E(f"{target} fit must be contain or cover; stretch is forbidden")
                        if asset.get("crop_ratio") not in VALID_CROP_RATIOS:
                            E(f"{target} crop_ratio must be one of {sorted(VALID_CROP_RATIOS)}")
                        if asset.get("crop_anchor") not in VALID_CROP_ANCHORS:
                            E(f"{target} crop_anchor must be one of {sorted(VALID_CROP_ANCHORS)}")
                        options = asset.get("crop_options")
                        if not isinstance(options, list) or not 2 <= len(options) <= 3:
                            E(f"{target} crop_options must contain 2-3 choices")
                        else:
                            for oi, option in enumerate(options):
                                if not isinstance(option, dict) or any(
                                    not str(option.get(field, "")).strip()
                                    for field in ("label", "fit", "crop_ratio", "crop_anchor", "tradeoff")
                                ):
                                    E(f"{target}.crop_options[{oi}] is incomplete")
            elif field in ("page_mode",):
                if p[field] not in ("rational", "emotional"):
                    W(f"layout_plan.json {pk}: 'page_mode' is '{p[field]}' — expected 'rational' or 'emotional'")
            elif field in ("visual_density",):
                if p[field] not in ("dense", "balanced", "airy"):
                    W(f"layout_plan.json {pk}: 'visual_density' is '{p[field]}' — expected 'dense', 'balanced', or 'airy'")

        suggestions = p.get("review_suggestions")
        if suggestions is not None and (
            not isinstance(suggestions, list)
            or any(not isinstance(item, str) or not item.strip() for item in suggestions)
        ):
            E(f"layout_plan.json {pk}: 'review_suggestions' must be an array of non-empty strings")

        # Wireframe zone checks
        wireframe = p.get("wireframe", [])
        for wi, zone in enumerate(wireframe):
            if not isinstance(zone, dict):
                continue
            for zf in ("label", "x", "y", "w", "h"):
                if zf not in zone:
                    W(f"layout_plan.json {pk} wireframe[{wi}]: missing '{zf}'")

    # Manifest pages
    for i, p in enumerate(manifest_pages):
        if not isinstance(p, dict):
            continue
        pk = p.get("page_key", f"[index {i}]")
        for legacy in LEGACY_ID_FIELDS:
            if legacy in p:
                W(f"page_manifest.json {pk}: uses legacy field '{legacy}' as identifier")
        for field in MANIFEST_REQUIRED:
            if field not in p:
                E(f"page_manifest.json {pk}: missing required field '{field}'")

    # ── 7. Manifest batch_config validation ──
    batch_config = manifest_data.get("batch_config", {}) if isinstance(manifest_data, dict) else {}
    batch_size = manifest_data.get("batch_size", 3) if isinstance(manifest_data, dict) else 3
    if not isinstance(batch_size, int) or batch_size <= 0:
        E("page_manifest.json batch_size must be a positive integer")
    if not isinstance(batch_config, dict):
        E("page_manifest.json batch_config must be an object")
    else:
        for bid, bdata in batch_config.items():
            if not isinstance(bdata, dict):
                E(
                    f"page_manifest.json batch_config.{bid}: must be an object with "
                    "'status' and 'pages'; list-style batches are not supported"
                )
                continue
            batch_pages = bdata.get("pages", [])
            if not isinstance(batch_pages, list) or not batch_pages:
                E(f"page_manifest.json batch_config.{bid}.pages must be a non-empty list")
                continue
            if len(batch_pages) > batch_size:
                # Check for explicit batch_size_override on this batch
                override = bdata.get("batch_size_override")
                if override and isinstance(override, int) and len(batch_pages) <= override:
                    pass  # explicitly allowed
                else:
                    E(f"page_manifest.json batch_config.{bid}: {len(batch_pages)} pages exceed batch_size {batch_size} (set 'batch_size_override' to explicitly allow)")
            for bpk in batch_pages:
                if bpk not in manifest_keys:
                    E(f"page_manifest.json batch_config.{bid}: references unknown page_key '{bpk}'")

    creative_direction = manifest_data.get("creative_direction") if isinstance(manifest_data, dict) else None
    if creative_direction is not None:
        if not isinstance(creative_direction, dict):
            E("page_manifest.json creative_direction must be an object")
        else:
            rules = creative_direction.get("approved_rules", [])
            if not isinstance(rules, list):
                E("page_manifest.json creative_direction.approved_rules must be an array")
            for i, rule in enumerate(rules):
                if (
                    not isinstance(rule, dict)
                    or not str(rule.get("id", "")).strip()
                    or not str(rule.get("rule", "")).strip()
                    or not str(rule.get("source_event_id", "")).strip()
                ):
                    E(f"page_manifest.json creative_direction.approved_rules[{i}] requires non-empty id, rule, and source_event_id")

    return errors, warnings, infos


def validate_template_profile(file_path, visual_manifest_path=""):
    path = Path(file_path)
    data, err = load_json(path)
    if err:
        return [err], [], []
    if not isinstance(data, dict):
        return ["template_profile.json root must be a JSON object"], [], []

    if data.get("method") == "visual_only":
        errors, warnings, infos = [], [], []
        sources = data.get("source_files")
        if not isinstance(sources, list) or not sources:
            errors.append("template_profile.json source_files must be a non-empty array")
        reviewed = data.get("pages_reviewed")
        if not isinstance(reviewed, list) or not reviewed:
            errors.append("template_profile.json pages_reviewed must be a non-empty array")
        if visual_manifest_path:
            manifest, manifest_err = load_json(Path(visual_manifest_path))
            if manifest_err:
                errors.append(manifest_err)
            else:
                expected = {
                    Path(page.get("image", "")).stem
                    for page in manifest.get("pages", [])
                    if isinstance(page, dict) and page.get("image")
                }
                actual = set(reviewed) if isinstance(reviewed, list) else set()
                if actual != expected:
                    missing = sorted(expected - actual)
                    extra = sorted(actual - expected)
                    if missing:
                        errors.append("template_profile.json pages_reviewed missing: " + ", ".join(missing))
                    if extra:
                        errors.append("template_profile.json pages_reviewed unknown: " + ", ".join(extra))
        direction = data.get("design_direction")
        required = {
            "overall_character", "color_roles", "type_hierarchy", "title_entry",
            "grid_and_alignment", "spacing_and_density", "image_language",
            "chart_language", "component_language", "deck_rhythm",
            "reusable_motifs", "page_exceptions",
        }
        if not isinstance(direction, dict):
            errors.append("template_profile.json design_direction must be an object")
        else:
            missing = sorted(required - set(direction))
            if missing:
                errors.append("template_profile.json design_direction missing: " + ", ".join(missing))
        if not isinstance(data.get("limitations", []), list):
            errors.append("template_profile.json limitations must be an array")
        reusable_assets = data.get("reusable_assets", [])
        if not isinstance(reusable_assets, list):
            errors.append("template_profile.json reusable_assets must be an array")
        else:
            for i, asset in enumerate(reusable_assets):
                if not isinstance(asset, dict):
                    errors.append(f"template_profile.json reusable_assets[{i}] must be an object")
                elif asset.get("fit") not in {"cover", "contain", "none"}:
                    errors.append(
                        f"template_profile.json reusable_assets[{i}].fit must be cover, contain, or none; stretch is forbidden"
                    )
        if not str(data.get("generated_at", "")).strip():
            warnings.append("template_profile.json generated_at should be set")
        return errors, warnings, infos

    errors, warnings, infos = [], [], []
    for key in TEMPLATE_REQUIRED_TOP_KEYS:
        if key not in data:
            errors.append(f"template_profile.json missing required key: {key}")
    if errors:
        return errors, warnings, infos

    if not isinstance(data.get("source_file"), str) or not data["source_file"].strip():
        errors.append("template_profile.json source_file must be a non-empty string")

    slide_size = data.get("slide_size")
    if not isinstance(slide_size, dict):
        errors.append("template_profile.json slide_size must be an object")
    else:
        for key in TEMPLATE_REQUIRED_SLIDE_SIZE_KEYS:
            if key not in slide_size:
                errors.append(f"template_profile.json slide_size missing {key}")

    colors = data.get("colors")
    if not isinstance(colors, list):
        errors.append("template_profile.json colors must be an array")
    else:
        for i, color in enumerate(colors):
            if not isinstance(color, dict):
                errors.append(f"template_profile.json colors[{i}] must be an object")
                continue
            for field in ("name", "hex", "role", "confidence"):
                if field not in color:
                    errors.append(f"template_profile.json colors[{i}] missing {field}")
            if color.get("confidence") not in ("parsed", "inferred"):
                errors.append(f"template_profile.json colors[{i}].confidence must be parsed or inferred")

    fonts = data.get("fonts")
    if not isinstance(fonts, dict):
        errors.append("template_profile.json fonts must be an object")
    elif fonts.get("confidence") not in ("parsed", "inferred", *VALID_CONFIDENCE_LEVELS):
        errors.append("template_profile.json fonts.confidence must be parsed, inferred, high, medium, or low")

    if not isinstance(data.get("layouts"), list):
        errors.append("template_profile.json layouts must be an array")

    tendencies = data.get("style_tendencies")
    if not isinstance(tendencies, dict):
        errors.append("template_profile.json style_tendencies must be an object")
    else:
        for field in ("color_tendency", "font_tendency", "layout_tendency", "overall_impression"):
            if field not in tendencies:
                errors.append(f"template_profile.json style_tendencies missing {field}")
        observations = tendencies.get("visual_observations", [])
        if not isinstance(observations, list):
            errors.append("template_profile.json style_tendencies.visual_observations must be an array when present")
        else:
            for i, observation in enumerate(observations):
                if not isinstance(observation, dict):
                    errors.append(f"template_profile.json style_tendencies.visual_observations[{i}] must be an object")
                    continue
                for field in ("observation", "evidence", "confidence"):
                    if not isinstance(observation.get(field), str) or not observation[field].strip():
                        errors.append(
                            f"template_profile.json style_tendencies.visual_observations[{i}].{field} must be a non-empty string"
                        )
                if observation.get("confidence") != "inferred":
                    errors.append(
                        f"template_profile.json style_tendencies.visual_observations[{i}].confidence must be inferred"
                    )

    confidence = data.get("confidence")
    if not isinstance(confidence, dict):
        errors.append("template_profile.json confidence must be an object")
    else:
        if confidence.get("overall") not in VALID_CONFIDENCE_LEVELS:
            errors.append("template_profile.json confidence.overall must be high, medium, or low")
        if not isinstance(confidence.get("reasons"), list) or not confidence["reasons"]:
            errors.append("template_profile.json confidence.reasons must be a non-empty array")

    policy = data.get("usage_policy")
    if not isinstance(policy, dict):
        errors.append("template_profile.json usage_policy must be an object")
    else:
        if policy.get("mode") not in {"extraction_audit_only", "reference_only"}:
            errors.append("template_profile.json usage_policy.mode must be extraction_audit_only")

    if not isinstance(data.get("generated_at"), str) or not data["generated_at"].strip():
        warnings.append("template_profile.json generated_at should be a non-empty ISO 8601 timestamp")

    visual_evidence = data.get("visual_evidence")
    if visual_evidence is not None:
        if not isinstance(visual_evidence, list):
            errors.append("template_profile.json visual_evidence must be an array when present")
        else:
            for i, item in enumerate(visual_evidence):
                if not isinstance(item, dict) or not str(item.get("source", "")).strip() or not isinstance(item.get("pages"), list) or not item["pages"]:
                    errors.append(f"template_profile.json visual_evidence[{i}] requires non-empty source and pages")

    for collection in ("components", "page_archetypes"):
        items = data.get(collection)
        if items is None:
            continue
        if not isinstance(items, list):
            errors.append(f"template_profile.json {collection} must be an array when present")
            continue
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"template_profile.json {collection}[{i}] must be an object")
                continue
            for field in ("name", "description", "evidence", "confidence"):
                if not isinstance(item.get(field), str) or not item[field].strip():
                    errors.append(f"template_profile.json {collection}[{i}].{field} must be a non-empty string")
            if item.get("confidence") != "inferred":
                errors.append(f"template_profile.json {collection}[{i}].confidence must be inferred")

    summary = data.get("downstream_summary")
    if summary is not None and (not isinstance(summary, str) or not summary.strip()):
        errors.append("template_profile.json downstream_summary must be a non-empty string when present")

    # New visual-first profiles use a direction package instead of construction
    # drawings. It remains optional so older profiles stay valid.
    direction = data.get("design_direction")
    if direction is not None:
        if not isinstance(direction, dict):
            errors.append("template_profile.json design_direction must be an object when present")
        else:
            for field in ("canvas", "color_roles", "type_hierarchy", "spacing_density", "visual_motifs", "flexibility"):
                item = direction.get(field)
                if not isinstance(item, dict):
                    errors.append(f"template_profile.json design_direction.{field} must be an object")
                    continue
                for key in ("direction", "evidence", "confidence"):
                    if not isinstance(item.get(key), str) or not item[key].strip():
                        errors.append(f"template_profile.json design_direction.{field}.{key} must be a non-empty string")
                if item.get("confidence") not in VALID_CONFIDENCE_LEVELS:
                    errors.append(f"template_profile.json design_direction.{field}.confidence must be high, medium, or low")
            anchors = direction.get("title_anchors")
            if not isinstance(anchors, list) or not anchors:
                errors.append("template_profile.json design_direction.title_anchors must be a non-empty array")
            else:
                for i, anchor in enumerate(anchors):
                    if not isinstance(anchor, dict):
                        errors.append(f"template_profile.json design_direction.title_anchors[{i}] must be an object")
                        continue
                    for key in ("page_nature", "direction", "evidence", "confidence"):
                        if not isinstance(anchor.get(key), str) or not anchor[key].strip():
                            errors.append(f"template_profile.json design_direction.title_anchors[{i}].{key} must be a non-empty string")
                    if anchor.get("confidence") not in VALID_CONFIDENCE_LEVELS:
                        errors.append(f"template_profile.json design_direction.title_anchors[{i}].confidence must be high, medium, or low")

    return errors, warnings, infos


def validate_self_review(project_dir):
    root = Path(project_dir)
    sr_path = root / "_internal" / "04_validation" / "self_review.json"
    sr, err = load_json(sr_path)
    if err:
        return [err], [], []
    if not isinstance(sr, dict):
        return ["self_review.json root must be a JSON object"], [], []

    errors, warnings, infos = [], [], []
    if "vision_available" not in sr:
        errors.append("self_review.json missing required field vision_available")

    visual_status = sr.get("visual_review_status")
    if visual_status not in (None, "completed"):
        errors.append("self_review.json visual_review_status must be completed before user review")

    vision_available = sr.get("vision_available", False)
    review_mode = sr.get("review_mode", "")
    if vision_available:
        infos.append("Vision: available")
    elif review_mode in ("external_feedback", "mixed") and str(sr.get("external_feedback_source", "")).strip():
        infos.append("Vision: completed from documented external feedback")
    else:
        errors.append("self_review.json has no completed visual evidence; resume the SVG stage from the current frozen task")

    pages = sr.get("pages", {})
    if not isinstance(pages, dict):
        errors.append("self_review.json pages must be an object")
    elif not pages:
        errors.append("self_review.json pages is empty")

    if isinstance(pages, dict):
        for pk, page in pages.items():
            if not isinstance(page, dict):
                errors.append(f"self_review.json {pk}: not an object")
                continue
            if vision_available and page.get("png_reviewed") is not True:
                errors.append(f"self_review.json {pk}: png_reviewed must be true when vision_available is true")
            if not vision_available and review_mode in ("external_feedback", "mixed"):
                if page.get("png_reviewed") is not True and page.get("external_feedback_applied") is not True:
                    errors.append(f"self_review.json {pk}: requires png_reviewed or external_feedback_applied")
            if page.get("must_fix"):
                errors.append(f"self_review.json {pk}: unresolved visual must_fix")

    return errors, warnings, infos


def report(errors, warnings, infos, success_message):
    for e in errors:
        print(f"ERROR: {e}")
    for w in warnings:
        print(f"WARNING: {w}")
    for i in infos:
        print(f"INFO: {i}")

    if not errors and not warnings and not infos:
        print(success_message)
    elif errors or warnings:
        print(f"\n{len(errors)} error(s), {len(warnings)} warning(s), {len(infos)} info(s)")

    sys.exit(1 if errors else 0)


def run_project(args):
    root = Path(args.project_dir)
    internal = root / "_internal"

    content_data, content_err = load_json(internal / "01_content" / "page_content.json")
    manifest_data, manifest_err = load_json(internal / "00_project" / "page_manifest.json")
    if args.stage in ("plan", "draft", "export", "all"):
        layout_data, layout_err = load_json(internal / "01_layout_plan" / "layout_plan.json")
    else:
        layout_data, layout_err = {"pages": []}, None

    errors = [err for err in (content_err, layout_err, manifest_err) if err]
    if errors:
        report(errors, [], [], "All contract checks passed.")

    errors, warnings, infos = validate_project(content_data, layout_data, manifest_data, args.stage, root)
    report(errors, warnings, infos, "All contract checks passed.")


def main():
    parser = argparse.ArgumentParser(description="Validate Planner's PPT Hell contracts.")
    sub = parser.add_subparsers(dest="mode")

    project = sub.add_parser("project", help="Validate content/layout/manifest consistency")
    project.add_argument("project_dir", help="Project root directory containing _internal/")
    project.add_argument(
        "--stage",
        choices=["content", "plan", "draft", "export", "all"],
        default="all",
        help="Validate only the contracts required for this workflow stage.",
    )
    project.set_defaults(func=run_project)

    template = sub.add_parser("template", help="Validate template_profile.json")
    template.add_argument("file_path", help="Path to template_profile.json")
    template.add_argument("--visual-manifest", default="", help="Optional visual_manifest.json for exact page coverage")
    template.set_defaults(
        func=lambda args: report(
            *validate_template_profile(args.file_path, args.visual_manifest),
            success_message=f"VALID: {args.file_path}",
        )
    )

    self_review = sub.add_parser("self-review", help="Validate self_review.json")
    self_review.add_argument("project_dir", help="Project root directory containing _internal/")
    self_review.set_defaults(
        func=lambda args: report(
            *validate_self_review(args.project_dir),
            success_message="Self-review validation passed.",
        )
    )

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(2)
    args.func(args)


if __name__ == "__main__":
    main()
