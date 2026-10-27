// Избранное: сохранённые поездки. Владелец: Frontend №2.
import { Link } from "react-router-dom";
import { money } from "../../data/format";
import { TRIPS } from "../../data/trips";
import { useFavorites } from "../../state/FavoritesContext";
import { useSearch } from "../../state/SearchContext";
import { Icon, PageHeader, Photo } from "../../ui";
import "./favorites.css";

export default function FavoritesPage() {
  const { ids, toggle } = useFavorites();
  const { trips: found } = useSearch(); // варианты из текущего поиска (в т.ч. из API) + демо-список
  const list = [...TRIPS, ...found.filter((f) => !TRIPS.some((t) => t.id === f.id))].filter((t) => ids.includes(t.id));
  return (
    <>
      <PageHeader large title="Избранное" />
      {list.length === 0 ? (
        <div className="page fav-empty">
          <div className="circle-btn" style={{ width: 72, height: 72 }}><Icon name="heart" size={30} /></div>
          <h2>Пока пусто</h2><p className="muted">Нажимайте ♥ на понравившихся вариантах — они появятся здесь.</p>
          <Link className="btn btn--sm" to="/">Найти путешествие</Link>
        </div>
      ) : (
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
