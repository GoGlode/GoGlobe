// /search/:id — живой поиск v0.3: прогресс (SSE/polling) → вопрос → готовый Trip. Переживает reload (состояние берётся из GET /searches/{id}).
import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { useSearch } from "../../state/SearchContext";
import { Icon } from "../../ui";
import ProgressView from "./ProgressView";
import "./status.css";

const STEPS = ["Разбираю запрос…", "Составляю маршрут по дням…", "Ищу тарифы…", "Проверяю данные…"];
const STAGE = { parsing: 0, itinerary: 1, quotes: 2, validating: 3 } as const;

function Fail({ icon = "x", title, text, children }: { icon?: "x" | "clock" | "search"; title: string; text: string; children?: React.ReactNode }) {
  return (
    <div className="page st" role="alert">
      <div className="st__ic st__ic--err"><Icon name={icon} size={30} stroke={2.4} /></div>
      <h2>{title}</h2><p className="muted">{text}</p>{children}
      <Link to="/" className="st__link">На главную</Link>
    </div>
  );
}

export default function SearchRoute() {
  const { searchId } = useParams();
  const nav = useNavigate();
  const { search, watch, retryWatch, answer, cancel, run, query, configError } = useSearch();
  useEffect(() => { if (searchId) watch(searchId); }, [searchId, watch]);
  if (!searchId) return <Navigate to="/" replace />;
  if (configError) return <Fail title="Ошибка конфигурации" text={configError} />;
  const { snapshot: s, error, stalled } = search.searchId === searchId ? search : { snapshot: null, error: null, stalled: false };

  if (error && !s) {
    if (error.isNotFound) return <Fail icon="search" title="Поиск не найден" text="Ссылка неверна или срок хранения поиска истёк. Начните новый поиск." />;
    return <Fail title="Не удалось получить статус" text={error.status === 0 ? "Нет связи с сервером." : error.message}><button className="btn" onClick={retryWatch}><Icon name="refresh" size={20} />Повторить</button></Fail>;
  }
  if (!s) return <ProgressView steps={STEPS} step={0} />;
  if (s.state === "completed") return <Navigate to={`/trip/${s.trip_id}`} replace />;
  if (s.state === "needs_clarification" && s.clarification) return <Clarify key={s.revision} field={s.clarification.field} question={s.clarification.message} query={query} onAnswer={answer} />;
  if (s.state === "failed") return (
    <Fail title="Не удалось собрать поездку" text={s.error?.message ?? "Поиск завершился ошибкой. Запрос не потерян."}>
      {query && <button className="btn" onClick={() => void run().then((id) => id && nav(`/search/${id}`))}><Icon name="refresh" size={20} />Повторить</button>}
    </Fail>
  );
  if (s.state === "cancelled") return <Fail icon="clock" title="Поиск отменён" text="Вы можете изменить запрос и начать заново." />;

  const step = s.stage ? STAGE[s.stage] ?? 0 : s.state === "queued" ? 0 : 1;
  const note = stalled ? "Поиск идёт дольше обычного. Можно подождать или повторить." : error ? "Связь нестабильна — переподключаемся…" : undefined;
  return <>
    <ProgressView steps={STEPS} step={step} onCancel={() => void cancel()} note={note} />
    {stalled && <div className="page" style={{ textAlign: "center" }}><button className="btn btn--sm" onClick={retryWatch}>Проверить ещё раз</button></div>}
  </>;
}

const HINT = { destination: "Например: Стамбул", duration_days: "Например: 5 (число дней, от 1 до 30)", conflict: "Напишите, какой из вариантов верный" } as const;

function Clarify({ field, question, query, onAnswer }: { field: keyof typeof HINT; question: string; query: string; onAnswer: (t: string) => Promise<{ status: number; message: string } | null> }) {
  const [text, setText] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ok = text.trim().length > 0 && !busy;
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); if (!ok) return;
    setBusy(true); setErr(null);
    const r = await onAnswer(text);
    setBusy(false);
    if (r) setErr(r.status === 409 ? "Вопрос изменился — показываем актуальный." : r.status === 422 ? `Ответ не принят: ${r.message}` : r.status === 0 ? "Нет связи с сервером. Ответ не отправлен — повторите." : r.message);
  };
  return (
    <form className="page st" onSubmit={submit}>
      <div className="st__ic"><Icon name="sparkle" size={30} /></div>
      <h2>Нужно уточнить</h2>
      {query && <p className="muted st__q">«{query}»</p>}
      <p className="st__ask glass" id="clarify-q">{question}</p>
      <label className="visually-hidden" htmlFor="clarify-a">Ваш ответ</label>
      <textarea id="clarify-a" className="st__ans" rows={3} maxLength={1000} placeholder={HINT[field] ?? ""} aria-describedby="clarify-q" value={text} onChange={(e) => setText(e.target.value)} />
      {err && <p className="home__error" role="alert">{err}</p>}
      <button className="btn" disabled={!ok}>{busy ? "Отправляем…" : "Продолжить поиск"}<Icon name="arrow-right" size={20} /></button>
      <Link to="/" className="st__link">Изменить запрос целиком</Link>
    </form>
  );
}
