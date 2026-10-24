// Нижняя «стеклянная» навигация: профиль · поездки · ИИ-поиск (центр) · избранное · история.
// Стекло-«линза» ведёт себя как капля жидкости: два её края идут на пружинах разной жёсткости — передний убегает,
// задний тянется следом (линза растягивается и чуть сплющивается), потом края сходятся с мягким перелётом.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { MaskIcon } from "./Icon";

const ITEMS = [
  { to: "/profile", icon: "nav-profile", label: "Профиль" },
  { to: "/trips", icon: "nav-calendar", label: "Мои поездки" },
  { to: "/", icon: "search-sparkle-nav", label: "Поиск", center: true },
  { to: "/favorites", icon: "nav-favorites", label: "Избранное" },
  { to: "/history", icon: "nav-history", label: "История" },
];

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
  const isActive = (to: string) => (to === "/" ? !["/profile", "/trips", "/favorites", "/history"].some((p) => pathname.startsWith(p)) : pathname.startsWith(to));
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
    const pad = ITEMS[activeIdx].center ? 4 : 0;
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
      <span ref={lensRef} className={`glassnav__lens ${moving && !dragging ? "is-moving" : ""} ${lens ? "is-ready" : ""} ${dragging ? "is-dragging" : ""}`} aria-hidden="true" />
      {ITEMS.map((it) => {
        const active = dragging ? ITEMS.indexOf(it) === overIdx : isActive(it.to);
        return (
          <NavLink key={it.to} to={it.to} draggable={false} aria-label={it.label} aria-current={active ? "page" : undefined}
            className={`glassnav__item ${it.center ? "glassnav__item--center" : ""} ${active ? "is-active" : ""}`}>
            <MaskIcon src={it.icon} size={it.center ? 34 : 26} />
          </NavLink>
        );
      })}
    </nav>
  );
}
