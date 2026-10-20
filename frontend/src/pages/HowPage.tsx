import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getChannels, getQuality, getRules, type Channel, type I18n, type Quality, type RuleBookEntry } from "../api";
import { useLang } from "../i18n";

const PIPELINE: { title: I18n; body: I18n; by: "rules" | "ai" | "agent" }[] = [
  {
    by: "rules",
    title: { en: "Remove personal details", ur: "ذاتی معلومات ہٹانا", roman: "Personal details hatana" },
    body: {
      en: "Phone, CNIC, card and account numbers, IBANs and one-time codes become placeholders before anything else happens. Numbers are kept only as one-way fingerprints, so repeat scam numbers can be spotted without storing them.",
      ur: "سب سے پہلے فون، شناختی کارڈ، کارڈ اور اکاؤنٹ نمبر، آئی بین اور کوڈ ہٹا دیے جاتے ہیں۔ نمبر صرف ایک طرفہ فنگر پرنٹ کی صورت میں رکھے جاتے ہیں تاکہ بار بار آنے والے فراڈ نمبر پہچانے جا سکیں۔",
      roman: "Sab se pehle phone, CNIC, card aur account number, IBAN aur code hata diye jate hain. Number sirf one-way fingerprint ki soorat mein rakhe jate hain taake baar baar aane wale fraud number pehchane ja sakein.",
    },
  },
  {
    by: "rules",
    title: { en: "Scan for patterns, including disguised ones", ur: "پیٹرن تلاش کرنا، چھپے ہوئے بھی", roman: "Patterns dhoondna, chhupe hue bhi" },
    body: {
      en: "Patterns in English, Urdu, Roman Urdu and common Pashto, Sindhi and Punjabi words look for requests for codes, fees and transfers, threats and prizes. Links written as \"hbl-verify[.]com\", look-alike Cyrillic letters, spaced-out words like \"O T P\" and text aimed at fooling an AI are caught too.",
      ur: "انگریزی، اردو، رومن اردو اور پشتو، سندھی، پنجابی کے عام الفاظ کے پیٹرن کوڈ، فیس، رقم کی منتقلی، دھمکی اور انعام تلاش کرتے ہیں۔ \"hbl-verify[.]com\" جیسے چھپائے گئے لنک، ملتے جلتے روسی حروف، \"O T P\" جیسے الگ الگ لکھے الفاظ اور اے آئی کو دھوکہ دینے والا متن بھی پکڑا جاتا ہے۔",
      roman: "English, Urdu, Roman Urdu aur Pashto, Sindhi, Punjabi ke aam alfaaz ke patterns code, fee, transfer, dhamki aur inaam dhoondte hain. \"hbl-verify[.]com\" jaise chhupaye gaye links, milte julte Russi huroof, \"O T P\" jaise alag alag likhe alfaaz aur AI ko dhoka dene wala text bhi pakra jata hai.",
    },
  },
  {
    by: "ai",
    title: { en: "AI reads the message", ur: "اے آئی پیغام پڑھتا ہے", roman: "AI message parhta hai" },
    body: {
      en: "A language model describes the message as structured data: who it claims to be, what it asks for, what pressure it applies, and whether it tries to talk to an AI. The message is treated as untrusted data. Identical scams are read once and cached.",
      ur: "لینگویج ماڈل پیغام کو منظم ڈیٹا میں بیان کرتا ہے: کون ہونے کا دعویٰ، کیا مطالبہ، کیسا دباؤ، اور کیا یہ اے آئی سے بات کرنے کی کوشش کرتا ہے۔ پیغام کو ناقابل اعتماد ڈیٹا سمجھا جاتا ہے۔ ایک جیسے فراڈ ایک بار پڑھ کر محفوظ کر لیے جاتے ہیں۔",
      roman: "Language model message ko structured data mein bayan karta hai: kaun hone ka daawa, kya mutalba, kaisa dabao, aur kya yeh AI se baat karne ki koshish karta hai. Message ko na-qabil-e-aitbar data samjha jata hai. Ek jaise fraud ek baar parh kar cache kar liye jate hain.",
    },
  },
  {
    by: "agent",
    title: { en: "A team of agents investigates", ur: "ایجنٹوں کی ٹیم تفتیش کرتی ہے", roman: "Agents ki team tafteesh karti hai" },
    body: {
      en: "A rules-based planner decides which specialists to run. A link specialist inspects links (look-alike domains, short links, domain age, Google Safe Browsing) while a memory specialist searches known scams, in parallel, each with its own tool loop. A guard then checks any link they skipped, refuses links that are not in the message, and looks up the watchlist and reported numbers.",
      ur: "قواعد پر مبنی منصوبہ ساز طے کرتا ہے کہ کون سے ماہر چلیں۔ لنک ماہر لنک جانچتا ہے اور ساتھ ہی میموری ماہر معلوم فراڈ تلاش کرتا ہے، ہر ایک اپنے ٹول کے ساتھ۔ پھر حفاظتی نظام ہر چھوٹا ہوا لنک خود جانچتا ہے، پیغام سے باہر کا لنک رد کرتا ہے، اور واچ لسٹ اور رپورٹ شدہ نمبر دیکھتا ہے۔",
      roman: "Rules par mabni planner tay karta hai ke kaun se specialists chalein. Link specialist links check karta hai aur saath hi memory specialist maloom fraud dhoondta hai, har ek apne tool ke saath. Phir safety guard har chhoota hua link khud check karta hai, message se bahar ka link radd karta hai, aur watchlist aur reported number dekhta hai.",
    },
  },
  {
    by: "rules",
    title: { en: "The rule book decides", ur: "قواعد فیصلہ کرتے ہیں", roman: "Rules faisla karte hain" },
    body: {
      en: "Published rules turn all the evidence into a score from 0 to 100 and a verdict. The same message always gets the same verdict, and a quality gate in CI fails if a change makes the numbers worse.",
      ur: "شائع شدہ قواعد تمام شواہد کو 0 سے 100 کے اسکور اور فیصلے میں بدلتے ہیں۔ ایک ہی پیغام کو ہمیشہ ایک ہی فیصلہ ملتا ہے، اور اگر کوئی تبدیلی نتائج خراب کرے تو CI کا کوالٹی گیٹ ناکام ہو جاتا ہے۔",
      roman: "Published rules tamam saboot ko 0 se 100 ke score aur faisle mein badalte hain. Ek hi message ko hamesha ek hi faisla milta hai, aur agar koi tabdeeli nataij kharab kare to CI ka quality gate fail ho jata hai.",
    },
  },
  {
    by: "ai",
    title: { en: "Explain and advise", ur: "وضاحت اور مشورہ", roman: "Wazahat aur mashwara" },
    body: {
      en: "The model explains the result in your language. If its wording contradicts the verdict it is thrown away. What-to-do steps and reporting channels are fixed text.",
      ur: "ماڈل آپ کی زبان میں نتیجہ سمجھاتا ہے۔ اگر اس کی بات فیصلے کے خلاف ہو تو رد کر دی جاتی ہے۔ اگلے اقدامات اور شکایت کے ادارے مقررہ متن ہیں۔",
      roman: "Model aap ki zuban mein natija samjhata hai. Agar us ki baat faisle ke khilaf ho to radd kar di jati hai. Agle iqdamat aur shikayat ke idaray muqarrara text hain.",
    },
  },
  {
    by: "rules",
    title: { en: "Review, remember, share", ur: "جائزہ، یاد، شیئر", roman: "Review, yaad, share" },
    body: {
      en: "Messages you choose to share go to a review queue. Approved reports join the scam memory, are grouped into campaigns, and their scam websites can be exported in STIX 2.1 for CERTs and police.",
      ur: "آپ کے شیئر کیے گئے پیغامات جائزے کی قطار میں جاتے ہیں۔ منظور شدہ رپورٹس فراڈ میموری میں شامل ہوتی ہیں، مہمات میں اکٹھی ہوتی ہیں، اور ان کی فراڈ ویب سائٹس سرٹ اور پولیس کے لیے STIX 2.1 میں برآمد کی جا سکتی ہیں۔",
      roman: "Aap ke share kiye gaye messages review ki qataar mein jate hain. Approved reports fraud memory mein shamil hoti hain, campaigns mein ikatthi hoti hain, aur un ki fraud websites CERT aur police ke liye STIX 2.1 mein export ki ja sakti hain.",
    },
  },
];

