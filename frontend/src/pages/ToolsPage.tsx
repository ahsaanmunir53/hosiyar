import { useEffect, useState, type FormEvent } from "react";
import { useLocation } from "react-router-dom";
import {
  ApiError,
  checkReceipt,
  familyCode,
  familyRemove,
  familyStatus,
  lookupValue,
  type LookupResult,
  type ReceiptResult,
} from "../api";
import Captcha, { captchaEnabled } from "../components/Captcha";
import { useLang } from "../i18n";

const STATUS_TONE: Record<LookupResult["status"], string> = {
  known_scam: "bad",
  reported: "bad",
  lookalike: "bad",
  no_reports: "muted",
  official: "good",
};

function Lookup() {
  const { t, pick } = useLang();
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<LookupResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [captcha, setCaptcha] = useState<string | null>(null);
  const [reset, setReset] = useState(0);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!value.trim()) return;
    if (captchaEnabled && !captcha) return setError(t("captcha_needed"));
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await lookupValue(value.trim(), captcha));
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 0 ? err.message : t("err_network"));
    } finally {
      setBusy(false);
      setReset((n) => n + 1);
    }
  }

  return (
    <section className="panel tool">
      <h2 className="panel__title">{t("lookup_title")}</h2>
      <form className="inline-form" onSubmit={submit}>
        <input type="text" value={value} onChange={(e) => setValue(e.target.value)} placeholder={t("lookup_placeholder")} dir="ltr" maxLength={500} />
        <button type="submit" className="btn btn--primary" disabled={busy}>
          {busy ? t("checking") : t("lookup_button")}
        </button>
      </form>
      <Captcha onToken={setCaptcha} resetKey={reset} />
      <p className="field__hint">{t("lookup_private")}</p>
      {error && <p className="form-error">{error}</p>}
      {result && (
        <div className={`lookup lookup--${STATUS_TONE[result.status]}`} aria-live="polite">
          <p className="lookup__value" dir="ltr">
            {result.display}
          </p>
          <p className="lookup__msg">{pick(result.message)}</p>
          {result.shortcode_note && <p className="field__hint">{pick(result.shortcode_note)}</p>}
          <p className="lookup__counts">
            <span>
              <strong>{result.confirmed_reports}</strong> {t("lookup_confirmed")}
            </span>
          </p>
        </div>
      )}
    </section>
  );
}

