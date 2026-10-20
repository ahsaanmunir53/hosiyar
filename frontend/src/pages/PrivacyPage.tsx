import { useEffect, useState } from "react";
import { forgetMe, getPrivacy, type I18n, type PrivacyInfo } from "../api";
import { useLang } from "../i18n";

const SECTIONS: { title: I18n; body: I18n }[] = [
  {
    title: { en: "Removed first", ur: "سب سے پہلے ہٹایا جاتا ہے", roman: "Sab se pehle hataya jata hai" },
    body: {
      en: "Phone numbers, CNICs, card numbers, IBANs, bank account numbers, email addresses and one-time codes are replaced with placeholders such as [PHONE_1] before the message is analysed, sent to an AI model or stored.",
      ur: "پیغام جانچنے، اے آئی کو بھیجنے یا محفوظ کرنے سے پہلے فون نمبر، شناختی کارڈ، کارڈ نمبر، آئی بین، بینک اکاؤنٹ، ای میل اور کوڈ [PHONE_1] جیسے نشانات سے بدل دیے جاتے ہیں۔",
      roman: "Message check karne, AI ko bhejne ya save karne se pehle phone number, CNIC, card number, IBAN, bank account, email aur code [PHONE_1] jaise nishanat se badal diye jate hain.",
    },
  },
  {
    title: { en: "Sent to AI providers", ur: "اے آئی کمپنیوں کو کیا جاتا ہے", roman: "AI companies ko kya jata hai" },
    body: {
      en: "Only the redacted text goes to Groq and Google Gemini. Screenshots and voice notes have to be read before they can be redacted, so they are sent as they are: crop out codes and account numbers first. Free tiers may let the provider use what is sent to improve its products.",
      ur: "صرف ذاتی معلومات کے بغیر متن گروق اور گوگل جیمنائی کو جاتا ہے۔ اسکرین شاٹ اور وائس نوٹ پڑھنے سے پہلے صاف نہیں ہو سکتے، اس لیے ویسے ہی جاتے ہیں: پہلے کوڈ اور اکاؤنٹ نمبر کاٹ دیں۔ مفت سروس میں کمپنی بھیجا گیا مواد اپنی بہتری کے لیے استعمال کر سکتی ہے۔",
      roman: "Sirf personal details ke baghair text Groq aur Google Gemini ko jata hai. Screenshot aur voice note parhne se pehle saaf nahi ho sakte, is liye waise hi jate hain: pehle code aur account number crop kar dein. Free service mein company bheja gaya data apni behtari ke liye use kar sakti hai.",
    },
  },
  {
    title: { en: "Kept for each check", ur: "ہر چیک کا کیا رکھا جاتا ہے", roman: "Har check ka kya rakha jata hai" },
    body: {
      en: "The verdict, score, scam type, language and which rules matched. The redacted message stays with the check so you can ask follow-up questions, and is deleted with the check record. The raw message is never stored. If you tick \"share\", the redacted message also goes to reviewers.",
      ur: "نتیجہ، اسکور، فراڈ کی قسم، زبان اور کون سے قواعد لگے۔ ذاتی معلومات کے بغیر پیغام چیک کے ساتھ رہتا ہے تاکہ آپ بعد میں سوال پوچھ سکیں، اور چیک کے ریکارڈ کے ساتھ حذف ہو جاتا ہے۔ اصل پیغام کبھی محفوظ نہیں ہوتا۔ اگر آپ \"شیئر\" پر نشان لگائیں تو یہی پیغام جائزہ کاروں کو بھی جاتا ہے۔",
      roman: "Natija, score, fraud ki qisam, zuban aur kaun se rules lage. Personal details ke baghair message check ke saath rehta hai taake aap baad mein sawal pooch sakein, aur check ke record ke saath delete ho jata hai. Asal message kabhi save nahi hota. Agar aap \"share\" par nishan lagayen to yehi message reviewers ko bhi jata hai.",
    },
  },
  {
    title: { en: "Fingerprints, not numbers", ur: "نمبر نہیں، فنگر پرنٹ", roman: "Number nahi, fingerprint" },
    body: {
      en: "To notice a scam number that keeps coming back, each number is turned into a one-way keyed fingerprint (HMAC). The number cannot be read back from it. A number only counts as reported after a reviewer approves it or several different Telegram accounts report it, so nobody can get an innocent number flagged from a browser.",
      ur: "بار بار آنے والا فراڈ نمبر پہچاننے کے لیے ہر نمبر کو ایک طرفہ فنگر پرنٹ (HMAC) میں بدلا جاتا ہے۔ اس سے نمبر واپس نہیں پڑھا جا سکتا۔ نمبر تب ہی رپورٹ شدہ مانا جاتا ہے جب جائزہ کار منظور کرے یا کئی مختلف ٹیلی گرام اکاؤنٹ رپورٹ کریں، تاکہ کوئی براؤزر سے کسی بے قصور کا نمبر نشان زد نہ کروا سکے۔",
      roman: "Baar baar aane wala fraud number pehchanne ke liye har number ko one-way fingerprint (HMAC) mein badla jata hai. Is se number wapas nahi parha ja sakta. Number tab hi reported mana jata hai jab reviewer approve kare ya kai mukhtalif Telegram accounts report karein, taake koi browser se kisi be-qusoor ka number flag na karwa sake.",
    },
  },
  {
    title: { en: "Never stored", ur: "کبھی محفوظ نہیں ہوتا", roman: "Kabhi save nahi hota" },
    body: {
      en: "Numbers and websites you look up, payment screenshots you check, QR codes (they are read on your device) and complaint packs (made on your device).",
      ur: "تلاش کیے گئے نمبر اور ویب سائٹس، چیک کیے گئے ادائیگی کے اسکرین شاٹ، کیو آر کوڈ (آپ کے آلے پر پڑھے جاتے ہیں) اور شکایت پیک (آپ کے آلے پر بنتے ہیں)۔",
      roman: "Dhoonde gaye number aur websites, check kiye gaye payment screenshots, QR codes (aap ke device par parhe jate hain) aur shikayat pack (aap ke device par bante hain).",
    },
  },
  {
    title: { en: "Who sees what", ur: "کون کیا دیکھتا ہے", roman: "Kaun kya dekhta hai" },
    body: {
      en: "Reviewers see redacted shared reports. A shared message appears on the public trends page only after a reviewer approves it. Everyone can see counts, scam types and confirmed scam websites. Exports for CERTs and police (STIX) contain confirmed websites and links without query strings, never number fingerprints.",
      ur: "جائزہ کار ذاتی معلومات کے بغیر شیئر کی گئی رپورٹس دیکھتے ہیں۔ شیئر کیا گیا پیغام عوامی صفحے پر صرف جائزہ کار کی منظوری کے بعد آتا ہے۔ سب لوگ گنتی، فراڈ کی اقسام اور تصدیق شدہ فراڈ ویب سائٹس دیکھ سکتے ہیں۔ سرٹ اور پولیس کے لیے برآمد (STIX) میں صرف تصدیق شدہ ویب سائٹس اور لنک ہوتے ہیں، نمبر کے فنگر پرنٹ کبھی نہیں۔",
      roman: "Reviewers personal details ke baghair share ki gayi reports dekhte hain. Share kiya gaya message public safhe par sirf reviewer ki approval ke baad aata hai. Sab log ginti, fraud ki aqsam aur tasdeeq shuda fraud websites dekh sakte hain. CERT aur police ke liye export (STIX) mein sirf tasdeeq shuda websites aur links hote hain, number ke fingerprint kabhi nahi.",
    },
  },
  {
    title: { en: "In your browser", ur: "آپ کے براؤزر میں", roman: "Aap ke browser mein" },
    body: {
      en: "A random ID and your language choice are saved in this browser. The ID lets Hoshiyar remember your reply language and lets you delete your checks below. It is not linked to your name or number.",
      ur: "اس براؤزر میں ایک بے ترتیب آئی ڈی اور آپ کی زبان محفوظ ہوتی ہے۔ آئی ڈی سے ہوشیار آپ کی زبان یاد رکھتا ہے اور آپ نیچے اپنے چیک حذف کر سکتے ہیں۔ یہ آپ کے نام یا نمبر سے منسلک نہیں۔",
      roman: "Is browser mein ek random ID aur aap ki zuban save hoti hai. ID se Hoshiyar aap ki zuban yaad rakhta hai aur aap neeche apne checks delete kar sakte hain. Yeh aap ke naam ya number se link nahi.",
    },
  },
];

