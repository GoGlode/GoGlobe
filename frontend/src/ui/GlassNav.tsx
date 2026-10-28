// Нижняя «стеклянная» навигация: профиль · поездки · ИИ-поиск (центр) · избранное · история.
// Стекло-«линза» ведёт себя как капля жидкости: два её края идут на пружинах разной жёсткости — передний убегает,
// задний тянется следом (линза растягивается и чуть сплющивается), потом края сходятся с мягким перелётом.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";

const ITEMS = [
  { to: "/flights", icon: "plane", label: "Перелёты" },
  { to: "/hotels", icon: "bed", label: "Отели" },
  { to: "/", icon: "search-sparkle-nav", label: "Поиск", center: true },
  { to: "/trips", icon: "nav-calendar", label: "Мои поездки" },
  { to: "/favorites", icon: "nav-favorites", label: "Избранное" },
];

// Фирменная иконка AI-поиска (как public/assets/icons/search-sparkle-nav.svg), но инлайном — чтобы звёзды мерцали отдельно от лупы
function SearchIcon({ size }: { size: number }) {
  return (
    <svg className="nav-search-ic" width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <g fill="none" stroke="currentColor" strokeWidth="5.2" strokeLinecap="round"><circle cx="30" cy="30.5" r="19.4" /><path d="M44 44.5 56.5 57" /></g>
      <path className="nav-search-ic__star" d="M30 19.5C31.05 27.25 33.24 29.45 41 30.5C33.24 31.55 31.05 33.74 30 41.5C28.95 33.74 26.75 31.55 19 30.5C26.75 29.45 28.95 27.25 30 19.5Z" fill="currentColor" stroke="currentColor" strokeWidth="1" strokeLinejoin="round" />
      <path className="nav-search-ic__spark" d="M10.5 1.7C11.13 6.35 12.45 7.67 17.1 8.3C12.45 8.93 11.13 10.25 10.5 14.9C9.87 10.25 8.55 8.93 3.9 8.3C8.55 7.67 9.87 6.35 10.5 1.7Z" fill="currentColor" stroke="currentColor" strokeWidth="0.8" strokeLinejoin="round" />
    </svg>
  );
}

// Контурные иконки инлайном: при выборе пункта их линии «дорисовываются» (stroke-dashoffset, см. glassnav.css)
function DrawIcon({ name, size }: { name: "nav-favorites" | "nav-profile" | "nav-calendar" | "nav-history" | "plane" | "bed"; size: number }) {
  const small = name === "plane" || name === "bed"; // эти иконки нарисованы на сетке 24×24
  return (
    <svg className="nav-draw" width={size} height={size} viewBox={small ? "0 0 24 24" : "0 0 64 64"} fill="none" stroke="currentColor" strokeWidth={small ? "1.9" : "4.2"} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {name === "plane" ? <path pathLength={1} d="M17.8 19.2L16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z" />
        : name === "bed" ? <><path pathLength={1} d="M3 19V6M3 15h18v4M21 15v-2.5A3.5 3.5 0 0017.5 9H11v6" /><circle className="nav-draw__2" pathLength={1} cx="7" cy="11.5" r="1.8" /></>
        : name === "nav-favorites" ? <path pathLength={1} d="M32 54 10.5 33.5C-2 20 16 4 29 16l3 3 3-3C48 4 66 20 53.5 33.5Z" />
        : name === "nav-profile" ? <><path pathLength={1} d="M21 20a11 11 0 1 1 22 0a11 11 0 1 1-22 0" /><path className="nav-draw__2" pathLength={1} d="M10 56c1.5-12 9.5-18 22-18s20.5 6 22 18Z" /></>
        : name === "nav-history" ? <><path pathLength={1} d="M11 25A22 22 0 1 1 10 38" /><path className="nav-draw__2" pathLength={1} d="M9 12v14h14" /><path className="nav-draw__3" pathLength={1} d="M32 17v16l11 7" /></>
        : <><rect pathLength={1} x="9" y="13" width="46" height="42" rx="6" /><path className="nav-draw__2" pathLength={1} d="M9 25h46" /><path className="nav-draw__3" pathLength={1} d="M20 7v12M44 7v12" />
          <path className="nav-draw__dots" d="M20 34h1M32 34h1M44 34h1M20 44h1M32 44h1M44 44h1" strokeWidth="5" /></>}
    </svg>
  );
}

type Box = { l: number; r: number; h: number };
// Пружины: ведущий край упругий, ведомый — мягче и медленнее
const LEAD = { k: 420, c: 27 };
const TRAIL = { k: 150, c: 14 };
const MAX_STRETCH = 2.7; // во сколько раз линза может вытянуться относительно своей ширины

