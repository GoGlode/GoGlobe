// История запросов: собственные поиски из этого браузера + демо-примеры. Хранится в localStorage
// (с защитой от недоступного хранилища), т.к. в API-контракте v0 эндпоинта истории нет.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { demoHistory, titleFromQuery, type HistoryEntry } from "../data/history";
import type { SearchParamsUI } from "../data/types";

const KEY = "goglobe.history.v1";
const MAX_OWN = 50;

interface Stored { own: HistoryEntry[]; favs: string[]; hidden: string[] }
interface Ctx {
  entries: HistoryEntry[];
  isFav: (id: string) => boolean;
  toggleFav: (id: string) => void;
  remove: (id: string) => void;
  record: (e: { query: string; params: SearchParamsUI; image?: string; resultTripIds: string[] }) => void;
}
const C = createContext<Ctx>(null!);
export const useHistory = () => useContext(C);

function load(): Stored {
  try {
    const s = JSON.parse(localStorage.getItem(KEY) ?? "null");
    if (s && Array.isArray(s.own)) return s;
  } catch { /* ignore */ }
  return { own: [], favs: ["demo-thailand"], hidden: [] };
}

export function HistoryProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<Stored>(load);
  const [demo] = useState(demoHistory);
  useEffect(() => { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch { /* ignore */ } }, [state]);

  const entries = useMemo(
    () => [...state.own, ...demo].filter((e) => !state.hidden.includes(e.id))
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt)),
    [state, demo],
  );
  const isFav = useCallback((id: string) => state.favs.includes(id), [state.favs]);
  const toggleFav = useCallback((id: string) => setState((s) => ({
    ...s, favs: s.favs.includes(id) ? s.favs.filter((x) => x !== id) : [...s.favs, id],
  })), []);
  const remove = useCallback((id: string) => setState((s) => ({
    own: s.own.filter((e) => e.id !== id), favs: s.favs.filter((x) => x !== id), hidden: [...s.hidden, id],
  })), []);
  const record = useCallback<Ctx["record"]>(({ query, params, image, resultTripIds }) => setState((s) => {
    // Повтор запроса из истории сохраняет его название и картинку
    const prev = [...s.own, ...demoHistory()].find((e) => e.query === query);
    const entry: HistoryEntry = {
      id: `h_${Date.now().toString(36)}`, title: prev?.title ?? titleFromQuery(query), query, params, days: prev?.days,
      createdAt: new Date().toISOString(), image: prev?.image ?? image ?? "/assets/photos/hero.jpg", resultTripIds,
    };
    return { ...s, own: [entry, ...s.own].slice(0, MAX_OWN) };
  }), []);

  const v = useMemo(() => ({ entries, isFav, toggleFav, remove, record }), [entries, isFav, toggleFav, remove, record]);
  return <C.Provider value={v}>{children}</C.Provider>;
}
