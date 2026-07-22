from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright

TEMPLATES_DIR = Path(__file__).parent / "templates"

_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))


def render_html(template_name: str, context: dict) -> str:
    return _env.get_template(template_name).render(**context)


class Renderer:
    """Owns a single long-lived Chromium instance, pinned to one worker
    thread (Playwright's sync API can only be driven from the thread that
    started it, but a WSGI server may handle each request on a different
    thread). Requests submit render jobs to that thread and block for the
    result, which also serializes renders without an extra lock."""

    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._executor.submit(self._start).result()

    def _start(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch()

    def render(self, template_name: str, context: dict, width: int, height: int) -> bytes:
        return self._executor.submit(self._render, template_name, context, width, height).result()

    def _render(self, template_name: str, context: dict, width: int, height: int) -> bytes:
        html = render_html(template_name, context)
        page = self._browser.new_page(viewport={"width": width, "height": height})
        try:
            page.set_content(html, wait_until="networkidle")
            return page.screenshot()
        finally:
            page.close()

    def close(self):
        self._executor.submit(self._stop).result()
        self._executor.shutdown()

    def _stop(self):
        self._browser.close()
        self._playwright.stop()


def render_screen(template_name: str, context: dict, width: int, height: int) -> bytes:
    """One-shot render (launches and tears down its own browser). Use
    Renderer instead when serving more than one request."""
    renderer = Renderer()
    try:
        return renderer.render(template_name, context, width, height)
    finally:
        renderer.close()
