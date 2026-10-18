// Прогресс + результаты поиска. Прогресс — Frontend №1, карточки/фильтры/состояния — Frontend №2.
import { Link } from "react-router-dom";
import OfferCard from "../components/OfferCard";
import ProgressSteps from "../components/ProgressSteps";
import { EmptyState, ErrorState, Warnings } from "../components/States";
import { useSearch } from "../state/SearchContext";

export default function ResultsPage() {
  const { phase, events, result } = useSearch();
  if (phase === "idle") return <p>Запрос ещё не отправлен. <Link to="/">На главную</Link></p>;
  if (phase === "loading") return <ProgressSteps events={events} />;
  if (phase === "failed" || result?.status === "error") return <ErrorState />;
  if (!result) return null;
  if (result.status === "needs_clarification") {
    // TODO(frontend-1): поле ответа на уточняющий вопрос
    return <div className="card"><strong>{result.clarifying_question}</strong><p><Link to="/">Уточнить запрос</Link></p></div>;
  }
  return (
    <>
      <h2>Подборка под ваш запрос</h2>
      <Warnings items={result.warnings} />
      {result.offers.length === 0 ? <EmptyState /> : (
        // TODO(frontend-2): фильтры и сортировка
        <div className="grid cols-2">{result.offers.map((o) => <OfferCard key={o.id} offer={o} />)}</div>
      )}
    </>
  );
}
