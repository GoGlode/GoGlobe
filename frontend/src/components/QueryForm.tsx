// Ввод запроса одним текстом. Владелец: Frontend №1. TODO: форма доп. параметров (даты, бюджет, люди).
import { useState } from "react";

const EXAMPLE =
  "Хочу на 5 дней в Турцию в ноябре, на двоих, бюджет до 120 000 рублей. Нужен хороший отель рядом с морем и прямой перелёт";

export default function QueryForm({ onSubmit, disabled }: { onSubmit: (q: string) => void; disabled?: boolean }) {
  const [q, setQ] = useState("");
  return (
    <form className="card grid" onSubmit={(e) => { e.preventDefault(); if (q.trim()) onSubmit(q.trim()); }}>
      <textarea rows={4} value={q} onChange={(e) => setQ(e.target.value)}
        placeholder="Опишите поездку обычными словами…" />
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button className="btn" disabled={disabled || !q.trim()}>Найти</button>
        <button type="button" className="btn secondary" onClick={() => setQ(EXAMPLE)}>Подставить пример</button>
      </div>
    </form>
  );
}
