// Загрузка данных API с состояниями loading / ready / error и повтором.
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/trips";

export type Async<T> = { status: "loading" } | { status: "ready"; data: T } | { status: "error"; error: ApiError };
export function useApi<T>(load: () => Promise<T>, deps: unknown[]): [Async<T>, () => void, (d: T) => void] {
  const [s, setS] = useState<Async<T>>({ status: "loading" });
  const seq = useRef(0);
  const run = useCallback(() => {
    const n = ++seq.current;
    setS({ status: "loading" });
    load().then((data) => { if (n === seq.current) setS({ status: "ready", data }); })
      .catch((e) => { if (n === seq.current) setS({ status: "error", error: e instanceof ApiError ? e : new ApiError(0, "UNKNOWN", "Что-то пошло не так", true) }); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { run(); return () => { seq.current++; }; }, [run]);
  return [s, run, (data) => setS({ status: "ready", data })];
}
