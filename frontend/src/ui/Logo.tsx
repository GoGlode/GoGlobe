// Логотип GoGlobe. В тёмной теме — вариант с осветлёнными тёмно-синими буквами «Go» (на тёмном фоне они сливались).
import type { CSSProperties } from "react";
import { useTheme } from "../state/ThemeContext";

export default function Logo({ className, style }: { className?: string; style?: CSSProperties }) {
  const { theme } = useTheme();
  return <img src={`/assets/brand/logo-goglobe${theme === "dark" ? "-dark" : ""}.png`} alt="GoGlobe" className={className} style={style} />;
}
