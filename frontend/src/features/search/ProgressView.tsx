// Экран ожидания: понятный процесс анализа (шаги из SSE-стадий backend: parsing → flights → hotels → validating → ranking). Владелец: Frontend №1.
import { useNavigate } from "react-router-dom";
import { SEARCH_STEPS } from "../../data/api";
import { useSearch } from "../../state/SearchContext";
import { Icon } from "../../ui";
import "./progress.css";

export default function ProgressView() {
  const { step, query } = useSearch();
  const nav = useNavigate();
  return (
    <div className="prog page" role="status" aria-live="polite">
      <div className="prog__globe"><img src="/assets/brand/app-icon-light.png" alt="" width={120} height={120} /><i /></div>
      <h1>GoGlobe создаёт ваше путешествие</h1>
      <p className="prog__q muted">«{query}»</p>
      <ol className="prog__steps glass">
        {SEARCH_STEPS.map((s, i) => (
          <li key={s} className={i < step ? "done" : i === step ? "now" : ""}>
            <span className="prog__ic">{i < step ? <Icon name="check" size={16} stroke={3} /> : i === step ? <b className="prog__spin" /> : null}</span>{s}
          </li>
        ))}
      </ol>
      <button className="btn btn--ghost btn--sm" onClick={() => nav("/")}>Отменить</button>
    </div>
  );
}
