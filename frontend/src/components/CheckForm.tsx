import { useEffect, useRef, useState, type FormEvent } from "react";
import { EXAMPLES } from "../examples";
import { useLang } from "../i18n";
import { decodeQr, previewPaymentQr } from "../lib/qr";
import Captcha, { captchaEnabled } from "./Captcha";

export type Mode = "text" | "image" | "audio" | "qr" | "pdf" | "email";

export interface CheckInput {
  mode: Mode;
  text: string;
  sender: string;
  share: boolean;
  file: Blob | null;
  filename: string;
  captcha: string | null;
}

interface Props {
  busy: boolean;
  onSubmit: (input: CheckInput) => void;
  initialText?: string;
  resetCaptcha: number;
}

export default function CheckForm({ busy, onSubmit, initialText, resetCaptcha }: Props) {
  const { t, pick } = useLang();
  const [mode, setMode] = useState<Mode>("text");
  const [text, setText] = useState(initialText ?? "");
  const [sender, setSender] = useState("");
  const [share, setShare] = useState(false);
  const [file, setFile] = useState<Blob | null>(null);
  const [filename, setFilename] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const [qrText, setQrText] = useState<string | null>(null);
  const [captcha, setCaptcha] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);

  useEffect(() => () => recorder.current?.stream.getTracks().forEach((tr) => tr.stop()), []);

  function switchMode(next: Mode) {
    setMode(next);
    setError(null);
    setFile(null);
    setFilename("");
    setQrText(null);
  }

  function pickFile(f: File | undefined) {
    if (!f) return;
    setFile(f);
    setFilename(f.name);
    setError(null);
  }

  async function pickQr(f: File | undefined) {
    if (!f) return;
    setFilename(f.name);
    setQrText(null);
    try {
      const decoded = await decodeQr(f);
      if (decoded) {
        setQrText(decoded);
        setError(null);
      } else setError(t("qr_none"));
    } catch {
      setError(t("qr_none"));
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (mode === "text" && !text.trim()) return setError(t("err_empty"));
    if (mode === "email" && !text.trim() && !file) return setError(t("err_email"));
    if (mode === "qr" && !qrText) return setError(filename ? t("qr_none") : t("err_file"));
    if (["image", "audio", "pdf"].includes(mode) && !file) return setError(t("err_file"));
    if (captchaEnabled && !captcha) return setError(t("captcha_needed"));
    setError(null);
    const body = mode === "qr" ? (qrText ?? "") : text.trim();
    onSubmit({ mode, text: body, sender: sender.trim(), share, file, filename, captcha });
  }

  async function toggleRecording() {
    if (recording) {
      recorder.current?.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const type = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "audio/ogg";
      const rec = new MediaRecorder(stream, { mimeType: type });
      chunks.current = [];
      rec.ondataavailable = (ev) => ev.data.size && chunks.current.push(ev.data);
      rec.onstop = () => {
        stream.getTracks().forEach((tr) => tr.stop());
        setFile(new Blob(chunks.current, { type }));
        setFilename(type === "audio/webm" ? "recording.webm" : "recording.ogg");
        setRecording(false);
      };
      recorder.current = rec;
      rec.start();
      setRecording(true);
      setError(null);
    } catch {
      setError(t("audio_denied"));
    }
  }

  const tabs: { id: Mode; label: string }[] = [
    { id: "text", label: t("tab_text") },
    { id: "image", label: t("tab_image") },
    { id: "audio", label: t("tab_audio") },
    { id: "qr", label: t("tab_qr") },
    { id: "pdf", label: t("tab_pdf") },
    { id: "email", label: t("tab_email") },
  ];
  const payment = qrText ? previewPaymentQr(qrText) : null;

  return (
    <form className="checkform" onSubmit={submit} aria-busy={busy}>
      <div className="segmented segmented--scroll" role="tablist" aria-label={t("input_label")}>
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={mode === tab.id}
            className={mode === tab.id ? "is-active" : ""}
            onClick={() => switchMode(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {mode === "text" && (
        <label className="field">
          <span className="field__label">{t("input_label")}</span>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={t("input_placeholder")}
            rows={6}
            maxLength={4000}
            dir="auto"
          />
        </label>
      )}

      {mode === "image" && (
        <div className="field">
          <label className="dropzone">
            <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => pickFile(e.target.files?.[0])} />
            <span>{filename ? `${t("file_chosen")}: ${filename}` : t("image_drop")}</span>
          </label>
          <p className="field__hint">{t("image_tip")}</p>
        </div>
      )}

      {mode === "audio" && (
        <div className="field">
          <div className="audio-row">
            <button type="button" className={`btn btn--ghost ${recording ? "is-recording" : ""}`} onClick={toggleRecording}>
              <span className="rec-dot" aria-hidden="true" />
              {recording ? t("audio_stop") : t("audio_record")}
            </button>
            <label className="dropzone dropzone--inline">
              <input type="file" accept="audio/*,.ogg,.opus,.m4a" onChange={(e) => pickFile(e.target.files?.[0])} />
              <span>{t("audio_pick")}</span>
            </label>
          </div>
          {filename && <p className="field__hint">{filename.startsWith("recording") ? t("audio_ready") : `${t("file_chosen")}: ${filename}`}</p>}
        </div>
      )}

      {mode === "qr" && (
        <div className="field">
          <label className="dropzone">
            <input type="file" accept="image/*" capture="environment" onChange={(e) => pickQr(e.target.files?.[0])} />
            <span>{filename ? `${t("file_chosen")}: ${filename}` : t("qr_drop")}</span>
          </label>
          <p className="field__hint">{t("qr_tip")}</p>
          {qrText && (
            <div className={`qrpreview ${payment ? "qrpreview--pay" : ""}`}>
              <span className="field__label">{payment ? t("qr_payment_title") : t("qr_found")}</span>
              {payment ? (
                <>
                  <p>{t("qr_payment_body")}</p>
                  <p className="qrpreview__who">
                    {t("qr_merchant")}: <strong>{payment.merchant ?? "—"}</strong>
                    {payment.amount && (
                      <>
                        {" · "}
                        {t("qr_amount")}: <bdi dir="ltr">{payment.amount}</bdi>
                      </>
                    )}
                  </p>
                </>
              ) : (
                <code dir="ltr">{qrText.slice(0, 300)}</code>
              )}
            </div>
          )}
        </div>
      )}

      {mode === "pdf" && (
        <div className="field">
          <label className="dropzone">
            <input type="file" accept="application/pdf,.pdf" onChange={(e) => pickFile(e.target.files?.[0])} />
            <span>{filename ? `${t("file_chosen")}: ${filename}` : t("pdf_drop")}</span>
          </label>
          <p className="field__hint">{t("pdf_tip")}</p>
        </div>
      )}

      {mode === "email" && (
        <div className="field">
          <label className="field">
            <span className="field__label">{t("email_label")}</span>
            <textarea
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                if (e.target.value) {
                  setFile(null);
                  setFilename("");
                }
              }}
              placeholder={"From: …\nSubject: …\nAuthentication-Results: …\n\n…"}
              rows={7}
              dir="ltr"
              spellCheck={false}
              className="mono"
            />
          </label>
          <p className="field__hint">{t("email_help")}</p>
          <label className="dropzone dropzone--inline">
            <input
              type="file"
              accept=".eml,message/rfc822"
              onChange={(e) => {
                pickFile(e.target.files?.[0]);
                setText("");
              }}
            />
            <span>{filename ? `${t("file_chosen")}: ${filename}` : t("email_pick")}</span>
          </label>
        </div>
      )}

      {mode !== "email" && mode !== "pdf" && (
        <label className="field field--narrow">
          <span className="field__label">{t("sender_label")}</span>
          <input type="text" value={sender} onChange={(e) => setSender(e.target.value)} placeholder={t("sender_hint")} maxLength={64} dir="auto" />
        </label>
      )}

      <label className="check">
        <input type="checkbox" checked={share} onChange={(e) => setShare(e.target.checked)} />
        <span>{t("share_label")}</span>
      </label>

      <Captcha onToken={setCaptcha} resetKey={resetCaptcha} />

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      <div className="form-actions">
        <button type="submit" className="btn btn--primary" disabled={busy}>
          {busy ? t("checking") : t("check_button")}
        </button>
      </div>

      {mode === "text" && (
        <div className="examples">
          <span className="examples__label">{t("examples")}</span>
          <div className="examples__list">
            {EXAMPLES.map((ex) => (
              <button
                key={ex.id}
                type="button"
                className="chip"
                onClick={() => {
                  setText(ex.text);
                  setSender(ex.sender ?? "");
                  setError(null);
                }}
              >
                {pick(ex.label)}
              </button>
            ))}
          </div>
        </div>
      )}
    </form>
  );
}