const RETENTION_LABELS: Record<string, I18n> = {
  checks: { en: "Check records and their follow-up threads", ur: "چیک کا ریکارڈ اور سوال جواب", roman: "Check ka record aur sawal jawab" },
  rejected_reports: { en: "Rejected shared reports", ur: "رد شدہ رپورٹس", roman: "Radd shuda reports" },
  pending_reports: { en: "Unreviewed shared reports", ur: "بغیر جائزہ رپورٹس", roman: "Baghair review reports" },
  ai_cache: { en: "Cached AI readings", ur: "اے آئی کی محفوظ ریڈنگ", roman: "AI ki cached reading" },
  alerts: { en: "Sent alerts", ur: "بھیجے گئے الرٹ", roman: "Bheje gaye alerts" },
  family_codes_hours: { en: "Unused family codes", ur: "غیر استعمال شدہ فیملی کوڈ", roman: "Ghair istemal shuda family codes" },
};

export default function PrivacyPage() {
  const { t, pick } = useLang();
  const [info, setInfo] = useState<PrivacyInfo | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [done, setDone] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getPrivacy().then(setInfo).catch(() => setInfo(null));
  }, []);

  async function forget() {
    setError(null);
    try {
      const r = await forgetMe();
      setDone(r.deleted.analyses ?? 0);
      setConfirming(false);
    } catch {
      setError(t("err_network"));
    }
  }

  return (
    <main className="page page--how">
      <header className="pagehead">
        <h1>{t("privacy_title")}</h1>
        <p>{t("privacy_sub")}</p>
      </header>
      <section className="panel">
        <ul className="privacy">
          {SECTIONS.map((s) => (
            <li key={s.title.en}>
              <h3>{pick(s.title)}</h3>
              <p>{pick(s.body)}</p>
            </li>
          ))}
        </ul>
      </section>
      {info && (
        <section className="panel">
          <h2 className="panel__title">{t("retention_title")}</h2>
          <div className="table-wrap">
            <table className="datatable">
              <tbody>
                {Object.entries(info.retention_days).map(([k, v]) => (
                  <tr key={k}>
                    <td>{RETENTION_LABELS[k] ? pick(RETENTION_LABELS[k]) : k}</td>
                    <td>
                      {v} {k.endsWith("hours") ? t("hours") : t("days")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="facts__tags">
            {Object.entries(info.providers).map(([k, v]) => (
              <span key={k} className={`tag ${v ? "" : "tag--muted"}`}>
                {k.replace(/_/g, " ")}: {v ? t("on") : t("off")}
              </span>
            ))}
          </p>
        </section>
      )}
      <section className="panel">
        <h2 className="panel__title">{t("forget_title")}</h2>
        <p className="muted">{t("forget_sub")}</p>
        {done !== null ? (
          <p className="notice notice--good">
            {t("forget_done")} {done}
          </p>
        ) : confirming ? (
          <div className="form-actions">
            <button type="button" className="btn btn--danger" onClick={forget}>
              {t("forget_confirm")}
            </button>
            <button type="button" className="btn btn--ghost" onClick={() => setConfirming(false)}>
              {t("close")}
            </button>
          </div>
        ) : (
          <button type="button" className="btn btn--ghost" onClick={() => setConfirming(true)}>
            {t("forget_button")}
          </button>
        )}
        {error && <p className="form-error">{error}</p>}
      </section>
    </main>
  );
}
