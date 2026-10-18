// API-контракт v0 — зеркало backend/app/schemas/search.py. Менять только вместе с backend (PR с меткой `contract`).
export interface Money { amount: number; currency: string }
export interface DateRange { from: string; to: string }

export interface SearchParams {
  dates?: DateRange;
  budget?: Money;
  travelers?: number;
  wishes?: string[];
}
export interface SearchRequest { query: string; params?: SearchParams; search_id?: string }

export interface ParsedQuery {
  destination?: string | null;
  dates?: DateRange | null;
  duration_days?: number | null;
  travelers?: number | null;
  budget?: Money | null;
  wishes: string[];
}

export interface Hotel {
  name: string; stars?: number | null; rating?: number | null; photos: string[];
  price?: Money | null; distance_to_sea_m?: number | null;
}
export interface Flight { direct: boolean; dates: DateRange; price?: Money | null; carrier?: string | null }
export interface Explanation {
  why: string[]; pros: string[]; cons: string[]; sources: string[];
  confidence: "confirmed" | "estimated";
}
export interface Offer {
  id: string; destination: string; hotel: Hotel; flight: Flight; total_price: Money;
  explanation: Explanation; booking_url: string; data_freshness: string; score?: number | null;
}

export type SearchStatus = "ok" | "needs_clarification" | "partial" | "empty" | "error";
export interface SearchResponse {
  search_id: string; status: SearchStatus; parsed: ParsedQuery;
  clarifying_question?: string | null; offers: Offer[]; warnings: string[];
}

export type Stage = "parsing" | "flights" | "hotels" | "validating" | "ranking" | "done" | "error";
export interface SearchEvent { stage: Stage; message: string }
