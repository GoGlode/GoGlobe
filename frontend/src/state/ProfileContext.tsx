// Локальный гостевой профиль: имя и аватар, которые пользователь задал сам, и предпочтения путешествий.
// Авторизации и API профиля в проекте нет, поэтому данные хранятся только в localStorage этого устройства.
// Никаких персональных данных по умолчанию: пустое имя = «Гость».
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { EMPTY_PREFS, type TravelPrefs } from "../data/preferences";

const KEY = "goglobe.profile.v1";
export interface LocalProfile { name: string; avatar: string | null }
interface Stored { profile: LocalProfile; prefs: TravelPrefs }
interface Ctx {
  profile: LocalProfile; prefs: TravelPrefs;
  /** Данные не удалось прочитать (хранилище недоступно или повреждено) */
  loadError: boolean;
  /** Возвращает false, если сохранить не удалось — UI не должен показывать «Сохранено». */
  saveProfile: (p: LocalProfile) => boolean;
  savePrefs: (p: TravelPrefs) => boolean;
}
const C = createContext<Ctx>(null!);
export const useProfile = () => useContext(C);

const EMPTY: Stored = { profile: { name: "", avatar: null }, prefs: EMPTY_PREFS };

function load(): { data: Stored; error: boolean } {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { data: EMPTY, error: false };
    const s = JSON.parse(raw);
    return { data: { profile: { ...EMPTY.profile, ...s.profile }, prefs: { ...EMPTY_PREFS, ...s.prefs } }, error: false };
  } catch {
    return { data: EMPTY, error: true };
  }
}

export function ProfileProvider({ children }: { children: ReactNode }) {
  const [initial] = useState(load);
  const [data, setData] = useState<Stored>(initial.data);

  const persist = useCallback((next: Stored) => {
    try {
      localStorage.setItem(KEY, JSON.stringify(next));
    } catch {
      return false;
    }
    setData(next);
    return true;
  }, []);
  const saveProfile = useCallback((profile: LocalProfile) => persist({ ...data, profile }), [data, persist]);
  const savePrefs = useCallback((prefs: TravelPrefs) => persist({ ...data, prefs }), [data, persist]);

  const v = useMemo(() => ({ profile: data.profile, prefs: data.prefs, loadError: initial.error, saveProfile, savePrefs }),
    [data, initial.error, saveProfile, savePrefs]);
  return <C.Provider value={v}>{children}</C.Provider>;
}
