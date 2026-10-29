// Состояние поиска. Владелец: Frontend №1.
// ЖИВОЙ режим (есть VITE_API_URL): POST /searches → search_id → SSE + polling → Trip. Демо-макеты сюда не попадают никогда.
// ДЕМО-режим (только dev / VITE_DEMO_MODE=true): прежний поиск на макетах data/trips.ts, везде с маркировкой.
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { answerQuestion, cancelSearch, createSearch, getSearch, newKey, streamSearch } from "../api/searches";
import { ApiError, CONFIG_ERROR, isLive } from "../api/trips";
import type { SearchStatus } from "../api/types";
import { isTerminal, type PlanRequest, type Snapshot } from "../api/v03Search";
import { searchTrips } from "../data/api";
import { toApiParams } from "../data/plan";
import type { SearchParamsUI, Trip } from "../data/types";
import { useHistory } from "./HistoryContext";

type Phase = "idle" | "loading" | "done" | "error";
export interface LiveSearch { searchId: string | null; snapshot: Snapshot | null; error: ApiError | null; stalled: boolean }
const NO_LIVE: LiveSearch = { searchId: null, snapshot: null, error: null, stalled: false };

interface Ctx {
  query: string; params: SearchParamsUI; phase: Phase; step: number; trips: Trip[];
  /** Статус демо-ответа (docs/api-contract.md): от него зависит, что рисует экран результатов демо */
  status: SearchStatus; clarifyingQuestion?: string; warnings: string[];
  setQuery: (q: string) => void; setParams: (p: SearchParamsUI) => void;
  /** Запуск поиска. Живой режим → id поиска (для /search/:id), при сбое null и `submitError`; демо → null. Повторный вызов во время отправки возвращает тот же результат. */
  run: (input?: { query: string; params: SearchParamsUI }) => Promise<string | null>;
  /** Показать уже полученные демо-результаты без нового поиска (открыть из истории). */
  restore: (query: string, params: SearchParamsUI, trips: Trip[]) => void;
  // --- живой режим ---
  live: boolean; configError: string | null; busy: boolean; submitError: ApiError | null; clearSubmitError: () => void;
  search: LiveSearch;
  /** Начать/возобновить наблюдение за поиском по id (в т.ч. после reload). Идемпотентно. */
  watch: (id: string) => void; retryWatch: () => void;
  answer: (text: string) => Promise<ApiError | null>; cancel: () => Promise<void>;
}
const C = createContext<Ctx>(null!);
export const useSearch = () => useContext(C);

const wait = (ms: number, signal: AbortSignal) => new Promise<void>((res) => { const t = setTimeout(res, ms); signal.addEventListener("abort", () => { clearTimeout(t); res(); }, { once: true }); });
const asApiError = (e: unknown) => (e instanceof ApiError ? e : new ApiError(0, "UNKNOWN", "Что-то пошло не так", true));

