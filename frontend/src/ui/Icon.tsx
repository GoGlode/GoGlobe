// Набор иконок (контурные, currentColor). Добавляйте новые сюда, не создавайте дубли в фичах.
import type { CSSProperties, ReactNode } from "react";

const P: Record<string, ReactNode> = {
  back: <path d="M15 18l-6-6 6-6" />,
  chevron: <path d="M9 18l6-6-6-6" />,
  "chevron-left": <path d="M15 18l-6-6 6-6" />,
  "arrow-right": <path d="M5 12h14M13 6l6 6-6 6" />,
  "arrow-up": <path d="M12 19V5M5 12l7-7 7 7" />,
  plus: <path d="M12 5v14M5 12h14" />,
  x: <path d="M6 6l12 12M18 6L6 18" />,
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  filter: <><path d="M4 7h9M17 7h3M4 17h3M11 17h9" /><circle cx="15" cy="7" r="2" /><circle cx="9" cy="17" r="2" /></>,
  heart: <path d="M12 20.5S4.5 16 4.5 10.2A4.2 4.2 0 0112 7.6a4.2 4.2 0 017.5 2.6c0 5.8-7.5 10.3-7.5 10.3z" />,
  calendar: <><rect x="4" y="5" width="16" height="15" rx="3.5" /><path d="M8 3v4M16 3v4M4 10h16" /></>,
  users: <><circle cx="9" cy="8" r="3" /><path d="M3.5 20c0-3.3 2.5-5.5 5.5-5.5s5.5 2.2 5.5 5.5" /><circle cx="17" cy="9" r="2.2" /><path d="M16.5 14.2c2.6 0 4.5 1.8 4.5 4.8" /></>,
  user: <><circle cx="12" cy="8" r="3.5" /><path d="M5 20c0-4 3-6 7-6s7 2 7 6" /></>,
  wallet: <><rect x="3" y="6" width="18" height="13" rx="3.5" /><path d="M3 10h18M16.5 14.5h.01" /></>,
  tag: <><path d="M3.5 12.5V4.5h8l9 9-8 8z" /><circle cx="8" cy="9" r="1.3" /></>,
  pin: <><path d="M12 21s7-6 7-11a7 7 0 10-14 0c0 5 7 11 7 11z" /><circle cx="12" cy="10" r="2.5" /></>,
  share: <path d="M12 15V3.5M7.5 8L12 3.5 16.5 8M5 12.5V18a2 2 0 002 2h10a2 2 0 002-2v-5.5" />,
  bed: <><path d="M3 19V6M3 15h18v4M21 15v-2.5A3.5 3.5 0 0017.5 9H11v6" /><circle cx="7" cy="11.5" r="1.8" /></>,
  plane: <path d="M17.8 19.2L16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z" />,
  car: <><path d="M4 16h16l-1.5-5.5A2 2 0 0016.6 9H7.4a2 2 0 00-1.9 1.5L4 16z" /><path d="M4 16v3M20 16v3" /><circle cx="8" cy="13.5" r=".6" /><circle cx="16" cy="13.5" r=".6" /></>,
  clock: <><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></>,
  coffee: <><path d="M4.5 9h11v5a5 5 0 01-5 5h-1a5 5 0 01-5-5z" /><path d="M15.5 10h1.5a2 2 0 010 4h-1.5M8 3.5v2.5M12 3.5v2.5" /></>,
  pool: <><path d="M3 17c1.5 0 1.5-1.2 3-1.2s1.5 1.2 3 1.2 1.5-1.2 3-1.2 1.5 1.2 3 1.2 1.5-1.2 3-1.2 1.5 1.2 3 1.2" /><path d="M8 13V6.5a2 2 0 012-2M14 13V6.5a2 2 0 012-2M8 9h6" /></>,
  wifi: <><path d="M3 9.5a13 13 0 0118 0M6 13a8.5 8.5 0 0112 0M9 16.5a4 4 0 016 0" /><circle cx="12" cy="19.5" r=".8" /></>,
  spa: <><path d="M12 20c-4 0-7-3-7-7 3 0 5.5 1.5 7 4 1.5-2.5 4-4 7-4 0 4-3 7-7 7z" /><path d="M12 17c-2-2.5-2-8 0-12 2 4 2 9.5 0 12z" /></>,
  view: <><rect x="3" y="5" width="18" height="14" rx="3" /><circle cx="9" cy="10" r="1.5" /><path d="M3.5 17l5-5 4 4 3-3 5 4" /></>,
  waves: <><path d="M3 9c1.5 0 1.5-1.4 3-1.4S7.5 9 9 9s1.5-1.4 3-1.4S13.5 9 15 9s1.5-1.4 3-1.4 1.5 1.4 3 1.4M3 14c1.5 0 1.5-1.4 3-1.4s1.5 1.4 3 1.4 1.5-1.4 3-1.4 1.5 1.4 3 1.4 1.5-1.4 3-1.4 1.5 1.4 3 1.4" /></>,
  landmark: <path d="M3 20.5h18M5 20V10M9.5 20V10M14.5 20V10M19 20V10M3 10l9-6 9 6z" />,
  leaf: <path d="M5 19C5 10 10 5 20 4c0 10-5 15-14 15zM5 19l8-8" />,
  utensils: <path d="M7 3v18M4 3v5a3 3 0 006 0V3M17 21V3c-2.5 1.5-3.5 4.5-3.5 8H17" />,
  map: <path d="M9 4L3 6.5v13.5l6-2.5 6 2.5 6-2.5V4l-6 2.5zM9 4v13.5M15 6.5V20" />,
  nav: <path d="M3.5 11l17-7.5-7.5 17-2-7.5z" />,
  bag: <><rect x="5" y="8" width="14" height="12" rx="3" /><path d="M9 8V5.5A1.5 1.5 0 0110.5 4h3A1.5 1.5 0 0115 5.5V8" /></>,
  suitcase: <><rect x="5.5" y="7.5" width="13" height="13" rx="3" /><path d="M9.5 7.5V5h5v2.5M9 11v6M15 11v6" /></>,
  meal: <path d="M6 3v7a2 2 0 002 2v9M10 3v7M8 3v5M16 21V3c-2 1.5-3 4.5-3 8h3" />,
  search: <><circle cx="11" cy="11" r="6.5" /><path d="M20 20l-4.2-4.2" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z" /></>,
  globe: <><circle cx="12" cy="12" r="8.5" /><path d="M3.5 12h17M12 3.5c2.3 2.4 3.5 5.2 3.5 8.5s-1.2 6.1-3.5 8.5c-2.3-2.4-3.5-5.2-3.5-8.5S9.7 5.9 12 3.5z" /></>,
  camera: <><path d="M4 8.5A2 2 0 016 6.5h2l1.5-2h5l1.5 2h2a2 2 0 012 2V17a2 2 0 01-2 2H6a2 2 0 01-2-2z" /><circle cx="12" cy="12.5" r="3.5" /></>,
  pencil: <path d="M4 20h4L19 9a2.8 2.8 0 00-4-4L4 16v4zM13.5 6.5l4 4" />,
  trash: <path d="M4 7h16M10 11v6M14 11v6M5.5 7l1 12a2 2 0 002 2h7a2 2 0 002-2l1-12M9 7V4.5h6V7" />,
  refresh: <><path d="M20 11.5A8 8 0 006.3 6.3L4 8.5" /><path d="M4 4v4.5h4.5M4 12.5a8 8 0 0013.7 5.2L20 15.5" /><path d="M20 20v-4.5h-4.5" /></>,
  swap: <path d="M7 4L3.5 7.5 7 11M3.5 7.5h14M17 13l3.5 3.5L17 20M20.5 16.5h-14" />,
  sparkle: <path d="M12 3l2.1 6 6 2.1-6 2.1L12 19.5l-2.1-6.3-6-2.1 6-2.1z" />,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6L7 7M17 17l1.4 1.4M5.6 18.4L7 17M17 7l1.4-1.4" /></>,
  star: <path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z" />,
};

export type IconName = keyof typeof P;

export default function Icon({ name, size = 22, stroke = 1.9, filled, style, className }: {
  name: IconName; size?: number; stroke?: number; filled?: boolean; style?: CSSProperties; className?: string;
}) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor"
      strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" style={style} className={className} aria-hidden="true">
      {P[name]}
    </svg>
  );
}

/** Иконка из пакета дизайнера (public/assets/icons/*.svg) с управлением цветом через color. */
export function MaskIcon({ src, size = 24, className }: { src: string; size?: number; className?: string }) {
  const url = `url(/assets/icons/${src}.svg)`;
  return <span className={`mask-icon ${className ?? ""}`} style={{ width: size, height: size, maskImage: url, WebkitMaskImage: url }} aria-hidden="true" />;
}
