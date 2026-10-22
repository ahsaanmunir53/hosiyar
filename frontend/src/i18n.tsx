import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { I18n, Lang } from "./api";

const S = {
  nav_check: { en: "Check a message", ur: "پیغام چیک کریں", roman: "Message check" },
  nav_trends: { en: "Trends", ur: "رجحانات", roman: "Trends" },
  nav_how: { en: "How it works", ur: "یہ کیسے کام کرتا ہے", roman: "Kaise kaam karta hai" },
  lang_label: { en: "Reply language", ur: "زبان", roman: "Zuban" },

  hero_title: {
    en: "Check a suspicious message before you reply.",
    ur: "جواب دینے سے پہلے مشکوک پیغام چیک کریں۔",
    roman: "Jawab dene se pehle mashkook message check karein.",
  },
  hero_sub: {
    en: "Paste an SMS or WhatsApp message, or add a screenshot, voice note, QR code, PDF or email. Personal details are removed first, links are inspected, and the message is compared with known scams.",
    ur: "ایس ایم ایس یا واٹس ایپ پیغام یہاں لگائیں، یا اسکرین شاٹ، وائس نوٹ، کیو آر کوڈ، پی ڈی ایف یا ای میل دیں۔ پہلے ذاتی معلومات ہٹائی جاتی ہیں، لنک جانچے جاتے ہیں اور پیغام کو معلوم فراڈ سے ملایا جاتا ہے۔",
    roman: "SMS ya WhatsApp message yahan paste karein, ya screenshot, voice note, QR code, PDF ya email dein. Pehle personal details hatai jati hain, links check hote hain aur message ko maloom fraud se milaya jata hai.",
  },
  tab_text: { en: "Text", ur: "متن", roman: "Text" },
  tab_image: { en: "Screenshot", ur: "اسکرین شاٹ", roman: "Screenshot" },
  tab_audio: { en: "Voice note", ur: "وائس نوٹ", roman: "Voice note" },
  input_label: { en: "The message you received", ur: "آپ کو ملنے والا پیغام", roman: "Aap ko milne wala message" },
  input_placeholder: {
    en: "Paste the message here…",
    ur: "پیغام یہاں لگائیں…",
    roman: "Message yahan paste karein…",
  },
  sender_label: { en: "Who sent it? (optional)", ur: "کس نے بھیجا؟ (اختیاری)", roman: "Kis ne bheja? (optional)" },
  sender_hint: { en: "For example 8171, HBL or 0300…", ur: "مثلاً 8171، HBL یا 0300…", roman: "Maslan 8171, HBL ya 0300…" },
  share_label: {
    en: "Share this message, with personal details removed, so it can be reviewed and added to the scam memory to warn others",
    ur: "یہ پیغام ذاتی معلومات ہٹا کر شیئر کریں تاکہ جائزے کے بعد اسے فراڈ میموری میں شامل کر کے دوسروں کو خبردار کیا جا سکے",
    roman: "Yeh message personal details hata kar share karein taake review ke baad ise fraud memory mein shamil kar ke doosron ko khabardar kiya ja sake",
  },
  check_button: { en: "Check message", ur: "پیغام چیک کریں", roman: "Message check karein" },
  checking: { en: "Checking…", ur: "چیک ہو رہا ہے…", roman: "Check ho raha hai…" },
  waking: {
    en: "The server was asleep and is starting up. This can take up to a minute the first time.",
    ur: "سرور سو رہا تھا اور اب چل رہا ہے۔ پہلی بار اس میں ایک منٹ تک لگ سکتا ہے۔",
    roman: "Server so raha tha aur ab start ho raha hai. Pehli dafa is mein ek minute tak lag sakta hai.",
  },
  wake_bar: {
    en: "Waking up the free server. Render's free plan puts it to sleep after 15 quiet minutes; it is back in 30 to 60 seconds.",
    ur: "مفت سرور جاگ رہا ہے۔ رینڈر کا مفت پلان 15 منٹ خاموشی کے بعد اسے سلا دیتا ہے، 30 سے 60 سیکنڈ میں یہ واپس آ جاتا ہے۔",
    roman: "Free server jag raha hai. Render ka free plan 15 minute khamoshi ke baad isay sula deta hai, 30 se 60 second mein wapas aa jata hai.",
  },
  wake_ready: { en: "The server is awake.", ur: "سرور جاگ گیا ہے۔", roman: "Server jag gaya hai." },
  wake_failed: {
    en: "The server is not answering. Check your connection, then try again.",
    ur: "سرور جواب نہیں دے رہا۔ اپنا انٹرنیٹ دیکھیں، پھر دوبارہ کوشش کریں۔",
    roman: "Server jawab nahi de raha. Apna internet check karein, phir dobara koshish karein.",
  },
  wake_retry: { en: "Try again", ur: "دوبارہ کوشش کریں", roman: "Dobara koshish karein" },
  examples: { en: "Try an example", ur: "مثال آزمائیں", roman: "Misaal try karein" },
  image_drop: {
    en: "Choose a screenshot (PNG, JPG or WebP, up to 5 MB)",
    ur: "اسکرین شاٹ منتخب کریں (PNG، JPG یا WebP، زیادہ سے زیادہ 5 MB)",
    roman: "Screenshot chunein (PNG, JPG ya WebP, 5 MB tak)",
  },
  image_tip: {
    en: "Crop out any codes or account numbers before uploading. The screenshot is read by Google's Gemini.",
    ur: "اپ لوڈ سے پہلے کوڈ یا اکاؤنٹ نمبر کاٹ دیں۔ اسکرین شاٹ گوگل جیمنائی پڑھتا ہے۔",
    roman: "Upload se pehle code ya account number crop kar dein. Screenshot Google Gemini parhta hai.",
  },
  audio_pick: { en: "Choose a voice note file", ur: "وائس نوٹ فائل منتخب کریں", roman: "Voice note file chunein" },
  audio_record: { en: "Record", ur: "ریکارڈ کریں", roman: "Record karein" },
  audio_stop: { en: "Stop recording", ur: "ریکارڈنگ بند کریں", roman: "Recording band karein" },
  audio_ready: { en: "Recording ready", ur: "ریکارڈنگ تیار ہے", roman: "Recording tayyar hai" },
  audio_denied: {
    en: "Microphone access was blocked. Allow it in the browser, or choose a file instead.",
    ur: "مائیکروفون کی اجازت نہیں ملی۔ براؤزر میں اجازت دیں یا فائل منتخب کریں۔",
    roman: "Microphone ki ijazat nahi mili. Browser mein allow karein ya file chunein.",
  },
  file_chosen: { en: "Selected", ur: "منتخب", roman: "Muntakhib" },
  note_label: { en: "Extra text (optional)", ur: "اضافی متن (اختیاری)", roman: "Izafi text (optional)" },

  err_network: {
    en: "Could not reach the checker. Check your connection and try again.",
    ur: "چیکر سے رابطہ نہیں ہو سکا۔ انٹرنیٹ چیک کر کے دوبارہ کوشش کریں۔",
    roman: "Checker se rabta nahi ho saka. Internet check kar ke dobara koshish karein.",
  },
  err_empty: { en: "Paste a message to check.", ur: "چیک کرنے کے لیے پیغام لگائیں۔", roman: "Check karne ke liye message paste karein." },
  err_file: { en: "Choose a file first.", ur: "پہلے فائل منتخب کریں۔", roman: "Pehle file chunein." },

  verdict_likely_scam: { en: "Likely scam", ur: "غالباً فراڈ", roman: "Ghaliban fraud" },
  verdict_suspicious: { en: "Suspicious", ur: "مشکوک", roman: "Mashkook" },
  verdict_no_red_flags: { en: "No red flags found", ur: "کوئی خطرے کی علامت نہیں ملی", roman: "Koi khatre ki alamat nahi mili" },
  risk_score: { en: "risk score", ur: "خطرہ اسکور", roman: "risk score" },
  written_by_ai: {
    en: "Explanation written by AI from the rule results. The verdict itself comes from the rule book.",
    ur: "یہ وضاحت قواعد کے نتائج سے اے آئی نے لکھی ہے۔ فیصلہ قواعد کی کتاب کرتی ہے۔",
    roman: "Yeh wazahat rules ke nataij se AI ne likhi hai. Faisla rule book karti hai.",
  },
  written_by_rules: {
    en: "Explanation from the rule book.",
    ur: "وضاحت قواعد کی کتاب سے۔",
    roman: "Wazahat rule book se.",
  },
  why_title: { en: "Why", ur: "کیوں", roman: "Kyun" },
  steps_title: { en: "What to do now", ur: "اب کیا کریں", roman: "Ab kya karein" },
  links_title: { en: "Links in the message", ur: "پیغام میں لنک", roman: "Message mein links" },
  similar_title: { en: "Similar known scams", ur: "ملتے جلتے معلوم فراڈ", roman: "Milte julte maloom fraud" },
  trail_title: { en: "How this was checked", ur: "یہ کیسے جانچا گیا", roman: "Yeh kaise check hua" },
  analyzed_title: { en: "What was analysed", ur: "کیا جانچا گیا", roman: "Kya check hua" },
  decisive: { en: "decisive", ur: "فیصلہ کن", roman: "faisla kun" },
  reassuring: { en: "reassuring", ur: "اطمینان بخش", roman: "itminan bakhsh" },
  src_pattern: { en: "pattern", ur: "پیٹرن", roman: "pattern" },
  src_ai: { en: "AI reading", ur: "اے آئی", roman: "AI" },
  "src_link-check": { en: "link check", ur: "لنک چیک", roman: "link check" },
  src_memory: { en: "memory", ur: "میموری", roman: "memory" },
  "src_file-check": { en: "file check", ur: "فائل کی جانچ", roman: "file check" },
  src_watchlist: { en: "watchlist", ur: "واچ لسٹ", roman: "watchlist" },
  src_sender: { en: "sender", ur: "بھیجنے والا", roman: "sender" },
  link_official: { en: "Official site of", ur: "اصل ویب سائٹ:", roman: "Asli website:" },
  link_lookalike: { en: "Imitates", ur: "نقل:", roman: "Naqal:" },
  link_short: { en: "Short link", ur: "مختصر لنک", roman: "Short link" },
  link_goes_to: { en: "goes to", ur: "جاتا ہے", roman: "jata hai" },
  link_age: { en: "days old", ur: "دن پرانی", roman: "din purani" },
  link_risky_tld: { en: "Risky ending", ur: "خطرناک ڈومین", roman: "Risky domain" },
  link_sb: { en: "Flagged by Safe Browsing", ur: "سیف براؤزنگ نے خطرناک کہا", roman: "Safe Browsing ne flag kiya" },
  link_unknown_age: { en: "Age not checked", ur: "عمر چیک نہیں ہوئی", roman: "Age check nahi hui" },
  similar_pattern: { en: "pattern library (sample)", ur: "پیٹرن لائبریری (نمونہ)", roman: "pattern library (sample)" },
  similar_community: { en: "shared by a user", ur: "صارف نے شیئر کیا", roman: "user ne share kiya" },
  similar_match: { en: "match", ur: "مماثلت", roman: "match" },
  similar_hidden: {
    en: "Shared by another person. The text is shown once a reviewer has checked it.",
    ur: "کسی اور نے شیئر کیا۔ متن جائزہ کار کی جانچ کے بعد دکھایا جاتا ہے۔",
    roman: "Kisi aur ne share kiya. Text reviewer ki jaanch ke baad dikhaya jata hai.",
  },
  number_seen: {
    en: "The phone number in this message appears in earlier scam reports.",
    ur: "اس پیغام والا فون نمبر پہلے فراڈ رپورٹس میں آ چکا ہے۔",
    roman: "Is message wala phone number pehle fraud reports mein aa chuka hai.",
  },
  redacted_note: { en: "Removed before analysis", ur: "جانچ سے پہلے ہٹایا گیا", roman: "Check se pehle hataya gaya" },
  red_PHONE: { en: "phone numbers", ur: "فون نمبر", roman: "phone numbers" },
  red_CNIC: { en: "CNIC numbers", ur: "شناختی کارڈ نمبر", roman: "CNIC numbers" },
  red_CARD: { en: "card numbers", ur: "کارڈ نمبر", roman: "card numbers" },
  red_CODE: { en: "codes", ur: "کوڈ", roman: "codes" },
  red_IBAN: { en: "IBANs", ur: "آئی بین", roman: "IBAN" },
  red_EMAIL: { en: "emails", ur: "ای میل", roman: "emails" },
  degraded_ai_off: {
    en: "AI is not connected, so this result comes from the rule book only.",
    ur: "اے آئی منسلک نہیں، اس لیے یہ نتیجہ صرف قواعد سے ہے۔",
    roman: "AI connected nahi, is liye yeh natija sirf rules se hai.",
  },
  degraded_ai_failed: {
    en: "The AI step failed (usually a free-tier rate limit or a service error), so this result comes from the rule book only. Details are under \"How this was checked\".",
    ur: "اے آئی والا مرحلہ ناکام ہوا (عموماً مفت حد پوری ہونے یا سروس کی خرابی سے)، اس لیے یہ نتیجہ صرف قواعد سے ہے۔ تفصیل \"یہ کیسے جانچا گیا\" میں ہے۔",
    roman: "AI wala step fail hua (aam tor par free limit poori hone ya service ki kharabi se), is liye yeh natija sirf rules se hai. Tafseel \"Yeh kaise check hua\" mein hai.",
  },
  why_empty: {
    en: "None of the rule book's warning signs matched this message.",
    ur: "قواعد کی کتاب کی کوئی بھی خطرے کی علامت اس پیغام سے میل نہیں کھاتی۔",
    roman: "Rule book ki koi bhi khatre ki alamat is message se match nahi hui.",
  },

  meta_model: { en: "Model", ur: "ماڈل", roman: "Model" },
  meta_rules: { en: "Rule book", ur: "قواعد", roman: "Rule book" },
  shared_yes: {
    en: "Added to the shared scam memory with personal details removed. Thank you.",
    ur: "ذاتی معلومات ہٹا کر مشترکہ فراڈ میموری میں شامل کر دیا گیا۔ شکریہ۔",
    roman: "Personal details hata kar shared fraud memory mein shamil kar diya gaya. Shukriya.",
  },
  followup_title: { en: "Ask about this message", ur: "اس پیغام کے بارے میں پوچھیں", roman: "Is message ke baare mein poochein" },
  followup_placeholder: {
    en: "For example: I already sent money, what now?",
    ur: "مثلاً: میں پیسے بھیج چکا ہوں، اب کیا کروں؟",
    roman: "Maslan: main paise bhej chuka hoon, ab kya karun?",
  },
  followup_button: { en: "Ask", ur: "پوچھیں", roman: "Poochein" },
  followup_suggest_1: { en: "I already sent money", ur: "میں پیسے بھیج چکا ہوں", roman: "Main paise bhej chuka hoon" },
  followup_suggest_2: { en: "How do I report it?", ur: "شکایت کیسے کروں؟", roman: "Shikayat kaise karun?" },
  followup_suggest_3: { en: "I shared the code", ur: "میں نے کوڈ بتا دیا", roman: "Maine code bata diya" },
  new_check: { en: "Check another message", ur: "دوسرا پیغام چیک کریں", roman: "Doosra message check karein" },

  trail_prepare: { en: "Removed personal details and scanned for known patterns", ur: "ذاتی معلومات ہٹائیں اور معلوم پیٹرن تلاش کیے", roman: "Personal details hatai aur maloom patterns dhoonde" },
  trail_read_with_ai: { en: "AI read the message and described it", ur: "اے آئی نے پیغام پڑھ کر بیان کیا", roman: "AI ne message parh kar bayan kiya" },
  trail_check_link_guard: { en: "Safety guard inspected every link", ur: "حفاظتی نظام نے ہر لنک جانچا", roman: "Safety guard ne har link check kiya" },
  trail_search_similar_reports_guard: { en: "Searched the scam memory for similar messages", ur: "ملتے جلتے پیغامات کے لیے فراڈ میموری تلاش کی", roman: "Milte julte messages ke liye fraud memory search ki" },
  trail_assess: { en: "Rule book scored the evidence and decided", ur: "قواعد نے شواہد کو اسکور کر کے فیصلہ کیا", roman: "Rule book ne saboot score kar ke faisla kiya" },
  by_rules: { en: "rules", ur: "قواعد", roman: "rules" },
  by_ai: { en: "AI", ur: "اے آئی", roman: "AI" },
  by_agent: { en: "AI agent", ur: "اے آئی ایجنٹ", roman: "AI agent" },
  by_guard: { en: "guard", ur: "حفاظت", roman: "guard" },
  trail_removed: { en: "personal details removed", ur: "ذاتی معلومات ہٹائی گئیں", roman: "personal details hatai gayin" },
  trail_signals: { en: "warning signs found", ur: "خطرے کی علامات ملیں", roman: "khatre ki alamat milin" },
  trail_found: { en: "similar messages found", ur: "ملتے جلتے پیغامات ملے", roman: "milte julte messages mile" },
  eval_note: {
    en: "Rules only, no AI, network link checks off. The messages were written by the project author, so these numbers are a sanity check rather than a benchmark. Details are in backend/eval/results.md.",
    ur: "صرف قواعد، اے آئی کے بغیر، نیٹ ورک لنک چیک بند۔ پیغامات پروجیکٹ کے مصنف نے لکھے ہیں، اس لیے یہ اعداد ابتدائی جانچ ہیں، معیاری بینچ مارک نہیں۔ تفصیل backend/eval/results.md میں ہے۔",
    roman: "Sirf rules, AI ke baghair, network link checks band. Messages project ke author ne likhe hain, is liye yeh numbers ibtidai jaanch hain, standard benchmark nahi. Tafseel backend/eval/results.md mein hai.",
  },
  eval_precision: { en: "Precision", ur: "درستگی", roman: "Precision" },
  eval_recall: { en: "Caught as likely scam", ur: "فراڈ کے طور پر پکڑے گئے", roman: "Fraud ke tor par pakre gaye" },
  eval_flagged: { en: "Flagged at all", ur: "کسی بھی طرح نشان زد", roman: "Kisi bhi tarah flag hue" },
  eval_fp: { en: "False alarms", ur: "غلط الارم", roman: "Ghalat alarm" },
  refused: { en: "refused: not a link from the message", ur: "رد: یہ پیغام کا لنک نہیں", roman: "radd: yeh message ka link nahi" },

  trends_title: { en: "What people are checking", ur: "لوگ کیا چیک کر رہے ہیں", roman: "Log kya check kar rahe hain" },
  trends_sub: {
    en: "Counts from the last 14 days. Message text appears only when the sender chose to share it, with personal details removed.",
    ur: "پچھلے 14 دنوں کی گنتی۔ پیغام کا متن صرف تب دکھایا جاتا ہے جب بھیجنے والے نے ذاتی معلومات ہٹا کر شیئر کیا ہو۔",
    roman: "Pichle 14 din ki ginti. Message ka text sirf tab dikhaya jata hai jab bhejne wale ne personal details hata kar share kiya ho.",
  },
  sample_note: {
    en: "Includes clearly labelled sample data so the page is not empty on a new install.",
    ur: "اس میں واضح طور پر نشان زدہ نمونہ ڈیٹا شامل ہے تاکہ نئی انسٹال پر صفحہ خالی نہ ہو۔",
    roman: "Is mein wazeh tor par label kiya gaya sample data shamil hai taake nayi install par page khali na ho.",
  },
  kpi_checks: { en: "messages checked", ur: "پیغامات چیک ہوئے", roman: "messages check hue" },
  daily_title: { en: "Checks per day", ur: "روزانہ چیک", roman: "Rozana checks" },
  show_table: { en: "Show as table", ur: "جدول میں دیکھیں", roman: "Table mein dekhein" },
  show_chart: { en: "Show as chart", ur: "چارٹ میں دیکھیں", roman: "Chart mein dekhein" },
  date: { en: "Date", ur: "تاریخ", roman: "Tareekh" },
  categories_title: { en: "Most common scam types", ur: "سب سے عام فراڈ", roman: "Sab se aam fraud" },
  brands_title: { en: "Most imitated names", ur: "سب سے زیادہ نقل کیے گئے نام", roman: "Sab se zyada naqal kiye gaye naam" },
  recent_title: { en: "Recently shared scams", ur: "حال ہی میں شیئر کیے گئے فراڈ", roman: "Haal hi mein share kiye gaye fraud" },
  sample_tag: { en: "sample", ur: "نمونہ", roman: "sample" },
  nothing_yet: { en: "Nothing here yet.", ur: "ابھی کچھ نہیں۔", roman: "Abhi kuch nahi." },
  loading: { en: "Loading…", ur: "لوڈ ہو رہا ہے…", roman: "Load ho raha hai…" },

  how_title: { en: "The model reads. The rules decide.", ur: "ماڈل پڑھتا ہے، فیصلہ قواعد کرتے ہیں۔", roman: "Model parhta hai, faisla rules karte hain." },
  how_sub: {
    en: "Hoshiyar uses language models where they are strong, reading messy multilingual text and choosing what to investigate, and keeps the verdict in a rule book anyone can inspect.",
    ur: "ہوشیار لینگویج ماڈل وہاں استعمال کرتا ہے جہاں وہ مضبوط ہیں، یعنی مختلف زبانوں کا الجھا ہوا متن پڑھنا اور تفتیش کا فیصلہ کرنا، اور فیصلہ ایسے قواعد پر رکھتا ہے جنہیں کوئی بھی دیکھ سکتا ہے۔",
    roman: "Hoshiyar language models wahan use karta hai jahan woh mazboot hain, yani mukhtalif zubanon ka uljha hua text parhna aur tafteesh ka faisla karna, aur faisla aise rules par rakhta hai jinhein koi bhi dekh sakta hai.",
  },
  pipeline_title: { en: "What happens to a message", ur: "پیغام کے ساتھ کیا ہوتا ہے", roman: "Message ke saath kya hota hai" },
  principles_title: { en: "Principles", ur: "اصول", roman: "Usool" },
  rulebook_title: { en: "The rule book", ur: "قواعد کی کتاب", roman: "Rule book" },
  rulebook_sub: {
    en: "Points each rule adds. A decisive rule marks a message as a likely scam on its own. Signals found only by the AI count for 70% and can never be decisive.",
    ur: "ہر قاعدہ کتنے پوائنٹس دیتا ہے۔ فیصلہ کن قاعدہ اکیلا پیغام کو فراڈ قرار دیتا ہے۔ صرف اے آئی کی پکڑی گئی علامات 70 فیصد شمار ہوتی ہیں اور کبھی فیصلہ کن نہیں ہوتیں۔",
    roman: "Har rule kitne points deta hai. Faisla kun rule akela message ko fraud qarar deta hai. Sirf AI ki pakri gayi alamat 70% count hoti hain aur kabhi faisla kun nahi hotin.",
  },
  points: { en: "points", ur: "پوائنٹس", roman: "points" },
  eval_title: { en: "How well it works", ur: "یہ کتنا درست ہے", roman: "Yeh kitna durust hai" },
  channels_title: { en: "Where to report in Pakistan", ur: "پاکستان میں شکایت کہاں کریں", roman: "Pakistan mein shikayat kahan karein" },
  footer: {
    en: "Hoshiyar gives guidance, not a guarantee. When in doubt, contact the organisation using a number you already trust.",
    ur: "ہوشیار رہنمائی دیتا ہے، ضمانت نہیں۔ شک ہو تو ادارے سے اس نمبر پر رابطہ کریں جو آپ کو پہلے سے معلوم ہو۔",
    roman: "Hoshiyar rehnumai deta hai, guarantee nahi. Shak ho to idaray se us number par rabta karein jo aap ko pehle se maloom ho.",
  },

  nav_tools: { en: "Tools", ur: "ٹولز", roman: "Tools" },
  nav_quiz: { en: "Quiz", ur: "کوئز", roman: "Quiz" },
  foot_quality: { en: "Quality", ur: "معیار", roman: "Quality" },
  foot_privacy: { en: "Privacy", ur: "رازداری", roman: "Privacy" },
  foot_admin: { en: "Review panel", ur: "جائزہ پینل", roman: "Review panel" },

  tab_qr: { en: "QR code", ur: "کیو آر کوڈ", roman: "QR code" },
  tab_pdf: { en: "PDF", ur: "پی ڈی ایف", roman: "PDF" },
  tab_email: { en: "Email", ur: "ای میل", roman: "Email" },
  qr_drop: { en: "Choose or take a photo of the QR code", ur: "کیو آر کوڈ کی تصویر منتخب کریں یا لیں", roman: "QR code ki tasveer chunein ya lein" },
  qr_tip: {
    en: "The code is read on your device. Only what it contains is sent for checking.",
    ur: "کوڈ آپ کے آلے پر ہی پڑھا جاتا ہے۔ صرف اس کے اندر لکھی بات چیک کے لیے بھیجی جاتی ہے۔",
    roman: "Code aap ke device par hi parha jata hai. Sirf us ke andar likhi baat check ke liye bheji jati hai.",
  },
  qr_found: { en: "The QR code contains", ur: "کیو آر کوڈ میں یہ لکھا ہے", roman: "QR code mein yeh likha hai" },
  qr_none: {
    en: "No QR code was found in that picture. Try a sharper photo, closer to the code.",
    ur: "اس تصویر میں کیو آر کوڈ نہیں ملا۔ کوڈ کے قریب سے صاف تصویر لیں۔",
    roman: "Is tasveer mein QR code nahi mila. Code ke qareeb se saaf tasveer lein.",
  },
  qr_payment_title: { en: "This is a payment code", ur: "یہ ادائیگی کا کوڈ ہے", roman: "Yeh payment ka code hai" },
  qr_payment_body: {
    en: "Scanning it sends money from your account to the merchant below. You never need to scan a code to receive money.",
    ur: "اسے اسکین کرنے سے آپ کے اکاؤنٹ سے نیچے دیے گئے دکاندار کو پیسے جاتے ہیں۔ رقم وصول کرنے کے لیے کبھی کوڈ اسکین نہیں کرنا پڑتا۔",
    roman: "Ise scan karne se aap ke account se neeche diye gaye dukandar ko paise jate hain. Raqam wasool karne ke liye kabhi code scan nahi karna parta.",
  },
  qr_merchant: { en: "Pays", ur: "وصول کنندہ", roman: "Wasool kunanda" },
  qr_amount: { en: "Amount", ur: "رقم", roman: "Raqam" },
  qr_checksum_bad: {
    en: "The code's checksum is wrong, so it may have been edited.",
    ur: "کوڈ کا چیک سم غلط ہے، شاید اس میں تبدیلی کی گئی ہے۔",
    roman: "Code ka checksum ghalat hai, shayad is mein tabdeeli ki gayi hai.",
  },
  pdf_drop: { en: "Choose a PDF (up to 5 MB)", ur: "پی ڈی ایف منتخب کریں (5 MB تک)", roman: "PDF chunein (5 MB tak)" },
  pdf_tip: {
    en: "Fake challans, offer letters and invoices often arrive as PDFs. The first 10 pages are read, and hidden scripts, links and attached files are checked.",
    ur: "جعلی چالان، آفر لیٹر اور بل اکثر پی ڈی ایف میں آتے ہیں۔ پہلے 10 صفحات پڑھے جاتے ہیں اور چھپے اسکرپٹ، لنک اور منسلک فائلیں جانچی جاتی ہیں۔",
    roman: "Jaali challan, offer letter aur bill aksar PDF mein aate hain. Pehle 10 safhe parhe jate hain aur chhupe script, links aur attached files check hoti hain.",
  },
  email_label: { en: "The email's full source", ur: "ای میل کا مکمل سورس", roman: "Email ka poora source" },
  email_help: {
    en: "Gmail: open the email, tap ⋮ and choose \"Show original\", then copy everything. Outlook: \"View message source\". The sender checks need the headers, not just the text.",
    ur: "جی میل: ای میل کھولیں، ⋮ دبائیں اور \"Show original\" چنیں، پھر سب کچھ کاپی کریں۔ آؤٹ لک: \"View message source\"۔ بھیجنے والے کی جانچ کے لیے ہیڈرز ضروری ہیں، صرف متن کافی نہیں۔",
    roman: "Gmail: email kholein, ⋮ dabayen aur \"Show original\" chunein, phir sab kuch copy karein. Outlook: \"View message source\". Sender check ke liye headers zaroori hain, sirf text kaafi nahi.",
  },
  email_pick: { en: "Or choose a saved .eml file", ur: "یا محفوظ کی گئی .eml فائل منتخب کریں", roman: "Ya save ki gayi .eml file chunein" },
  err_email: {
    en: "Paste the email's full source, or choose an .eml file.",
    ur: "ای میل کا مکمل سورس لگائیں، یا .eml فائل منتخب کریں۔",
    roman: "Email ka poora source paste karein, ya .eml file chunein.",
  },
  share_note: {
    en: "Shared from another app. Check the text, then tap the button.",
    ur: "دوسری ایپ سے شیئر کیا گیا۔ متن دیکھ لیں، پھر بٹن دبائیں۔",
    roman: "Doosri app se share kiya gaya. Text dekh lein, phir button dabayen.",
  },
  captcha_needed: { en: "Please complete the check below first.", ur: "پہلے نیچے والی تصدیق مکمل کریں۔", roman: "Pehle neeche wali tasdeeq mukammal karein." },

  lang_note: { en: "Written in", ur: "پیغام کی زبان:", roman: "Message ki zuban:" },
  lang_note_tail: {
    en: "The rules know a few common words in it; the AI reading covers the rest.",
    ur: "قواعد اس کے چند عام الفاظ جانتے ہیں؛ باقی اے آئی پڑھتا ہے۔",
    roman: "Rules is ke chand aam alfaaz jante hain; baqi AI parhta hai.",
  },
  lang_ps: { en: "Pashto", ur: "پشتو", roman: "Pashto" },
  lang_sd: { en: "Sindhi", ur: "سندھی", roman: "Sindhi" },
  lang_pa: { en: "Punjabi (Shahmukhi)", ur: "پنجابی (شاہ مکھی)", roman: "Punjabi (Shahmukhi)" },
  lang_pa_roman: { en: "Punjabi (Roman)", ur: "پنجابی (رومن)", roman: "Punjabi (Roman)" },
  report_pending: {
    en: "Shared for review. A reviewer checks it before it joins the scam memory. Thank you.",
    ur: "جائزے کے لیے شیئر ہو گیا۔ فراڈ میموری میں شامل ہونے سے پہلے جائزہ کار اسے دیکھے گا۔ شکریہ۔",
    roman: "Review ke liye share ho gaya. Fraud memory mein shamil hone se pehle reviewer ise dekhega. Shukriya.",
  },
  account_seen: {
    en: "The bank account in this message appears in earlier scam reports.",
    ur: "اس پیغام والا بینک اکاؤنٹ پہلے فراڈ رپورٹس میں آ چکا ہے۔",
    roman: "Is message wala bank account pehle fraud reports mein aa chuka hai.",
  },
  red_ACCOUNT: { en: "account numbers", ur: "اکاؤنٹ نمبر", roman: "account numbers" },
  read_aloud: { en: "Listen", ur: "سنیں", roman: "Sunein" },
  stop_reading: { en: "Stop", ur: "روکیں", roman: "Rokein" },
  no_voice: {
    en: "This device has no voice for this language, so it is read with the default voice.",
    ur: "اس آلے میں اس زبان کی آواز نہیں، اس لیے عام آواز میں پڑھا جا رہا ہے۔",
    roman: "Is device mein is zuban ki awaz nahi, is liye aam awaz mein parha ja raha hai.",
  },
  complaint_pack: { en: "Make a complaint pack", ur: "شکایت پیک بنائیں", roman: "Shikayat pack banayen" },
  complaint_title: { en: "Complaint pack", ur: "شکایت پیک", roman: "Shikayat pack" },
  complaint_sub: {
    en: "Everything to include in an NCCIA or PTA complaint. It is made on your device and includes the original message, so keep it private.",
    ur: "این سی سی آئی اے یا پی ٹی اے کی شکایت میں شامل کرنے کی ہر چیز۔ یہ آپ کے آلے پر بنتا ہے اور اس میں اصل پیغام شامل ہے، اس لیے اسے نجی رکھیں۔",
    roman: "NCCIA ya PTA ki shikayat mein shamil karne ki har cheez. Yeh aap ke device par banta hai aur is mein asal message shamil hai, is liye ise private rakhein.",
  },
  copy: { en: "Copy", ur: "کاپی کریں", roman: "Copy karein" },
  copied: { en: "Copied", ur: "کاپی ہو گیا", roman: "Copy ho gaya" },
  download_txt: { en: "Download .txt", ur: ".txt ڈاؤن لوڈ", roman: ".txt download" },
  print: { en: "Print", ur: "پرنٹ", roman: "Print" },
  close: { en: "Close", ur: "بند کریں", roman: "Band karein" },
  report_site: { en: "Report this website", ur: "یہ ویب سائٹ رپورٹ کریں", roman: "Yeh website report karein" },
  takedown_loading: { en: "Finding who registered it…", ur: "رجسٹرار تلاش ہو رہا ہے…", roman: "Registrar dhoonda ja raha hai…" },
  takedown_registrar: { en: "Registered with", ur: "رجسٹرار", roman: "Registrar" },
  takedown_email: { en: "Email the registrar's abuse team", ur: "رجسٹرار کی ابیوز ٹیم کو ای میل کریں", roman: "Registrar ki abuse team ko email karein" },
  takedown_google: { en: "Report to Google Safe Browsing", ur: "گوگل سیف براؤزنگ کو رپورٹ کریں", roman: "Google Safe Browsing ko report karein" },
  takedown_google_tip: {
    en: "Paste this address in Google's form:",
    ur: "یہ پتہ گوگل کے فارم میں لگائیں:",
    roman: "Yeh address Google ke form mein paste karein:",
  },
  takedown_no_abuse: {
    en: "No abuse contact was found for this domain. You can still report it to Google and NCCIA.",
    ur: "اس ڈومین کا ابیوز رابطہ نہیں ملا۔ آپ پھر بھی گوگل اور این سی سی آئی اے کو رپورٹ کر سکتے ہیں۔",
    roman: "Is domain ka abuse contact nahi mila. Aap phir bhi Google aur NCCIA ko report kar sakte hain.",
  },
  link_homograph: { en: "Look-alike letters for", ur: "ملتے جلتے حروف، اصل:", roman: "Milte julte huroof, asal:" },
  file_email_title: { en: "Who sent this email", ur: "یہ ای میل کس نے بھیجی", roman: "Yeh email kis ne bheji" },
  file_from: { en: "From", ur: "بھیجنے والا", roman: "Bhejne wala" },
  file_reply_to: { en: "Replies go to", ur: "جواب جائے گا", roman: "Jawab jayega" },
  file_checks: { en: "Sender checks", ur: "بھیجنے والے کی جانچ", roman: "Sender ki jaanch" },
  file_attachments: { en: "Attachments", ur: "منسلکہ فائلیں", roman: "Attachments" },
  file_pdf_title: { en: "Inside the PDF", ur: "پی ڈی ایف کے اندر", roman: "PDF ke andar" },
  file_pages: { en: "Pages read", ur: "پڑھے گئے صفحات", roman: "Parhe gaye safhe" },
  file_active: { en: "Scripts and actions", ur: "اسکرپٹ اور خودکار عمل", roman: "Script aur khud-kar amal" },
  file_links: { en: "Links", ur: "لنک", roman: "Links" },
  file_none: { en: "none found", ur: "کچھ نہیں ملا", roman: "kuch nahi mila" },
  trail_plan: { en: "Planner chose which specialists to run", ur: "منصوبہ ساز نے طے کیا کون سے ماہر چلیں", roman: "Planner ne tay kiya kaun se specialists chalein" },
  trail_link_agent: { en: "Link specialist (AI agent) reported", ur: "لنک ماہر (اے آئی ایجنٹ) کی رپورٹ", roman: "Link specialist (AI agent) ki report" },
  trail_memory_agent: { en: "Memory specialist (AI agent) reported", ur: "میموری ماہر (اے آئی ایجنٹ) کی رپورٹ", roman: "Memory specialist (AI agent) ki report" },
  trail_check_link_agent: { en: "Link specialist inspected a link", ur: "لنک ماہر نے لنک جانچا", roman: "Link specialist ne link check kiya" },
  trail_search_similar_reports_agent: { en: "Memory specialist searched the scam memory", ur: "میموری ماہر نے فراڈ میموری تلاش کی", roman: "Memory specialist ne fraud memory search ki" },
  trail_lookup_indicators: { en: "Looked up numbers, accounts and sites in reviewed reports", ur: "نمبر، اکاؤنٹ اور ویب سائٹس جائزہ شدہ رپورٹس میں تلاش کیے", roman: "Number, account aur websites reviewed reports mein dhoonde" },
  cached: { en: "cached", ur: "محفوظ شدہ", roman: "cached" },

  tools_title: { en: "Check before you trust", ur: "بھروسہ کرنے سے پہلے چیک کریں", roman: "Bharosa karne se pehle check karein" },
  tools_sub: {
    en: "Look up a number, website or account, check a payment screenshot, set up family alerts, and use Hoshiyar outside this website.",
    ur: "نمبر، ویب سائٹ یا اکاؤنٹ تلاش کریں، ادائیگی کا اسکرین شاٹ چیک کریں، فیملی الرٹ لگائیں، اور ہوشیار کو اس ویب سائٹ کے باہر بھی استعمال کریں۔",
    roman: "Number, website ya account dhoondein, payment screenshot check karein, family alert lagayen, aur Hoshiyar ko is website ke bahar bhi use karein.",
  },
  lookup_title: { en: "Look up a number, website or account", ur: "نمبر، ویب سائٹ یا اکاؤنٹ تلاش کریں", roman: "Number, website ya account dhoondein" },
  lookup_placeholder: { en: "0300 1234567, a website, or an account number", ur: "0300 1234567، ویب سائٹ یا اکاؤنٹ نمبر", roman: "0300 1234567, website ya account number" },
  lookup_button: { en: "Look up", ur: "تلاش کریں", roman: "Dhoondein" },
  lookup_private: {
    en: "What you type is not stored. Numbers are compared as one-way fingerprints.",
    ur: "آپ کا لکھا محفوظ نہیں ہوتا۔ نمبر ایک طرفہ فنگر پرنٹ کی صورت میں ملائے جاتے ہیں۔",
    roman: "Aap ka likha save nahi hota. Number one-way fingerprint ki soorat mein milaye jate hain.",
  },
  lookup_confirmed: { en: "confirmed reports", ur: "تصدیق شدہ رپورٹس", roman: "tasdeeq shuda reports" },
  receipt_title: { en: "Is this payment real?", ur: "کیا یہ ادائیگی اصلی ہے؟", roman: "Kya yeh payment asli hai?" },
  receipt_sub: {
    en: "Someone sent you a JazzCash, Easypaisa or bank screenshot as proof of payment. A screenshot can never prove a payment; this check points out things to look at.",
    ur: "کسی نے ادائیگی کے ثبوت کے طور پر جاز کیش، ایزی پیسہ یا بینک کا اسکرین شاٹ بھیجا ہے۔ اسکرین شاٹ ادائیگی کا ثبوت نہیں ہو سکتا؛ یہ جانچ دیکھنے کی چیزیں بتاتی ہے۔",
    roman: "Kisi ne payment ke saboot ke tor par JazzCash, Easypaisa ya bank ka screenshot bheja hai. Screenshot payment ka saboot nahi ho sakta; yeh check dekhne ki cheezein batata hai.",
  },
  receipt_pick: { en: "Choose the payment screenshot", ur: "ادائیگی کا اسکرین شاٹ منتخب کریں", roman: "Payment screenshot chunein" },
  receipt_button: { en: "Check screenshot", ur: "اسکرین شاٹ چیک کریں", roman: "Screenshot check karein" },
  receipt_fields: { en: "What the screenshot says", ur: "اسکرین شاٹ میں کیا لکھا ہے", roman: "Screenshot mein kya likha hai" },
  receipt_findings: { en: "Things to look at", ur: "دیکھنے کی چیزیں", roman: "Dekhne ki cheezein" },
  receipt_expected: { en: "Amount you are expecting (optional)", ur: "آپ کو کتنی رقم ملنی ہے (اختیاری)", roman: "Aap ko kitni raqam milni hai (ikhtiyari)" },
  receipt_mine: {
    en: "Your own number or account (optional, last 4 digits are enough)",
    ur: "آپ کا اپنا نمبر یا اکاؤنٹ (اختیاری، آخری 4 ہندسے کافی ہیں)",
    roman: "Aap ka apna number ya account (ikhtiyari, aakhri 4 digits kaafi hain)",
  },
  receipt_private: {
    en: "These two help catch \"I sent you too much\" tricks and payments sent to someone else. They are compared and forgotten, never stored.",
    ur: "یہ دونوں \"زیادہ بھیج دیے\" والی چال اور کسی اور کو بھیجی گئی ادائیگی پکڑنے میں مدد دیتے ہیں۔ صرف موازنہ ہوتا ہے، محفوظ نہیں کیے جاتے۔",
    roman: "Yeh dono \"zyada bhej diye\" wali chaal aur kisi aur ko bheji gayi payment pakarne mein madad dete hain. Sirf muqabla hota hai, save nahi kiye jate.",
  },
  receipt_likely_fake: {
    en: "Strong signs this screenshot is fake or edited. Do not hand anything over until the money shows in your own app.",
    ur: "اس اسکرین شاٹ کے جعلی یا ایڈٹ شدہ ہونے کی واضح نشانیاں ہیں۔ جب تک رقم آپ کی اپنی ایپ میں نظر نہ آئے، کچھ حوالے نہ کریں۔",
    roman: "Is screenshot ke jaali ya edit kiye hue hone ki wazeh nishaniyan hain. Jab tak raqam aap ki apni app mein nazar na aaye, kuch hawale na karein.",
  },
  receipt_suspicious: {
    en: "Some things do not add up. Check your own app before you trust this screenshot.",
    ur: "کچھ چیزیں میل نہیں کھاتیں۔ اس اسکرین شاٹ پر بھروسہ کرنے سے پہلے اپنی ایپ چیک کریں۔",
    roman: "Kuch cheezein mel nahi khatein. Is screenshot par bharosa karne se pehle apni app check karein.",
  },
  receipt_none: {
    en: "Nothing obviously wrong was found, but that proves nothing. Check your own app.",
    ur: "کوئی واضح خرابی نہیں ملی، لیکن اس سے کچھ ثابت نہیں ہوتا۔ اپنی ایپ چیک کریں۔",
    roman: "Koi wazeh kharabi nahi mili, lekin is se kuch sabit nahi hota. Apni app check karein.",
  },
  experimental: { en: "Experimental", ur: "تجرباتی", roman: "Tajurbati" },
  family_title: { en: "Family alerts", ur: "فیملی الرٹ", roman: "Family alert" },
  family_sub: {
    en: "If someone in your family often gets scam messages, a relative can get a Telegram alert whenever a check from this browser comes back as a likely scam. They see the scam type, never the message.",
    ur: "اگر گھر میں کسی کو اکثر فراڈ پیغامات آتے ہیں تو اس براؤزر کا کوئی چیک فراڈ نکلنے پر کسی رشتہ دار کو ٹیلی گرام الرٹ مل سکتا ہے۔ انہیں صرف فراڈ کی قسم دکھتی ہے، پیغام کبھی نہیں۔",
    roman: "Agar ghar mein kisi ko aksar fraud messages aate hain to is browser ka koi check fraud nikalne par kisi rishtedar ko Telegram alert mil sakta hai. Unhein sirf fraud ki qisam dikhti hai, message kabhi nahi.",
  },
  family_get: { en: "Get a family code", ur: "فیملی کوڈ لیں", roman: "Family code lein" },
  family_code_is: { en: "Your code (valid for 24 hours)", ur: "آپ کا کوڈ (24 گھنٹے کے لیے)", roman: "Aap ka code (24 ghante ke liye)" },
  family_how: {
    en: "Ask your relative to open the Hoshiyar bot in Telegram and send:",
    ur: "اپنے رشتہ دار سے کہیں کہ ٹیلی گرام میں ہوشیار بوٹ کھول کر یہ بھیجیں:",
    roman: "Apne rishtedar se kahein ke Telegram mein Hoshiyar bot khol kar yeh bhejein:",
  },
  family_linked: { en: "relative(s) get alerts from this browser.", ur: "رشتہ داروں کو اس براؤزر کے الرٹ ملتے ہیں۔", roman: "rishtedaron ko is browser ke alert milte hain." },
  family_stop: { en: "Stop family alerts", ur: "فیملی الرٹ بند کریں", roman: "Family alert band karein" },
  family_unavailable: {
    en: "Family alerts need the Telegram bot, which is not set up on this server yet.",
    ur: "فیملی الرٹ کے لیے ٹیلی گرام بوٹ ضروری ہے، جو ابھی اس سرور پر نہیں لگا۔",
    roman: "Family alert ke liye Telegram bot zaroori hai, jo abhi is server par nahi laga.",
  },
  install_title: { en: "Use Hoshiyar anywhere", ur: "ہوشیار کو کہیں بھی استعمال کریں", roman: "Hoshiyar ko kahin bhi use karein" },
  install_pwa: { en: "Install on your phone", ur: "فون پر انسٹال کریں", roman: "Phone par install karein" },
  install_pwa_sub: {
    en: "Adds Hoshiyar to your home screen. On Android you can then share a message from WhatsApp straight to it.",
    ur: "ہوشیار کو ہوم اسکرین پر لگا دیتا ہے۔ اینڈرائیڈ پر پھر آپ واٹس ایپ سے پیغام سیدھا اس میں شیئر کر سکتے ہیں۔",
    roman: "Hoshiyar ko home screen par laga deta hai. Android par phir aap WhatsApp se message seedha is mein share kar sakte hain.",
  },
  install_button: { en: "Install", ur: "انسٹال کریں", roman: "Install karein" },
  install_ios: {
    en: "On iPhone: open this site in Safari, tap Share, then \"Add to Home Screen\".",
    ur: "آئی فون پر: یہ سائٹ سفاری میں کھولیں، شیئر دبائیں، پھر \"Add to Home Screen\"۔",
    roman: "iPhone par: yeh site Safari mein kholein, Share dabayen, phir \"Add to Home Screen\".",
  },
  install_done: { en: "Installed", ur: "انسٹال ہو گیا", roman: "Install ho gaya" },
  install_ext: { en: "Browser extension", ur: "براؤزر ایکسٹینشن", roman: "Browser extension" },
  install_ext_sub: {
    en: "Right-click any text or link to check it, and see a warning on look-alike bank and government sites. The look-alike check runs inside your browser; nothing you browse is sent anywhere.",
    ur: "کسی بھی متن یا لنک پر رائٹ کلک کر کے چیک کریں، اور جعلی بینک اور سرکاری ویب سائٹس پر انتباہ دیکھیں۔ یہ جانچ آپ کے براؤزر کے اندر ہوتی ہے؛ آپ کی براؤزنگ کہیں نہیں بھیجی جاتی۔",
    roman: "Kisi bhi text ya link par right click kar ke check karein, aur jaali bank aur sarkari websites par warning dekhein. Yeh jaanch aap ke browser ke andar hoti hai; aap ki browsing kahin nahi bheji jati.",
  },
  install_tg: { en: "Telegram bot", ur: "ٹیلی گرام بوٹ", roman: "Telegram bot" },
  install_tg_sub: {
    en: "Forward a message, screenshot or voice note to the bot and get the verdict in your language.",
    ur: "بوٹ کو پیغام، اسکرین شاٹ یا وائس نوٹ فارورڈ کریں اور اپنی زبان میں نتیجہ پائیں۔",
    roman: "Bot ko message, screenshot ya voice note forward karein aur apni zuban mein natija payein.",
  },
  install_mcp: { en: "For AI assistants (MCP)", ur: "اے آئی اسسٹنٹس کے لیے (MCP)", roman: "AI assistants ke liye (MCP)" },
  install_mcp_sub: {
    en: "Claude Desktop and other MCP clients can call Hoshiyar's check, lookup and campaign tools. The rule book's verdict is passed through unchanged.",
    ur: "کلاڈ ڈیسک ٹاپ اور دوسرے MCP کلائنٹ ہوشیار کے چیک، تلاش اور مہم والے ٹولز استعمال کر سکتے ہیں۔ قواعد کا فیصلہ بغیر تبدیلی کے آگے جاتا ہے۔",
    roman: "Claude Desktop aur doosre MCP clients Hoshiyar ke check, lookup aur campaign tools use kar sakte hain. Rule book ka faisla baghair tabdeeli ke aage jata hai.",
  },

  campaigns_title: { en: "Scam campaigns", ur: "فراڈ مہمات", roman: "Fraud muhimmat" },
  campaigns_sub: {
    en: "Reports that share a website, number or wording are grouped. Only reviewed or rule-confirmed reports count.",
    ur: "جن رپورٹس میں ایک ہی ویب سائٹ، نمبر یا الفاظ ہوں انہیں اکٹھا کیا جاتا ہے۔ صرف جائزہ شدہ یا قواعد سے تصدیق شدہ رپورٹس شمار ہوتی ہیں۔",
    roman: "Jin reports mein ek hi website, number ya alfaaz hon unhein ikattha kiya jata hai. Sirf reviewed ya rules se tasdeeq shuda reports shumar hoti hain.",
  },
  reports_word: { en: "reports", ur: "رپورٹس", roman: "reports" },
  last_seen: { en: "last seen", ur: "آخری بار", roman: "aakhri baar" },
  weekly_title: { en: "This week's warning", ur: "اس ہفتے کا انتباہ", roman: "Is hafte ki warning" },
  weekly_none: {
    en: "No weekly warning has been sent yet.",
    ur: "ابھی تک کوئی ہفتہ وار انتباہ نہیں بھیجا گیا۔",
    roman: "Abhi tak koi haftawar warning nahi bheji gayi.",
  },
  weekly_flagged: { en: "checks flagged", ur: "چیک نشان زد", roman: "checks flag hue" },
  weekly_avoid: { en: "Do not open", ur: "یہ نہ کھولیں", roman: "Yeh na kholein" },

  quiz_title: { en: "Spot the scam", ur: "فراڈ پہچانیں", roman: "Fraud pehchanein" },
  quiz_sub: {
    en: "Eight messages like the ones people really get. Is each one a scam or genuine?",
    ur: "آٹھ پیغامات، ویسے ہی جیسے لوگوں کو واقعی آتے ہیں۔ ہر ایک فراڈ ہے یا اصلی؟",
    roman: "Aath messages, waise hi jaise logon ko waqai aate hain. Har ek fraud hai ya asli?",
  },
  quiz_scam: { en: "Scam", ur: "فراڈ", roman: "Fraud" },
  quiz_real: { en: "Genuine", ur: "اصلی", roman: "Asli" },
  quiz_next: { en: "Next", ur: "اگلا", roman: "Agla" },
  quiz_right: { en: "Right.", ur: "درست۔", roman: "Durust." },
  quiz_wrong: { en: "Not quite.", ur: "صحیح نہیں۔", roman: "Sahi nahi." },
  quiz_score: { en: "Your score", ur: "آپ کا اسکور", roman: "Aap ka score" },
  quiz_again: { en: "Play again", ur: "دوبارہ کھیلیں", roman: "Dobara khelein" },
  quiz_from: { en: "From", ur: "از", roman: "Az" },
  quiz_share: { en: "Share with family", ur: "گھر والوں سے شیئر کریں", roman: "Ghar walon se share karein" },
  quiz_question: { en: "Message", ur: "پیغام", roman: "Message" },

  quality_title: { en: "How well it works, in numbers", ur: "یہ کتنا درست ہے، اعداد میں", roman: "Yeh kitna durust hai, numbers mein" },
  quality_sub: {
    en: "Produced by eval/run_eval.py and eval/redteam.py. The CI pipeline fails if precision, recall or the red-team pass rate drop below the thresholds.",
    ur: "یہ eval/run_eval.py اور eval/redteam.py سے بنتے ہیں۔ اگر درستگی، پکڑ یا ریڈ ٹیم کا نتیجہ حد سے نیچے جائے تو CI ناکام ہو جاتا ہے۔",
    roman: "Yeh eval/run_eval.py aur eval/redteam.py se bante hain. Agar precision, recall ya red-team ka natija had se neeche jaye to CI fail ho jata hai.",
  },
  q_test: { en: "Held-out test set", ur: "الگ رکھا گیا ٹیسٹ سیٹ", roman: "Alag rakha gaya test set" },
  q_dev: { en: "Development set (used for tuning)", ur: "ڈیولپمنٹ سیٹ (ٹیوننگ کے لیے)", roman: "Development set (tuning ke liye)" },
  q_ai: { en: "Test set with the AI pipeline", ur: "اے آئی کے ساتھ ٹیسٹ سیٹ", roman: "AI ke saath test set" },
  q_redteam: { en: "Red team: attempts to fool the checker", ur: "ریڈ ٹیم: چیکر کو دھوکہ دینے کی کوششیں", roman: "Red team: checker ko dhoka dene ki koshishein" },
  q_by_category: { en: "Caught by scam type", ur: "فراڈ کی قسم کے لحاظ سے", roman: "Fraud ki qisam ke lihaz se" },
  q_by_language: { en: "Caught by language", ur: "زبان کے لحاظ سے", roman: "Zuban ke lihaz se" },
  q_attack: { en: "Attack", ur: "حملہ", roman: "Hamla" },
  q_expect: { en: "Expected", ur: "متوقع", roman: "Mutawaqqa" },
  q_got: { en: "Got", ur: "نتیجہ", roman: "Natija" },
  q_passed: { en: "passed", ur: "کامیاب", roman: "kamyab" },
  q_missed: { en: "Missed or false alarm", ur: "چھوٹ گئے یا غلط الارم", roman: "Chhoot gaye ya ghalat alarm" },
  q_none: { en: "none", ur: "کوئی نہیں", roman: "koi nahi" },
  q_generated: { en: "Generated", ur: "تاریخ", roman: "Tareekh" },
  q_honest: {
    en: "All sets were written by the project author. The red-team cases were written together with the defences, so they are regression tests, not proof that the checker cannot be fooled.",
    ur: "تمام سیٹ پروجیکٹ کے مصنف نے لکھے ہیں۔ ریڈ ٹیم کیسز دفاع کے ساتھ ہی لکھے گئے، اس لیے یہ ریگریشن ٹیسٹ ہیں، اس بات کا ثبوت نہیں کہ چیکر کو دھوکہ نہیں دیا جا سکتا۔",
    roman: "Tamam sets project ke author ne likhe hain. Red-team cases defences ke saath hi likhe gaye, is liye yeh regression tests hain, is baat ka saboot nahi ke checker ko dhoka nahi diya ja sakta.",
  },
  q_more: { en: "Full numbers", ur: "مکمل اعداد", roman: "Mukammal numbers" },

  privacy_title: { en: "What happens to your data", ur: "آپ کے ڈیٹا کے ساتھ کیا ہوتا ہے", roman: "Aap ke data ke saath kya hota hai" },
  privacy_sub: {
    en: "Hoshiyar is built to need as little of your data as possible. This page lists exactly what is kept, for how long, and who sees it.",
    ur: "ہوشیار کو اس طرح بنایا گیا ہے کہ اسے آپ کا کم سے کم ڈیٹا چاہیے۔ اس صفحے پر لکھا ہے کہ کیا رکھا جاتا ہے، کتنی دیر، اور کون دیکھتا ہے۔",
    roman: "Hoshiyar ko is tarah banaya gaya hai ke use aap ka kam se kam data chahiye. Is safhe par likha hai ke kya rakha jata hai, kitni dair, aur kaun dekhta hai.",
  },
  retention_title: { en: "How long things are kept", ur: "کیا کتنی دیر رکھا جاتا ہے", roman: "Kya kitni dair rakha jata hai" },
  days: { en: "days", ur: "دن", roman: "din" },
  hours: { en: "hours", ur: "گھنٹے", roman: "ghante" },
  forget_title: { en: "Delete my data", ur: "میرا ڈیٹا حذف کریں", roman: "Mera data delete karein" },
  forget_sub: {
    en: "Removes the checks made from this browser, your language setting and family alerts. Reports you shared stay, because they are already anonymised, but they are no longer linked to you.",
    ur: "اس براؤزر سے کیے گئے چیک، زبان کی ترتیب اور فیملی الرٹ حذف ہو جاتے ہیں۔ آپ کی شیئر کی گئی رپورٹس رہتی ہیں کیونکہ وہ پہلے ہی گمنام ہیں، لیکن آپ سے منسلک نہیں رہتیں۔",
    roman: "Is browser se kiye gaye checks, zuban ki setting aur family alerts delete ho jate hain. Aap ki share ki gayi reports rehti hain kyunke woh pehle hi gumnaam hain, lekin aap se link nahi rehtin.",
  },
  forget_button: { en: "Delete my data", ur: "میرا ڈیٹا حذف کریں", roman: "Mera data delete karein" },
  forget_confirm: { en: "Yes, delete it", ur: "ہاں، حذف کریں", roman: "Haan, delete karein" },
  forget_done: { en: "Done. Checks deleted:", ur: "ہو گیا۔ حذف شدہ چیک:", roman: "Ho gaya. Delete hue checks:" },
  on: { en: "on", ur: "فعال", roman: "on" },
  off: { en: "off", ur: "بند", roman: "off" },
} satisfies Record<string, I18n>;

export type StringKey = keyof typeof S;

interface LangState {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: StringKey | string) => string;
  pick: (value: I18n | undefined | null) => string;
}

const Ctx = createContext<LangState | null>(null);

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem("ss_lang");
    if (saved === "en" || saved === "ur" || saved === "roman") return saved;
  } catch {
    /* storage unavailable */
  }
  return "en";
}

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);

  useEffect(() => {
    const root = document.documentElement;
    root.lang = lang === "ur" ? "ur" : "en";
    root.dir = lang === "ur" ? "rtl" : "ltr";
    root.dataset.lang = lang;
  }, [lang]);

  const value = useMemo<LangState>(() => {
    const setLang = (l: Lang) => {
      setLangState(l);
      try {
        localStorage.setItem("ss_lang", l);
      } catch {
        /* ignore */
      }
    };
    return {
      lang,
      setLang,
      t: (key) => (S as Record<string, I18n>)[key]?.[lang] ?? (S as Record<string, I18n>)[key]?.en ?? key,
      pick: (v) => (v ? v[lang] || v.en : ""),
    };
  }, [lang]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useLang(): LangState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useLang outside LangProvider");
  return v;
}
