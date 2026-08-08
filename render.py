from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright

import dither

TEMPLATES_DIR = Path(__file__).parent / "templates"

_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))

# Removes data-trim-overflow elements that run past the canvas edge, so widgets
# can render a variable number of items without precomputing how many fit.
_TRIM_OVERFLOW_JS = """
() => {
  document.querySelectorAll('[data-trim-overflow]').forEach(el => {
    if (el.getBoundingClientRect().bottom > window.innerHeight) el.remove();
  });
}
"""


def render_html(template_name: str, context: dict) -> str:
    return _env.get_template(template_name).render(**context)


class Renderer:
    """Long-lived Chromium instance pinned to one worker thread, since
    Playwright's sync API can't be driven from more than one thread."""

    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._executor.submit(self._start).result()

    def _start(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch()

    def render(
        self,
        template_name: str,
        context: dict,
        width: int,
        height: int,
        palette: list[tuple[int, int, int]] | None = None,
    ) -> bytes:
        return self._executor.submit(self._render, template_name, context, width, height, palette).result()

    def _render(
        self,
        template_name: str,
        context: dict,
        width: int,
        height: int,
        palette: list[tuple[int, int, int]] | None = None,
    ) -> bytes:
        html = render_html(template_name, context)
        page = self._browser.new_page(viewport={"width": width, "height": height})
        try:
            page.set_content(html, wait_until="networkidle")
            page.evaluate(_TRIM_OVERFLOW_JS)
            png = page.screenshot()
        finally:
            page.close()
        return dither.apply(png, palette) if palette else png

    def close(self):
        self._executor.submit(self._stop).result()
        self._executor.shutdown()

    def _stop(self):
        self._browser.close()
        self._playwright.stop()


def render_screen(
    template_name: str,
    context: dict,
    width: int,
    height: int,
    palette: list[tuple[int, int, int]] | None = None,
) -> bytes:
    """One-shot render (launches and tears down its own browser). Use
    Renderer instead when serving more than one request."""
    renderer = Renderer()
    try:
        return renderer.render(template_name, context, width, height, palette)
    finally:
        renderer.close()
