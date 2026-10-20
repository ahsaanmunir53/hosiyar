import { useEffect, useState } from "react";
import type { Lang } from "../api";
import { useLang } from "../i18n";

// Roman Urdu reads best with an Indian English or Hindi voice; Urdu script needs an Urdu voice.
const VOICE_PREFS: Record<Lang, string[]> = {
  en: ["en-PK", "en-IN", "en-GB", "en"],
  ur: ["ur-PK", "ur-IN", "ur"],
  roman: ["hi-IN", "en-IN", "en"],
};

function pickVoice(lang: Lang): SpeechSynthesisVoice | null {
  const voices = window.speechSynthesis.getVoices();
  for (const pref of VOICE_PREFS[lang]) {
    const v = voices.find((x) => x.lang.toLowerCase().startsWith(pref.toLowerCase()));
    if (v) return v;
  }
  return null;
}

/** Reads the result aloud with the device's own speech engine (nothing is sent anywhere). */
export default function ReadAloud({ text }: { text: string }) {
  const { t, lang } = useLang();
  const [speaking, setSpeaking] = useState(false);
  const [noVoice, setNoVoice] = useState(false);
  const supported = typeof window !== "undefined" && "speechSynthesis" in window;

  useEffect(() => () => {
    if (supported) window.speechSynthesis.cancel();
  }, [supported]);

  if (!supported) return null;

  function toggle() {
    const synth = window.speechSynthesis;
    if (speaking) {
      synth.cancel();
      setSpeaking(false);
      return;
    }
    const u = new SpeechSynthesisUtterance(text);
    const voice = pickVoice(lang);
    setNoVoice(!voice);
    if (voice) {
      u.voice = voice;
      u.lang = voice.lang;
    } else {
      u.lang = lang === "ur" ? "ur-PK" : "en-IN";
    }
    u.rate = 0.95;
    u.onend = () => setSpeaking(false);
    u.onerror = () => setSpeaking(false);
    synth.cancel();
    synth.speak(u);
    setSpeaking(true);
  }

  return (
    <span className="readaloud">
      <button type="button" className="btn btn--ghost btn--small" onClick={toggle} aria-pressed={speaking}>
        <svg viewBox="0 0 20 20" width="15" height="15" aria-hidden="true">
          <path d="M3 8h3l4-3v10l-4-3H3z" fill="currentColor" />
          {speaking ? (
            <path d="M13 7l4 6M17 7l-4 6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          ) : (
            <path d="M13 7.5a3.5 3.5 0 010 5M15 5a7 7 0 010 10" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          )}
        </svg>
        {speaking ? t("stop_reading") : t("read_aloud")}
      </button>
      {speaking && noVoice && <span className="field__hint">{t("no_voice")}</span>}
    </span>
  );
}
