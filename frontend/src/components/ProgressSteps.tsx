// Экран ожидания: показываем процесс анализа. Владелец: Frontend №1.
import type { SearchEvent } from "../api/types";

export default function ProgressSteps({ events }: { events: SearchEvent[] }) {
  return (
    <div className="card" aria-live="polite">
      <strong>GoGlobe ищет подходящие варианты…</strong>
      <ul>
        {events.map((e, i) => (
          <li key={i} className={i === events.length - 1 ? "" : "muted"}>{e.message}</li>
        ))}
        {events.length === 0 && <li className="muted">Отправляю запрос…</li>}
      </ul>
    </div>
  );
}
