# SPDX-License-Identifier: Apache-2.0
"""Layer B driver: headless Edge/Chromium (Playwright) renders three.js toon objects on the GPU.

One browser page per object; `frame(state)` returns a transparent PNG that the SVG frame embeds in place of
the 2.5D body, so 2D effects, camera, subtitles and layer order are unchanged. Host config:
  MOTIONBRIEF_BROWSER_CHANNEL   e.g. msedge (installed browser) — empty = Playwright's bundled Chromium
  MOTIONBRIEF_BROWSER_ARGS      extra launch flags (space-separated), e.g. GPU/ANGLE selection
"""
from __future__ import annotations

import base64
import mimetypes
import os
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORIGIN = "http://mb-three.invalid/"
# new headless + high-performance GPU: verified to give ANGLE/D3D11 on the NVIDIA dGPU (not SwiftShader)
DEFAULT_ARGS = ["--headless=new", "--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist",
                "--force_high_performance_gpu"]


class ToonRenderer:
    def __init__(self, spec: dict, size: int = 900):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = None
        self.size = size
        # A browser launched while others start / the CPU is saturated sometimes gets no WebGL context, and a
        # page reload inside that browser does not recover it (seen in a full run): relaunch with backoff.
        for attempt in range(5):
            try:
                self._launch()
                self.page.evaluate("s => window.setup(s)", {**spec, "size": size})
                break
            except Exception:
                self._close_browser()
                if attempt == 4:
                    self._pw.stop()
                    raise
                time.sleep(1.5 * (attempt + 1))
        self.gpu = self.page.evaluate("window.gpu()")

    def _launch(self) -> None:
        args = os.environ.get("MOTIONBRIEF_BROWSER_ARGS", "").split() or DEFAULT_ARGS
        # headless=False + "--headless=new" in args: Playwright's own headless flag would select the old mode
        self._browser = self._pw.chromium.launch(channel=os.environ.get("MOTIONBRIEF_BROWSER_CHANNEL") or None,
                                                 headless="--headless=new" not in args, args=args)
        self.page = self._browser.new_page(viewport={"width": self.size, "height": self.size})
        self.page.route(f"{ORIGIN}**", self._serve)
        self.page.goto(ORIGIN + "chip.html")
        self.page.wait_for_function("window.ready === true")

    def _close_browser(self) -> None:
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None

    @staticmethod
    def _serve(route) -> None:
        rel = route.request.url[len(ORIGIN):].split("?")[0]
        p = (HERE / rel).resolve()
        if HERE not in p.parents or not p.is_file():
            route.fulfill(status=404, body="")
            return
        ctype = "text/javascript" if p.suffix in (".js", ".mjs") else mimetypes.guess_type(p.name)[0] or "text/html"
        route.fulfill(status=200, body=p.read_bytes(), headers={"Content-Type": ctype})

    def frame_uri(self, state: dict) -> str:
        """PNG data URI of the object at `state` (embedded directly into the SVG frame)."""
        return self.page.evaluate("st => window.draw(st)", state)

    def frame_png(self, state: dict) -> bytes:
        return base64.b64decode(self.frame_uri(state).split(",", 1)[1])

    def close(self) -> None:
        self._close_browser()
        self._pw.stop()

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()