export function SearchProvider({ children }: { children: ReactNode }) {
  const { record } = useHistory();
  const [query, setQuery] = useState("");
  const [params, setParams] = useState<SearchParamsUI>({});
  const [phase, setPhase] = useState<Phase>("idle");
  const [step, setStep] = useState(0);
  const [trips, setTrips] = useState<Trip[]>([]);
  const [meta, setMeta] = useState<{ status: SearchStatus; clarifyingQuestion?: string; warnings: string[] }>({ status: "ok", warnings: [] });
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState<ApiError | null>(null);
  const [search, setSearch] = useState<LiveSearch>(NO_LIVE);
  const seq = useRef(0);
  const inflight = useRef<Promise<string | null> | null>(null);
  const attempt = useRef<{ sig: string; key: string } | null>(null);
  const w = useRef<{ id: string; ctl: AbortController } | null>(null);

  // ---------- наблюдение: SSE, при обрыве — GET polling с backoff ----------
  const apply = useCallback((s: Snapshot) => setSearch((cur) =>
    cur.searchId !== s.search_id || (cur.snapshot && s.revision < cur.snapshot.revision) ? cur : { ...cur, snapshot: s, error: null }), []);

  const watch = useCallback((id: string) => {
    if (w.current?.id === id && !w.current.ctl.signal.aborted) return;
    w.current?.ctl.abort();
    const ctl = new AbortController(); w.current = { id, ctl };
    const { signal } = ctl;
    setSearch({ searchId: id, snapshot: null, error: null, stalled: false });
    void (async () => {
      let snap: Snapshot | null = null, sseFails = 0, delay = 1000;
      const started = Date.now();
      const take = (s: Snapshot) => { if (!snap || s.revision >= snap.revision) { snap = s; apply(s); } };
      const done = () => snap != null && (isTerminal((snap as Snapshot).state) || (snap as Snapshot).state === "needs_clarification");
      try {
        take(await getSearch(id, signal));
        while (!signal.aborted && !done()) {
          if (sseFails < 3) { try { await streamSearch(id, take, signal); delay = 1000; } catch { if (signal.aborted) return; sseFails++; } }
          if (signal.aborted || done()) return;
          take(await getSearch(id, signal));
          if (done()) return;
          await wait(delay, signal); delay = Math.min(Math.round(delay * 1.6), 5000);
          if (Date.now() - started > 5 * 60_000) { setSearch((c) => ({ ...c, stalled: true })); return; }
        }
      } catch (e) {
        if (!signal.aborted) setSearch((c) => (c.searchId === id ? { ...c, error: asApiError(e) } : c));
      }
    })();
  }, [apply]);

  const retryWatch = useCallback(() => { const id = w.current?.id ?? search.searchId; if (!id) return; w.current?.ctl.abort(); w.current = null; watch(id); }, [watch, search.searchId]);

  const answer = useCallback(async (text: string) => {
    const s = search.snapshot, q = s?.clarification;
    if (!s || !q) return new ApiError(0, "NO_QUESTION", "Вопрос уже неактуален");
    try {
      await answerQuestion(s.search_id, { question_id: q.question_id, expected_revision: s.revision, answer: text.trim() }, newKey());
      w.current?.ctl.abort(); w.current = null; watch(s.search_id);
      return null;
    } catch (e) {
      const err = asApiError(e);
      if (err.isConflict) { w.current?.ctl.abort(); w.current = null; watch(s.search_id); } // вопрос/ревизия сменились — подтягиваем актуальное
      return err;
    }
  }, [search.snapshot, watch]);

  const cancel = useCallback(async () => {
    const id = search.searchId; if (!id) return;
    try { apply(await cancelSearch(id)); } catch (e) { setSearch((c) => ({ ...c, error: asApiError(e) })); }
  }, [search.searchId, apply]);

  // ---------- запуск ----------
  const run = useCallback((input?: { query: string; params: SearchParamsUI }): Promise<string | null> => {
    const q = input?.query ?? query, p = input?.params ?? params;
    if (input) { setQuery(q); setParams(p); }
    if ((isLive || CONFIG_ERROR) && inflight.current) return inflight.current; // двойной клик → один поиск (до смены seq!)
    const my = ++seq.current;

    if (isLive || CONFIG_ERROR) {
      setSubmitError(null); setBusy(true); setPhase("loading");
      const req: PlanRequest = { query: q.trim(), params: toApiParams(p) };
      const sig = JSON.stringify(req);
      const key = attempt.current?.sig === sig ? attempt.current.key : newKey(); // повтор после обрыва — тот же ключ идемпотентности
      attempt.current = { sig, key };
      const pr = (async () => {
        try {
          const a = await createSearch(req, key);
          attempt.current = null;
          if (my !== seq.current) return null;
          record({ query: q, params: p, resultTripIds: [a.trip_id] });
          setSearch({ searchId: a.search_id, snapshot: null, error: null, stalled: false });
          return a.search_id;
        } catch (e) {
          const err = asApiError(e);
          if (!(err.status === 0 || err.status >= 500)) attempt.current = null; // 4xx — исправлять запрос, ключ новый
          if (my === seq.current) setSubmitError(err);
          return null;
        } finally { inflight.current = null; setBusy(false); setPhase("idle"); }
      })();
      inflight.current = pr;
      return pr;
    }

    // ДЕМО: макеты + имитация шагов
    setPhase("loading"); setStep(0);
    return searchTrips(q, p, (i) => { if (my === seq.current) setStep(i); }, new URLSearchParams(window.location.search).get("status")).then((r) => {
      if (my !== seq.current) return null; // устаревший ответ предыдущего поиска
      if (r.status === "error") throw new Error("search error");
      setTrips(r.trips); setMeta({ status: r.status, clarifyingQuestion: r.clarifyingQuestion, warnings: r.warnings }); setPhase("done");
      record({ query: q, params: p, image: r.trips[0]?.hero, resultTripIds: r.trips.map((t) => t.id) });
      return null;
    }).catch(() => { if (my === seq.current) setPhase("error"); return null; });
  }, [query, params, record]);

  const restore = useCallback((q: string, p: SearchParamsUI, t: Trip[]) => {
    seq.current++;
    setQuery(q); setParams(p); setTrips(t); setMeta({ status: "ok", warnings: [] }); setStep(0); setPhase("done");
  }, []);

  const v = useMemo<Ctx>(() => ({
    query, params, phase, step, trips, ...meta, setQuery, setParams, run, restore,
    live: isLive, configError: CONFIG_ERROR, busy, submitError, clearSubmitError: () => setSubmitError(null), search, watch, retryWatch, answer, cancel,
  }), [query, params, phase, step, trips, meta, run, restore, busy, submitError, search, watch, retryWatch, answer, cancel]);
  return <C.Provider value={v}>{children}</C.Provider>;
}
