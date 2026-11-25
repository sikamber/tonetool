import type { components } from "./schema";

type Schemas = components["schemas"];

export type Piece = Schemas["Piece"];
export type Measure = Schemas["Measure"];
export type Note = Schemas["Note"];
export type Section = Schemas["Section"];
export type Track = Schemas["Track"];
export type PieceSummary = Schemas["PieceSummary"];
export type PieceEdits = Schemas["PieceEdits"];
export type TrackEdit = Schemas["TrackEdit"];
export type VoiceKind = Track["voice"];
