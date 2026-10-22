// Рамка iPhone для показа мобильного приложения на компьютере.
// Приложение работает внутри iframe с шириной телефона, поэтому верстка и навигация — как на устройстве.
import { useEffect, useState } from "react";
import "./phone.css";

const SCREEN_W = 393;
const SCREEN_H = 852;
const BEZEL = 12;
const FRAME_H = SCREEN_H + BEZEL * 2;
const MARGIN = 96; // место под подпись и поля сверху/снизу

/** Показывать ли рамку: только верхнее окно на широком экране; ?frame=0 — без рамки. */
export function shouldUsePhoneFrame() {
  return window.self === window.top
    && new URLSearchParams(window.location.search).get("frame") !== "0"
    && window.matchMedia("(min-width: 700px)").matches;
}

export default function PhoneFrame() {
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const fit = () => setScale(Math.min(1, (window.innerHeight - MARGIN) / FRAME_H));
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, []);

  const src = `${window.location.pathname}${window.location.search}`;
  const plain = `${window.location.pathname}?frame=0`;

  return (
    <div className="phone-stage">
      <div className="phone-slot" style={{ width: (SCREEN_W + BEZEL * 2) * scale, height: FRAME_H * scale }}>
        <div className="phone" style={{ transform: `scale(${scale})` }}>
          <div className="phone__screen">
            <div className="phone__status" aria-hidden="true">
              <span className="phone__time">9:41</span>
              <span className="phone__island" />
              <StatusIcons />
            </div>
            <iframe className="phone__app" src={src} title="GoGlobe — мобильное приложение" />
            <div className="phone__home" aria-hidden="true"><span /></div>
          </div>
        </div>
      </div>
      <p className="phone-caption">
        Демо мобильного приложения GoGlobe · <a href={plain}>открыть без рамки</a>
      </p>
    </div>
  );
}

function StatusIcons() {
  return (
    <span className="phone__icons">
      <svg width="18" height="12" viewBox="0 0 18 12" fill="currentColor">
        <rect x="0" y="8" width="3" height="4" rx="1" /><rect x="5" y="5.5" width="3" height="6.5" rx="1" />
        <rect x="10" y="3" width="3" height="9" rx="1" /><rect x="15" y="0" width="3" height="12" rx="1" />
      </svg>
      <svg width="16" height="12" viewBox="0 0 16 12" fill="currentColor">
        <path d="M8 2.6c2.3 0 4.4.9 6 2.4l1.2-1.3A10.2 10.2 0 0 0 8 .8C5.2.8 2.7 1.9.8 3.7L2 5c1.6-1.5 3.7-2.4 6-2.4Zm0 3.5c1.3 0 2.5.5 3.5 1.3l1.2-1.3A7 7 0 0 0 8 4.3a7 7 0 0 0-4.7 1.8l1.2 1.3c1-.8 2.2-1.3 3.5-1.3Zm0 3.4c.4 0 .8.2 1.1.4L8 11.2 6.9 9.9c.3-.2.7-.4 1.1-.4Z" />
      </svg>
      <svg width="27" height="13" viewBox="0 0 27 13" fill="none">
        <rect x="0.5" y="0.5" width="23" height="12" rx="3.5" stroke="currentColor" opacity=".4" />
        <rect x="2" y="2" width="20" height="9" rx="2" fill="currentColor" />
        <path d="M25 4.5v4c.8-.3 1.3-1.1 1.3-2s-.5-1.7-1.3-2Z" fill="currentColor" opacity=".45" />
      </svg>
    </span>
  );
}
