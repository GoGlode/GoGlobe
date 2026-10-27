import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import Icon from "./Icon";

/** large — заголовок вкладки (Профиль, Поездки, Избранное, История): крупно слева, без кнопки «назад» */
export default function PageHeader({ title, right, onBack, light, large }: { title?: string; right?: ReactNode; onBack?: () => void; light?: boolean; large?: boolean }) {
  const nav = useNavigate();
  if (large) {
    return (
      <header className="page-header page-header--large">
        <h1 className="page-header__title">{title}</h1>
        {right && <div className="row" style={{ gap: 8, justifyContent: "flex-end" }}>{right}</div>}
      </header>
    );
  }
  return (
    <header className="page-header" style={{ color: light ? "#fff" : undefined }}>
      <button className="circle-btn" aria-label="Назад" onClick={onBack ?? (() => nav(-1))}><Icon name="back" /></button>
      <h1 className="page-header__title">{title}</h1>
      <div className="row" style={{ gap: 8, minWidth: 44, justifyContent: "flex-end" }}>{right}</div>
    </header>
  );
}
