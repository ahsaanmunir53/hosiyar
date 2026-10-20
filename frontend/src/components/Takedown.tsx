import { useState } from "react";
import { getTakedown, type TakedownInfo } from "../api";
import { useLang } from "../i18n";

/** Who registered a scam site and how to report it. The site itself is never opened. */
export default function Takedown({ url }: { url: string }) {
  const { t } = useLang();
  const [info, setInfo] = useState<TakedownInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [copied, setCopied] = useState(false);

  async function open() {
    setBusy(true);
    setFailed(false);
    try {
      setInfo(await getTakedown(url));
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  async function copyUrl() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable */
    }
  }

  if (!info) {
    return (
      <button type="button" className="linkbtn" onClick={open} disabled={busy}>
        {busy ? t("takedown_loading") : t("report_site")}
        {failed && ` · ${t("err_network")}`}
      </button>
    );
  }
  return (
    <div className="takedown">
      {info.registrar && (
        <p>
          {t("takedown_registrar")}: <strong>{info.registrar}</strong>
          {info.registered && <span className="muted"> · {info.registered}</span>}
        </p>
      )}
      {info.mailto ? (
        <a className="btn btn--ghost btn--small" href={info.mailto}>
          {t("takedown_email")} ({info.abuse_email})
        </a>
      ) : (
        <p className="field__hint">{t("takedown_no_abuse")}</p>
      )}
      <p className="field__hint">
        {t("takedown_google_tip")}{" "}
        <button type="button" className="linkbtn" onClick={copyUrl} dir="ltr">
          {copied ? t("copied") : url.replace(/^https?:\/\//, "")}
        </button>
      </p>
      <a className="btn btn--ghost btn--small" href={info.google_report_url} target="_blank" rel="noreferrer">
        {t("takedown_google")}
      </a>
    </div>
  );
}
