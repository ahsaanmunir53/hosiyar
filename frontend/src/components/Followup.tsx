import { useState, type FormEvent } from "react";
import { ApiError, askFollowup, type FollowupAnswer } from "../api";
import { useLang } from "../i18n";

export default function Followup({ threadId }: { threadId: string }) {
  const { t, lang } = useLang();
  const [question, setQuestion] = useState("");
  const [answers, setAnswers] = useState<FollowupAnswer[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask(q: string) {
    if (!q.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await askFollowup(threadId, q.trim(), lang);
      setAnswers((a) => [...a, res.answer]);
      setQuestion("");
    } catch (e) {
      setError(e instanceof ApiError && e.status !== 0 ? e.message : t("err_network"));
    } finally {
      setBusy(false);
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    void ask(question);
  }

  return (
    <section className="followup">
      <h3>{t("followup_title")}</h3>
      {answers.length > 0 && (
        <ul className="followup__thread">
          {answers.map((a, i) => (
            <li key={i}>
              <p className="followup__q" dir="auto">
                {a.question}
              </p>
              <p className="followup__a" dir="auto">
                {a.answer}
              </p>
            </li>
          ))}
        </ul>
      )}
      <div className="examples__list">
        {(["followup_suggest_1", "followup_suggest_2", "followup_suggest_3"] as const).map((k) => (
          <button key={k} type="button" className="chip" onClick={() => void ask(t(k))} disabled={busy}>
            {t(k)}
          </button>
        ))}
      </div>
      <form className="followup__form" onSubmit={submit}>
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={t("followup_placeholder")}
          maxLength={500}
          dir="auto"
          aria-label={t("followup_title")}
        />
        <button type="submit" className="btn btn--primary" disabled={busy || !question.trim()}>
          {busy ? t("checking") : t("followup_button")}
        </button>
      </form>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
