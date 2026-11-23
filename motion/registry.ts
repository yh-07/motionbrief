// SPDX-License-Identifier: Apache-2.0
// Generators may only COMPOSE registered components; they may not invent new ones.
import registry from "./registry.json";

export type ComponentName = keyof typeof registry.components;
export const REGISTRY = registry.components;

export function isRegistered(name: string): name is ComponentName {
  return Object.prototype.hasOwnProperty.call(REGISTRY, name);
}
