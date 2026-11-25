import { INK } from "./lineStyles";

/** ISO 5456-2 projection method symbol (truncated cone, small end on the left).
 *  First angle: side view (circles) to the RIGHT of the cone; third angle: to the LEFT.
 *  Drawn in a 26 x 10 mm box with its top-left at (x, y). */
export function ProjectionSymbol({
  x,
  y,
  method,
  thin,
  thick,
}: {
  x: number;
  y: number;
  method: "first_angle" | "third_angle";
  thin: number;
  thick: number;
}) {
  const h = 10; // large diameter
  const small = 5;
  const coneLen = 10;
  const gap = 4;
  const cy = y + h / 2;
  const coneX = method === "first_angle" ? x : x + h + gap;
  const circX = method === "first_angle" ? x + coneLen + gap + h / 2 : x + h / 2;
  const trap = [
    [coneX, cy - small / 2],
    [coneX + coneLen, cy - h / 2],
    [coneX + coneLen, cy + h / 2],
    [coneX, cy + small / 2],
  ]
    .map(([px, py]) => `${px},${py}`)
    .join(" ");
  return (
    <g fill="none" stroke={INK}>
      <polygon points={trap} strokeWidth={thick} />
      <circle cx={circX} cy={cy} r={h / 2} strokeWidth={thick} />
      <circle cx={circX} cy={cy} r={small / 2} strokeWidth={thick} />
      <g strokeWidth={thin} strokeDasharray="3 0.8 0.6 0.8">
        <line x1={x - 1} y1={cy} x2={x + coneLen + gap + h + 1} y2={cy} />
        <line x1={circX} y1={cy - h / 2 - 1} x2={circX} y2={cy + h / 2 + 1} />
      </g>
    </g>
  );
}
