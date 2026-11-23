# SPDX-License-Identifier: Apache-2.0
"""13-stage content pipeline. Phase 1: interfaces + stubs for the LLM-driven stages;
the deterministic stages are real and live in `motionbrief.agent.actions`.

  1 Topic/Script        LLM   (stub)          8 Render       code  agent.actions.render_scene
  2 Research & Facts    LLM   research.py     9 Subtitles    code  audio.mix.build_subtitles
  3 Story/Director      LLM   director.py    10 Sound design code  audio.mix.mix
  4 Storyboard          LLM   (stub)         11 QA           code  quality.gates (G1->G2->G3)
  5 Visual design       LLM   (stub)         12 Package      code  agent.actions.assemble
  6 Motion design       LLM   (stub)         13 Metrics      code  metrics.json (+manual, D6)
  7 Narration/TTS       code  tts.provider    Publish        HUMAN gate (not automated in MVP)

Rule: stages 4-6 may only emit components that exist in motion/registry.json; the
resulting Scene IR must pass `ir.models.validate` before any task is issued.
"""
from __future__ import annotations

STAGES = ["topic_script", "research", "director", "storyboard", "visual_design", "motion_design",
          "narration_tts", "render", "subtitles", "sound_design", "qa", "package", "metrics"]
LLM_STAGES = {"topic_script", "research", "director", "storyboard", "visual_design", "motion_design"}


def stage_owner(stage: str) -> str:
    return "strong_llm" if stage in LLM_STAGES else "deterministic_code+local_agent"
