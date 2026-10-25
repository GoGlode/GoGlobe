// История запросов: поиск, фильтры, избранное, открыть результаты / повторить запрос. Владелец: Frontend №2.
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { HistoryEntry } from "../../data/history";
import { getTrip } from "../../data/trips";
import type { Trip } from "../../data/types";
import { useFavorites } from "../../state/FavoritesContext";
import { useHistory } from "../../state/HistoryContext";
import { useSearch } from "../../state/SearchContext";
import { Icon, Logo, Photo } from "../../ui";
import "./history.css";

type Filter = "all" | "results" | "fav";
const FILTERS: { id: Filter; label: string; icon?: "sparkle" | "heart" }[] = [
  { id: "all", label: "Все запросы" },
  { id: "results", label: "С результатами", icon: "sparkle" },
  { id: "fav", label: "Избранное", icon: "heart" },
];

const dayKey = (iso: string) => new Date(iso).toDateString();
const time = (iso: string) => new Date(iso).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
function dayLabel(iso: string): string {
  const d = new Date(iso), today = new Date(), yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return "Сегодня";
  if (d.toDateString() === yesterday.toDateString()) return "Вчера";
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "long", ...(d.getFullYear() !== today.getFullYear() && { year: "numeric" }) });
}

export default function HistoryPage() {
  const { entries, isFav, toggleFav, remove } = useHistory();
  const { run, restore, setQuery, setParams } = useSearch();
  const favorites = useFavorites();
  const nav = useNavigate();
  const [text, setText] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [oldestFirst, setOldestFirst] = useState(false);
  const [sortOpen, setSortOpen] = useState(false);

  const list = useMemo(() => {
    const q = text.trim().toLowerCase();
    const out = entries.filter((e) =>
      (!q || `${e.title} ${e.query}`.toLowerCase().includes(q))
      && (filter !== "results" || e.resultTripIds.length > 0)
      && (filter !== "fav" || isFav(e.id)));
    return oldestFirst ? [...out].reverse() : out;
  }, [entries, text, filter, isFav, oldestFirst]);

  const groups = useMemo(() => {
    const g: { label: string; items: HistoryEntry[] }[] = [];
    for (const e of list) {
      const last = g[g.length - 1];
      if (last && dayKey(last.items[0].createdAt) === dayKey(e.createdAt)) last.items.push(e);
      else g.push({ label: dayLabel(e.createdAt), items: [e] });
    }
    return g;
  }, [list]);

  const open = (e: HistoryEntry) => {
    const trips = e.resultTripIds.map(getTrip).filter(Boolean) as Trip[];
    restore(e.query, e.params, trips);
    nav("/results");
  };
  const repeat = (e: HistoryEntry) => { void run({ query: e.query, params: e.params }); nav("/results"); };
  const edit = (e: HistoryEntry) => { setQuery(e.query); setParams(e.params); nav("/"); };
  const hasDemo = list.some((e) => e.demo);

  return (
    <div className="hist">
      <header className="hist__top">
        <Link to="/" aria-label="GoGlobe — на главную"><Logo className="hist__logo" /></Link>
      </header>
      <h1 className="hist__title">История</h1>
      <p className="hist__sub muted">Твои идеи для следующих путешествий</p>

      <div className="hist__search glass">
        <Icon name="search" size={22} />
        <label className="visually-hidden" htmlFor="hist-q">Поиск по истории</label>
        <input id="hist-q" type="search" placeholder="Найти прошлый запрос…" value={text} onChange={(e) => setText(e.target.value)} />
        <button type="button" className="hist__filter-btn" aria-label="Сортировка" aria-expanded={sortOpen} onClick={() => setSortOpen(!sortOpen)}>
          <Icon name="filter" size={22} />
        </button>
      </div>
      {sortOpen && (
        <div className="hist__sort card fade-up" role="group" aria-label="Порядок">
          {[false, true].map((old) => (
            <button key={String(old)} type="button" className={`chip ${oldestFirst === old ? "chip--active" : ""}`}
              aria-pressed={oldestFirst === old} onClick={() => { setOldestFirst(old); setSortOpen(false); }}>
              {old ? "Сначала старые" : "Сначала новые"}
            </button>
          ))}
        </div>
      )}

      <div className="scroll-x hist__chips" role="group" aria-label="Фильтр">
        {FILTERS.map((f) => (
          <button key={f.id} type="button" className={`chip ${filter === f.id ? "chip--active" : ""}`} aria-pressed={filter === f.id}
            onClick={() => setFilter(f.id)}>
            {f.icon && <Icon name={f.icon} size={18} />}{f.label}
          </button>
        ))}
      </div>
      {hasDemo && <p className="hist__demo">Примеры запросов — демонстрационные данные</p>}

      {entries.length === 0 ? (
        <Empty title="История пуста" text="Здесь появятся ваши запросы после первого поиска." />
      ) : groups.length === 0 ? (
        <Empty title="Ничего не нашли" text="Попробуйте другой запрос или фильтр."
          extra={<button type="button" className="btn btn--sm btn--ghost" onClick={() => { setText(""); setFilter("all"); }}>Сбросить</button>} />
      ) : groups.map((g) => (
        <section key={g.label + g.items[0].id} className="hist__group" aria-label={g.label}>
          <h2 className="hist__day">{g.label}</h2>
          {g.items.map((e) => (
            <HistoryCard key={e.id} e={e} fav={isFav(e.id)} saved={e.resultTripIds.some(favorites.has)}
              onFav={() => toggleFav(e.id)} onOpen={() => open(e)} onRepeat={() => repeat(e)}
              onEdit={() => edit(e)} onRemove={() => remove(e.id)} />
          ))}
        </section>
      ))}
    </div>
  );
}

