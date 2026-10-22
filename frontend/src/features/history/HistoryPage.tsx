// История запросов: повторить поиск в один тап. Владелец: Frontend №1.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Icon, PageHeader } from "../../ui";
import { clearHistory, readHistory } from "./historyStore";
import "./history.css";

export default function HistoryPage() {
  const [items, setItems] = useState(readHistory);
  const nav = useNavigate();
  return (
    <>
      <PageHeader title="История" onBack={() => nav("/")} right={items.length ? <button className="circle-btn" aria-label="Очистить" onClick={() => { clearHistory(); setItems([]); }}><Icon name="x" size={20} /></button> : undefined} />
      {items.length === 0 ? (
        <div className="page hist-empty"><div className="circle-btn" style={{ width: 72, height: 72 }}><Icon name="clock" size={30} /></div><h2>Пока нет запросов</h2><p className="muted">Здесь появятся ваши поиски — их можно повторить в один тап.</p></div>
      ) : (
        <div className="page hist">
          {items.map((h) => (
            <button key={h.at} className="hist__item glass" onClick={() => nav("/", { state: { q: h.q } })}>
              <Icon name="clock" size={20} /><span><b>{h.q}</b><small className="muted">{new Date(h.at).toLocaleString("ru-RU", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" })}</small></span><Icon name="chevron" size={18} />
            </button>
          ))}
        </div>
      )}
    </>
  );
}