export default function GlassNav() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const navRef = useRef<HTMLElement>(null);
  const lensRef = useRef<HTMLSpanElement>(null);
  const [lens, setLens] = useState<Box | null>(null);
  const [moving, setMoving] = useState(false);
  const seen = useRef(false);
  const [dragX, setDragX] = useState<number | null>(null);
  const [overIdx, setOverIdx] = useState(0);
  const drag = useRef<{ id: number; startX: number; startLens: number; moved: boolean; w: number; min: number; max: number; centers: number[] } | null>(null);
  const justDragged = useRef(false);
  const isActive = (to: string) => (to === "/" ? !["/flights", "/hotels", "/trips", "/favorites"].some((p) => pathname.startsWith(p)) : pathname.startsWith(to));
  const activeIdx = ITEMS.findIndex((it) => isActive(it.to));

  // ── Физика линзы ──
  const target = useRef<Box>({ l: 0, r: 56, h: 56 });
  const cur = useRef({ l: 0, r: 56, vl: 0, vr: 0, ready: false });
  const raf = useRef(0);
  const paint = () => {
    const el = lensRef.current;
    if (!el) return;
    const { l, r } = cur.current, T = target.current;
    const stretch = Math.max(0, (r - l) / Math.max(1, T.r - T.l) - 1);
    const h = T.h / (1 + stretch * 0.4); // растянулась по горизонтали — стала ниже
    el.style.translate = `${l}px 0`;
    el.style.width = `${Math.max(8, r - l)}px`;
    el.style.height = `${h}px`;
    el.style.setProperty("--lens-h", `${h}px`);
  };
  const run = () => {
    if (raf.current) return;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = Math.min(0.032, (now - last) / 1000);
      last = now;
      const T = target.current, C = cur.current;
      const rightLeads = (T.l + T.r) / 2 - (C.l + C.r) / 2 >= 0;
      const sl = rightLeads ? TRAIL : LEAD, sr = rightLeads ? LEAD : TRAIL;
      C.vl += (sl.k * (T.l - C.l) - sl.c * C.vl) * dt; C.l += C.vl * dt;
      C.vr += (sr.k * (T.r - C.r) - sr.c * C.vr) * dt; C.r += C.vr * dt;
      const maxW = (T.r - T.l) * MAX_STRETCH;
      if (C.r - C.l > maxW) { if (rightLeads) C.l = C.r - maxW; else C.r = C.l + maxW; }
      paint();
      const calm = Math.abs(T.l - C.l) < 0.05 && Math.abs(T.r - C.r) < 0.05 && Math.abs(C.vl) < 0.05 && Math.abs(C.vr) < 0.05;
      if (calm) { C.l = T.l; C.r = T.r; C.vl = C.vr = 0; paint(); raf.current = 0; return; }
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
  };
  useEffect(() => () => cancelAnimationFrame(raf.current), []);

  // Куда стремится линза: под активный пункт или за пальцем
  useLayoutEffect(() => {
    if (!lens) return;
    target.current = dragX === null ? lens : { l: dragX, r: dragX + (drag.current?.w ?? lens.r - lens.l), h: 56 };
    if (!cur.current.ready) { cur.current = { l: target.current.l, r: target.current.r, vl: 0, vr: 0, ready: true }; paint(); return; }
    run();
  }, [lens, dragX]);

  const measure = () => {
    const el = navRef.current?.children[activeIdx + 1] as HTMLElement | undefined;
    if (!el) return;
    const pad = 0;
    setLens({ l: el.offsetLeft - pad, r: el.offsetLeft + el.offsetWidth + pad, h: el.offsetHeight + pad * 2 });
  };
  useLayoutEffect(measure, [activeIdx]);
  useEffect(() => {
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [activeIdx]);
  useEffect(() => {
    if (!seen.current) { seen.current = true; return; }
    setMoving(true);
    const t = setTimeout(() => setMoving(false), 700);
    return () => clearTimeout(t);
  }, [activeIdx]);

  // ── Перетаскивание ──
  const nearest = (centers: number[], x: number) => centers.reduce((best, c, i) => (Math.abs(c - x) < Math.abs(centers[best] - x) ? i : best), 0);
  const onDown = (e: React.PointerEvent) => {
    if (!lens || (e.pointerType === "mouse" && e.button !== 0)) return;
    const items = Array.from(navRef.current!.children).slice(1) as HTMLElement[];
    const first = items[0], last = items[items.length - 1];
    const w = items[1].offsetWidth;
    drag.current = { id: e.pointerId, startX: e.clientX, startLens: lens.l, moved: false, w, min: first.offsetLeft, max: last.offsetLeft + last.offsetWidth - w,
      centers: items.map((el) => el.offsetLeft + el.offsetWidth / 2) };
  };
  const onMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d || e.pointerId !== d.id) return;
    const dx = e.clientX - d.startX;
    if (!d.moved) {
      if (Math.abs(dx) < 6) return;
      d.moved = true;
      navRef.current!.setPointerCapture(e.pointerId);
    }
    const x = Math.min(d.max, Math.max(d.min, d.startLens + dx));
    setDragX(x);
    setOverIdx(nearest(d.centers, x + d.w / 2));
  };
  const onUp = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d || e.pointerId !== d.id) return;
    drag.current = null;
    if (!d.moved) return;
    justDragged.current = true;
    setTimeout(() => { justDragged.current = false; }, 0);
    const idx = nearest(d.centers, Math.min(d.max, Math.max(d.min, d.startLens + e.clientX - d.startX)) + d.w / 2);
    setDragX(null);
    if (idx !== activeIdx) navigate(ITEMS[idx].to);
  };
  const onCancel = () => { drag.current = null; setDragX(null); };
  const dragging = dragX !== null;

  return (
    <nav ref={navRef} className="glassnav glass" aria-label="Основная навигация" onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp}
      onPointerCancel={onCancel} onClickCapture={(e) => { if (justDragged.current) { e.preventDefault(); e.stopPropagation(); } }}>
      <span ref={lensRef} className={`glassnav__lens ${moving && !dragging ? "is-moving" : ""} ${lens ? "is-ready" : ""} ${dragging ? "is-dragging" : ""} ${ITEMS[activeIdx].center ? "is-on-center" : ""}`} aria-hidden="true" />
      {ITEMS.map((it) => {
        const active = dragging ? ITEMS.indexOf(it) === overIdx : isActive(it.to);
        return (
          <NavLink key={it.to} to={it.to} draggable={false} aria-label={it.label} aria-current={active ? "page" : undefined}
            className={`glassnav__item ${it.center ? "glassnav__item--center" : ""} ${active ? "is-active" : ""}`}>
            {it.center ? <SearchIcon size={34} /> : <DrawIcon name={it.icon as "nav-favorites"} size={26} />}
          </NavLink>
        );
      })}
    </nav>
  );
}