function HistoryCard({ e, fav, saved, onFav, onOpen, onRepeat, onEdit, onRemove }: {
  e: HistoryEntry; fav: boolean; saved: boolean;
  onFav: () => void; onOpen: () => void; onRepeat: () => void; onEdit: () => void; onRemove: () => void;
}) {
  const hasResults = e.resultTripIds.length > 0;
  const meta = [
    e.params.dates && { icon: "calendar" as const, t: e.params.dates },
    !e.params.dates && e.days && { icon: "calendar" as const, t: `${e.days} дней` },
    e.params.travelers && { icon: "users" as const, t: e.params.travelers },
    e.params.budget && { icon: "wallet" as const, t: e.params.budget },
  ].filter(Boolean) as { icon: "calendar" | "users" | "wallet"; t: string }[];

  return (
    <article className="hcard2">
      <div className="hcard2__img"><Photo src={e.image} alt="" /></div>
      <div className="hcard2__body">
        <div className="hcard2__head">
          <span className="hcard2__time"><Icon name="clock" size={16} />{time(e.createdAt)}{e.demo && <span className="hcard2__tag">Пример</span>}</span>
          <button type="button" className={`hcard2__fav ${fav ? "is-on" : ""}`} aria-pressed={fav}
            aria-label={fav ? "Убрать запрос из избранного" : "Добавить запрос в избранное"} onClick={onFav}>
            <Icon name="heart" size={22} filled={fav} />
          </button>
          <Menu title={e.title} onEdit={onEdit} onRemove={onRemove} />
        </div>
        <h3>{e.title}</h3>
        <p className="hcard2__q">{e.query}</p>
        {meta.length > 0 && <div className="hcard2__meta">{meta.map((m) => <span key={m.t}><Icon name={m.icon} size={16} />{m.t}</span>)}</div>}
        {hasResults ? (
          <span className={`hcard2__status ${saved ? "is-saved" : ""}`}>
            <Icon name={saved ? "check" : "sparkle"} size={14} stroke={saved ? 2.6 : 1.9} />{saved ? "Результаты сохранены" : "Есть результаты"}
          </span>
        ) : <span className="hcard2__status is-none">Без результатов</span>}
      </div>
      <div className="hcard2__actions">
        {hasResults && <button type="button" className="btn btn--sm" onClick={onOpen}>Открыть <Icon name="chevron" size={18} /></button>}
        <button type="button" className="btn btn--sm btn--ghost" onClick={onRepeat}><Icon name="refresh" size={18} />Повторить запрос</button>
      </div>
    </article>
  );
}

function Menu({ title, onEdit, onRemove }: { title: string; onEdit: () => void; onRemove: () => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (ev: MouseEvent | KeyboardEvent) => {
      if (ev instanceof KeyboardEvent ? ev.key === "Escape" : !ref.current?.contains(ev.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close); document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [open]);
  return (
    <div className="hmenu" ref={ref}>
      <button type="button" className="hmenu__btn" aria-label={`Действия: ${title}`} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span /><span /><span />
      </button>
      {open && (
        <div className="hmenu__list fade-up" role="menu">
          <button type="button" role="menuitem" onClick={() => { setOpen(false); onEdit(); }}><Icon name="search" size={18} />Изменить запрос</button>
          <button type="button" role="menuitem" className="is-danger" onClick={() => { setOpen(false); onRemove(); }}><Icon name="x" size={18} />Удалить из истории</button>
        </div>
      )}
    </div>
  );
}

function Empty({ title, text, extra }: { title: string; text: string; extra?: ReactNode }) {
  return (
    <div className="hist__empty">
      <div className="circle-btn" style={{ width: 64, height: 64 }}><Icon name="clock" size={28} /></div>
      <h2>{title}</h2><p className="muted">{text}</p>
      <div className="row" style={{ justifyContent: "center" }}>{extra}<Link className="btn btn--sm" to="/">Создать путешествие</Link></div>
    </div>
  );
}
