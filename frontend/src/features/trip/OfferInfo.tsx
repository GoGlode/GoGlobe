// Что стоит за вариантом по контракту (Offer): плюсы/минусы, источник, уверенность, свежесть данных, бронирование.
// Нужен и карточке выдачи, и странице поездки; принцип «ИИ ничего не выдумывает» — источник и дата всегда на виду.
import { freshnessLabel } from "../../data/format";
import type { Trip } from "../../data/types";
import { Icon } from "../../ui";
import "./offer.css";

const CONF = { confirmed: "Подтверждено источником", estimated: "Оценка" } as const;
const isHttp = (u?: string) => !!u && /^https?:\/\//i.test(u); // только http(s): никаких javascript: из ответа API

/** «Подтверждено / Оценка · Источник: … · данные от …» */
export function SourceLine({ trip: t }: { trip: Trip }) {
  const e = t.explanation;
  return (
    <p className="src">
      <span className={`src__conf src__conf--${e.confidence}`}>{CONF[e.confidence]}</span>
      <span>{e.sources.length ? `Источник: ${e.sources.join(", ")}` : "Источник не указан"}</span>
      <span>{freshnessLabel(t.dataFreshness)}</span>
    </p>
  );
}

export function ProsCons({ trip: t }: { trip: Trip }) {
  const { pros, cons } = t.explanation;
  if (!pros.length && !cons.length) return null;
  return (
    <div className="pc">
      {pros.length > 0 && <section><h4>Плюсы</h4><ul>{pros.map((x) => <li key={x}><Icon name="check" size={16} stroke={2.4} />{x}</li>)}</ul></section>}
      {cons.length > 0 && <section className="pc__cons"><h4>Минусы</h4><ul>{cons.map((x) => <li key={x}><Icon name="x" size={16} stroke={2.4} />{x}</li>)}</ul></section>}
    </div>
  );
}

export const hasBooking = (t: Trip) => isHttp(t.bookingUrl);
export const bookingHint = (t: Trip) => `Ссылки на бронирование пока нет${t.demo ? " — демо-данные" : ""}`;

/** «Забронировать» по booking_url; нет ссылки (демо) — неактивная кнопка. compact (карточка) дополнительно подписывает причину. */
export function BookButton({ trip: t, compact }: { trip: Trip; compact?: boolean }) {
  const cls = `btn ${compact ? "btn--sm" : ""}`;
  if (hasBooking(t)) return <a className={cls} href={t.bookingUrl} target="_blank" rel="noopener noreferrer">Забронировать<Icon name="arrow-right" size={18} /></a>;
  return <span className="book-off"><button type="button" className={`${cls} btn--ghost`} disabled>Забронировать</button></span>;
}
