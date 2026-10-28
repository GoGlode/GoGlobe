// Локальный МОК backend API v0.3 для проверки фронтенда без настоящего сервера: node scripts/mock-api-v03.mjs [порт]
// Реализует session, searches (+SSE, clarifications, cancellation), trips/{id}. Хранение в памяти. Это не backend и не продакшен.
// Сценарии по тексту запроса: «уточни» → needs_clarification; «ошибка» → failed; «разрыв» → SSE обрывается; «медленно» → 40 с.
import http from "node:http";
import { randomUUID } from "node:crypto";

const PORT = Number(process.argv[2] ?? 8000);
const searches = new Map(), keys = new Map(), log = [];
const iso = (t = Date.now()) => new Date(t).toISOString();
const day = (s) => Date.parse(`${s}T00:00:00Z`);

function snapshot(s) {
  const el = Date.now() - s.t0, slow = /медленно/i.test(s.query), k = slow ? 10 : 1;
  let state = s.state, stage = null;
  if (state === "queued") { // по времени: queued → processing(parsing/itinerary/quotes) → итог
    const stages = ["parsing", "itinerary", "quotes", "validating"];
    const i = Math.floor(el / (1200 * k));
    if (i < 1) { state = "queued"; } else if (i < 5) { state = "processing"; stage = stages[Math.min(i - 1, 3)]; }
    else if (/ошибк/i.test(s.query)) state = "failed";
    else if (/уточни/i.test(s.query) && !s.answered) state = "needs_clarification";
    else state = "completed";
    s.revision = s.base + Math.min(i, 5);
  }
  const ready = state === "completed";
  const comp = (st) => ({ state: st, missing_fields: [], error: null, incomplete: false });
  return {
    search_id: s.id, kind: "plan", trip_id: s.trip_id, trip_revision: 2, revision: s.revision, state, stage,
    result_status: ready ? "partial" : null,
    clarification: state === "needs_clarification" ? { question_id: "q_1", field: "destination", message: "Куда именно хотите поехать?" } : null,
    components: { itinerary: comp(ready ? "ready" : "processing"), hotels: comp("blocked"), flights: comp("blocked") },
    warnings: [], error: state === "failed" ? { code: "PLAN_FAILED", message: "Не удалось составить маршрут (мок).", retryable: true, details: [] } : null,
    data_mode: "demo", created_at: iso(s.t0), updated_at: iso(), expires_at: iso(s.t0 + 7 * 864e5), requested_components: ["itinerary", "hotels", "flights"],
  };
}

function trip(s) {
  const p = s.params ?? {}, n = p.duration_days ?? 5, start = p.dates?.start_date ?? null;
  const days = Array.from({ length: n }, (_, i) => ({
    day_index: i + 1, date: start ? iso(day(start) + i * 864e5).slice(0, 10) : null,
    items: [{ item_id: `i${i}`, order: 1, title: `Прогулка, день ${i + 1}`, kind: "activity", local_time: null, place: null, verification: "suggested", source_ids: [] }],
  }));
  const comp = (st, m = []) => ({ state: st, missing_fields: m, error: null, incomplete: false });
  return {
    trip_id: s.trip_id, revision: 2, title: `Поездка (${n} дн.)`, description: `Запрос: ${s.query}`, destination: { name: p.destination ?? "Стамбул", timezone: null, photos: [] },
    duration_days: n, schedule: { start_date: start, end_date: p.dates?.end_date ?? null, timezone: null }, origin: p.origin ?? null, travelers: p.travelers ?? null,
    itinerary: { days }, components: { itinerary: comp("ready"), hotels: comp("blocked", ["travelers", "stay"]), flights: comp("blocked", ["origin", "flight_dates"]) },
    price_summary: { status: "unknown", money: null, basis: "trip_total", coverage: [], exclusions: ["hotels", "flights", "activities", "transfers"], source_ids: [], checked_at: null, valid_until: null, stale: false, note: null },
    booking_status: "not_booked", sources: [], saved_at: null, favorite_at: null, data_mode: "demo", created_at: iso(s.t0), updated_at: iso(), expires_at: iso(s.t0 + 7 * 864e5),
    budget: p.budget ?? null, wishes: p.wishes ?? [],
  };
}

const err = (res, status, code, message) => send(res, status, { error: { code, message, retryable: status >= 500, details: [] }, request_id: randomUUID() });
function send(res, status, body) { res.writeHead(status, { "Content-Type": "application/json", "Cache-Control": "no-store" }); res.end(JSON.stringify(body)); }
const readBody = (req) => new Promise((r) => { let b = ""; req.on("data", (c) => (b += c)); req.on("end", () => { try { r(b ? JSON.parse(b) : {}); } catch { r(null); } }); });

