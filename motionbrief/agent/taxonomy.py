# SPDX-License-Identifier: Apache-2.0
"""Failure taxonomy for the local (weak) agent.

RETRYABLE   timeout / I/O / encoder crash           -> retry locally (bounded)
DEGRADABLE  WebGL/3D backend unavailable             -> re-plan with fallback renderer
ESCALATE    IR invalid (IRInvalid) / unknown component / fact gate / narration too long
                                                     -> hand back to the strong model
FATAL       missing dependency (ffmpeg, TTS, ...) or unclassified bug -> stop and report
"""
from __future__ import annotations

import subprocess
from enum import Enum

from motionbrief.audio.mix import NarrationTooLong
from motionbrief.ir.models import IRInvalid
from motionbrief.render.backend import BackendUnavailable, RenderFailure
from motionbrief.render.ffmpeg import FFmpegError
from motionbrief.tts.provider import TTSUnavailable


class Status(str, Enum):
    OK = "ok"
    RETRYABLE = "retryable"
    DEGRADED = "degraded"
    ESCALATE = "escalate"
    FATAL = "fatal"


class InvalidTask(ValueError):
    """Task manifest failed schema validation -> ESCALATE."""


class GateFailed(RuntimeError):
    """A deterministic quality gate failed -> ESCALATE (creative fix needed)."""


def classify(exc: BaseException) -> Status:
    if isinstance(exc, (TimeoutError, subprocess.TimeoutExpired, OSError, RenderFailure, FFmpegError,
                        BrokenPipeError)) and not isinstance(exc, (FileNotFoundError,)):
        return Status.RETRYABLE
    if isinstance(exc, BackendUnavailable):
        return Status.DEGRADED
    if isinstance(exc, (TTSUnavailable, FileNotFoundError, ModuleNotFoundError)):
        return Status.FATAL
    if isinstance(exc, (InvalidTask, GateFailed, NarrationTooLong, IRInvalid, KeyError)):
        return Status.ESCALATE
    return Status.FATAL
