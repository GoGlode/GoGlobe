// Избранные поездки и отели (localStorage, с защитой от недоступного хранилища).
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

const KEY = "goglobe.favorites.v1";
interface Ctx { has: (id: string) => boolean; toggle: (id: string) => void; ids: string[] }
const C = createContext<Ctx>(null!);
export const useFavorites = () => useContext(C);

function load(): string[] { try { return JSON.parse(localStorage.getItem(KEY) ?? "[]"); } catch { return []; } }

export function FavoritesProvider({ children }: { children: ReactNode }) {
  const [ids, setIds] = useState<string[]>(load);
  useEffect(() => { try { localStorage.setItem(KEY, JSON.stringify(ids)); } catch { /* ignore */ } }, [ids]);
  const toggle = useCallback((id: string) => setIds((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id])), []);
  const has = useCallback((id: string) => ids.includes(id), [ids]);
  return <C.Provider value={{ has, toggle, ids }}>{children}</C.Provider>;
}
