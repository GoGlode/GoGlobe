// Транспорт API v0.3 для поездок: Trip, тарифы, сохранение, избранное, расписание. Владелец: Frontend №2.
// С VITE_API_URL — настоящие запросы (cookie-сессия). Без него — ЯВНЫЙ демо-режим на фикстурах из docs/api/v0.3 (в памяти вкладки,
// на сервер ничего не уходит; страницы показывают плашку «демо»). При ошибке настоящего API демо-данные НЕ подставляются.
import examples from "./fixtures/examples.json";
import type {
  Accepted, ApiErrorBody, FlightList, HotelList, QuoteRequest, ScheduleRequest, Trip, TripCard, TripFlags, TripList,
} from "./v03";

const BASE = import.meta.env.VITE_API_URL as string | undefined;
// Демо разрешено в dev или при явном VITE_DEMO_MODE=true. Прод без VITE_API_URL — ошибка конфигурации, а не «красивые» фальшивые данные.
const DEMO_OK = !import.meta.env.PROD || import.meta.env.VITE_DEMO_MODE === "true";
export const isDemoApi = !BASE && DEMO_OK;
export const isLive = !!BASE;
export const CONFIG_ERROR = !BASE && !DEMO_OK ? "Не задан VITE_API_URL: приложение не знает адрес backend. Задайте его в настройках деплоя (или VITE_DEMO_MODE=true для демо)." : null;

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public retryable = false) { super(message); }
  get isNotFound() { return this.status === 404 || this.status === 410; }
  get isExpired() { return this.status === 410 || /EXPIRED/i.test(this.code); }
  get isConflict() { return this.status === 409; }
}

// ---------- настоящий транспорт ----------
let session: Promise<void> | null = null;
export const resetSession = () => { session = null; };
const ensureSession = () => (session ??= fetch(`${BASE}/api/v1/session`, {
  method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: "{}",
}).then((r) => { if (!r.ok) throw new ApiError(r.status, "SESSION", "Не удалось начать сессию", true); }).catch((e) => { session = null; throw e; }));

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
/** Безопасные запросы (GET) повторяются при обрыве сети и 502–504; изменяющие — никогда (кроме явного повтора с тем же Idempotency-Key). */
export async function apiCall<T>(method: string, path: string, body?: unknown, headers: Record<string, string> = {}, signal?: AbortSignal): Promise<T> {
  if (CONFIG_ERROR) throw new ApiError(0, "CONFIG", CONFIG_ERROR);
  for (let i = 0; ; i++) {
    try { return await call<T>(method, path, body, headers, false, signal); }
    catch (e) {
      const retryable = method === "GET" && e instanceof ApiError && (e.status === 0 || (e.status >= 502 && e.status <= 504)) && e.code !== "ABORTED";
      if (!retryable || i >= 2 || signal?.aborted) throw e;
      await sleep(400 * (i + 1));
    }
  }
}

async function call<T>(method: string, path: string, body?: unknown, headers: Record<string, string> = {}, retried = false, signal?: AbortSignal): Promise<T> {
  await ensureSession();
  let r: Response;
  try {
    r = await fetch(`${BASE}/api/v1${path}`, {
      method, credentials: "include",
      headers: { ...(body !== undefined ? { "Content-Type": "application/json" } : {}), ...headers },
      body: body === undefined ? undefined : JSON.stringify(body), signal,
    });
  } catch (e) {
    if (signal?.aborted) throw new ApiError(0, "ABORTED", "Запрос отменён");
    throw new ApiError(0, "NETWORK", "Нет связи с сервером", true);
  }
  if (r.status === 403 && !retried) { session = null; return call(method, path, body, headers, true, signal); } // сессия истекла — один раз пересоздаём
  if (r.status === 204) return undefined as T;
  let json: unknown = null;
  try { json = await r.json(); } catch { /* невалидный JSON — ниже */ }
  if (!r.ok) {
    const e = (json as { error?: ApiErrorBody } | null)?.error;
    throw new ApiError(r.status, e?.code ?? `HTTP_${r.status}`, e?.message ?? `Ошибка сервера (${r.status})`, e?.retryable ?? r.status >= 500);
  }
  if (json === null || typeof json !== "object") throw new ApiError(r.status, "BAD_JSON", "Сервер вернул некорректный ответ", true);
  return json as T;
}

// ---------- демо-режим (фикстуры) ----------
const fx = <T,>(name: string): T => structuredClone((examples as Record<string, { value: unknown }>)[name].value) as T;
const wait = () => new Promise((r) => setTimeout(r, 250));
const demoQuery = (k: string) => new URLSearchParams(window.location.search).get(k);
const iso = (d: Date) => d.toISOString();
const day = (s: string) => Date.parse(`${s}T00:00:00Z`);

/** Живая копия фикстуры: сроки сдвинуты относительно «сейчас», чтобы демо-поездка не выглядела просроченной. */
function demoTrip(): Trip {
  const t = fx<Trip>("trip_relative");
  t.expires_at = iso(new Date(Date.now() + 7 * 864e5));
  return t;
}
const demo = { trip: null as Trip | null, revision: 0 };
const store = (): Trip => (demo.trip ??= demoTrip());
function demoCard(t: Trip): TripCard {
  return {
    trip_id: t.trip_id, revision: t.revision, title: t.title, destination_name: t.destination.name, cover_url: t.destination.photos[0] ?? null,
    duration_days: t.duration_days, start_date: t.schedule.start_date, end_date: t.schedule.end_date, price_summary: t.price_summary,
    saved_at: t.saved_at, favorite_at: t.favorite_at, expires_at: t.expires_at,
  };
}
const flags = (t: Trip): TripFlags => ({ trip_id: t.trip_id, revision: t.revision, saved_at: t.saved_at, favorite_at: t.favorite_at, expires_at: t.expires_at });
const notFound = () => new ApiError(404, "TRIP_NOT_FOUND", "Поездка не найдена");

