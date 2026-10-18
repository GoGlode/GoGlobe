// Состояния: пусто / ошибка / уточнение / предупреждения. Владелец: Frontend №2 (тексты и вид — от дизайнера).
export const EmptyState = ({ hint }: { hint?: string }) => (
  <div className="card"><strong>Ничего не нашли</strong><p className="muted">{hint ?? "Попробуйте изменить бюджет или даты."}</p></div>
);
export const ErrorState = ({ onRetry }: { onRetry?: () => void }) => (
  <div className="card"><strong>Что-то пошло не так</strong>
    <p className="muted">Не удалось получить данные. Попробуйте ещё раз.</p>
    {onRetry && <button className="btn" onClick={onRetry}>Повторить</button>}</div>
);
export const Warnings = ({ items }: { items: string[] }) =>
  items.length ? <div className="card" style={{ borderColor: "var(--c-accent)" }}>{items.map((w) => <div key={w}>⚠ {w}</div>)}</div> : null;
