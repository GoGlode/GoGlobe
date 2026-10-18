// Главный экран. Владелец: Frontend №1.
import { useNavigate } from "react-router-dom";
import QueryForm from "../components/QueryForm";
import { useSearch } from "../state/SearchContext";

export default function HomePage() {
  const { run, phase } = useSearch();
  const nav = useNavigate();
  return (
    <>
      <h1>Один запрос — готовая подборка</h1>
      <p className="muted">One request. A trip that makes sense.</p>
      <QueryForm disabled={phase === "loading"} onSubmit={(query) => { void run({ query }); nav("/results"); }} />
    </>
  );
}
