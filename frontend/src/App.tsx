import { Route, Routes } from "react-router-dom";
import CreditsPage from "./features/credits/CreditsPage";
import FavoritesPage from "./features/favorites/FavoritesPage";
import FlightsScreen from "./features/flights/FlightsScreen";
import HotelsPage from "./features/hotels/HotelsPage";
import HistoryPage from "./features/history/HistoryPage";
import HomePage from "./features/home/HomePage";
import DeviceDataPage from "./features/profile/DeviceDataPage";
import PreferencesPage from "./features/profile/PreferencesPage";
import ProfileEditPage from "./features/profile/ProfileEditPage";
import ProfilePage from "./features/profile/ProfilePage";
import ResultsRoute from "./features/search/ResultsRoute";
import SearchRoute from "./features/search/SearchRoute";
import TripPage from "./features/trip/TripPage";
import MyTripsPage from "./features/trips/MyTripsPage";
import { AppShell } from "./ui";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/results" element={<ResultsRoute />} />
        <Route path="/search/:searchId" element={<SearchRoute />} />
        <Route path="/trip/:id/:tab?" element={<TripPage />} />
        <Route path="/trips" element={<MyTripsPage />} />
        <Route path="/favorites" element={<FavoritesPage />} />
        <Route path="/hotels" element={<HotelsPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/profile/edit" element={<ProfileEditPage />} />
        <Route path="/profile/preferences" element={<PreferencesPage />} />
        <Route path="/profile/settings" element={<DeviceDataPage />} />
        <Route path="/credits" element={<CreditsPage />} />
        <Route path="/flights" element={<FlightsScreen />} />
        <Route path="*" element={<HomePage />} />
      </Routes>
    </AppShell>
  );
}
