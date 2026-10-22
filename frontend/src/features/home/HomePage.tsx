// Главная «Куда поедем?»: hero, поле запроса, параметры, CTA, популярные направления. Владелец: Frontend №1.
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { DESTINATIONS } from "../../data/trips";
import { useFavorites } from "../../state/FavoritesContext";
import { useSearch } from "../../state/SearchContext";
import { Icon, MaskIcon } from "../../ui";
import { pushHistory } from "../history/historyStore";
import Sheet from "./Sheet";
import "./home.css";

const OPTIONS = {
  dates: ["Любые", "Май 2025", "Июнь 2025", "Июль 2025", "Сентябрь 2025"],
  travelers: ["1–2", "1 человек", "2 человека", "3–4 человека", "5 и больше"],
  budget: ["Любой", "До $1000", "До $1500", "До $2500", "От $2500"],
} as const;
const CHIPS = [
  { key: "dates", icon: "calendar", label: "Даты" },
  { key: "travelers", icon: "users", label: "Путешественники" },
  { key: "budget", icon: "wallet", label: "Бюджет" },
] as const;

export default function HomePage() {
  const { query, setQuery, params, setParams, run } = useSearch();
  const { has, toggle } = useFavorites();
  const nav = useNavigate();
  const loc = useLocation();
  const [open, setOpen] = useState<keyof typeof OPTIONS | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => { const q = (loc.state as { q?: string } | null)?.q; if (q) setQuery(q); }, [loc.state, setQuery]);

  const submit = () => {
    if (!query.trim()) { setErr(true); return; }
    pushHistory(query.trim());
    void run();
    nav("/results");
  };

  return (
    <div className="home">
      <section className="home__hero">
        <img src="/assets/images/hero-santorini.jpg" alt="" />
        <div className="home__shade" />
        <header className="home__top">
          <div><div className="home__logo">GoGlobe</div><div className="home__tag">Plan. Explore. Travel.</div></div>
          <button className="circle-btn" aria-label="Профиль" onClick={() => nav("/profile")}><MaskIcon src="nav-profile" size={22} /></button>
        </header>
        <div className="home__title">
          <h1>Куда<br />поедем?</h1>
          <p>Расскажите о своей идеальной поездке — и мы создадим для вас маршрут</p>
        </div>
      </section>

      <section className="home__panel">
        <form className={`home__search glass ${err ? "has-err" : ""}`} onSubmit={(e) => { e.preventDefault(); submit(); }}>
          <MaskIcon src="search-sparkle" size={28} className="home__sparkle" />
          <input aria-label="Опишите поездку" value={query} onChange={(e) => { setQuery(e.target.value); setErr(false); }} placeholder="Например: Италия на 7 дней, море и культура" />
        </form>
        {err && <p className="home__err">Опишите, куда и как хотите поехать</p>}

        <div className="home__chips">
          {CHIPS.map((c) => (
            <button key={c.key} type="button" className="home__chip glass" onClick={() => setOpen(c.key)}>
              <Icon name={c.icon} size={22} />
              <span><b>{c.label}</b><small>{params[c.key] ?? OPTIONS[c.key][0]}</small></span>
            </button>
          ))}
        </div>

        <button className="btn home__cta" onClick={submit}><MaskIcon src="search-sparkle-white" size={26} /> Создать путешествие <Icon name="arrow-right" size={20} /></button>

        <div className="home__head"><h2>Популярные направления</h2><button onClick={() => setQuery("Греция на 7 дней, море и культура")}>Все <Icon name="chevron" size={16} /></button></div>
        <div className="scroll-x home__dest">
          {DESTINATIONS.map((d) => (
            <article key={d.id} className="dest" onClick={() => { setQuery(`${d.name}: ${d.sub.toLowerCase()}`); setErr(false); window.scrollTo?.(0, 0); document.getElementById("scroll-root")?.scrollTo({ top: 0, behavior: "smooth" }); }}>
              <div className="dest__img"><img src={d.img} alt={d.name} loading="lazy" />
                <button className={`dest__heart ${has(`dest-${d.id}`) ? "is-on" : ""}`} aria-label="В избранное" onClick={(e) => { e.stopPropagation(); toggle(`dest-${d.id}`); }}><Icon name="heart" size={18} filled={has(`dest-${d.id}`)} /></button></div>
              <b>{d.name}</b><small className="muted">{d.sub}</small>
            </article>
          ))}
        </div>
      </section>

      {open && <Sheet title={CHIPS.find((c) => c.key === open)!.label} options={[...OPTIONS[open]]} value={params[open]} onPick={(v) => setParams({ ...params, [open]: v })} onClose={() => setOpen(null)} />}
    </div>
  );
}
