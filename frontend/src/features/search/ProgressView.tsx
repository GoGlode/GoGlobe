// Экран ожидания: что ищем и на каком шаге поиск. Владелец: Frontend №1.
import { Link } from "react-router-dom";
import { SEARCH_STEPS } from "../../data/api";
import { useSearch } from "../../state/SearchContext";
import { Icon } from "../../ui";
import { TripSkeleton } from "./StatusViews";
import "./progress.css";

export default function ProgressView() {
  const { query, params, step } = useSearch();
  const chips = [params.dates, params.travelers, params.budget].filter(Boolean) as string[];
  const percent = Math.round(((step + 1) / SEARCH_STEPS.length) * 100);

  return (
    <div className="prog">
      <header className="prog__top">
        <Link to="/" aria-label="GoGlobe — на главную"><img src="/assets/brand/logo-goglobe.png" alt="GoGlobe" className="prog__logo" /></Link>
      </header>

      <div className="prog__orb" aria-hidden="true">
        <span className="prog__ring" />
        <span className="prog__core"><Icon name="sparkle" size={34} /></span>
      </div>
      <h1 className="prog__title">Подбираю путешествие</h1>
      {query && <p className="prog__query glass">«{query}»</p>}
      {chips.length > 0 && <div className="prog__chips">{chips.map((c) => <span key={c} className="chip">{c}</span>)}</div>}

      <div className="prog__bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} aria-label="Ход поиска">
        <span style={{ width: `${percent}%` }} />
      </div>
      <ol className="prog__steps card" aria-live="polite">
        {SEARCH_STEPS.map((s, i) => (
          <li key={s} className={i < step ? "is-done" : i === step ? "is-now" : ""}>
            <span className="prog__dot">{i < step ? <Icon name="check" size={14} stroke={2.6} /> : i === step ? <span className="prog__spin" /> : null}</span>
            {s.replace("…", "")}
          </li>
        ))}
      </ol>
      <TripSkeleton />
      <p className="prog__demo">Демонстрационный режим — тестовые данные</p>
    </div>
  );
}
