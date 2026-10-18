// Состояние поиска (запрос -> статусы -> результат). Владелец: Frontend №1.
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { search, subscribeEvents } from "../api/client";
import type { SearchEvent, SearchRequest, SearchResponse } from "../api/types";

type Phase = "idle" | "loading" | "done" | "failed";
interface Ctx {
  phase: Phase;
  events: SearchEvent[];
  result: SearchResponse | null;
  run: (req: Omit<SearchRequest, "search_id">) => Promise<void>;
}
const SearchCtx = createContext<Ctx>(null!);
export const useSearch = () => useContext(SearchCtx);

export function SearchProvider({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [events, setEvents] = useState<SearchEvent[]>([]);
  const [result, setResult] = useState<SearchResponse | null>(null);

  const run = useCallback(async (req: Omit<SearchRequest, "search_id">) => {
    const search_id = crypto.randomUUID().slice(0, 12); // клиентский id -> SSE открываем до ответа POST
    setPhase("loading"); setEvents([]); setResult(null);
    const unsub = subscribeEvents(search_id, (e) => setEvents((p) => [...p, e]));
    try {
      setResult(await search({ ...req, search_id }));
      setPhase("done");
    } catch {
      setPhase("failed");
    } finally {
      unsub();
    }
  }, []);

  return <SearchCtx.Provider value={{ phase, events, result, run }}>{children}</SearchCtx.Provider>;
}
