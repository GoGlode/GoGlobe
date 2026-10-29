// Тема оформления: светлая / тёмная. Хранится только в localStorage этого устройства.
// Смена темы — круговое «раскрытие» от переключателя (View Transitions API), как восход/закат; без поддержки API — плавное перекрашивание.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { flushSync } from "react-dom";

export type Theme = "light" | "dark";
export const THEME_KEY = "goglobe.theme.v1";

export function readTheme(): Theme {
  try { return localStorage.getItem(THEME_KEY) === "dark" ? "dark" : "light"; } catch { return "light"; }
}
export function applyTheme(t: Theme) {
  document.documentElement.dataset.theme = t;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", t === "dark" ? "#0a1222" : "#EAF4FF");
}
/** Тема в других окнах/iframe того же сайта (рамка телефона на компьютере) */
export function useThemeSync() {
  useEffect(() => {
    applyTheme(readTheme());
    const on = (e: StorageEvent) => { if (e.key === THEME_KEY) applyTheme(readTheme()); };
    window.addEventListener("storage", on);
    return () => window.removeEventListener("storage", on);
  }, []);
}

interface Ctx {
  theme: Theme;
  /** origin — точка на экране (центр переключателя), из которой «раскрывается» новая тема */
  setTheme: (t: Theme, origin?: { x: number; y: number }) => void;
}
const C = createContext<Ctx>(null!);
export const useTheme = () => useContext(C);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(readTheme);
  useThemeSync();
  useEffect(() => {
    const on = (e: StorageEvent) => { if (e.key === THEME_KEY) setThemeState(readTheme()); };
    window.addEventListener("storage", on);
    return () => window.removeEventListener("storage", on);
  }, []);

  const setTheme = useCallback((next: Theme, origin?: { x: number; y: number }) => {
    try { localStorage.setItem(THEME_KEY, next); } catch { /* тема сменится, но не сохранится */ }
    const root = document.documentElement;
    const change = () => { flushSync(() => setThemeState(next)); applyTheme(next); };
    const doc = document as Document & { startViewTransition?: (cb: () => void) => { ready: Promise<void> } };
    if (doc.startViewTransition && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      const x = origin?.x ?? window.innerWidth / 2, y = origin?.y ?? window.innerHeight / 2;
      const r = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
      doc.startViewTransition(change).ready.then(() => {
        root.animate({ clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${r}px at ${x}px ${y}px)`] },
          { duration: 800, easing: "cubic-bezier(.4, 0, .2, 1)", pseudoElement: "::view-transition-new(root)" });
      }).catch(() => {});
    } else {
      root.classList.add("theme-fade");
      change();
      setTimeout(() => root.classList.remove("theme-fade"), 700);
    }
  }, []);

  const v = useMemo(() => ({ theme, setTheme }), [theme, setTheme]);
  return <C.Provider value={v}>{children}</C.Provider>;
}
