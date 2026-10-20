import { NavLink } from "react-router-dom";
import type { Lang } from "../api";
import { useLang } from "../i18n";

const LANGS: { id: Lang; label: string }[] = [
  { id: "en", label: "English" },
  { id: "ur", label: "اردو" },
  { id: "roman", label: "Roman" },
];

export default function Header() {
  const { t, lang, setLang } = useLang();
  return (
    <header className="topbar">
      <NavLink to="/" className="wordmark" aria-label="Hoshiyar home">
        <svg viewBox="0 0 32 32" width="28" height="28" aria-hidden="true">
          <circle cx="16" cy="16" r="14.5" fill="none" stroke="currentColor" strokeOpacity=".45" />
          <circle cx="16" cy="16" r="11" fill="none" stroke="var(--foil-gold)" strokeOpacity=".7" />
          <path d="M16 7.5l6.5 2.5v5c0 4.5-2.8 7.8-6.5 9.5-3.7-1.7-6.5-5-6.5-9.5v-5z" fill="currentColor" />
        </svg>
        <span className="wordmark__en">Hoshiyar</span>
        <span className="wordmark__ur" lang="ur">ہوشیار</span>
      </NavLink>
      <nav className="topnav" aria-label="Main">
        <NavLink to="/" end>
          {t("nav_check")}
        </NavLink>
        <NavLink to="/tools">{t("nav_tools")}</NavLink>
        <NavLink to="/trends">{t("nav_trends")}</NavLink>
        <NavLink to="/quiz">{t("nav_quiz")}</NavLink>
        <NavLink to="/how">{t("nav_how")}</NavLink>
      </nav>
      <div className="langswitch" role="group" aria-label={t("lang_label")}>
        {LANGS.map((l) => (
          <button
            key={l.id}
            type="button"
            className={l.id === lang ? "is-active" : ""}
            aria-pressed={l.id === lang}
            lang={l.id === "ur" ? "ur" : "en"}
            onClick={() => setLang(l.id)}
          >
            {l.label}
          </button>
        ))}
      </div>
    </header>
  );
}