/** `?mock=notfound|expired|error` — проверка состояний; `?hotels=` и `?flights=` — offers|blocked|empty|failed|partial. */
async function demoCall<T>(method: string, fullPath: string, body?: unknown): Promise<T> {
  await wait();
  const path = fullPath.split("?")[0];
  const mock = demoQuery("mock");
  const m = path.match(/^\/trips\/([^/]+)(?:\/(\w[\w-]*))?/);
  const id = m?.[1];
  if (path.startsWith("/trips/") && id !== store().trip_id) throw notFound();
  if (mock === "notfound" && method === "GET" && !m?.[2]) throw notFound();
  if (mock === "expired" && method === "GET" && !m?.[2]) throw new ApiError(410, "TRIP_EXPIRED", "Срок хранения поездки истёк");
  if (mock === "error" && method === "GET") throw new ApiError(500, "INTERNAL", "Сервер временно недоступен", true);
  const t = store();
  if (method === "GET" && path === "/trips") return { items: t.saved_at ? [demoCard(t)] : [], next_cursor: null, sources: [] } as T;
  if (method === "GET" && path === "/favorites") return { items: t.favorite_at ? [demoCard(t)] : [], next_cursor: null, sources: [] } as T;
  if (method === "GET" && !m?.[2]) return t as T;
  if (method === "GET" && (m?.[2] === "hotels" || m?.[2] === "flights")) {
    const kind = m[2] === "hotels" ? "hotel" : "flight", variant = demoQuery(m[2]) ?? (t.components[m[2]].state === "ready" ? "offers" : "blocked");
    const list = fx<HotelList & FlightList>(`${kind}_${variant}`);
    list.trip_revision = t.revision;
    return list as T;
  }
  if (method === "PUT" && m?.[2] === "saved") { t.saved_at ??= iso(new Date()); return flags(t) as T; }
  if (method === "DELETE" && m?.[2] === "saved") { t.saved_at = null; t.favorite_at = null; return undefined as T; }
  if (method === "PUT" && path.startsWith("/favorites/")) { t.saved_at ??= iso(new Date()); t.favorite_at ??= iso(new Date()); return flags(t) as T; }
  if (method === "DELETE" && path.startsWith("/favorites/")) { t.favorite_at = null; return undefined as T; }
  if (method === "PUT" && m?.[2] === "schedule") {
    const b = body as ScheduleRequest;
    if (b.expected_revision !== t.revision || demoQuery("mock") === "conflict") throw new ApiError(409, "REVISION_CONFLICT", "Поездка изменилась. Получите актуальную версию.");
    const n = t.itinerary?.days.length ?? t.duration_days ?? 0;
    if (n && Math.round((day(b.end_date) - day(b.start_date)) / 864e5) + 1 !== n) throw new ApiError(422, "SCHEDULE_DURATION", `Нужно ровно ${n} дн. по программе`);
    t.schedule = { start_date: b.start_date, end_date: b.end_date, timezone: b.timezone };
    t.itinerary?.days.forEach((d) => { d.date = iso(new Date(day(b.start_date) + (d.day_index - 1) * 864e5)).slice(0, 10); });
    t.revision += 1;
    return t as T;
  }
  if (method === "POST" && m?.[2] === "quote-searches") {
    const b = body as QuoteRequest;
    if (b.expected_revision !== t.revision) throw new ApiError(409, "REVISION_CONFLICT", "Поездка изменилась. Получите актуальную версию.");
    return fx<Accepted>("quote_accepted") as T;
  }
  throw new ApiError(501, "DEMO_NOT_IMPLEMENTED", "В демо-режиме не поддерживается");
}

const go = <T,>(method: string, path: string, body?: unknown, headers?: Record<string, string>) =>
  isDemoApi ? demoCall<T>(method, path, body) : apiCall<T>(method, path, body, headers);

// ---------- методы ----------
const enc = encodeURIComponent;
export const getTrip = (id: string) => go<Trip>("GET", `/trips/${enc(id)}`);
export const getHotels = (id: string) => go<HotelList>("GET", `/trips/${enc(id)}/hotels`);
export const getFlights = (id: string) => go<FlightList>("GET", `/trips/${enc(id)}/flights`);
export const saveTrip = (id: string) => go<TripFlags>("PUT", `/trips/${enc(id)}/saved`, {});
export const unsaveTrip = (id: string) => go<void>("DELETE", `/trips/${enc(id)}/saved`);
export const addFavorite = (id: string) => go<TripFlags>("PUT", `/favorites/${enc(id)}`, {});
export const removeFavorite = (id: string) => go<void>("DELETE", `/favorites/${enc(id)}`);
export const setSchedule = (id: string, b: ScheduleRequest) => go<Trip>("PUT", `/trips/${enc(id)}/schedule`, b);
const asList = (l: TripList): TripList => {
  if (!l || !Array.isArray(l.items)) throw new ApiError(0, "BAD_JSON", "Сервер вернул некорректный список", true);
  return l;
};
export const listSaved = () => go<TripList>("GET", "/trips?saved=true&limit=50").then(asList);
export const listFavorites = () => go<TripList>("GET", "/favorites?limit=50").then(asList);
export const startQuoteSearch = (id: string, b: QuoteRequest) =>
  go<Accepted>("POST", `/trips/${enc(id)}/quote-searches`, b, { "Idempotency-Key": crypto.randomUUID() });
