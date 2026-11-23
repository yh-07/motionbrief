# SPDX-License-Identifier: Apache-2.0
"""Story/Director: decide durationTier FIRST, then hand off to storyboard.

Deterministic prior (explainable, testable) + optional LLM override via `deep_reasoning`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from motionbrief.llm.router import CapabilityRouter


@dataclass
class TopicBrief:
    title: str
    mechanisms: int            # number of distinct mechanisms to explain
    single_counterintuitive: bool = False
    hero: bool = False


def decide_tier(b: TopicBrief) -> str:
    """single concept -> micro; one complete problem -> core; 2-3 chained mechanisms -> deep (hero only, D7)."""
    if b.single_counterintuitive or b.mechanisms <= 1:
        return "micro"
    if b.mechanisms >= 5 and b.hero:
        return "deep"
    return "core"


def direct(b: TopicBrief, router: Optional[CapabilityRouter] = None) -> dict:
    tier = decide_tier(b)
    plan = {"title": b.title, "durationTier": tier, "beats": ["hook", "context", "reveal", "mechanism", "payoff",
                                                               "callback"]}
    if router is not None:
        res = router.chat("deep_reasoning", [
            {"role": "system", "content": "You are a director for 20-120s technical explainer shorts."},
            {"role": "user", "content": f"Propose hook + beat sheet for: {b.title}; tier={tier}. JSON only."}])
        plan["llm"] = {"provider": res.provider, "family": res.family, "raw": res.text}
    return plan