export default function HowPage() {
  const { t, pick } = useLang();
  const [rules, setRules] = useState<RuleBookEntry[] | null>(null);
  const [channels, setChannels] = useState<Channel[] | null>(null);
  const [quality, setQuality] = useState<Quality | null>(null);

  useEffect(() => {
    getQuality()
      .then(setQuality)
      .catch(() => setQuality(null));
    getRules()
      .then((r) => setRules(r.rules))
      .catch(() => setRules([]));
    getChannels()
      .then((c) => setChannels(Object.values(c)))
      .catch(() => setChannels([]));
  }, []);

  return (
    <main className="page page--how">
      <header className="pagehead">
        <h1>{t("how_title")}</h1>
        <p>{t("how_sub")}</p>
      </header>

      <section className="panel">
        <h2 className="panel__title">{t("pipeline_title")}</h2>
        <ol className="pipeline">
          {PIPELINE.map((p, i) => (
            <li key={i} className={`pipeline__step pipeline__step--${p.by}`}>
              <span className="pipeline__num" aria-hidden="true">
                {i + 1}
              </span>
              <div>
                <h3>
                  {pick(p.title)} <span className="tag tag--muted">{t(`by_${p.by}`)}</span>
                </h3>
                <p>{pick(p.body)}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="panel">
        <h2 className="panel__title">{t("eval_title")}</h2>
        <p className="muted">{t("eval_note")}</p>
        <div className="table-wrap">
          <table className="datatable">
            <thead>
              <tr>
                <th></th>
                <th>{t("eval_precision")}</th>
                <th>{t("eval_recall")}</th>
                <th>{t("eval_flagged")}</th>
                <th>{t("eval_fp")}</th>
              </tr>
            </thead>
            <tbody>
              {quality?.eval &&
                ([
                  ["q_test", quality.eval.test],
                  ["q_dev", quality.eval.dev],
                ] as const).map(([label, set]) => {
                  const run = set.runs.find((r) => r.name === "rules + pattern memory") ?? set.runs[0];
                  const pct = (x: number) => `${(x * 100).toFixed(1)}%`;
                  return (
                    <tr key={label}>
                      <td>
                        {t(label)} ({set.messages})
                      </td>
                      <td>{pct(run.strict.precision)}</td>
                      <td>{pct(run.strict.recall)}</td>
                      <td>{pct(run.flagged.recall)}</td>
                      <td>
                        {run.flagged.fp} / {set.legit}
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
        <p>
          <Link to="/quality">{t("q_more")} →</Link>
        </p>
      </section>

      <section className="panel">
        <h2 className="panel__title">{t("rulebook_title")}</h2>
        <p className="muted">{t("rulebook_sub")}</p>
        {!rules && <p className="muted">{t("loading")}</p>}
        {rules && (
          <ul className="rulebook">
            {rules.map((r) => (
              <li key={r.id} className={r.weight < 0 ? "is-good" : ""}>
                <span className="rulebook__pts" dir="ltr">
                  {r.weight > 0 ? `+${r.weight}` : r.weight}
                </span>
                <div>
                  <strong>{pick(r.title).replace(/\{\w+\}/g, "…")}</strong>
                  <p>{pick(r.why).replace(/\{\w+\}/g, "…")}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel">
        <h2 className="panel__title">{t("channels_title")}</h2>
        {channels && channels.length > 0 && (
          <ul className="channels">
            {channels.map((c) => (
              <li key={c.name}>
                <strong>{c.name}</strong>
                <span>{c.for}</span>
                <span dir="ltr">
                  {c.url && (
                    <a href={c.url} target="_blank" rel="noreferrer">
                      {c.url.replace(/^https?:\/\/(www\.)?/, "")}
                    </a>
                  )}
                  {c.url && c.phone ? " · " : ""}
                  {c.phone}
                  {c.sms_shortcode ? ` · SMS ${c.sms_shortcode}` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
