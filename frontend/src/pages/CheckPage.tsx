import { useEffect, useRef, useState } from "react";
import { analyzeEmail, analyzeFile, analyzeText, ApiError, type Analysis } from "../api";
import CheckForm, { type CheckInput } from "../components/CheckForm";
import Result from "../components/Result";
import Seal, { type SealStatus } from "../components/seal/Seal";
import { useLang } from "../i18n";

export interface Submitted {
  text: string;
  sender: string;
  filename: string;
  at: Date;
}

export default function CheckPage({ prefill, note }: { prefill?: string; note?: string }) {
  const { t, lang } = useLang();
  const [busy, setBusy] = useState(false);
  const [slow, setSlow] = useState(false);
  const [result, setResult] = useState<Analysis | null>(null);
  const [submitted, setSubmitted] = useState<Submitted | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [formKey, setFormKey] = useState(0);
  const [captchaReset, setCaptchaReset] = useState(0);
  const resultRef = useRef<HTMLDivElement>(null);

  const status: SealStatus = busy ? "scanning" : result ? result.verdict : "idle";

  useEffect(() => {
    if (!busy) return;
    const id = setTimeout(() => setSlow(true), 5000);
    return () => clearTimeout(id);
  }, [busy]);

  useEffect(() => {
    if (result) resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [result]);

  async function run(input: CheckInput) {
    setBusy(true);
    setSlow(false);
    setError(null);
    setResult(null);
    const common = { share: input.share, language: lang, captcha: input.captcha };
    try {
      let res: Analysis;
      if (input.mode === "text" || input.mode === "qr") {
        res = await analyzeText({ ...common, text: input.text, sender: input.sender, sourceKind: input.mode });
      } else if (input.mode === "email" && !input.file) {
        res = await analyzeEmail({ ...common, raw: input.text });
      } else {
        res = await analyzeFile({ ...common, file: input.file as Blob, filename: input.filename, sender: input.sender });
      }
      setSubmitted({ text: input.text, sender: input.sender, filename: input.filename, at: new Date() });
      setResult(res);
    } catch (e) {
      setError(e instanceof ApiError && e.status !== 0 ? e.message : t("err_network"));
    } finally {
      setBusy(false);
      setSlow(false);
      setCaptchaReset((n) => n + 1);
    }
  }

  return (
    <main className="page page--check">
      <section className="hero">
        <div className="hero__copy">
          <h1 className="hero__title">{t("hero_title")}</h1>
          <p className="hero__sub">{t("hero_sub")}</p>
          {note && <p className="notice notice--lead">{note}</p>}
          <CheckForm key={formKey} busy={busy} onSubmit={run} initialText={formKey === 0 ? prefill : undefined} resetCaptcha={captchaReset} />
          {slow && <p className="notice">{t("waking")}</p>}
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
        </div>
        <div className="hero__seal">
          <Seal status={status} />
        </div>
      </section>

      <div ref={resultRef} className="result-anchor">
        {result && (
          <Result
            result={result}
            submitted={submitted}
            onReset={() => {
              setResult(null);
              setSubmitted(null);
              setFormKey((k) => k + 1);
              window.scrollTo({ top: 0, behavior: "smooth" });
            }}
          />
        )}
      </div>
    </main>
  );
}
