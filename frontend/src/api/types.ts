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
  kind: CylinderFeature["kind"];
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

export interface Part {
  part_id: string;
  name: string;
  source: "sample" | "upload";
  sample_id: string | null;
  default_material: string | null;
  geometry: PartGeometry;
  views: Record<ViewName, ViewData>;
  mesh_url: string;
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
}
