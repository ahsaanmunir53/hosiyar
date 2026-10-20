import { useState } from "react";
import type { I18n } from "../api";
import { useLang } from "../i18n";

interface Item {
  from: string;
  text: string;
  scam: boolean;
  why: I18n;
}

// Written for this quiz; numbers and links are made up and partly masked.
const ITEMS: Item[] = [
  {
    from: "0301-•••••67",
    text: "Mubarak ho! BISP ki 25,000 ki qist aa gayi hai. Hasil karne ke liye 500 rupay registration fee is number par Easypaisa karein.",
    scam: true,
    why: {
      en: "BISP says its official SMS come only from 8171, and it never asks for a fee to release your money.",
      ur: "بی آئی ایس پی کے مطابق سرکاری ایس ایم ایس صرف 8171 سے آتے ہیں، اور رقم دینے کے لیے کبھی فیس نہیں مانگی جاتی۔",
      roman: "BISP ke mutabiq sarkari SMS sirf 8171 se aate hain, aur raqam dene ke liye kabhi fee nahi mangi jati.",
    },
  },
  {
    from: "HBL",
    text: "Your HBL OTP for login is 482913. Do not share it with anyone. HBL will never ask for your OTP.",
    scam: false,
    why: {
      en: "A normal one-time code from the bank's own sender name, with a warning not to share it. Genuine, but still never give the code to anyone who calls.",
      ur: "بینک کے اپنے نام سے عام کوڈ، ساتھ میں کسی کو نہ بتانے کی تنبیہ۔ اصلی ہے، پھر بھی کال کرنے والے کسی شخص کو کوڈ نہ بتائیں۔",
      roman: "Bank ke apne naam se aam code, saath mein kisi ko na batane ki tanbeeh. Asli hai, phir bhi call karne wale kisi shakhs ko code na batayen.",
    },
  },
  {
    from: "+92 3••-•••••12",
    text: "Maine ghalti se aap ke number par 6 digit code bhej diya hai, please jaldi wapas bhej dein.",
    scam: true,
    why: {
      en: "That code is the login code for your own WhatsApp. Whoever gets it takes over your account and messages your contacts for money.",
      ur: "وہ کوڈ آپ کے اپنے واٹس ایپ کا لاگ اِن کوڈ ہے۔ جسے مل جائے وہ آپ کا اکاؤنٹ لے کر آپ کے رابطوں سے پیسے مانگتا ہے۔",
      roman: "Woh code aap ke apne WhatsApp ka login code hai. Jise mil jaye woh aap ka account le kar aap ke contacts se paise mangta hai.",
    },
  },
  {
    from: "JazzCash-Alert",
    text: "Dear customer, your JazzCash account will be suspended in 24 hours. Verify your CNIC now at jazzcash-verify.top",
    scam: true,
    why: {
      en: "The link imitates JazzCash. Its real site is jazzcash.com.pk, and wallets do not threaten to close your account by SMS.",
      ur: "یہ لنک جاز کیش کی نقل ہے۔ اصل ویب سائٹ jazzcash.com.pk ہے، اور والیٹ ایس ایم ایس پر اکاؤنٹ بند کرنے کی دھمکی نہیں دیتے۔",
      roman: "Yeh link JazzCash ki naqal hai. Asal website jazzcash.com.pk hai, aur wallet SMS par account band karne ki dhamki nahi dete.",
    },
  },
  {
    from: "Ammi",
    text: "Beta main 7 baje tak ghar aa jaungi, khana mat banana.",
    scam: false,
    why: {
      en: "A saved contact, no request for money, codes or links. Nothing to worry about.",
      ur: "محفوظ رابطہ، نہ پیسے مانگے، نہ کوڈ، نہ لنک۔ پریشانی کی کوئی بات نہیں۔",
      roman: "Mehfooz contact, na paise mange, na code, na link. Pareshani ki koi baat nahi.",
    },
  },
  {
    from: "0345-•••••90",
    text: "Online job! Like YouTube videos and earn Rs 3,000 daily from home. Registration fee only Rs 1,500. Join today, seats limited.",
    scam: true,
    why: {
      en: "Real employers pay you; they never charge a registration fee. \"Like videos and earn\" is a well-known task scam.",
      ur: "اصلی کمپنی تنخواہ دیتی ہے، رجسٹریشن فیس نہیں لیتی۔ \"ویڈیو لائک کریں اور کمائیں\" مشہور فراڈ ہے۔",
      roman: "Asli company tankhwah deti hai, registration fee nahi leti. \"Video like karein aur kamayein\" mashoor fraud hai.",
    },
  },
  {
    from: "0306-•••••37",
    text: "Your Traffic Challan PSID 4926•••••2559 of Rs.1000 is unpaid. Pay now at psca-echallan.cc to avoid a penalty.",
    scam: true,
    why: {
      en: "Punjab Safe Cities Authority says genuine e-challans come from an official short code, not a personal number. Check your vehicle yourself at echallan.psca.gop.pk.",
      ur: "پنجاب سیف سٹیز اتھارٹی کے مطابق اصلی ای چالان سرکاری شارٹ کوڈ سے آتے ہیں، ذاتی نمبر سے نہیں۔ اپنی گاڑی خود echallan.psca.gop.pk پر چیک کریں۔",
      roman: "Punjab Safe Cities Authority ke mutabiq asli e-challan official short code se aate hain, personal number se nahi. Apni gaari khud echallan.psca.gop.pk par check karein.",
    },
  },
  {
    from: "Daraz",
    text: "Your order #1234 has been shipped and will arrive by Friday. Track it in the Daraz app.",
    scam: false,
    why: {
      en: "No payment request, no link asking for details, and it points you to the app you already use. Genuine.",
      ur: "نہ ادائیگی کا مطالبہ، نہ تفصیل مانگنے والا لنک، اور آپ کو اسی ایپ کی طرف بھیجتا ہے جو آپ پہلے سے استعمال کرتے ہیں۔ اصلی ہے۔",
      roman: "Na payment ka mutalba, na details mangne wala link, aur aap ko usi app ki taraf bhejta hai jo aap pehle se use karte hain. Asli hai.",
    },
  },
];

