import { NavLink } from "react-router-dom";
import { TABS } from "./tabsList";

export default function TripTabs({ id, current }: { id: string; current: string }) {
  return (
    <div className="ttabs scroll-x" role="tablist">
      {TABS.map((t) => (
        <NavLink key={t.id} role="tab" aria-selected={t.id === current} replace to={t.id === "overview" ? `/trip/${id}` : `/trip/${id}/${t.id}`} className={`ttab ${t.id === current ? "is-on" : ""}`}>{t.label}</NavLink>
      ))}
    </div>
  );
}
