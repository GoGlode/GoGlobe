import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { FavoritesProvider } from "./state/FavoritesContext";
import PhoneFrame, { shouldUsePhoneFrame } from "./ui/PhoneFrame";
import { SearchProvider } from "./state/SearchContext";
import "./design/global.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {shouldUsePhoneFrame() ? <PhoneFrame /> : (
      <BrowserRouter>
        <SearchProvider>
          <FavoritesProvider>
            <App />
          </FavoritesProvider>
        </SearchProvider>
      </BrowserRouter>
    )}
  </React.StrictMode>,
);
