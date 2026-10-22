// Состояние поиска: запрос → параметры → ход выполнения → результаты. Общий для Home / Progress / Results.
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { searchTrips } from "../data/api";
import type { SearchParamsUI, Trip } from "../data/types";

type Phase = "idle" | "loading" | "done" | "error";
interface Ctx {
  query: string; params: SearchParamsUI; phase: Phase; step: number; trips: Trip[];
  setQuery: (q: string) => void; setParams: (p: SearchParamsUI) => void; run: () => Promise<void>;
}
const C = createContext<Ctx>(null!);
export const useSearch = () => useContext(C);

export function SearchProvider({ children }: { children: ReactNode }) {
  const [query, setQuery] = useState("");
  const [params, setParams] = useState<SearchParamsUI>({});
  const [phase, setPhase] = useState<Phase>("idle");
  const [step, setStep] = useState(0);
  const [trips, setTrips] = useState<Trip[]>([]);

  const run = useCallback(async () => {
    setPhase("loading"); setStep(0);
    try { setTrips(await searchTrips(query, params, setStep)); setPhase("done"); } catch { setPhase("error"); }
  }, [query, params]);

  const v = useMemo(() => ({ query, params, phase, step, trips, setQuery, setParams, run }), [query, params, phase, step, trips, run]);
  return <C.Provider value={v}>{children}</C.Provider>;
}
