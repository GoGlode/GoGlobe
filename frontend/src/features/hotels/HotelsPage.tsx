// Отели: все варианты по городам, фильтры. Вкладка нижнего меню.
import { useMemo, useState } from "react";
import { TRIPS } from "../../data/trips";
import type { Hotel } from "../../data/types";
import { useFavorites } from "../../state/FavoritesContext";
import { useSearch } from "../../state/SearchContext";
import { HotelCard } from "../trip/tabs/HotelsTab";
import "../trip/trip.css";

const FILTERS = [{ id: "all", label: "Все" }, { id: "boutique", label: "Бутик-отели" }, { id: "stars45", label: "4★ и 5★" }, { id: "view", label: "С видом" }] as const;

export default function HotelsPage() {
  const { has, toggle } = useFavorites();
  const { trips: found } = useSearch();
  const hotels = useMemo(() => {
    const seen = new Map<string, Hotel>();
    for (const t of [...TRIPS, ...found]) for (const h of t.hotels) if (!seen.has(h.id)) seen.set(h.id, h);
    return [...seen.values()];
  }, [found]);
  const cities = useMemo(() => [...new Set(hotels.map((h) => h.city))], [hotels]);
  const [city, setCity] = useState<string>("all");
  const [f, setF] = useState<(typeof FILTERS)[number]["id"]>("all");
  const list = hotels.filter((h) => (city === "all" || h.city === city) && (f === "all" || h.tags.includes(f)));
  return (
    <>
      <div className="scroll-x" style={{ padding: "18px var(--s-4) 10px" }}>
        {["all", ...cities].map((c) => <button key={c} className={`chip ${city === c ? "chip--active" : ""}`} onClick={() => setCity(c)}>{c === "all" ? "Все города" : c}</button>)}
      </div>
      <div className="scroll-x" style={{ padding: "0 var(--s-4) 12px" }}>
        {FILTERS.map((x) => <button key={x.id} className={`chip ${f === x.id ? "chip--active" : ""}`} onClick={() => setF(x.id)}>{x.label}</button>)}
      </div>
      {list.length === 0 && <p className="muted" style={{ textAlign: "center", padding: 32 }}>Нет отелей по выбранным фильтрам</p>}
      {list.map((h) => <HotelCard key={h.id} h={h} fav={has(h.id)} onFav={() => toggle(h.id)} />)}
    </>
  );
}
