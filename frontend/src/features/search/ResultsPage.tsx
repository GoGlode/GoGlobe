// Результаты поиска: «Я подобрал N вариантов», карусель карточек, ✕ / ♥. Владелец: Frontend №2.
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate } from "react-router-dom";
import { money, plural } from "../../data/format";
import type { Trip } from "../../data/types";
import { useFavorites } from "../../state/FavoritesContext";
import { useSearch } from "../../state/SearchContext";
import { BookButton, SourceLine } from "../trip/OfferInfo";
import { SHARE_TEXT, shareTrip } from "../../data/share";
import { Icon, PageHeader, Photo, useToast } from "../../ui";
import FilterBar from "./FilterBar";
import { NO_FILTERS, applyFilters, isFiltered, type Filters } from "./filters";
import { ClarifyView, EmptyView, ErrorView, WarningsBanner } from "./StatusViews";
import "./results.css";

/** Запускает на кнопке анимацию тапа (класс .tap снимается по окончании, поэтому каждое нажатие проигрывается заново) */
const tap = (e: { currentTarget: HTMLElement }) => { const b = e.currentTarget; b.classList.remove("tap"); void b.offsetWidth; b.classList.add("tap"); };

const DOT = 9, PITCH = 17, MAX_BLOB = 62; // точка 9px + зазор 8px; предельная длина капли
const LEAD = { k: 520, c: 30 }, TRAIL = { k: 60, c: 8.5 };

export default function ResultsPage() {
  const { trips: all, query, params, phase, status, clarifyingQuestion, warnings, run } = useSearch();
  const { has, toggle } = useFavorites();
  const nav = useNavigate();
  const rail = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [heartTap, setHeartTap] = useState(0); // счётчик нажатий ♥: меняется ключ иконки, поэтому анимация играет при каждом тапе
  const { show, toast } = useToast();
  const share = async (t: Trip) => { const m = SHARE_TEXT[await shareTrip(t)]; if (m) show(m); };
  const trips = useMemo(() => applyFilters(all, filters), [all, filters]);

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
  useEffect(() => () => { cancelAnimationFrame(phys.current.raf); phys.current.raf = 0; }, []); // raf=0, иначе после перемонтирования (StrictMode) капля считает, что анимация уже идёт
  useEffect(() => { setActive(0); phys.current.target = 0; rail.current?.scrollTo({ left: 0 }); runBlob(); }, [filters]); // другая выборка — начинаем с первой карточки

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
  if (!all.length) return <EmptyView />;

  const cur = trips[Math.min(active, trips.length - 1)]; // при пустой выборке фильтров undefined

  return (
    <div className="res">
      <PageHeader title="Варианты" onBack={() => nav(-1)} />

      {status === "partial" && <WarningsBanner warnings={warnings} />}

      <FilterBar value={filters} onChange={setFilters} shown={trips.length} total={all.length} />

      {trips.length === 0 ? (
        <p className="res__none">Под выбранные фильтры вариантов нет.<button type="button" className="btn btn--sm" onClick={() => setFilters(NO_FILTERS)}>Сбросить фильтры</button></p>
      ) : (<>
        <div className="res__rail scroll-x" ref={rail}>
          {trips.map((t, i) => <TripCard key={t.id} trip={t} index={i} total={trips.length} fav={has(t.id)} onFav={() => toggle(t.id)} onShare={() => void share(t)} onOpen={() => nav(`/trip/${t.id}`)} />)}
        </div>

        {createPortal(<div className="res__controls">
          <button className="res__round res__round--skip" aria-label="Пропустить" onAnimationEnd={(e) => e.currentTarget.classList.remove("tap")} onClick={(e) => { tap(e); go(Math.min(active + 1, trips.length - 1)); }}><Icon name="x" size={26} /></button>
          <div className="res__dots" role="tablist"><span ref={blob} className="res__blob" aria-hidden="true" />{trips.map((t, i) => <button key={t.id} role="tab" aria-selected={i === active} aria-label={`Вариант ${i + 1}`} onClick={() => go(i)} />)}</div>
          <button className={`res__round res__round--heart ${heartTap ? "tap" : ""} ${has(cur.id) ? "is-on" : ""}`} aria-label="В избранное" onAnimationEnd={(e) => { if (e.target === e.currentTarget || e.currentTarget.contains(e.target as Node)) setHeartTap(0); }} onClick={() => { setHeartTap(1); toggle(cur.id); }}><Icon name="heart" size={26} filled={has(cur.id)} /></button>
        </div>, document.querySelector(".app") ?? document.body)}
      </>)}
      {toast}
    </div>
  );
}

function TripCard({ trip: t, index, total, fav, onFav, onShare, onOpen }: { trip: Trip; index: number; total: number; fav: boolean; onFav: () => void; onShare: () => void; onOpen: () => void }) {
  return (
    <article className="tcard">
      <div className="tcard__img" onClick={onOpen} role="link" aria-label={t.title}>
        <Photo src={t.hero} pos={t.heroPos} alt={t.title} />
        <span className="tcard__count">{index + 1} / {total}</span>
        <button className="tcard__heart tcard__share" aria-label="Поделиться ссылкой" onClick={(e) => { e.stopPropagation(); onShare(); }}><Icon name="share" size={20} /></button>
        <button className={`tcard__heart ${fav ? "is-on" : ""}`} aria-label={fav ? "Убрать из избранного" : "В избранное"} onClick={(e) => { e.stopPropagation(); onFav(); }}><Icon name="heart" size={22} filled={fav} /></button>
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
