// Редактирование предпочтений путешественника (сохраняются локально, см. state/ProfileContext.tsx).
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { BUDGETS, CABIN_PREFS, DIRECTIONS, EMPTY_PREFS, PACES, STAYS, STYLES, type DirectionId, type TravelPrefs } from "../../data/preferences";
import { useProfile } from "../../state/ProfileContext";
import { Icon, PageHeader, Photo } from "../../ui";
import "./profile.css";

type Single = Exclude<keyof TravelPrefs, "directions">;
const GROUPS: { key: Single; title: string; options: readonly { id: string; label: string }[] }[] = [
  { key: "budget", title: "Бюджет", options: BUDGETS },
  { key: "style", title: "Стиль путешествия", options: STYLES },
  { key: "stay", title: "Тип проживания", options: STAYS },
  { key: "cabin", title: "Класс перелёта", options: CABIN_PREFS },
  { key: "pace", title: "Темп путешествия", options: PACES },
];

export default function PreferencesPage() {
  const { prefs, savePrefs } = useProfile();
  const nav = useNavigate();
  const [draft, setDraft] = useState<TravelPrefs>(prefs);
  const [error, setError] = useState<string | null>(null);

  const toggleDir = (id: DirectionId) => setDraft((d) => ({
    ...d, directions: d.directions.includes(id) ? d.directions.filter((x) => x !== id) : [...d.directions, id],
  }));
  const setOne = (key: Single, id: string) => setDraft((d) => ({ ...d, [key]: d[key] === id ? undefined : id }));
  const changed = JSON.stringify(draft) !== JSON.stringify(prefs);
  const save = () => {
    if (!savePrefs(draft)) return setError("Не удалось сохранить: хранилище браузера недоступно. Предпочтения не изменены.");
    nav("/profile");
  };

  return (
    <div className="prof-sub-screen">
      <PageHeader title="Мои предпочтения" onBack={() => nav("/profile")} />
      <div className="page prof-form">
        <section>
          <h2 className="prof-sub">Любимые направления <small className="muted">можно несколько</small></h2>
          <div className="prof-dir-grid">
            {DIRECTIONS.map((d) => {
              const on = draft.directions.includes(d.id);
              return (
                <button key={d.id} type="button" className={`prof-dir-tile ${on ? "is-on" : ""}`} aria-pressed={on} onClick={() => toggleDir(d.id)}>
                  <Photo src={d.img} alt="" /><span>{d.label}</span>{on && <i><Icon name="check" size={14} stroke={2.8} /></i>}
                </button>
              );
            })}
          </div>
        </section>
        {GROUPS.map((g) => (
          <section key={g.key}>
            <h2 className="prof-sub">{g.title}</h2>
            <div className="prof-chips" role="group" aria-label={g.title}>
              {g.options.map((o) => (
                <button key={o.id} type="button" className={`chip ${draft[g.key] === o.id ? "chip--active" : ""}`} aria-pressed={draft[g.key] === o.id}
                  onClick={() => setOne(g.key, o.id)}>{o.label}</button>
              ))}
            </div>
          </section>
        ))}
        {error && <p className="prof__alert" role="alert">{error}</p>}
        <div className="prof-actions">
          <button type="button" className="btn btn--ghost" onClick={() => setDraft(EMPTY_PREFS)}>Сбросить</button>
          <button type="button" className="btn" disabled={!changed} onClick={save}>Сохранить</button>
        </div>
      </div>
    </div>
  );
}
