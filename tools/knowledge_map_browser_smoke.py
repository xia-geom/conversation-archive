"""Optional real-Chromium smoke: synthetic data only; blocked non-loopback requests."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from conversation_archive.knowledge_map import demo
from conversation_archive.knowledge_server import MapHTTPServer
from conversation_archive.knowledge_store import Store, build
from conversation_archive import organization as org


def exercise(assets, output, executable=None):
    from playwright.sync_api import sync_playwright, expect
    expect.set_options(timeout=10000)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    errors, outside, checks = [], [], []
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp) / "demo"
        demo(root)
        store = Store(root / "map.sqlite3", root / "organization")
        with MapHTTPServer(store, assets) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as engine:
                    launch = {"headless": True, "args": ["--no-sandbox"]}
                    if executable:
                        launch["executable_path"] = executable
                    browser = engine.chromium.launch(**launch)
                    context = browser.new_context(viewport={"width": 1440, "height": 1050})
                    def intercept(route):
                        if not route.request.url.startswith(server.origin + "/"):
                            outside.append(route.request.url.split("?")[0]); route.abort()
                        else:
                            route.continue_()
                    context.route("**/*", intercept)
                    page = context.new_page()
                    page.on("pageerror", lambda exc: errors.append(str(exc)))
                    page.goto(server.launch_url, wait_until="networkidle")
                    expect(page.locator("#focus-title")).to_have_text("Orchard project")
                    expect(page.locator("#graph-count")).to_contain_text("connections")
                    checks.append("real_cytoscape_graph_rendered")
                    page.screenshot(path=str(output / "overview.png"), full_page=True)
                    page.locator(".navigation summary").click()
                    page.locator("#edge-list button").filter(has_text="refers to").first.click()
                    expect(page.locator("#inspector")).to_contain_text("demo-project")
                    assert "Display shortcut" in page.locator("#inspector").inner_text()
                    checks.append("edge_evidence_and_rule_scope_visible")
                    page.screenshot(path=str(output / "evidence.png"), full_page=True)
                    page.locator("#search").fill("E0004")
                    expect(page.locator("#results button")).to_have_count(1)
                    page.locator("#results button").click()
                    expect(page.locator("#focus-title")).to_contain_text("postponed")
                    page.locator("#status").select_option("all")
                    expect(page.locator("#edge-list")).to_contain_text("rejected")
                    page.locator("#status").select_option("recorded")
                    expect(page.locator("#edge-list")).not_to_contain_text("rejected")
                    checks.append("status_filter_removes_rejected_paths")
                    page.locator("#mentions").check()
                    expect(page.locator("#node-list")).to_contain_text("mention")
                    checks.append("primitive_mentions_can_be_inspected")
                    page.set_viewport_size({"width": 390, "height": 844})
                    page.wait_for_timeout(250)
                    assert page.evaluate("""() => {
                        const b = cy.elements().renderedBoundingBox();
                        return b.x1 >= 0 && b.y1 >= 0 && b.x2 <= cy.width() && b.y2 <= cy.height();
                    }""")
                    checks.append("map_refits_inside_narrow_canvas")
                    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                    page.screenshot(path=str(output / "mobile.png"), full_page=True)
                    checks.append("narrow_viewport_no_horizontal_overflow")
                    # The canonical correction writer changes a source; the open map must stop.
                    state = org.read_state(root / "organization")
                    event = {"event_id": "browser-revoke", "actor": "Synthetic reviewer", "answer": "Fixture revocation",
                             "expected_state_sha256": org.digest(state), "operations": [
                                 {"op": "revoke", "rule_id": "browser-revoke-rule", "target": "demo-project"}]}
                    org.apply(root / "organization", event)
                    page.locator("#search").fill("Rowan")
                    expect(page.locator("#notice")).to_have_class("error")
                    assert "rebuild" in page.locator("#notice").inner_text().lower()
                    checks.append("stale_source_clears_view_and_requests_rebuild")
                    browser.close()
            finally:
                server.shutdown(); thread.join(timeout=5)
        # Hostile text must remain text. Use another invented input, not a real archive.
        attack_run = Path(temp) / "hostile"
        hostile = '<img src="https://example.invalid/never-requested" onerror="window.archiveXss=true">'
        org.prepare({"version": "1.0", "entries": [{"entry_id": "E9999", "text": hostile}], "catalog": [], "proposals": []}, attack_run)
        hostile_db = Path(temp) / "hostile.sqlite3"
        build(attack_run, hostile_db)
        with MapHTTPServer(Store(hostile_db, attack_run), assets) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                with sync_playwright() as engine:
                    launch = {"headless": True, "args": ["--no-sandbox"]}
                    if executable:
                        launch["executable_path"] = executable
                    browser = engine.chromium.launch(**launch)
                    page = browser.new_page()
                    page.on("pageerror", lambda exc: errors.append(str(exc)))
                    page.route("**/*", intercept)
                    page.goto(server.launch_url, wait_until="networkidle")
                    page.locator("#results button").first.click()
                    expect(page.locator("#inspector")).to_contain_text("onerror")
                    assert page.locator("#inspector img").count() == 0
                    assert page.evaluate("window.archiveXss !== true")
                    checks.append("untrusted_html_remains_inert_text")
                    browser.close()
            finally:
                server.shutdown(); thread.join(timeout=5)
    result = {"synthetic_only": True, "checks": checks, "page_errors": errors,
              "non_loopback_requests": outside, "model_calls": 0}
    (output / "browser-report.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if errors or outside:
        raise AssertionError("Browser errors or unexpected external requests; inspect the synthetic report")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--browser")
    args = parser.parse_args()
    print(json.dumps(exercise(args.assets, args.output, args.browser), indent=2))
