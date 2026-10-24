// Профиль: гостевой профиль этого устройства, статистика поездок, предпочтения, меню разделов. Владелец: Frontend №2.
// Авторизации и API профиля нет — персональные данные не выдумываются (см. state/ProfileContext.tsx).
import { Link } from "react-router-dom";
import { DIRECTIONS, prefSummary } from "../../data/preferences";
import { MY_TRIPS, getTrip } from "../../data/trips";
import { useProfile } from "../../state/ProfileContext";
import { Icon, Photo, type IconName } from "../../ui";
import Avatar from "./Avatar";
import "./profile.css";

const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };

/** Статистика по поездкам приложения (сейчас MY_TRIPS — демо-данные). */
function tripStats() {
  const trips = MY_TRIPS.map((m) => ({ m, t: getTrip(m.tripId) }));
  return {
    trips: trips.length,
    countries: new Set(trips.map(({ t }) => t?.country).filter(Boolean)).size,
    cities: new Set(trips.flatMap(({ t }) => t?.cities ?? [])).size,
    planned: MY_TRIPS.filter((m) => m.end >= today()).length,
  };
}

const MENU: { to: string; icon: IconName; label: string }[][] = [
  [
    { to: "/trips", icon: "suitcase", label: "Мои поездки и календарь" },
    { to: "/favorites", icon: "heart", label: "Избранное" },
    { to: "/history", icon: "clock", label: "История запросов" },
    { to: "/flights", icon: "plane", label: "Перелёты" },
  ],
  [
    { to: "/profile/settings", icon: "settings", label: "Данные на устройстве" },
    { to: "/credits", icon: "view", label: "Фото и лицензии" },
  ],
];

export default function ProfilePage() {
  const { profile, prefs, loadError } = useProfile();
  const s = tripStats();
  const stats: { icon: IconName; n: number; label: string }[] = [
    { icon: "plane", n: s.trips, label: "Поездок" }, { icon: "globe", n: s.countries, label: "Стран" },
    { icon: "pin", n: s.cities, label: "Городов" }, { icon: "calendar", n: s.planned, label: "В планах" },
  ];
  const fav = DIRECTIONS.filter((d) => prefs.directions.includes(d.id));
  const summary = prefSummary(prefs).filter((x) => x.value);

  return (
    <div className="prof">
      <header className="prof__top">
        <h1>Профиль</h1>
        <Link to="/profile/settings" className="circle-btn" aria-label="Данные на устройстве"><Icon name="settings" /></Link>
      </header>

      {loadError && <p className="prof__alert" role="alert">Не удалось прочитать сохранённые данные. Изменения могут не сохраниться — проверьте настройки браузера.</p>}

      <section className="prof-card prof-user">
        <Link to="/profile/edit" className="prof-user__row" aria-label="Редактировать профиль">
          <Avatar name={profile.name} src={profile.avatar} size={84} />
          <span className="prof-user__txt">
            <b>{profile.name || "Гость"}</b>
            <small>Без аккаунта · данные хранятся на этом устройстве</small>
            <span className="prof-chip"><Icon name="user" size={14} />Гостевой доступ</span>
          </span>
          <Icon name="chevron" size={20} className="prof-go" />
        </Link>
        <Link to="/profile/edit" className="prof-edit"><Icon name="pencil" size={18} />Редактировать профиль</Link>
      </section>

      <section className="prof-card">
        <div className="prof-card__head"><h2>Мои путешествия</h2><Link to="/trips">Все <Icon name="chevron" size={16} stroke={2.4} /></Link></div>
        <div className="prof-stats">
          {stats.map((x) => <div key={x.label}><Icon name={x.icon} size={22} /><b>{x.n}</b><small>{x.label}</small></div>)}
        </div>
        <p className="prof-note">По демо-поездкам приложения</p>
      </section>

      <section className="prof-card">
        <div className="prof-card__head"><h2>Мои предпочтения</h2><Link to="/profile/preferences">{fav.length || summary.length ? "Изменить" : "Указать"} <Icon name="chevron" size={16} stroke={2.4} /></Link></div>
        {fav.length === 0 && summary.length === 0 ? (
          <div className="prof-empty">
            <p className="muted">Расскажите, какие путешествия вам нравятся, — так будет проще подбирать варианты.</p>
            <Link className="btn btn--sm" to="/profile/preferences">Указать предпочтения</Link>
          </div>
        ) : (
          <>
            {fav.length > 0 && <>
              <h3 className="prof-sub">Любимые направления</h3>
              <ul className="scroll-x prof-dirs">
                {fav.map((d) => <li key={d.id}><span className="prof-dir"><Photo src={d.img} alt="" /></span><small>{d.label}</small></li>)}
              </ul>
            </>}
            {summary.length > 0 && (
              <div className="prof-prefs">
                {summary.map((x) => <div key={x.title}><span className="prof-prefs__ic"><Icon name={x.icon} size={20} /></span><span><small>{x.title}</small><span className="prof-prefs__vals">{x.value!.split(", ").map((v) => <b key={v}>{v}</b>)}</span></span></div>)}
              </div>
            )}
          </>
        )}
      </section>

      {MENU.map((group, i) => (
        <nav key={i} className="prof-card prof-menu" aria-label={i === 0 ? "Разделы" : "Прочее"}>
          {group.map((m) => <Link key={m.to} to={m.to}><Icon name={m.icon} size={22} /><span>{m.label}</span><Icon name="chevron" size={18} stroke={2.2} /></Link>)}
        </nav>
      ))}
    </div>
  );
}
