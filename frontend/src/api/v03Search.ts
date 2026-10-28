// Типы поиска API v0.3 (Snapshot, Question) — зеркало docs/api/v0.3/GoGlobe_openapi_v0.3.json.
import type { Accepted, ApiErrorBody, Components, DataMode, Warning } from "./v03";

export interface Dates { start_date: string; end_date: string }
export interface TravelersP { adults: number; children_ages: number[] }
export type Wish = "near_sea" | "sea_view" | "direct_flight" | "breakfast";
export interface Params {
  destination?: string; duration_days?: number; dates?: Dates; origin?: string;
  travelers?: TravelersP; budget?: { amount_minor: number; currency: "RUB" }; wishes?: Wish[];
}
export interface PlanRequest { query: string; params?: Params }
export interface Question { question_id: string; field: "destination" | "duration_days" | "conflict"; message: string }
export type SearchState = "queued" | "processing" | "needs_clarification" | "completed" | "failed" | "cancelled";
export type SearchStage = "parsing" | "itinerary" | "quotes" | "validating";
export interface Snapshot {
  search_id: string; kind: "plan" | "quotes"; trip_id: string; trip_revision: number; revision: number; state: SearchState;
  stage: SearchStage | null; result_status: "ok" | "partial" | "empty" | null; clarification: Question | null; components: Components;
  warnings: Warning[]; error: ApiErrorBody | null; data_mode: DataMode; created_at: string; updated_at: string; expires_at: string;
  requested_components: ("itinerary" | "hotels" | "flights")[];
}
export const isTerminal = (s: SearchState) => s === "completed" || s === "failed" || s === "cancelled";
export type { Accepted };
