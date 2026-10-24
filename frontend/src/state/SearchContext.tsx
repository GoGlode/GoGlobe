// Состояние поиска: запрос → параметры → ход выполнения → результаты. Общий для Home / Progress / Results / History.
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { searchTrips } from "../data/api";
import type { SearchStatus } from "../api/types";
import type { SearchParamsUI, Trip } from "../data/types";
import { useHistory } from "./HistoryContext";

type Phase = "idle" | "loading" | "done" | "error";
interface Ctx {
  query: string; params: SearchParamsUI; phase: Phase; step: number; trips: Trip[];
  /** Статус ответа (docs/api-contract.md): от него зависит, что рисует экран результатов */
  status: SearchStatus; clarifyingQuestion?: string; warnings: string[];
  setQuery: (q: string) => void; setParams: (p: SearchParamsUI) => void;
  /** Запуск поиска; с аргументом — по переданному запросу/параметрам (повтор из истории). */
  run: (input?: { query: string; params: SearchParamsUI }) => Promise<void>;
  /** Показать уже полученные результаты без нового поиска (открыть из истории). */
  restore: (query: string, params: SearchParamsUI, trips: Trip[]) => void;
}
const C = createContext<Ctx>(null!);
export const useSearch = () => useContext(C);

export function SearchProvider({ children }: { children: ReactNode }) {
  const { record } = useHistory();
  const [query, setQuery] = useState("");
  const [params, setParams] = useState<SearchParamsUI>({});
  const [phase, setPhase] = useState<Phase>("idle");
  const [step, setStep] = useState(0);
  const [trips, setTrips] = useState<Trip[]>([]);
  const [meta, setMeta] = useState<{ status: SearchStatus; clarifyingQuestion?: string; warnings: string[] }>({ status: "ok", warnings: [] });

  const run = useCallback(async (input?: { query: string; params: SearchParamsUI }) => {
    const q = input?.query ?? query, p = input?.params ?? params;
    if (input) { setQuery(q); setParams(p); }
    setPhase("loading"); setStep(0);
    try {
      const r = await searchTrips(q, p, setStep, new URLSearchParams(window.location.search).get("status"));
      if (r.status === "error") throw new Error("search error");
      setTrips(r.trips); setMeta({ status: r.status, clarifyingQuestion: r.clarifyingQuestion, warnings: r.warnings }); setPhase("done");
      record({ query: q, params: p, image: r.trips[0]?.hero, resultTripIds: r.trips.map((t) => t.id) });
    } catch { setPhase("error"); }
  }, [query, params, record]);

  const restore = useCallback((q: string, p: SearchParamsUI, t: Trip[]) => {
    setQuery(q); setParams(p); setTrips(t); setMeta({ status: "ok", warnings: [] }); setStep(0); setPhase("done");
  }, []);

  const v = useMemo(() => ({ query, params, phase, step, trips, ...meta, setQuery, setParams, run, restore }),
    [query, params, phase, step, trips, meta, run, restore]);
  return <C.Provider value={v}>{children}</C.Provider>;
}
