// Фото из пакета дизайнера. Это концепт-изображения, не фото реальных объектов (см. public/assets/README в архиве).
import type { CSSProperties } from "react";

export default function Photo({ src, alt = "", pos = "center", style, className }: { src?: string; alt?: string; pos?: string; style?: CSSProperties; className?: string }) {
  // Фото может не прийти из API: вместо битой картинки — нейтральная заглушка (см. .photo--empty)
  if (!src) return <div className={`photo photo--empty ${className ?? ""}`} style={style} role={alt ? "img" : undefined} aria-label={alt || undefined} />;
  return <img className={`photo ${className ?? ""}`} src={src} alt={alt} loading="lazy" style={{ objectPosition: pos, ...style }} />;
}
