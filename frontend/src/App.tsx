import { Link, Route, Routes } from "react-router-dom";
import HomePage from "./pages/HomePage";
import OfferPage from "./pages/OfferPage";
import ResultsPage from "./pages/ResultsPage";

export default function App() {
  return (
    <>
      <header className="container" style={{ paddingBottom: 0 }}>
        <Link to="/" style={{ textDecoration: "none", fontSize: 24, fontWeight: 800 }}>
          Go<span style={{ color: "var(--c-primary)" }}>Globe</span>
        </Link>
      </header>
      <main className="container">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/results" element={<ResultsPage />} />
          <Route path="/offers/:id" element={<OfferPage />} />
        </Routes>
      </main>
    </>
  );
}