export default function QuizPage() {
  const { t, pick } = useLang();
  const [index, setIndex] = useState(0);
  const [answer, setAnswer] = useState<boolean | null>(null);
  const [score, setScore] = useState(0);
  const done = index >= ITEMS.length;
  const item = ITEMS[Math.min(index, ITEMS.length - 1)];

  function choose(saysScam: boolean) {
    if (answer !== null) return;
    setAnswer(saysScam);
    if (saysScam === item.scam) setScore((s) => s + 1);
  }

  function next() {
    setAnswer(null);
    setIndex((i) => i + 1);
  }

  function restart() {
    setIndex(0);
    setScore(0);
    setAnswer(null);
  }

  async function share() {
    const url = `${window.location.origin}/quiz`;
    try {
      if (navigator.share) await navigator.share({ title: t("quiz_title"), url });
      else await navigator.clipboard.writeText(url);
    } catch {
      /* cancelled */
    }
  }

  return (
    <main className="page page--quiz">
      <header className="pagehead">
        <h1>{t("quiz_title")}</h1>
        <p>{t("quiz_sub")}</p>
      </header>

      {!done ? (
        <section className="panel quiz" aria-live="polite">
          <div className="quiz__progress" aria-label={`${index + 1} / ${ITEMS.length}`}>
            {ITEMS.map((_, i) => (
              <span key={i} className={i < index ? "is-done" : i === index ? "is-now" : ""} />
            ))}
          </div>
          <p className="field__hint">
            {t("quiz_question")} {index + 1} / {ITEMS.length}
          </p>
          <div className="bubble">
            <span className="bubble__from">
              {t("quiz_from")}: <bdi dir="ltr">{item.from}</bdi>
            </span>
            <p dir="auto">{item.text}</p>
          </div>
          <div className="quiz__choices">
            <button
              type="button"
              className={`btn ${answer === true ? (item.scam ? "btn--right" : "btn--wrong") : "btn--ghost"}`}
              onClick={() => choose(true)}
              disabled={answer !== null}
            >
              {t("quiz_scam")}
            </button>
            <button
              type="button"
              className={`btn ${answer === false ? (!item.scam ? "btn--right" : "btn--wrong") : "btn--ghost"}`}
              onClick={() => choose(false)}
              disabled={answer !== null}
            >
              {t("quiz_real")}
            </button>
          </div>
          {answer !== null && (
            <div className={`quiz__why ${answer === item.scam ? "is-right" : "is-wrong"}`}>
              <strong>{answer === item.scam ? t("quiz_right") : t("quiz_wrong")}</strong>{" "}
              <span>
                {item.scam ? t("quiz_scam") : t("quiz_real")}. {pick(item.why)}
              </span>
              <div>
                <button type="button" className="btn btn--primary btn--small" onClick={next}>
                  {t("quiz_next")}
                </button>
              </div>
            </div>
          )}
        </section>
      ) : (
        <section className="panel quiz quiz--done">
          <p className="field__label">{t("quiz_score")}</p>
          <p className="quiz__score">
            {score} <span>/ {ITEMS.length}</span>
          </p>
          <div className="quiz__choices">
            <button type="button" className="btn btn--primary" onClick={restart}>
              {t("quiz_again")}
            </button>
            <button type="button" className="btn btn--ghost" onClick={share}>
              {t("quiz_share")}
            </button>
          </div>
        </section>
      )}
    </main>
  );
}
