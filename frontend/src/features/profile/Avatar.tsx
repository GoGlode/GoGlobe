// Аватар: фото, если пользователь его выбрал, иначе инициалы или значок гостя.
import { Icon } from "../../ui";

export default function Avatar({ name, src, size = 84 }: { name: string; src: string | null; size?: number }) {
  const initials = name.trim().split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase()).join("");
  return (
    <span className="avatar" style={{ width: size, height: size, fontSize: size * 0.36 }} aria-hidden="true">
      {src ? <img src={src} alt="" /> : initials || <Icon name="user" size={size * 0.46} />}
    </span>
  );
}
