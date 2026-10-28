// Каркас приложения: мобильная колонка + нижняя навигация. Скрытие навигации — по маршруту.
import type { ReactNode } from "react";
import { useLocation } from "react-router-dom";
import GlassNav from "./GlassNav";
import "./glassnav.css";

// Без нижней навигации: «Обзор» поездки (там hero и свой CTA), как в макетах. На результатах меню есть — чтобы удобно вернуться на главную
const NO_NAV = [/^\/trip\/[^/]+\/?$/, /^\/trip\/[^/]+\/overview\/?$/];

export default function AppShell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const hideNav = NO_NAV.some((r) => r.test(pathname));
  return (
    <div className={`app ${hideNav ? "app--nonav" : ""}`}>
      <div className="app__scroll" id="scroll-root">{children}</div>
      {!hideNav && <GlassNav />}
    </div>
  );
}
