#!/usr/bin/env python3
"""Browser regression for the two full-deck human review surfaces."""

import base64
import atexit
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright


def assert_viewport(page, label):
    metrics = page.evaluate("""() => ({
      viewportW: innerWidth, viewportH: innerHeight,
      rootW: document.documentElement.scrollWidth,
      rootH: document.documentElement.scrollHeight,
      bodyW: document.body.scrollWidth,
      bodyH: document.body.scrollHeight
    })""")
    assert metrics["rootW"] <= metrics["viewportW"], (label, metrics)
    assert metrics["rootH"] <= metrics["viewportH"], (label, metrics)


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
    project = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else None
    uploads = project / "_internal" / "01_layout_plan" / "uploads" if project else None
    before_uploads = set(uploads.rglob("*")) if uploads and uploads.exists() else set()

    def cleanup_test_uploads():
        if not uploads or not uploads.exists():
            return
        for path in sorted(set(uploads.rglob("*")) - before_uploads, reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    pass

    atexit.register(cleanup_test_uploads)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})

        page.goto(base + "/", wait_until="networkidle")
        assert page.locator(".nav-item.reviewed").count() == 0
        assert page.get_by_role("button", name="提交本轮审阅", exact=True).count() == 1
        before = page.locator(".page-card.active .asset-tab").count()
        with tempfile.TemporaryDirectory() as tmp:
            upload = Path(tmp) / "sample.png"
            upload.write_bytes(base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            ))
            page.locator(".page-card.active [data-new-slot-upload]").set_input_files(str(upload))
            page.wait_for_timeout(500)
        assert page.locator(".page-card.active .asset-tab").count() == before + 1
        assert page.locator(".page-card.active .asset-new-note").count() == 1
        assert page.locator(".page-card.active .asset-next-round:visible").count() == 1
        page.locator(".page-card.active [data-new-slot-drop]").evaluate("""zone => {
          const raw = atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=');
          const bytes = Uint8Array.from(raw, c => c.charCodeAt(0));
          const transfer = new DataTransfer();
          transfer.items.add(new File([bytes], 'dragged.png', {type:'image/png'}));
          for (const type of ['dragenter','dragover','drop']) {
            zone.dispatchEvent(new DragEvent(type, {bubbles:true, cancelable:true, dataTransfer:transfer}));
          }
        }""")
        page.wait_for_timeout(500)
        assert page.locator(".page-card.active .asset-tab").count() == before + 2
        page.get_by_role("button", name="提交本轮审阅", exact=True).click()
        assert page.locator("#reviewSubmitSheet.open").count() == 1
        assert page.locator("#reviewSubmitSheet #globalFeedback").count() == 1
        assert page.locator("text=批准未处理页并提交").count() == 1
        assert_viewport(page, "layout")

        page.goto(base + "/review", wait_until="networkidle")
        assert page.locator(".nav-item.reviewed").count() == 0
        assert page.locator(".nav-item.pass").count() == 0
        assert page.get_by_role("button", name="提交本轮审阅", exact=True).count() == 1
        page.get_by_role("button", name="批准当前页").click()
        assert page.locator(".nav-item.reviewed").count() == 1
        page.get_by_role("button", name="提交本轮审阅", exact=True).click()
        assert page.locator("#reviewSubmitSheet.open").count() == 1
        assert page.locator("#reviewSubmitSheet #globalFeedback").count() == 1
        assert page.locator("text=批准未处理页并提交").count() == 1
        assert_viewport(page, "visual")
        browser.close()
    print("review UI regression: PASS")


if __name__ == "__main__":
    main()
