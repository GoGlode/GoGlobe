// «Данные на устройстве»: что GoGlobe хранит в этом браузере, и удаление всех этих данных.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { prefCount } from "../../data/preferences";
import { useFavorites } from "../../state/FavoritesContext";
import { useHistory } from "../../state/HistoryContext";
import { useProfile } from "../../state/ProfileContext";
import { Icon, PageHeader } from "../../ui";
import "./profile.css";

const PREFIX = "goglobe.";

export default function DeviceDataPage() {
  const nav = useNavigate();
  const { profile, prefs } = useProfile();
  const { ids } = useFavorites();
  const { entries } = useHistory();
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const count = prefCount(prefs);
  const rows = [
    { icon: "user" as const, t: "Профиль", v: profile.name || profile.avatar ? "имя и фото заданы" : "не заполнен" },
    { icon: "sparkle" as const, t: "Предпочтения", v: count ? `${count} выбрано` : "не указаны" },
    { icon: "heart" as const, t: "Избранное", v: `${ids.length}` },
    { icon: "clock" as const, t: "Ваши запросы в истории", v: `${entries.filter((e) => !e.demo).length}` },
  ];

  const wipe = () => {
    try {
      Object.keys(localStorage).filter((k) => k.startsWith(PREFIX)).forEach((k) => localStorage.removeItem(k));
    } catch {
      return setError("Не удалось удалить данные: хранилище браузера недоступно.");
    }
    window.location.assign("/profile");
  };

  return (
    <div className="prof-sub-screen">
      <PageHeader title="Данные на устройстве" onBack={() => nav("/profile")} />
      <div className="page prof-form">
        <p className="muted" style={{ fontSize: 14, lineHeight: 1.45 }}>
          Аккаунтов пока нет, поэтому всё, что вы сохраняете в GoGlobe, хранится только в этом браузере и не отправляется на сервер.
        </p>
        <div className="prof-card prof-menu prof-menu--static">
          {rows.map((r) => <div key={r.t}><Icon name={r.icon} size={22} /><span>{r.t}</span><small className="muted">{r.v}</small></div>)}
        </div>
        {error && <p className="prof__alert" role="alert">{error}</p>}
        {!confirm ? (
          <button type="button" className="btn btn--ghost prof-danger" onClick={() => setConfirm(true)}><Icon name="trash" size={20} />Удалить все мои данные</button>
        ) : (
          <div className="prof-card prof-confirm" role="alertdialog" aria-label="Подтверждение удаления">
            <b>Удалить профиль, предпочтения, избранное и историю с этого устройства?</b>
            <p className="muted">Отменить это действие нельзя.</p>
            <div className="prof-actions">
              <button type="button" className="btn btn--ghost" onClick={() => setConfirm(false)}>Отмена</button>
              <button type="button" className="btn prof-danger-solid" onClick={wipe}>Удалить</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
