// Mirrors backend/app/api/schemas.py + app/layout/models.py

export type Vec3 = [number, number, number];
export type Point2 = [number, number];

export type OrthoView = "front" | "top" | "bottom" | "left" | "right" | "rear";
export type ViewName = OrthoView | "isometric";
export type PageFormat = "A4" | "A3" | "A2" | "A1";
export type Orientation = "landscape" | "portrait";
export type DrawingStandard = "ISO" | "ANSI";

export interface CylinderFeature {
  id: string;
  kind: "hole" | "boss" | "concave_arc" | "convex_arc";
  radius: number;
  diameter: number;
  axis: Vec3;
  axis_aligned: "X" | "Y" | "Z" | null;
  center: Vec3;
  length: number;
  through: boolean | null;
}

export interface FeatureGroup {
  kind: CylinderFeature["kind"] | "chamfer" | "slot";
  label: string;
  count: number;
  diameter: number | null;
  radius: number | null;
  feature_ids: string[];
}

export interface PartGeometry {
  bbox_min: Vec3;
  bbox_max: Vec3;
  size: Vec3;
  volume: number;
  surface_area: number;
  center_of_mass: Vec3;
  solid_count: number;
  face_count: number;
  features: CylinderFeature[];
  feature_groups: FeatureGroup[];
}

export interface CenterMark {
  cx: number;
  cy: number;
  r: number;
  feature_ids: string[];
}

export interface Centerline {
  p0: Point2;
  p1: Point2;
  feature_ids: string[];
}

export interface ViewData {
  name: ViewName;
  is_isometric: boolean;
  bbox: [number, number, number, number];
  width: number;
  height: number;
  visible: { svg_path: string };
  hidden: { svg_path: string };
  tangent: { svg_path: string };
  tangent_hidden: { svg_path: string };
  center_marks: CenterMark[];
  centerlines: Centerline[];
}

export type UpAxis = "+Z" | "-Z" | "+Y" | "-Y" | "+X" | "-X";

export interface ModelOrientation {
  up: UpAxis;
  turn: 0 | 90 | 180 | 270;
  auto: boolean; // up axis was detected from the STEP header
  source_system: string | null; // CAD system that wrote the file
}

export interface Part {
  part_id: string;
  name: string;
  source: "sample" | "upload";
  sample_id: string | null;
  default_material: string | null;
  geometry: PartGeometry;
  views: Record<ViewName, ViewData>;
  mesh_url: string;
  orientation: ModelOrientation;
}

export interface Sample {
  id: string;
  name: string;
  description: string;
  default_material: string;
}

export interface SheetConfig {
  page_format: PageFormat;
  orientation: Orientation;
  standard: DrawingStandard;
  ortho_views: OrthoView[];
  show_isometric: boolean;
  scale: string; // "auto" | "1:2"
  section_view: OrthoView | null; // drawn as a full section (ISO 128-44)
  section_depth: number | null; // mm behind the face nearest the viewer; null = auto
}

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface ViewPlacement {
  view: ViewName;
  scale: number;
  scale_label: string;
  x_offset: number;
  y_offset: number;
  rect: Rect;
  grid_cell: [number, number] | null;
}

export interface SheetLayout {
  page_format: PageFormat;
  orientation: Orientation;
  standard: DrawingStandard;
  projection_method: "first_angle" | "third_angle";
  page_width: number;
  page_height: number;
  frame: Rect;
  title_block: Rect;
  zones: { columns: string[]; rows: string[]; col_edges: number[]; row_edges: number[] };
  view_clearance: number;
  scale: number;
  scale_label: string;
  auto_scale: boolean;
  placements: ViewPlacement[];
  fits: boolean;
  warnings: string[];
  section: SectionOverlay | null;
}

export interface OverlayText {
  x: number;
  y: number; // baseline
  text: string;
  size: number;
  anchor: "start" | "middle" | "end";
}

/** backend/app/layout/section_overlay.py: replacement view geometry (view-local) +
 *  paper-space hatching, cutting-plane line, arrows and labels. */
export interface SectionOverlay {
  view: OrthoView;
  letter: string;
  depth: number;
  depth_max: number;
  auto: boolean;
  visible_svg: string;
  tangent_svg: string;
  center_marks: CenterMark[];
  centerlines: Centerline[];
  hatch: [number, number, number, number][];
  lines: { x1: number; y1: number; x2: number; y2: number; style: "thick" | "thin" | "chain" }[];
  arrows: Point2[][];
  texts: OverlayText[];
  label: OverlayText;
}

// --- annotations (backend/app/annotation/models.py) -------------------------
export type DimensionMode = "none" | "overall" | "key" | "full";

export interface LinearDim {
  type: "linear";
  id: string;
  view: ViewName;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  orientation: "horizontal" | "vertical";
  offset_mm: number; // paper mm; horizontal + above / − below, vertical + right / − left
  offset_from: "edge" | "points";
  value_mm: number;
  prefix: "" | "Ø";
  tolerance_text: string | null;
  text_shift_mm: number;
}

export interface CircleDim {
  type: "diameter" | "radius" | "leader"; // leader: arrow on (cx, cy) itself, radius 0
  id: string;
  view: ViewName;
  cx: number;
  cy: number;
  radius: number;
  leader_angle_deg: number; // CCW from +x, y up
  leader_len_mm: number;
  inside: boolean;
  label_text: string;
  feature_ids: string[];
}

export type Dimension = LinearDim | CircleDim;

export interface AnnotationSet {
  mode: DimensionMode;
  views: OrthoView[];
  source: "deterministic" | "ai" | "ai_cached" | "precomputed";
  dimensions: Dimension[];
  notes: string[];
  fallback_reason: string | null;
  model: string | null;
  rejected: number;
}

export interface AnnotateRequest {
  mode: DimensionMode;
  ortho_views: OrthoView[];
  use_ai: boolean;
  tolerance: string;
}

/** User drag overrides, keyed by dimension id. */
export interface DimOverride {
  offset_mm?: number;
  text_shift_mm?: number;
  leader_angle_deg?: number;
  leader_len_mm?: number;
}
