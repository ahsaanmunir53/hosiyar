import { useEffect, useRef, useState } from "react";

import { onWaking, warmUp } from "../api";
import { useLang } from "../i18n";

type State = "hidden" | "waking" | "ready" | "failed";

/** Bottom bar shown while the free Render server wakes up, with a running count of seconds. */
export default function WakeBar() {
  const { t } = useLang();
  const [state, setState] = useState<State>("hidden");
  const [seconds, setSeconds] = useState(0);
  const started = useRef<number | null>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const off = onWaking((waking) => {
      if (hideTimer.current) clearTimeout(hideTimer.current);
      if (waking) {
        started.current ??= Date.now() - 3500;
        setState("waking");
      } else if (started.current !== null) {
        started.current = null;
        setState("ready");
        hideTimer.current = setTimeout(() => setState("hidden"), 2500);
      }
    });
    warmUp().then((ok) => {
      if (!ok) setState("failed");
    });
    return () => {
      off();
      if (hideTimer.current) clearTimeout(hideTimer.current);
    };
  }, []);

  useEffect(() => {
    if (state !== "waking") return;
    const tick = () => setSeconds(Math.round((Date.now() - (started.current ?? Date.now())) / 1000));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [state]);

  if (state === "hidden") return null;
  return (
    <div className={`wakebar wakebar--${state}`} role="status" aria-live="polite">
      {state === "waking" && (
        <>
          <span className="wakebar__dot" aria-hidden />
          <span className="wakebar__text">{t("wake_bar")}</span>
          <span className="wakebar__secs" aria-hidden>{seconds}s</span>
        </>
      )}
      {state === "ready" && <span className="wakebar__text">{t("wake_ready")}</span>}
      {state === "failed" && (
        <>
          <span className="wakebar__text">{t("wake_failed")}</span>
          <button className="wakebar__retry" onClick={() => {
            setState("hidden");
            warmUp().then((ok) => !ok && setState("failed"));
          }}>{t("wake_retry")}</button>
        </>
      )}
    </div>
  );
}
