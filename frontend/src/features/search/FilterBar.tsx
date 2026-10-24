// Панель фильтров и сортировки на экране результатов: цена, звёзды отеля, прямой рейс.
import { NO_FILTERS, isFiltered, type Filters, type Sort } from "./filters";

const SORTS: { id: Sort; label: string }[] = [{ id: "default", label: "Подходящие" }, { id: "price-asc", label: "Дешевле" }, { id: "price-desc", label: "Дороже" }];

export default function FilterBar({ value: f, onChange, shown, total }: { value: Filters; onChange: (f: Filters) => void; shown: number; total: number }) {
  const set = (p: Partial<Filters>) => onChange({ ...f, ...p });
  const chip = (on: boolean, label: string, onClick: () => void) => <button type="button" className={`chip ${on ? "chip--active" : ""}`} aria-pressed={on} onClick={onClick}>{label}</button>;
  return (
    <div className="res__filters" role="group" aria-label="Фильтры и сортировка">
      <div className="scroll-x res__chips">
        {SORTS.map((s) => chip(f.sort === s.id, s.label, () => set({ sort: s.id })))}
        {chip(f.direct, "Прямой рейс", () => set({ direct: !f.direct }))}
        {chip(f.stars === 4, "Отель 4★+", () => set({ stars: f.stars === 4 ? 0 : 4 }))}
        {chip(f.stars === 5, "Отель 5★", () => set({ stars: f.stars === 5 ? 0 : 5 }))}
      </div>
      {isFiltered(f) && (
        <p className="res__found" aria-live="polite">Показано {shown} из {total}<button type="button" onClick={() => onChange(NO_FILTERS)}>Сбросить</button></p>
      )}
    </div>
  );
}
