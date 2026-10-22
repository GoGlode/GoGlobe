// Профиль (референс): гость, настройки-заглушки. Владелец: Frontend №1.
import { useNavigate } from "react-router-dom";
import { Icon, PageHeader, type IconName } from "../../ui";
import "./profile.css";

const ROWS: { icon: IconName; title: string; value: string }[] = [
  { icon: "wallet", title: "Валюта", value: "USD ($)" }, { icon: "pin", title: "Город вылета", value: "Москва" },
  { icon: "sparkle", title: "Язык", value: "Русский" }, { icon: "clock", title: "Уведомления", value: "Включены" },
];

export default function ProfilePage() {
  const nav = useNavigate();
  return (
    <>
      <PageHeader title="Профиль" onBack={() => nav("/")} />
      <div className="page prof">
        <div className="prof__me glass"><img src="/assets/brand/app-icon-light.png" alt="" width={64} height={64} /><div><b>Гость</b><small className="muted">Войти позже — пока демо</small></div></div>
        <div className="prof__list glass">
          {ROWS.map((r) => <div key={r.title} className="prof__row"><Icon name={r.icon} size={22} /><span>{r.title}</span><small className="muted">{r.value}</small></div>)}
        </div>
        <p className="muted prof__ver">GoGlobe · демо-версия</p>
      </div>
    </>
  );
}
