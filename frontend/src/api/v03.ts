// Типы API v0.3 — зеркало docs/api/v0.3/GoGlobe_openapi_v0.3.json (только то, что нужно Trip/тарифам/сохранению).
// Не смешивать с api/types.ts (редакция v0: Offer, /api/search). Менять только вместе с OpenAPI (отдельный PR с контрактом).
export interface Money { amount_minor: number; currency: string }
export interface Travelers { adults: number; children_ages: number[] }
export interface Schedule { start_date: string | null; end_date: string | null; timezone: string | null }
export type SourceKind = "provider" | "catalog" | "estimate_method";
export interface Source { source_id: string; name: string; url: string | null; checked_at: string; kind: SourceKind }
export interface Warning { code: string; message: string; trip_id: string | null }
export interface ApiErrorBody { code: string; message: string; retryable: boolean; details: unknown[] }

export type PriceStatus = "unknown" | "estimated" | "quoted";
export type PriceBasis = "trip_total" | "party_stay_total" | "party_return_total" | "room_night" | "person_total";
export type Part = "hotels" | "flights" | "activities" | "transfers";
export interface Price {
  status: PriceStatus; money: Money | null; basis: PriceBasis; coverage: Part[]; exclusions: Part[];
  source_ids: string[]; checked_at: string | null; valid_until: string | null; stale: boolean; note: string | null;
}

export type ComponentState = "not_requested" | "blocked" | "queued" | "processing" | "ready" | "empty" | "failed";
export interface Component { state: ComponentState; missing_fields: string[]; error: ApiErrorBody | null; incomplete: boolean }
export interface Components { itinerary: Component; hotels: Component; flights: Component }

export interface Place {
  place_id: string; name: string; latitude: number | null; longitude: number | null; timezone: string | null;
  verification: "verified" | "unknown"; source_ids: string[];
}
export type ItemKind = "activity" | "arrival" | "departure" | "hotel" | "meal" | "transfer";
export type Verification = "suggested" | "verified" | "unknown";
export interface Item {
  item_id: string; order: number; title: string; kind: ItemKind; local_time: string | null; place: Place | null;
  verification: Verification; source_ids: string[];
}
export interface Day { day_index: number; date: string | null; items: Item[] }
export interface Itinerary { days: Day[] }

export type DataMode = "live" | "demo";
export interface Trip {
  trip_id: string; revision: number; title: string; description: string;
  destination: { name: string; timezone: string | null; photos: string[] };
  duration_days: number | null; schedule: Schedule; origin: string | null; travelers: Travelers | null;
  itinerary: Itinerary | null; components: Components; price_summary: Price; booking_status: "not_booked";
  sources: Source[]; saved_at: string | null; favorite_at: string | null; data_mode: DataMode;
  created_at: string; updated_at: string; expires_at: string | null;
}
export interface TripFlags { trip_id: string; revision: number; saved_at: string | null; favorite_at: string | null; expires_at: string | null }
export interface TripCard {
  trip_id: string; revision: number; title: string; destination_name: string; cover_url: string | null;
  duration_days: number | null; start_date: string | null; end_date: string | null; price_summary: Price;
  saved_at: string | null; favorite_at: string | null; expires_at: string | null;
}
export interface TripList { items: TripCard[]; next_cursor: string | null; sources: Source[] }

export interface Airport { code: string; timezone: string }
export interface Segment { origin: Airport; destination: Airport; departure_at: string; arrival_at: string; duration_minutes: number }
export type Availability = "available" | "unknown";
export interface HotelOffer {
  offer_id: string; name: string; photos: string[]; place: Place | null; stars: number | null; rating: number | null;
  check_in: string; check_out: string; total_price: Price; nightly_price: Price; booking_url: string | null;
  availability: Availability; source_ids: string[];
}
export interface FlightOffer {
  offer_id: string; outbound_segments: Segment[]; inbound_segments: Segment[]; total_price: Price;
  booking_url: string | null; availability: Availability; source_ids: string[];
}
interface OfferList<T, C> {
  trip_id: string; trip_revision: number; state: ComponentState; missing_fields: string[]; items: T[]; sources: Source[];
  warnings: Warning[]; error: ApiErrorBody | null; data_mode: DataMode; context: C | null; incomplete: boolean;
}
export type HotelList = OfferList<HotelOffer, { travelers: Travelers; stay: { check_in: string; check_out: string } }>;
export type FlightList = OfferList<FlightOffer, { travelers: Travelers; origin: string; flight_dates: { outbound_date: string; return_date: string } }>;

export interface ScheduleRequest { expected_revision: number; start_date: string; end_date: string; timezone: string }
export interface QuoteRequest {
  expected_revision: number; components: ("hotels" | "flights")[]; origin?: string; travelers?: Travelers;
  stay?: { check_in: string; check_out: string }; flight_dates?: { outbound_date: string; return_date: string };
}
export interface Accepted { search_id: string; trip_id: string; state: "queued" | "processing"; revision: number; expires_at: string }
