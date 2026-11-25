"""Exercise the built starter at a project subpath in Chromium."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import tempfile
import threading
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    screenshots = ROOT / "browser-checks"
    screenshots.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        shutil.copytree(ROOT / "dist", Path(temporary) / "example-tool")
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=temporary))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={"width": 1280, "height": 1000})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}/example-tool/")
                page.locator("#results .card").first.wait_for()
                assert "Report date" in page.locator("#status").inner_text()
                page.locator("#results .follow").first.click()
                page.reload()
                page.locator("#results .card").first.wait_for()
                page.locator("#saved-only").check()
                assert page.locator("#results .card").count() == 1
                page.locator("#saved-only").uncheck()
                page.locator("#topics-tab").click()
                page.locator("#search").fill("Halifax")
                assert page.locator("#results .card").count() >= 1
                assert "worldwide views" in page.locator("#results").inner_text()
                with page.expect_download() as download:
                    page.locator("#export").click()
                assert download.value.suggested_filename.endswith(".csv")
                page.locator("#search").fill('<img src=x onerror="alert(1)">')
                assert page.locator("#results img").count() == 0
                assert "No articles match" in page.locator("#results").inner_text()
                page.locator("#search").fill("")
                page.locator("#clear-saved").click()
                assert page.locator("#followed-links a").count() == 0
                page.screenshot(path=str(screenshots / "desktop.png"), full_page=True)
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.screenshot(path=str(screenshots / "mobile.png"), full_page=True)
                assert not errors, errors
                browser.close()
            print("Browser checks passed: subpath, data, modes, follows, CSV, safe text and mobile layout")
        finally:
            server.shutdown()


if __name__ == "__main__":
    main()
