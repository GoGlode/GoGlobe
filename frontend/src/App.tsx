import { Route, Routes } from "react-router-dom";
import CreditsPage from "./features/credits/CreditsPage";
import FavoritesPage from "./features/favorites/FavoritesPage";
import HistoryPage from "./features/history/HistoryPage";
import HomePage from "./features/home/HomePage";
import ProfilePage from "./features/profile/ProfilePage";
import ResultsRoute from "./features/search/ResultsRoute";
import TripPage from "./features/trip/TripPage";
import MyTripsPage from "./features/trips/MyTripsPage";
import { AppShell } from "./ui";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/results" element={<ResultsRoute />} />
        <Route path="/trip/:id/:tab?" element={<TripPage />} />
        <Route path="/trips" element={<MyTripsPage />} />
        <Route path="/favorites" element={<FavoritesPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/credits" element={<CreditsPage />} />
        <Route path="*" element={<HomePage />} />
      </Routes>
    </AppShell>
  );
}
