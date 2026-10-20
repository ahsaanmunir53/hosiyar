import { useMemo, useState } from "react";
import type { Analysis, Lang } from "../api";
import { useLang } from "../i18n";
import type { Submitted } from "../pages/CheckPage";

const L: Record<string, Record<Lang, string>> = {
  heading: { en: "SCAM COMPLAINT PACK", ur: "فراڈ شکایت پیک", roman: "FRAUD SHIKAYAT PACK" },
  when: { en: "Date and time I checked it", ur: "چیک کرنے کی تاریخ اور وقت", roman: "Check karne ki tareekh aur waqt" },
  sender: { en: "Sender (number or name)", ur: "بھیجنے والا (نمبر یا نام)", roman: "Bhejne wala (number ya naam)" },
  file: { en: "File", ur: "فائل", roman: "File" },
  message: { en: "The message, exactly as received", ur: "پیغام، بالکل جیسا ملا", roman: "Message, bilkul jaisa mila" },
  verdict: { en: "Hoshiyar result", ur: "ہوشیار کا نتیجہ", roman: "Hoshiyar ka natija" },
  reasons: { en: "Warning signs", ur: "خطرے کی علامات", roman: "Khatre ki alamat" },
  links: { en: "Links in the message", ur: "پیغام میں لنک", roman: "Message mein links" },
  where: { en: "Where to report", ur: "کہاں شکایت کریں", roman: "Kahan shikayat karein" },
  attach: {
    en: "Attach: screenshots of the message and sender, any payment receipts or transaction IDs, and your CNIC copy if the portal asks for it.",
    ur: "ساتھ لگائیں: پیغام اور بھیجنے والے کے اسکرین شاٹ، ادائیگی کی رسید یا ٹرانزیکشن آئی ڈی، اور اگر پورٹل مانگے تو شناختی کارڈ کی کاپی۔",
    roman: "Saath lagayen: message aur bhejne wale ke screenshots, payment ki raseed ya transaction ID, aur agar portal mange to CNIC ki copy.",
  },
  not_given: { en: "(not given)", ur: "(نہیں دیا)", roman: "(nahi diya)" },
  footer: {
    en: "Hoshiyar gives guidance, not legal advice. Keep the original messages on your phone.",
    ur: "ہوشیار رہنمائی دیتا ہے، قانونی مشورہ نہیں۔ اصل پیغامات اپنے فون میں محفوظ رکھیں۔",
    roman: "Hoshiyar rehnumai deta hai, qanooni mashwara nahi. Asal messages apne phone mein mehfooz rakhein.",
  },
};

function buildPack(result: Analysis, submitted: Submitted | null, lang: Lang, verdictLabel: string): string {
  const lines: string[] = [L.heading[lang], "=".repeat(28), ""];
  const when = (submitted?.at ?? new Date()).toLocaleString(lang === "ur" ? "ur-PK" : "en-GB");
  lines.push(`${L.when[lang]}: ${when}`);
  lines.push(`${L.sender[lang]}: ${submitted?.sender || L.not_given[lang]}`);
  if (submitted?.filename) lines.push(`${L.file[lang]}: ${submitted.filename}`);
  lines.push("", `${L.message[lang]}:`, submitted?.text?.trim() || result.analyzed_text, "");
  lines.push(`${L.verdict[lang]}: ${verdictLabel} (${result.score}/100), ${result.category.label[lang]}`);
  const reasons = result.reasons.filter((r) => r.weight > 0);
  if (reasons.length) {
    lines.push("", `${L.reasons[lang]}:`);
    reasons.forEach((r) => lines.push(`- ${r.title[lang]}`));
  }
  if (result.links.length) {
    lines.push("", `${L.links[lang]}:`);
    result.links.forEach((l) => lines.push(`- ${l.url.replace(/\./g, "[.]")}`));
  }
  lines.push("", `${L.where[lang]}:`);
  lines.push("- NCCIA: https://www.nccia.gov.pk");
  lines.push("- PTA: https://complaint.pta.gov.pk · 0800-55055");
  lines.push("- FIA: 1799");
  if (["bank_wallet", "investment", "loan", "job_task"].includes(result.category.id)) lines.push("- State Bank of Pakistan: 111-727-273");
  lines.push("", L.attach[lang], "", L.footer[lang]);
  return lines.join("\n");
}

/** A ready-to-file complaint, built on the device from the original message. Nothing is uploaded. */
export default function ComplaintPack({ result, submitted }: { result: Analysis; submitted: Submitted | null }) {
  const { t, lang } = useLang();
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const text = useMemo(() => buildPack(result, submitted, lang, t(`verdict_${result.verdict}`)), [result, submitted, lang, t]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  function download() {
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `hoshiyar-complaint-${new Date().toISOString().slice(0, 10)}.txt`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  if (!open) {
    return (
      <button type="button" className="btn btn--ghost btn--small" onClick={() => setOpen(true)}>
        {t("complaint_pack")}
      </button>
    );
  }
  return (
    <section className="panel complaint print-area" aria-label={t("complaint_title")}>
      <div className="complaint__head">
        <h3>{t("complaint_title")}</h3>
        <button type="button" className="btn btn--ghost btn--small no-print" onClick={() => setOpen(false)}>
          {t("close")}
        </button>
      </div>
      <p className="field__hint no-print">{t("complaint_sub")}</p>
      <pre className="complaint__text" dir="auto">
        {text}
      </pre>
      <div className="complaint__actions no-print">
        <button type="button" className="btn btn--ghost btn--small" onClick={copy}>
          {copied ? t("copied") : t("copy")}
        </button>
        <button type="button" className="btn btn--ghost btn--small" onClick={download}>
          {t("download_txt")}
        </button>
        <button type="button" className="btn btn--ghost btn--small" onClick={() => window.print()}>
          {t("print")}
        </button>
      </div>
    </section>
  );
}
