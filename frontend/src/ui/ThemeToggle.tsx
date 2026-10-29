// Переключатель «день / ночь»: солнце превращается в луну, небо темнеет, появляются звёзды.
import { useRef } from "react";
import { useTheme } from "../state/ThemeContext";
import "./themetoggle.css";

export default function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const ref = useRef<HTMLButtonElement>(null);
  const dark = theme === "dark";
  const toggle = () => {
    const r = ref.current?.getBoundingClientRect();
    setTheme(dark ? "light" : "dark", r && { x: r.left + r.width / 2, y: r.top + r.height / 2 });
  };
  return (
    <button ref={ref} type="button" role="switch" aria-checked={dark} aria-label="Тёмная тема" className={`tt ${dark ? "is-night" : ""}`} onClick={toggle}>
      <span className="tt__sky" /><span className="tt__night" />
      <svg className="tt__svg" viewBox="0 0 80 80" aria-hidden="true">
        <defs>
          <mask id="tt-crescent"><rect width="80" height="80" fill="#fff" /><circle cx="49" cy="31" r="17" fill="#000" /></mask>
        </defs>
        <g className="tt__stars">
          <circle className="tt__star s1" cx="22" cy="20" r="2.6" /><circle className="tt__star s2" cx="58" cy="19" r="2" /><circle className="tt__star s3" cx="63" cy="40" r="3" />
          <circle className="tt__star s4" cx="16" cy="55" r="2" fill="#fff" /><circle className="tt__star s5" cx="46" cy="62" r="2.2" fill="#fff" />
        </g>
        <g className="tt__sun" fill="none" stroke="#f7931e" strokeWidth="3.4" strokeLinecap="round">
          <circle cx="40" cy="40" r="7.5" />
          <path d="M40 22v-3M40 58v3M22 40h-3M58 40h3M27.3 27.3l-2.1-2.1M52.7 52.7l2.1 2.1M27.3 52.7l-2.1 2.1M52.7 27.3l2.1-2.1" />
        </g>
        <g className="tt__moon"><circle cx="38" cy="43" r="19" fill="#fff27a" mask="url(#tt-crescent)" /></g>
      </svg>
    </button>
  );
}
