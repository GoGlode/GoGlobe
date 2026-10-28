// Короткое сообщение внизу экрана («Ссылка скопирована»). Использование: const { show, toast } = useToast(); … {toast}
import { useRef, useState } from "react";

export function useToast() {
  const [msg, setMsg] = useState<string | null>(null);
  const timer = useRef<number>();
  const show = (m: string) => { setMsg(m); window.clearTimeout(timer.current); timer.current = window.setTimeout(() => setMsg(null), 2400); };
  return { show, toast: msg ? <div className="toast" role="status">{msg}</div> : null };
}
