// /results: пока идёт поиск — экран прогресса (Frontend №1), потом — карусель вариантов (Frontend №2).
import { Navigate } from "react-router-dom";
import { useSearch } from "../../state/SearchContext";
import ProgressView from "./ProgressView";
import ResultsPage from "./ResultsPage";

export default function ResultsRoute() {
  const { phase } = useSearch();
  if (phase === "idle") return <Navigate to="/" replace />;
  return phase === "loading" ? <ProgressView /> : <ResultsPage />;
}
