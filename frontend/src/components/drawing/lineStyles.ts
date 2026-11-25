import type { PageFormat } from "../../api/types";

/** ISO 128 line groups: 0.7 for large sheets, 0.5 otherwise; thin = half. Paper mm. */
export function lineWeights(format: PageFormat) {
  const thick = format === "A1" || format === "A2" ? 0.7 : 0.5;
  return { thick, thin: thick / 2 };
}

export const HIDDEN_DASH = [3, 1.5];
export const CENTER_DASH = [12, 2, 1.5, 2];
export const CENTER_OVERSHOOT = 3; // paper mm beyond the feature

/** Dash pattern expressed in a view's model units so it measures correctly on paper. */
export const dash = (pattern: number[], scale: number) => pattern.map((p) => +(p / scale).toFixed(4)).join(" ");

export const INK = "#0b1220";