function Receipt() {
  const { t, pick } = useLang();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ReceiptResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [captcha, setCaptcha] = useState<string | null>(null);
  const [reset, setReset] = useState(0);
  const [expectedAmount, setExpectedAmount] = useState("");
  const [myAccount, setMyAccount] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return setError(t("err_file"));
    if (captchaEnabled && !captcha) return setError(t("captcha_needed"));
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await checkReceipt(file, file.name, captcha, { expectedAmount, myAccount }));
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 0 ? err.message : t("err_network"));
    } finally {
      setBusy(false);
      setReset((n) => n + 1);
    }
  }

  const fields = result
    ? Object.entries(result.fields).filter(([k, v]) => v && k !== "visual_issues" && (typeof v === "string" ? v.trim() : true))
    : [];
  return (
    <section className="panel tool">
      <h2 className="panel__title">
        {t("receipt_title")} <span className="tag tag--warn">{t("experimental")}</span>
      </h2>
      <p className="muted">{t("receipt_sub")}</p>
      <form className="inline-form" onSubmit={submit}>
        <label className="dropzone dropzone--inline">
          <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <span>{file ? `${t("file_chosen")}: ${file.name}` : t("receipt_pick")}</span>
        </label>
        <div className="receipt-extra">
          <label className="field">
            <span className="field__label">{t("receipt_expected")}</span>
            <input type="text" inputMode="decimal" value={expectedAmount} onChange={(e) => setExpectedAmount(e.target.value)}
              placeholder="2500" dir="ltr" maxLength={40} />
          </label>
          <label className="field">
            <span className="field__label">{t("receipt_mine")}</span>
            <input type="text" inputMode="numeric" value={myAccount} onChange={(e) => setMyAccount(e.target.value)}
              placeholder="0300 1234567 / 4567" dir="ltr" maxLength={40} autoComplete="off" />
          </label>
          <p className="field__hint">{t("receipt_private")}</p>
        </div>
        <button type="submit" className="btn btn--primary" disabled={busy}>
          {busy ? t("checking") : t("receipt_button")}
        </button>
      </form>
      <Captcha onToken={setCaptcha} resetKey={reset} />
      {error && <p className="form-error">{error}</p>}
      {result && (
        <div className="receipt" aria-live="polite">
          {result.unavailable && <p className="notice">{result.unavailable}</p>}
          {result.assessment === "likely_fake" && <p className="notice notice--bad" role="alert">{t("receipt_likely_fake")}</p>}
          {result.assessment === "suspicious" && <p className="notice">{t("receipt_suspicious")}</p>}
          {fields.length > 0 && (
            <>
              <h3>{t("receipt_fields")}</h3>
              <dl className="facts">
                {fields.map(([k, v]) => (
                  <div key={k} className="facts__row">
                    <dt>{k.replace(/_/g, " ")}</dt>
                    <dd dir="auto">{Array.isArray(v) ? v.join(", ") : v}</dd>
                  </div>
                ))}
              </dl>
            </>
          )}
          {!result.unavailable && (
            <>
              <h3>{t("receipt_findings")}</h3>
              {result.findings.length ? (
                <ul className="findings">
                  {result.findings.map((f, i) => (
                    <li key={i} className={`findings__item findings__item--${f.severity}`}>
                      {pick(f.text)}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted">{t("receipt_none")}</p>
              )}
            </>
          )}
          <ol className="steps">
            {result.advice.map((a, i) => (
              <li key={i} className={i === 0 ? "is-urgent" : ""}>
                {pick(a)}
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}

function Family() {
  const { t } = useLang();
  const [status, setStatus] = useState<{ guardians: number; available: boolean; bot: string | null } | null>(null);
  const [code, setCode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    familyStatus()
      .then((s) => {
        setStatus(s);
        if (s.pending_code) setCode(s.pending_code);
      })
      .catch(() => setStatus({ guardians: 0, available: false, bot: null }));
  }, []);

  async function getCode() {
    setError(null);
    try {
      const r = await familyCode();
      setCode(r.code);
      setStatus((s) => (s ? { ...s, bot: r.bot } : s));
    } catch (err) {
      setError(err instanceof ApiError && err.status !== 0 ? err.message : t("err_network"));
    }
  }

  async function stop() {
    await familyRemove().catch(() => undefined);
    setCode(null);
    setStatus((s) => (s ? { ...s, guardians: 0 } : s));
  }

  return (
    <section className="panel tool">
      <h2 className="panel__title">{t("family_title")}</h2>
      <p className="muted">{t("family_sub")}</p>
      {status && !status.available && <p className="notice">{t("family_unavailable")}</p>}
      {status?.available && (
        <>
          {status.guardians > 0 && (
            <p className="notice notice--good">
              {status.guardians} {t("family_linked")}
            </p>
          )}
          {code ? (
            <div className="familycode">
              <span className="field__label">{t("family_code_is")}</span>
              <p className="familycode__code" dir="ltr">
                {code}
              </p>
              <p>{t("family_how")}</p>
              <code dir="ltr" className="familycode__cmd">
                /guard {code}
              </code>
              {status.bot && (
                <p>
                  <a href={`https://t.me/${status.bot}`} target="_blank" rel="noreferrer" dir="ltr">
                    t.me/{status.bot}
                  </a>
                </p>
              )}
            </div>
          ) : (
            <button type="button" className="btn btn--primary" onClick={getCode}>
              {t("family_get")}
            </button>
          )}
          {(status.guardians > 0 || code) && (
            <button type="button" className="btn btn--ghost btn--small" onClick={stop}>
              {t("family_stop")}
            </button>
          )}
        </>
      )}
      {error && <p className="form-error">{error}</p>}
    </section>
  );
}

interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: string }>;
}

function Install() {
  const { t } = useLang();
  const [prompt, setPrompt] = useState<InstallPromptEvent | null>(null);
  const [installed, setInstalled] = useState(false);
  const isIos = /iphone|ipad|ipod/i.test(navigator.userAgent);

  useEffect(() => {
    const onPrompt = (e: Event) => {
      e.preventDefault();
      setPrompt(e as InstallPromptEvent);
    };
    const onInstalled = () => setInstalled(true);
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    if (window.matchMedia?.("(display-mode: standalone)").matches) setInstalled(true);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  return (
    <section className="panel tool" id="install">
      <h2 className="panel__title">{t("install_title")}</h2>
      <ul className="install">
        <li>
          <h3>{t("install_pwa")}</h3>
          <p>{t("install_pwa_sub")}</p>
          {installed ? (
            <span className="tag tag--good">{t("install_done")}</span>
          ) : prompt ? (
            <button type="button" className="btn btn--ghost btn--small" onClick={() => prompt.prompt().then(() => setPrompt(null))}>
              {t("install_button")}
            </button>
          ) : (
            isIos && <p className="field__hint">{t("install_ios")}</p>
          )}
        </li>
        <li>
          <h3>{t("install_ext")}</h3>
          <p>{t("install_ext_sub")}</p>
        </li>
        <li>
          <h3>{t("install_tg")}</h3>
          <p>{t("install_tg_sub")}</p>
        </li>
        <li>
          <h3>{t("install_mcp")}</h3>
          <p>{t("install_mcp_sub")}</p>
          <code className="install__code" dir="ltr">
            python app/mcp_server.py
          </code>
        </li>
      </ul>
    </section>
  );
}

export default function ToolsPage() {
  const { t } = useLang();
  const { hash } = useLocation();
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: "smooth" });
  }, [hash]);
  return (
    <main className="page page--tools">
      <header className="pagehead">
        <h1>{t("tools_title")}</h1>
        <p>{t("tools_sub")}</p>
      </header>
      <div className="twocol twocol--top">
        <Lookup />
        <Family />
      </div>
      <Receipt />
      <Install />
    </main>
  );
}
