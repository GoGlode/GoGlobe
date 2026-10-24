// Результаты поиска: «Я подобрал N вариантов», карусель карточек, ✕ / ♥. Владелец: Frontend №2.
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { money, plural } from "../../data/format";
import type { Trip } from "../../data/types";
import { useFavorites } from "../../state/FavoritesContext";
import { useSearch } from "../../state/SearchContext";
import { BookButton, SourceLine } from "../trip/OfferInfo";
import { Icon, Photo } from "../../ui";
import { ClarifyView, EmptyView, ErrorView, WarningsBanner } from "./StatusViews";
import "./results.css";

const DOT = 9, PITCH = 17, MAX_BLOB = 62; // точка 9px + зазор 8px; предельная длина капли
const LEAD = { k: 520, c: 30 }, TRAIL = { k: 60, c: 8.5 };

export default function ResultsPage() {
  const { trips, query, params, phase, status, clarifyingQuestion, warnings, run } = useSearch();
  const { has, toggle } = useFavorites();
  const nav = useNavigate();
  const rail = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);

  // Капля-индикатор: два её края идут на пружинах разной жёсткости за положением прокрутки — капля вытягивается и собирается
  const blob = useRef<HTMLSpanElement>(null);
  const phys = useRef({ target: 0, l: 0, r: DOT, vl: 0, vr: 0, raf: 0 });
  const runBlob = () => {
    const P = phys.current;
    if (P.raf) return;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = Math.min(0.032, (now - last) / 1000); last = now;
      const tl = P.target * PITCH, tr = tl + DOT;
      const rightLeads = (tl + tr) / 2 >= (P.l + P.r) / 2;
      const sl = rightLeads ? TRAIL : LEAD, sr = rightLeads ? LEAD : TRAIL;
      P.vl += (sl.k * (tl - P.l) - sl.c * P.vl) * dt; P.l += P.vl * dt;
      P.vr += (sr.k * (tr - P.r) - sr.c * P.vr) * dt; P.r += P.vr * dt;
      if (P.r - P.l > MAX_BLOB) { if (rightLeads) P.l = P.r - MAX_BLOB; else P.r = P.l + MAX_BLOB; }
      const w = Math.max(DOT * 0.7, P.r - P.l);
      const el = blob.current;
      if (el) { el.style.translate = `${P.l}px -50%`; el.style.width = `${w}px`; el.style.height = `${DOT / (1 + Math.max(0, w / DOT - 1) * 0.08)}px`; }
      const calm = Math.abs(tl - P.l) < 0.05 && Math.abs(tr - P.r) < 0.05 && Math.abs(P.vl) < 0.05 && Math.abs(P.vr) < 0.05;
      if (calm) { P.l = tl; P.r = tr; P.vl = P.vr = 0; P.raf = 0; if (el) { el.style.translate = `${tl}px -50%`; el.style.width = `${DOT}px`; el.style.height = `${DOT}px`; } return; }
      P.raf = requestAnimationFrame(tick);
    };
    P.raf = requestAnimationFrame(tick);
  };
  useEffect(() => () => cancelAnimationFrame(phys.current.raf), []);

  useEffect(() => {
    const el = rail.current; if (!el) return;
    const on = () => {
      const card = el.children[0] as HTMLElement | undefined; if (!card) return;
      const p = el.scrollLeft / (card.offsetWidth + 12);
      setActive(Math.round(p));
      phys.current.target = Math.min(Math.max(p, 0), Math.max(0, trips.length - 1));
      runBlob();
    };
    el.addEventListener("scroll", on, { passive: true });
    return () => el.removeEventListener("scroll", on);
  }, [trips.length]);

  const go = (i: number) => { const el = rail.current; const c = el?.children[i] as HTMLElement | undefined; if (el && c) el.scrollTo({ left: i * (c.offsetWidth + 12), behavior: "smooth" }); };

  if (phase === "error") return <ErrorView onRetry={() => void run()} />;
  if (status === "needs_clarification") return <ClarifyView question={clarifyingQuestion} query={query} onAnswer={(q) => void run({ query: q, params })} />;
  if (!trips.length) return <EmptyView />;

  const chips = [{ icon: "calendar", t: params.dates ?? "Любые даты" }, { icon: "users", t: params.travelers ?? "1–2 человека" }, { icon: "tag", t: params.budget ?? "Любой бюджет" }] as const;
  const cur = trips[Math.min(active, trips.length - 1)];

  return (
    <div className="res">
      <header className="res__top">
        <Link to="/" aria-label="GoGlobe — на главную"><img src="/assets/brand/logo-goglobe.png" alt="GoGlobe" height={30} style={{ height: 30, width: "auto" }} /></Link>
        <Link to="/" className="circle-btn" aria-label="Изменить запрос"><Icon name="filter" size={20} /></Link>
      </header>

      <div className="res__query glass">
        <span className="res__spark"><Icon name="sparkle" size={20} /></span>
        <p>{query || "Куда поехать на 7 дней в мае? Пляжи, красивая природа, бюджет до $1500 на двоих"}</p>
        <Link to="/" className="res__send" aria-label="Уточнить"><Icon name="arrow-up" size={20} stroke={2.4} /></Link>
      </div>
      <div className="scroll-x res__chips">
        {chips.map((c) => <span key={c.t} className="chip"><Icon name={c.icon} size={16} />{c.t}</span>)}
      </div>

      {status === "partial" && <WarningsBanner warnings={warnings} />}

      <div className="res__bubble fade-up">
        <span className="res__avatar"><Icon name="sparkle" size={18} /></span>
        <p className="glass">Я проанализировал ваши предпочтения и подобрал {trips.length} {plural(trips.length, "вариант", "варианта", "вариантов")} путешествий, которые идеально вам подходят.</p>
      </div>

      <div className="res__rail scroll-x" ref={rail}>
        {trips.map((t, i) => <TripCard key={t.id} trip={t} index={i} total={trips.length} fav={has(t.id)} onFav={() => toggle(t.id)} onOpen={() => nav(`/trip/${t.id}`)} />)}
      </div>

      <div className="res__controls">
        <button className="res__round" aria-label="Пропустить" onClick={() => go(Math.min(active + 1, trips.length - 1))}><Icon name="x" size={26} /></button>
        <div className="res__dots" role="tablist"><span ref={blob} className="res__blob" aria-hidden="true" />{trips.map((t, i) => <button key={t.id} role="tab" aria-selected={i === active} aria-label={`Вариант ${i + 1}`} onClick={() => go(i)} />)}</div>
        <button className={`res__round res__round--heart ${has(cur.id) ? "is-on" : ""}`} aria-label="В избранное" onClick={() => toggle(cur.id)}><Icon name="heart" size={26} filled={has(cur.id)} /></button>
      </div>
      <p className="res__demo muted">Демо-данные: цены и фото ориентировочные</p>
    </div>
  );
}

