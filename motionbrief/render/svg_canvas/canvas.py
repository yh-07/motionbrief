# SPDX-License-Identifier: Apache-2.0
"""Pixel canvas for one aspect ratio. Centre uses integer division so SVG text stays '540', not '540.0'."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Canvas:
    w: int
    h: int

    @property
    def cx(self) -> int:
        return self.w // 2

    @property
    def cy(self) -> int:
        return self.h // 2


_CANVASES = {"9:16": Canvas(1080, 1920), "16:9": Canvas(1920, 1080)}


def canvas_for(aspect: str) -> Canvas:
    return _CANVASES[aspect]
