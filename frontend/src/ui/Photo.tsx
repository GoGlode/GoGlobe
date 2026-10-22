// Фото из пакета дизайнера. Это концепт-изображения, не фото реальных объектов (см. public/assets/README в архиве).
import type { CSSProperties } from "react";

export default function Photo({ src, alt = "", pos = "center", style, className }: { src: string; alt?: string; pos?: string; style?: CSSProperties; className?: string }) {
  return <img className={`photo ${className ?? ""}`} src={src} alt={alt} loading="lazy" style={{ objectPosition: pos, ...style }} />;
}
