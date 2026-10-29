// Избранное: сохранённые поездки. Владелец: Frontend №2.
import { Link } from "react-router-dom";
import { dateRange, money } from "../../data/format";
import { TRIPS } from "../../data/trips";
import { useFavorites } from "../../state/FavoritesContext";
import { useSearch } from "../../state/SearchContext";
import { ApiError, isDemoApi, listFavorites, removeFavorite } from "../../api/trips";
import { Icon, PageHeader, Photo } from "../../ui";
import { Notice } from "../trip/ApiTripPage";
import { PriceBlock } from "../trip/PriceBlock";
import { useApi } from "../trip/useApi";
import "./favorites.css";

export default function FavoritesPage() {
  const { ids, toggle } = useFavorites();
  const { trips: found } = useSearch(); // варианты из текущего поиска (в т.ч. из API) + демо-список
  const list = !isDemoApi ? [] : [...TRIPS, ...found.filter((f) => !TRIPS.some((t) => t.id === f.id))].filter((t) => ids.includes(t.id));
  const [srv, reload] = useApi(listFavorites, []);
  const cards = srv.status === "ready" ? srv.data.items : [];
  const unfav = async (id: string) => { try { await removeFavorite(id); } catch { /* список перезагрузится и покажет правду */ } reload(); };
  if (!isDemoApi && srv.status === "error") return <><PageHeader large title="Избранное" /><Notice icon="x" title="Не удалось загрузить избранное" text={srv.error instanceof ApiError ? srv.error.message : "Ошибка"}><button className="btn btn--sm" onClick={reload}>Повторить</button></Notice></>;
  return (
    <>
      <PageHeader large title="Избранное" />
      {cards.length > 0 && (
        <div className="page fav-list">
          {cards.map((c) => (
            <article className="fav" key={c.trip_id}>
              <Link to={`/trip/${c.trip_id}`} className="fav__img"><Photo src={c.cover_url ?? ""} alt={c.title} /></Link>
              <div className="fav__txt"><Link to={`/trip/${c.trip_id}`}><b>{c.title}</b></Link>
                <small className="muted">{c.start_date && c.end_date ? `${dateRange(c.start_date, c.end_date)} · ` : "даты не назначены · "}{c.duration_days ? `${c.duration_days} дн.` : ""}</small><PriceBlock p={c.price_summary} compact empty="Цена неизвестна" /></div>
              <button className="circle-btn" aria-label="Убрать из избранного" style={{ color: "var(--c-danger)" }} onClick={() => void unfav(c.trip_id)}><Icon name="heart" filled size={20} /></button>
            </article>
          ))}
        </div>
      )}
      {!isDemoApi && srv.status === "loading" && <p className="page muted" role="status">Загружаем избранное…</p>}
      {list.length === 0 && cards.length === 0 && (isDemoApi || srv.status !== "loading") ? (
        <div className="page fav-empty">
          <div className="circle-btn" style={{ width: 72, height: 72 }}><Icon name="heart" size={30} /></div>
          <h2>Пока пусто</h2><p className="muted">Нажимайте ♥ на понравившихся вариантах — они появятся здесь.</p>
          <Link className="btn btn--sm" to="/">Найти путешествие</Link>
        </div>
      ) : list.length === 0 ? null : (
        <div className="page fav-list">
          {list.map((t) => (
            <article className="fav" key={t.id}>
              <Link to={`/trip/${t.id}`} className="fav__img"><Photo src={t.hero} pos={t.heroPos} alt={t.title} /></Link>
              <div className="fav__txt"><Link to={`/trip/${t.id}`}><b>{t.title}</b></Link><small className="muted">{t.dates} · {t.days} дней</small><span className="fav__price">{money(t.price)} <small className="muted">на двоих</small></span></div>
              <button className="circle-btn" aria-label="Убрать из избранного" style={{ color: "var(--c-danger)" }} onClick={() => toggle(t.id)}><Icon name="heart" filled size={20} /></button>
            </article>
          ))}
        </div>
      )}
    </>
  );
}
