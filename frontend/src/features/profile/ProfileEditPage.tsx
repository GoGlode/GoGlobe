// Редактирование гостевого профиля: имя и аватар (хранятся только на этом устройстве).
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useProfile } from "../../state/ProfileContext";
import { Icon, PageHeader } from "../../ui";
import Avatar from "./Avatar";
import "./profile.css";

const MAX_NAME = 40;
const NAME_RE = /^[\p{L}][\p{L}\s'’-]*$/u;
const AVATAR_PX = 192;

/** Уменьшает фото до 192×192 (JPEG), чтобы оно поместилось в локальное хранилище. */
function resize(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const c = document.createElement("canvas");
      c.width = c.height = AVATAR_PX;
      const side = Math.min(img.width, img.height);
      c.getContext("2d")!.drawImage(img, (img.width - side) / 2, (img.height - side) / 2, side, side, 0, 0, AVATAR_PX, AVATAR_PX);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL("image/jpeg", 0.82));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("bad image")); };
    img.src = url;
  });
}

export default function ProfileEditPage() {
  const { profile, saveProfile } = useProfile();
  const nav = useNavigate();
  const [name, setName] = useState(profile.name);
  const [avatar, setAvatar] = useState(profile.avatar);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const file = useRef<HTMLInputElement>(null);

  const trimmed = name.trim().replace(/\s+/g, " ");
  const nameError = trimmed && !NAME_RE.test(trimmed) ? "Используйте только буквы, пробел, дефис или апостроф" : null;
  const changed = trimmed !== profile.name || avatar !== profile.avatar;

  const pick = async (f?: File) => {
    setError(null);
    if (!f) return;
    if (!f.type.startsWith("image/")) return setError("Выберите файл изображения");
    if (f.size > 10 * 1024 * 1024) return setError("Файл больше 10 МБ");
    try { setAvatar(await resize(f)); } catch { setError("Не удалось прочитать изображение"); }
  };
  const save = () => {
    if (nameError || saving) return;
    setSaving(true);
    const ok = saveProfile({ name: trimmed, avatar });
    setSaving(false);
    if (!ok) return setError("Не удалось сохранить: хранилище браузера недоступно или переполнено. Изменения не применены.");
    nav("/profile");
  };

  return (
    <div className="prof-sub-screen">
      <PageHeader title="Редактировать профиль" onBack={() => nav("/profile")} />
      <form className="page prof-form" onSubmit={(e) => { e.preventDefault(); save(); }}>
        <div className="prof-avatar-edit">
          <Avatar name={trimmed} src={avatar} size={112} />
          <div className="row" style={{ gap: 8, flexWrap: "wrap", justifyContent: "center" }}>
            <button type="button" className="btn btn--sm btn--ghost" onClick={() => file.current?.click()}><Icon name="camera" size={18} />{avatar ? "Заменить фото" : "Добавить фото"}</button>
            {avatar && <button type="button" className="btn btn--sm btn--ghost" onClick={() => setAvatar(null)}><Icon name="trash" size={18} />Удалить</button>}
          </div>
          <input ref={file} type="file" accept="image/*" hidden onChange={(e) => { void pick(e.target.files?.[0]); e.target.value = ""; }} />
        </div>

        <label className="prof-field">
          <span>Имя</span>
          <input value={name} maxLength={MAX_NAME} placeholder="Как к вам обращаться" autoComplete="given-name"
            aria-invalid={!!nameError} onChange={(e) => setName(e.target.value)} />
          <small className={nameError ? "is-error" : "muted"}>{nameError ?? `Необязательно · до ${MAX_NAME} символов`}</small>
        </label>

        <div className="prof-info card">
          <Icon name="user" size={20} />
          <p>Вход по email и синхронизация между устройствами появятся после подключения аккаунтов. Сейчас профиль хранится только в этом браузере.</p>
        </div>

        {error && <p className="prof__alert" role="alert">{error}</p>}
        <button className="btn" disabled={!changed || !!nameError || saving}>{saving ? "Сохраняю…" : "Сохранить"}</button>
      </form>
    </div>
  );
}
