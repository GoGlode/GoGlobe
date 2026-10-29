import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { FavoritesProvider } from "./state/FavoritesContext";
import { HistoryProvider } from "./state/HistoryContext";
import { ProfileProvider } from "./state/ProfileContext";
import PhoneFrame, { shouldUsePhoneFrame } from "./ui/PhoneFrame";
import { ThemeProvider } from "./state/ThemeContext";
import { SearchProvider } from "./state/SearchContext";
import "./design/global.css";
import "./ui/liquid.css"; // стеклянные кнопки — после всех стилей экранов
import "./ui/unify.css"; // единый стиль по образцу главной — после liquid
import "./design/dark.css"; // тёмная тема — последней, перекрывает светлые цвета

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {shouldUsePhoneFrame() ? <PhoneFrame /> : (
      <BrowserRouter>
        <HistoryProvider>
          <SearchProvider>
            <FavoritesProvider>
              <ProfileProvider>
                <ThemeProvider>
                  <App />
                </ThemeProvider>
              </ProfileProvider>
            </FavoritesProvider>
          </SearchProvider>
        </HistoryProvider>
      </BrowserRouter>
    )}
  </React.StrictMode>,
);