function TripCard({ trip: t, index, total, fav, onFav, onOpen }: { trip: Trip; index: number; total: number; fav: boolean; onFav: () => void; onOpen: () => void }) {
  return (
    <article className="tcard">
      <div className="tcard__img" onClick={onOpen} role="link" aria-label={t.title}>
        <Photo src={t.hero} pos={t.heroPos} alt={t.title} />
        <span className="tcard__count">{index + 1} / {total}</span>
        <button className={`tcard__heart ${fav ? "is-on" : ""}`} aria-label="В избранное" onClick={(e) => { e.stopPropagation(); onFav(); }}><Icon name="heart" size={22} filled={fav} /></button>
      </div>
      <div className="tcard__body">
        <div onClick={onOpen} role="link" style={{ cursor: "pointer" }}>
          <h2>{t.title}</h2>
          <p className="muted tcard__sum">{t.summary}</p>
        </div>
        <div className="tcard__tags">{t.tags.map((x) => <span key={x.label} className="chip chip--tag"><Icon name={x.icon} size={16} />{x.label}</span>)}</div>
        <div className="tcard__stats">
          <div><Icon name="calendar" size={24} /><span><b>{t.days} дней</b><small>{t.dates.replace(/ \d{4}$/, "")}</small></span></div>
          <div><Icon name="users" size={24} /><span><b>{t.travelers} человека</b></span></div>
          <div><Icon name="wallet" size={24} /><span><b>{money(t.price)}</b><small>на двоих</small></span></div>
        </div>
        <div className="tcard__thumbs">{t.photos.slice(0, 4).map((p, i) => <Photo key={i} src={p.src} pos={p.pos} alt={p.label} />)}</div>
        <div className="tcard__why"><span><Icon name="sparkle" size={18} /></span><div>
          <b>Почему этот вариант</b>
          {t.explanation.why.length > 1 ? <ul className="why-list">{t.explanation.why.map((w) => <li key={w}>{w}</li>)}</ul> : <p>{t.explanation.why[0] ?? t.why}</p>}
          <SourceLine trip={t} />
        </div></div>
        <div className="tcard__book"><BookButton trip={t} compact /></div>
      </div>
    </article>
  );
}