http.createServer(async (req, res) => {
  const origin = req.headers.origin;
  if (origin) { res.setHeader("Access-Control-Allow-Origin", origin); res.setHeader("Access-Control-Allow-Credentials", "true"); res.setHeader("Vary", "Origin"); }
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Idempotency-Key, Accept"); res.setHeader("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS");
  if (req.method === "OPTIONS") { res.writeHead(204); return res.end(); }
  const u = new URL(req.url, "http://x"), path = u.pathname.replace(/^\/api\/v1/, ""), m = req.method;
  if (u.pathname === "/__log") return send(res, 200, log);
  const hasCookie = /gg_sid=/.test(req.headers.cookie ?? "");
  if (path === "/session" && m === "POST") { res.setHeader("Set-Cookie", "gg_sid=mock; Path=/; SameSite=Lax; HttpOnly"); return send(res, 200, { expires_at: iso(Date.now() + 864e5), recovery_enabled: false }); }
  if (!hasCookie) return err(res, 403, "NO_SESSION", "Нет сессии");

  if (path === "/searches" && m === "POST") {
    const key = req.headers["idempotency-key"]; if (!key) return err(res, 422, "IDEMPOTENCY_REQUIRED", "Нужен Idempotency-Key");
    const body = await readBody(req); log.push({ at: iso(), key, body });
    if (!body || typeof body.query !== "string" || !body.query.trim()) return err(res, 422, "VALIDATION", "query обязателен");
    if (/429/.test(body.query)) return err(res, 429, "RATE_LIMIT", "Слишком много запросов");
    if (/500/.test(body.query)) return err(res, 500, "INTERNAL", "Сбой");
    if (keys.has(key)) return send(res, 202, keys.get(key));
    const id = `s_${randomUUID().slice(0, 8)}`, s = { id, trip_id: `t_${randomUUID().slice(0, 8)}`, query: body.query, params: body.params, t0: Date.now(), state: "queued", base: 1, revision: 1 };
    searches.set(id, s);
    const acc = { search_id: id, trip_id: s.trip_id, state: "queued", revision: 1, expires_at: iso(Date.now() + 864e5) };
    keys.set(key, acc); return send(res, 202, acc);
  }
  let mm = path.match(/^\/searches\/([^/]+)(?:\/(\w+))?$/);
  if (mm) {
    const s = searches.get(mm[1]); if (!s) return err(res, 404, "SEARCH_NOT_FOUND", "Поиск не найден");
    if (!mm[2] && m === "GET") return send(res, 200, snapshot(s));
    if (mm[2] === "events" && m === "GET") {
      res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-store" });
      let last = -1, n = 0;
      const tick = () => { const sn = snapshot(s); if (sn.revision !== last) { last = sn.revision; res.write(`id: ${sn.revision}\nevent: ${sn.state === "completed" || sn.state === "failed" ? "finished" : "progress"}\ndata: ${JSON.stringify(sn)}\n\n`); n++; }
        if (["completed", "failed", "cancelled", "needs_clarification"].includes(sn.state) || (/разрыв/i.test(s.query) && n >= 2)) { clearInterval(h); res.end(); } };
      const h = setInterval(tick, 400); tick(); req.on("close", () => clearInterval(h)); return;
    }
    if (mm[2] === "clarifications" && m === "POST") {
      const b = await readBody(req); log.push({ at: iso(), clarification: b });
      if (!b?.question_id || !b.answer) return err(res, 422, "VALIDATION", "question_id и answer обязательны");
      if (b.expected_revision !== snapshot(s).revision) return err(res, 409, "REVISION_CONFLICT", "Ревизия устарела");
      s.answered = true; s.params = { ...(s.params ?? {}), destination: b.answer }; s.t0 = Date.now() - 4000; s.base = s.revision + 1;
      return send(res, 202, { search_id: s.id, trip_id: s.trip_id, state: "processing", revision: s.revision + 1, expires_at: iso(Date.now() + 864e5) });
    }
    if (mm[2] === "cancellation" && m === "PUT") { s.state = "cancelled"; s.revision += 1; return send(res, 200, snapshot(s)); }
  }
  mm = path.match(/^\/trips\/([^/]+)$/);
  if (mm && m === "GET") { const s = [...searches.values()].find((x) => x.trip_id === mm[1]); return s ? send(res, 200, trip(s)) : err(res, 404, "TRIP_NOT_FOUND", "Поездка не найдена"); }
  err(res, 404, "NOT_FOUND", "Не реализовано в моке");
}).listen(PORT, () => console.log(`mock API v0.3 on http://localhost:${PORT}`));
