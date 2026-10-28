// Каркас приложения: мобильная колонка + нижняя навигация. Скрытие навигации — по маршруту.
import { useEffect, useRef, type ReactNode } from "react";
import { useLocation, useNavigationType } from "react-router-dom";
import GlassNav from "./GlassNav";
import "./glassnav.css";

// Без нижней навигации: «Обзор» поездки (там hero и свой CTA), как в макетах. На результатах меню есть — чтобы удобно вернуться на главную
const NO_NAV = [/^\/trip\/[^/]+\/?$/, /^\/trip\/[^/]+\/overview\/?$/];

// Вкладки нижнего меню переключаются мягким «растворением», вглубь — сдвигом справа, назад — слева
const ROOTS = new Set(["/", "/hotels", "/trips", "/favorites", "/history", "/profile", "/flights"]);
const section = (p: string) => (p.startsWith("/trip/") ? p.split("/").slice(0, 3).join("/") : p); // вкладки внутри поездки — тот же экран

export default function AppShell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const navType = useNavigationType();
  const scroller = useRef<HTMLDivElement>(null);
  const hideNav = NO_NAV.some((r) => r.test(pathname));
  const dir = navType === "POP" ? "back" : ROOTS.has(pathname) ? "tab" : "forward";
  const sec = section(pathname);
  useEffect(() => { if (navType !== "POP") scroller.current?.scrollTo({ top: 0 }); }, [sec, navType]); // новый экран открывается сверху
  return (
    <div className={`app ${hideNav ? "app--nonav" : ""}`} data-dir={dir}>
      <div className="app__scroll" id="scroll-root" ref={scroller}>{children}</div>
      {!hideNav && <GlassNav />}
    </div>
  );
}
