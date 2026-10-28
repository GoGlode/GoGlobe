// Поле выбора города с выпадающим списком подсказок (вместо системного <datalist>, который на iOS выглядит как серая панель над клавиатурой).
// Список фильтруется по мере ввода: по началу любого слова города или по коду; ё = е; регистр не важен.
// Рендерит <input> и список — кладите внутрь контейнера с position: relative (например, label.fl-field).
import { useId, useMemo, useState } from "react";
import Icon from "./Icon";

export interface CityOption { key: string; label: string; city: string; code?: string }

const norm = (s: string) => s.toLowerCase().replace(/ё/g, "е").trim();

interface Props {
  value: string;
  onChange: (text: string) => void;
  options: CityOption[];
  placeholder?: string;
  /** Выбран пункт списка (по умолчанию в поле подставляется его label) */
  onPick?: (o: CityOption) => void;
  className?: string;
}

export default function CityInput({ value, onChange, options, placeholder, onPick, className }: Props) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);

  const list = useMemo(() => {
    const q = norm(value);
    // Пустое поле или точное совпадение с выбранным вариантом — показываем все города
    if (!q || options.some((o) => norm(o.label) === q)) return options;
    const starts = (o: CityOption) => norm(o.city).split(/[\s(-]+/).some((w) => w.startsWith(q)) || norm(o.code ?? "").startsWith(q);
    const first = options.filter(starts);
    const rest = options.filter((o) => !first.includes(o) && norm(o.label).includes(q));
    return [...first, ...rest];
  }, [value, options]);

  const pick = (o: CityOption) => {
    onChange(o.label);
    onPick?.(o);
    setOpen(false);
  };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) return setOpen(true);
      setCursor((c) => (c + (e.key === "ArrowDown" ? 1 : -1) + list.length) % Math.max(1, list.length));
    } else if (e.key === "Enter" && open && list[cursor]) {
      e.preventDefault();
      pick(list[cursor]);
    } else if (e.key === "Escape") setOpen(false);
  };

  return (
    <>
      <input className={className} placeholder={placeholder} value={value} autoComplete="off" autoCapitalize="words" spellCheck={false}
        role="combobox" aria-expanded={open} aria-controls={id} aria-autocomplete="list"
        onChange={(e) => { onChange(e.target.value); setCursor(0); setOpen(true); }}
        onFocus={(e) => { setOpen(true); e.target.select(); }} onBlur={() => setOpen(false)} onKeyDown={onKey} />
      {open && (
        <ul className="city-menu" id={id} role="listbox">
          {list.length === 0 && <li className="city-menu__empty">Такого города нет в списке</li>}
          {list.map((o, i) => (
            <li key={o.key} role="option" aria-selected={i === cursor} className={`city-menu__item ${i === cursor ? "is-cursor" : ""}`}
              onMouseDown={(e) => e.preventDefault()} onClick={() => pick(o)} onMouseEnter={() => setCursor(i)}>
              <Icon name="pin" size={18} /><span>{o.city}</span>{o.code && <small>{o.code}</small>}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
