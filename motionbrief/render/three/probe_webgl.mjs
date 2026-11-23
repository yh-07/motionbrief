// SPDX-License-Identifier: Apache-2.0
// Phase 3: launch Remotion's bundled Chromium with chromiumOptions {gl: 'angle'} and try to
// create a WebGL2 context. Prints "webgl:ok" on success. Until Layer B lands, always fails
// so the pipeline degrades to the 2.5D SVG fallback (by design).
console.log("webgl:unavailable (Layer B skeleton)");
process.exit(1);
