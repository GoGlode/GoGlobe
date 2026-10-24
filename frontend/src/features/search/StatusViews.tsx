// Состояния ответа поиска, кроме «ok» (docs/api-contract.md): уточнение, частичный результат, пусто, ошибка, плюс skeleton загрузки.
import { useState } from "react";
import { Link } from "react-router-dom";
import { Icon } from "../../ui";
import "./status.css";

/** needs_clarification: показываем вопрос бэкенда и поле для ответа; ответ дописывается к исходному запросу */
export function ClarifyView({ question, query, onAnswer }: { question?: string | null; query: string; onAnswer: (fullQuery: string) => void }) {
  const [answer, setAnswer] = useState("");
  const ok = answer.trim().length > 0;
  return (
    <form className="page st" onSubmit={(e) => { e.preventDefault(); if (ok) onAnswer(`${query.trim().replace(/[.!?]+$/, "")}. ${answer.trim()}`); }}>
      <div className="st__ic"><Icon name="sparkle" size={30} /></div>
      <h2>Нужно уточнить</h2>
      {query && <p className="muted st__q">«{query}»</p>}
      <p className="st__ask glass" id="clarify-q">{question || "Уточните, пожалуйста, детали поездки: даты, бюджет и количество путешественников."}</p>
      <label className="visually-hidden" htmlFor="clarify-a">Ваш ответ</label>
      <textarea id="clarify-a" className="st__ans" rows={3} maxLength={500} placeholder="Например: на 5 дней, с 10 ноября, на двоих" aria-describedby="clarify-q"
        value={answer} onChange={(e) => setAnswer(e.target.value)} />
      <button className="btn" disabled={!ok}>Продолжить поиск<Icon name="arrow-right" size={20} /></button>
      <Link to="/" className="st__link">Изменить запрос целиком</Link>
    </form>
  );
}

/** partial: варианты есть, но часть источников недоступна — баннер с warnings над выдачей */
export function WarningsBanner({ warnings }: { warnings: string[] }) {
  if (!warnings.length) return null;
  return (
    <div className="warn" role="status">
      <b><Icon name="clock" size={18} />Данные неполные</b>
      <ul>{warnings.map((w) => <li key={w}>{w}</li>)}</ul>
    </div>
  );
}

/** empty: честное «ничего не нашли» без выдуманных вариантов и совет, что изменить */
export function EmptyView() {
  return (
    <div className="page st">
      <div className="st__ic st__ic--soft"><Icon name="search" size={30} /></div>
      <h2>Ничего не нашли</h2>
      <p className="muted">Под ваши параметры подходящих вариантов нет. Мы не придумываем предложения, чтобы выглядеть полезнее.</p>
      <ul className="st__tips">
        <li>Увеличьте бюджет или сдвиньте даты</li>
        <li>Уберите пожелания вроде «прямой рейс» или «первая линия»</li>
        <li>Попробуйте другое направление</li>
      </ul>
      <Link className="btn" to="/">Изменить параметры</Link>
    </div>
  );
}

/** error: сбой запроса — понятный текст и повтор */
export function ErrorView({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="page st" role="alert">
      <div className="st__ic st__ic--err"><Icon name="x" size={30} stroke={2.4} /></div>
      <h2>Что-то пошло не так</h2>
      <p className="muted">Не удалось получить подборку. Ваш запрос сохранён — попробуйте ещё раз.</p>
      <button className="btn" onClick={onRetry}><Icon name="refresh" size={20} />Повторить</button>
      <Link to="/" className="st__link">На главную</Link>
    </div>
  );
}

/** Загрузка: каркас карточки с пропусками, пока варианты ещё не пришли */
export function TripSkeleton() {
  return (
    <div className="skel" aria-hidden="true">
      <div className="skel__img" /><div className="skel__line skel__line--lg" /><div className="skel__line" /><div className="skel__line skel__line--sm" />
    </div>
  );
}
