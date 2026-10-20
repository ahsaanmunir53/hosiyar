import { useLang } from "../i18n";
import CheckPage from "./CheckPage";

// Read once per page load. Kept outside React state because the page can be mounted twice
// while lazy parts (the 3D seal) load, and the address bar is cleared after the first read.
let captured: string | null = null;

function captureShared(): string {
  if (captured === null) {
    const q = new URLSearchParams(window.location.search);
    const parts = [q.get("title"), q.get("text"), q.get("url")].filter((x): x is string => Boolean(x && x.trim()));
    captured = [...new Set(parts)].join("\n").slice(0, 4000);
    window.history.replaceState(null, "", "/");
  }
  return captured;
}

/** Target of the installed app's "share to Hoshiyar" (Web Share Target, GET). The shared text is
 * moved into the form and removed from the address bar and browser history straight away; the
 * service worker answers /share from its cache, so the text does not reach the web server. */
export default function SharePage() {
  const { t } = useLang();
  const prefill = captureShared();
  return <CheckPage prefill={prefill} note={prefill ? t("share_note") : undefined} />;
}
