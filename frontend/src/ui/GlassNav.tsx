// Нижняя «стеклянная» навигация: профиль · поездки · ИИ-поиск (центр) · избранное · история.
import { NavLink, useLocation } from "react-router-dom";
import { MaskIcon } from "./Icon";

const ITEMS = [
  { to: "/profile", icon: "nav-profile", label: "Профиль" },
  { to: "/trips", icon: "nav-calendar", label: "Мои поездки" },
  { to: "/", icon: "search-sparkle-nav", label: "Поиск", center: true },
  { to: "/favorites", icon: "nav-favorites", label: "Избранное" },
  { to: "/history", icon: "nav-history", label: "История" },
];

export default function GlassNav() {
  const { pathname } = useLocation();
  return (
    <nav className="glassnav glass" aria-label="Основная навигация">
      {ITEMS.map((it) => {
        const active = it.to === "/" ? !["/profile", "/trips", "/favorites", "/history"].some((p) => pathname.startsWith(p)) : pathname.startsWith(it.to);
        return (
          <NavLink key={it.to} to={it.to} aria-label={it.label} aria-current={active ? "page" : undefined}
            className={`glassnav__item ${it.center ? "glassnav__item--center" : ""} ${active ? "is-active" : ""}`}>
            <MaskIcon src={it.icon} size={it.center ? 34 : 26} />
          </NavLink>
        );
      })}
    </nav>
  );
}
