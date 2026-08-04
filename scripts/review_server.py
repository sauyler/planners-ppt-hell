import argparse
import base64
import hashlib
import json
import mimetypes
import os
import re
import socket
import sys
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent / "template"))
from layout_canvas import registry_canvases_ready  # noqa: E402
from template_visual_gate import review_complete as template_canvas_review_complete  # noqa: E402


def atomic_json_write(path, data):
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


def validate_template_decisions(data, expected_layouts):
    """Validate and summarize per-layout pass/discard/revise decisions."""
    action = str(data.get("submission_action", "")).strip().lower()
    if action not in {"submit_batch", "approve_all"}:
        return "submission_action must be submit_batch or approve_all", {}
    layouts = data.get("layouts", {})
    valid = set(layouts) == set(expected_layouts) and all(
        isinstance(layouts[key], dict)
        and isinstance(layouts[key].get("approved"), bool)
        and layouts[key].get("decision") in {"pass", "discard", "revise"}
        and layouts[key].get("approved") == (layouts[key].get("decision") == "pass")
        for key in expected_layouts
    )
    if not valid:
        return "feedback must cover the exact layout set with pass/discard/revise decisions", {}
    all_pass = all(layouts[key]["decision"] == "pass" for key in expected_layouts)
    if data.get("approved") != all_pass or data.get("all_approved") != all_pass:
        return "approved/all_approved must reflect the per-layout decisions", {}
    overall = str(data.get("overall_feedback", "")).strip()
    missing = [
        key for key, item in layouts.items()
        if item["decision"] == "revise" and not str(item.get("custom_feedback", "")).strip() and not overall
    ]
    if missing:
        return "each revised layout requires per-layout or overall feedback", {}
    if action == "approve_all" and not all_pass:
        return "approve_all requires every layout to pass", {}
    return "", {
        "all_pass": all_pass,
        "discarded_layouts": sorted(key for key, item in layouts.items() if item["decision"] == "discard"),
        "revision_layouts": sorted(key for key, item in layouts.items() if item["decision"] == "revise"),
    }


