// Нижняя шторка для выбора значений (даты / путешественники / бюджет). Рендерится внутрь .app, чтобы не вылезать за «телефон».
import { createPortal } from "react-dom";
import { Icon } from "../../ui";

export default function Sheet({ title, options, value, onPick, onClose }: { title: string; options: string[]; value?: string; onPick: (v: string | undefined) => void; onClose: () => void }) {
  const host = document.querySelector(".app");
  if (!host) return null;
  return createPortal(
    <div className="sheet-back" onClick={onClose} role="presentation">
      <div className="sheet glass fade-up" role="dialog" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <div className="sheet__grip" />
        <h3>{title}</h3>
        {options.map((o, i) => {
          const on = value === o || (!value && i === 0);
          return <button key={o} className={`sheet__opt ${on ? "on" : ""}`} onClick={() => { onPick(i === 0 ? undefined : o); onClose(); }}>{o}{on && <Icon name="check" size={20} />}</button>;
        })}
      </div>
    </div>,
    host,
  );
}
