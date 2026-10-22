import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import Icon from "./Icon";

export default function PageHeader({ title, right, onBack, light }: { title?: string; right?: ReactNode; onBack?: () => void; light?: boolean }) {
  const nav = useNavigate();
  return (
    <header className="page-header" style={{ color: light ? "#fff" : undefined }}>
      <button className="circle-btn" aria-label="Назад" onClick={onBack ?? (() => nav(-1))}><Icon name="back" /></button>
      <h1 className="page-header__title">{title}</h1>
      <div className="row" style={{ gap: 8, minWidth: 44, justifyContent: "flex-end" }}>{right}</div>
    </header>
  );
}
