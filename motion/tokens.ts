// SPDX-License-Identifier: Apache-2.0
// Single source of truth is tokens.json (shared with the Python renderer and G1 QA).
import tokens from "./tokens.json";

export type Easing = "easeOutExpo" | "easeInCubic" | "spring" | "impactPop";
export const TOKENS = tokens;

export const ease = {
  easeOutExpo: (t: number) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t)),
  easeInCubic: (t: number) => t * t * t,
  spring: (t: number) => 1 - Math.exp(-6 * t) * Math.cos(10 * t),
  impactPop: (t: number) => {
    const [a, b, c] = tokens.impactPop;
    if (t <= 0) return a;
    if (t < 0.5) return a + (b - a) * (t / 0.5);
    if (t < 1) return b + (c - b) * ((t - 0.5) / 0.5);
    return c;
  },
};
