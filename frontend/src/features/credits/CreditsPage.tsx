// Атрибуция фотографий (требование лицензий CC BY / CC BY-SA).
import { PHOTO_CREDITS } from "../../data/photoCredits";
import { PageHeader } from "../../ui";

export default function CreditsPage() {
  return (
    <>
      <PageHeader title="Фото и лицензии" />
      <div className="page" style={{ display: "grid", gap: 12 }}>
        <p className="muted" style={{ fontSize: 14, lineHeight: 1.45 }}>
          Фотографии направлений взяты с Wikimedia Commons и используются по указанным лицензиям.
          Это виды мест, а не фото конкретных отелей или предложений.
        </p>
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 10 }}>
          {PHOTO_CREDITS.map((c) => (
            <li key={c.file} className="row" style={{ alignItems: "center", fontSize: 13, overflowWrap: "anywhere" }}>
              <img src={c.file} alt="" loading="lazy" style={{ width: 64, height: 44, objectFit: "cover", borderRadius: 8, flex: "none" }} />
              <div>
                <a href={c.source} target="_blank" rel="noreferrer" style={{ color: "var(--c-primary)" }}>{c.title}</a>
                <div className="muted">
                  {c.author || "Автор не указан"} ·{" "}
                  {c.license_url ? <a href={c.license_url} target="_blank" rel="noreferrer" style={{ textDecoration: "underline" }}>{c.license}</a> : c.license}
                </div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