def validate_layout_feedback_assets(project_root, data, expected_pages):
    """Validate the multi-image UI handoff before it becomes revision input."""
    project_root = Path(project_root).resolve()
    try:
        plan = json.loads(
            (project_root / "_internal" / "01_layout_plan" / "layout_plan.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        plan = {}
    expected_slots = {}
    for page in plan.get("pages", []):
        if not isinstance(page, dict) or not page.get("page_key"):
            continue
        assets = page.get("visual_asset_strategy", {}).get("assets", [])
        expected_slots[page["page_key"]] = {
            str(item.get("slot_label", "")).strip()
            for item in assets if isinstance(item, dict) and str(item.get("slot_label", "")).strip()
        }
    pages = data.get("pages", {})
    allowed_anchors = {
        "center", "top", "bottom", "left", "right",
        "top left", "top right", "bottom left", "bottom right",
    }
    for page_key in sorted(expected_pages):
        page = pages.get(page_key, {})
        uploads = page.get("asset_uploads", []) if isinstance(page, dict) else None
        if not isinstance(uploads, list):
            return f"{page_key}.asset_uploads must be an array"
        labels = [str(item.get("slot_label", "")).strip() for item in uploads if isinstance(item, dict)]
        if len(labels) != len(uploads) or any(not label for label in labels) or len(set(labels)) != len(labels):
            return f"{page_key}.asset_uploads requires one unique non-empty slot_label per image"
        declared = expected_slots.get(page_key, set())
        existing_labels = {
            str(item.get("slot_label", "")).strip() for item in uploads
            if isinstance(item, dict) and item.get("is_new") is not True
        }
        if declared and existing_labels != declared:
            return f"{page_key}.asset_uploads must preserve every declared layout image slot"
        for item in uploads:
            label = str(item.get("slot_label", "")).strip()
            is_new = item.get("is_new") is True or item.get("operation") == "add"
            if label not in declared and not is_new:
                return f"{page_key}.{label} is an undeclared slot and must use operation=add"
            if is_new and (item.get("operation") != "add" or item.get("changed") is not True):
                return f"{page_key}.{label} new image slots require operation=add and changed=true"
            if item.get("fit") not in {"contain", "cover"}:
                return f"{page_key}.{item.get('slot_label')}.fit must be contain or cover"
            ratio = str(item.get("crop_ratio", "")).strip()
            if ratio != "original" and not re.fullmatch(r"[1-9]\d*:[1-9]\d*", ratio):
                return f"{page_key}.{item.get('slot_label')}.crop_ratio must be original or W:H"
            if str(item.get("crop_anchor", "")).strip() not in allowed_anchors:
                return f"{page_key}.{item.get('slot_label')}.crop_anchor is invalid"
            if item.get("changed") is True:
                rel = str(item.get("path", "")).strip()
                target = (project_root / rel).resolve() if rel else None
                if not target or project_root not in target.parents or not target.is_file():
                    return f"{page_key}.{item.get('slot_label')} changed image path is missing or outside the project"
    return ""


class ReviewHandler(SimpleHTTPRequestHandler):
    project_root: Path = None
    session_id: str = ""

    def log_message(self, format, *args):
        print(f"[server] {args[0]}" if args else format, flush=True)

    def _json_response(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, rel_path, content_type="text/html; charset=utf-8"):
        fp = (self.project_root / rel_path).resolve()
        if self.project_root not in fp.parents:
            self._json_response({"error": "Path outside project"}, 403)
            return
        if fp.exists():
            body = fp.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._json_response({"error": f"File not found: {rel_path}"}, 404)

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            raise ValueError("invalid Content-Length")
        if length < 0 or length > 20 * 1024 * 1024:
            raise ValueError("payload exceeds 20 MiB")
        return self.rfile.read(length) if length else b""

    def _sha256_file(self, rel_path):
        fp = self.project_root / rel_path
        if not fp.exists() or not fp.is_file():
            return ""
        digest = hashlib.sha256()
        with fp.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _png_hashes(self):
        png_dir = self.project_root / "_internal" / "03_png_preview"
        if not png_dir.exists():
            return {}
        return {
            p.name: self._sha256_file(p.relative_to(self.project_root))
            for p in sorted((png_dir / "pages").glob("*.png"))
        }

    def _template_png_hashes(self):
        png_dir = self.project_root / "_internal" / "00_project" / "template_visuals"
        return {
            p.name: self._sha256_file(p.relative_to(self.project_root))
            for p in sorted(png_dir.glob("*.png"))
        } if png_dir.is_dir() else {}

    def _template_package_hashes(self):
        base = self.project_root / "_internal" / "00_project" / "fidelity_template"
        files = [base / "template_registry.json"]
        files.extend(sorted((base / "layout_canvases").glob("*.svg")))
        files.extend(sorted((base / "canvas_previews" / "pages").glob("*.png")))
        files.append(base / "canvas_previews" / "full_deck_contact_sheet.png")
        return {
            str(path.relative_to(self.project_root)): self._sha256_file(path.relative_to(self.project_root))
            for path in files if path.is_file()
        }

    def _expected_page_keys(self):
        try:
            manifest = json.loads((self.project_root / "_internal" / "00_project" / "page_manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return set()
        return {page.get("page_key") for page in manifest.get("pages", []) if isinstance(page, dict) and page.get("page_key")}

    def _append_event(self, event_type, details):
        event_path = self.project_root / "_internal" / "00_project" / "flow_events.jsonl"
        event_path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "time": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "details": details,
        }
        with event_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _with_provenance(self, data, route):
        now = datetime.now(timezone.utc).isoformat()
        html_rel = {
            "/template-feedback": "00_template_review.html",
            "/layout-feedback": "01_layout_direction.html",
            "/review-feedback": "02_visual_review.html",
        }[route]
        # Approval key removed — structural constraints (forbidden_writes + gate)
        # prevent the model from skipping review; password is redundant here.
        data.pop("approval_key", None)

        data["provenance"] = {
            "source": "review_server",
            "route": route,
            "session_id": self.session_id,
            "submitted_at": now,
            "html": html_rel,
            "html_sha256": self._sha256_file(html_rel),
            "png_sha256": self._png_hashes() if route == "/review-feedback" else self._template_png_hashes() if route == "/template-feedback" else {},
            "template_package_sha256": self._template_package_hashes() if route == "/template-feedback" else {},
        }
        if route == "/layout-feedback":
            data["provenance"]["layout_plan_sha256"] = self._sha256_file(
                "_internal/01_layout_plan/layout_plan.json"
            )
        return data

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path == "" or path == "/":
            self._serve_file("01_layout_direction.html")
        elif path == "/template":
            self._serve_file("00_template_review.html")
        elif path == "/review":
            self._serve_file("02_visual_review.html")
        elif path == "/health":
            self._json_response({
                "status": "running",
                "project_dir": str(self.project_root),
                "session_id": self.session_id,
                "pid": os.getpid(),
            })
        elif (path.startswith("/_internal/03_png_preview/")
              or path.startswith("/_internal/05_review/versions/")
              or path.startswith("/_internal/00_project/template_visuals/")
              or path.startswith("/_internal/00_project/template_media/")
              or path.startswith("/_internal/00_project/source/assets/")
              or path.startswith("/_internal/01_layout_plan/uploads/")):
            fp = (self.project_root / path.lstrip("/")).resolve()
            if self.project_root not in fp.parents:
                self._json_response({"error": "Path outside project"}, 403)
                return
            if fp.is_file():
                ct = mimetypes.guess_type(fp.name)[0] or "application/octet-stream"
                body = fp.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", ct)
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)
            else:
                self._json_response({"error": "Not found"}, 404)
        else:
            self._json_response({"error": "Not found"}, 404)

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        try:
            body = self._read_body()
        except ValueError as exc:
            self._json_response({"error": str(exc)}, 413)
            return
        data = {}
        if body:
            ct = self.headers.get("Content-Type", "")
            if "application/json" in ct:
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    pass
            elif "application/x-www-form-urlencoded" in ct:
                parsed = parse_qs(body.decode("utf-8"))
                data = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
        if not isinstance(data, dict):
            self._json_response({"error": "JSON payload must be an object"}, 400)
            return

        if path == "/layout-asset":
            page_key = str(data.get("page_key", "")).strip()
            slot_label = str(data.get("slot_label", "")).strip()
            filename = Path(str(data.get("filename", "image"))).name
            encoded = str(data.get("data_base64", ""))
            if page_key not in self._expected_page_keys() or not slot_label:
                self._json_response({"error": "valid page_key and slot_label are required"}, 400)
                return
            suffix = Path(filename).suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
                self._json_response({"error": "only PNG, JPEG, WEBP and GIF images are accepted"}, 400)
                return
            try:
                payload = base64.b64decode(encoded, validate=True)
            except (ValueError, TypeError):
                self._json_response({"error": "invalid base64 image"}, 400)
                return
            if not payload or len(payload) > 12 * 1024 * 1024:
                self._json_response({"error": "image must be between 1 byte and 12 MiB"}, 400)
                return
            safe_slot = "".join(char if char.isalnum() or char in "-_" else "_" for char in slot_label)[:64]
            output = (
                self.project_root / "_internal" / "01_layout_plan" / "uploads" / page_key
                / f"{safe_slot}-{uuid.uuid4().hex[:10]}{suffix}"
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(payload)
            rel = output.relative_to(self.project_root).as_posix()
            self._json_response({
                "status": "ok",
                "path": rel,
                "url": f"/{rel}",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "slot_label": slot_label,
            })

        elif path == "/template-feedback":
            manifest = {}
            try:
                manifest = json.loads((self.project_root / "_internal" / "00_project" / "page_manifest.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
            intake_mode = manifest.get("template_intake", {}).get("mode", "reference")
            fidelity_ready = True
            expected_layouts = {"reference_system"}
            if intake_mode == "fidelity":
                try:
                    registry = json.loads((self.project_root / "_internal" / "00_project" / "fidelity_template" / "template_registry.json").read_text(encoding="utf-8"))
                    expected_layouts = set(registry.get("layouts", {}))
                    fidelity_ready = bool(registry.get("layouts")) and all(
                        layout.get("required_components") for layout in registry.get("layouts", {}).values()
                    ) and registry_canvases_ready(
                        registry, self.project_root / "_internal" / "00_project" / "fidelity_template"
                    ) and template_canvas_review_complete(self.project_root)
                except (OSError, json.JSONDecodeError):
                    fidelity_ready = False
                if not expected_layouts:
                    expected_layouts = {"reference_system"}
            layout_feedback = data.get("layouts", {})
            decision_error, decision_summary = validate_template_decisions(data, expected_layouts)
            if decision_error:
                self._json_response({"error": decision_error}, 400)
                return
            all_pass = decision_summary["all_pass"]
            candidate_audit_ready = True
            if all_pass:
                try:
                    profile = json.loads((self.project_root / "_internal" / "00_project" / "template_profile.json").read_text(encoding="utf-8"))
                    asset_registry = json.loads((self.project_root / "_internal" / "00_project" / "template_asset_registry.json").read_text(encoding="utf-8"))
                    facts = profile.get("structural_extraction", {})
                    candidate_ids = {
                        item.get("asset_id") for item in facts.get("assets", []) if isinstance(item, dict) and item.get("asset_id")
                    } | {
                        item.get("candidate_id") for item in facts.get("native_shapes", []) if isinstance(item, dict) and item.get("candidate_id")
                    }
                    candidate_audit_ready = not candidate_ids or set(asset_registry.get("reviewed_source_ids", [])) == candidate_ids
                except (OSError, json.JSONDecodeError):
                    candidate_audit_ready = False
            if all_pass and (not str(data.get("template_name", "")).strip()
                             or not candidate_audit_ready
                             or not fidelity_ready):
                self._json_response({"error": "Feedback requires the current layout set; all-pass requires a template name, candidate audit, and visual gate."}, 400)
                return
            data["discarded_layouts"] = decision_summary["discarded_layouts"]
            data["revision_layouts"] = decision_summary["revision_layouts"]
            data["submitted_at"] = datetime.now(timezone.utc).isoformat()
            data = self._with_provenance(data, "/template-feedback")
            atomic_json_write(self.project_root / "_internal" / "00_project" / "template_feedback.json", data)
            self._append_event("template_feedback_submitted", data.get("provenance", {}))
            self._json_response({"status": "ok", "written": "_internal/00_project/template_feedback.json"})

        elif path == "/layout-feedback":
            expected = self._expected_page_keys()
            supplied = set((data.get("pages") or {}).keys()) if isinstance(data, dict) else set()
            if supplied != expected:
                self._json_response({"error": "layout feedback page set must exactly match the manifest"}, 400)
                return
            asset_error = validate_layout_feedback_assets(self.project_root, data, expected)
            if asset_error:
                self._json_response({"error": asset_error}, 400)
                return
            data["updated_at"] = datetime.now(timezone.utc).isoformat()
            data = self._with_provenance(data, "/layout-feedback")
            atomic_json_write(self.project_root / "_internal" / "01_layout_plan" / "layout_feedback.json", data)
            self._append_event("layout_feedback_submitted", data.get("provenance", {}))
            self._json_response({"status": "ok", "written": "_internal/01_layout_plan/layout_feedback.json"})

        elif path == "/review-feedback":
            expected = self._expected_page_keys()
            supplied = set((data.get("pages") or {}).keys()) if isinstance(data, dict) else set()
            if supplied != expected:
                self._json_response({"error": "visual feedback page set must exactly match the manifest"}, 400)
                return
            data["submitted_at"] = datetime.now(timezone.utc).isoformat()
            data = self._with_provenance(data, "/review-feedback")
            review_dir = self.project_root / "_internal" / "05_review"
            review_dir.mkdir(parents=True, exist_ok=True)
            latest_path = review_dir / "feedback.json"
            atomic_json_write(latest_path, data)
            self._append_event("visual_feedback_submitted", data.get("provenance", {}))
            written = ["_internal/05_review/feedback.json"]
            self._json_response({"status": "ok", "written": written})

        elif path == "/shutdown":
            self._json_response({"status": "shutting_down"})
            print("[server] Shutting down.", flush=True)
            threading.Thread(target=self.server.shutdown, daemon=True).start()

        else:
            self._json_response({"error": "Unknown endpoint"}, 404)

def find_port(start=8765):
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("No free port found")


def main():
    parser = argparse.ArgumentParser(description="Local review server for Planner's PPT Hell.")
    parser.add_argument("project_dir", help="Project root directory")
    parser.add_argument("--port", type=int, default=0, help="Port (default: auto-find from 8765)")
    args = parser.parse_args()

    root = Path(args.project_dir).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        sys.exit(1)

    port = args.port if args.port else find_port()
    ReviewHandler.project_root = root
    ReviewHandler.session_id = uuid.uuid4().hex
    server = ThreadingHTTPServer(("127.0.0.1", port), ReviewHandler)

    # Write server metadata for controller preflight diagnostics.
    server_meta_path = root / "_internal" / "00_project" / "review_server.json"
    server_meta = {
        "pid": os.getpid(),
        "port": port,
        "session_id": ReviewHandler.session_id,
        "layout_url": f"http://127.0.0.1:{port}/",
        "template_review_url": f"http://127.0.0.1:{port}/template",
        "visual_review_url": f"http://127.0.0.1:{port}/review",
        "health_url": f"http://127.0.0.1:{port}/health",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "project_dir": str(root),
    }
    atomic_json_write(server_meta_path, server_meta)

    print(f"[server] Project: {root}")
    print(f"[server] Session: {ReviewHandler.session_id}", flush=True)
    print(f"[server] ═══════════════════════════════════════════════", flush=True)
    print(f"[server] Phase 0 — 模板提取审阅: http://127.0.0.1:{port}/template", flush=True)
    print(f"[server] Phase 1 — 版式方向审阅: http://127.0.0.1:{port}/", flush=True)
    print(f"[server] Phase 4 — 视觉审阅:     http://127.0.0.1:{port}/review", flush=True)
    print(f"[server] ═══════════════════════════════════════════════", flush=True)
    print(f"[server] Health: http://127.0.0.1:{port}/health", flush=True)
    print(f"[server] 请使用以上 URL 提交反馈，不要直接打开 file:// HTML。", flush=True)
    print(f"[server] Ctrl+C to stop", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[server] Stopped.", flush=True)
    finally:
        server.server_close()
        current = {}
        if server_meta_path.exists():
            try:
                current = json.loads(server_meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                current = {}
        if current.get("session_id") == ReviewHandler.session_id:
            server_meta_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
