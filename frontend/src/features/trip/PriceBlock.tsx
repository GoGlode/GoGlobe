import type { Price } from "../../api/v03";
import { priceView } from "./priceFormat";

/** Цена с базой расчёта, охватом, свежестью и предупреждением. Нет цены — честная подпись, не прочерк «0». */
export function PriceBlock({ p, empty, compact }: { p: Price; empty?: string; compact?: boolean }) {
  const v = priceView(p);
  if (!v.amount) return <p className="muted pb pb--none">{empty ?? "Цена неизвестна"}{p.note ? ` ${p.note}` : ""}</p>;
  return (
    <div className={`pb ${compact ? "pb--c" : ""}`}>
      <b className="pb__amt">{v.amount}</b> <span className="pb__basis">{v.basis}</span>
      <small className="pb__status">{v.status}{v.checked ? ` · ${v.checked}` : ""}</small>
      {!compact && v.covers && <small>{v.covers}</small>}
      {v.excludes && <small className="muted">{v.excludes}</small>}
      {v.warn && <small className="pb__warn" role="note">{v.warn}</small>}
    </div>
  );
}
