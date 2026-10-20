/* Shared settings for the popup, options page and background worker. */
const HOSHIYAR_DEFAULTS = {
  apiUrl: "http://localhost:8000",
  appUrl: "",
  integrationKey: "",
  language: "en",
  banner: true,
};

async function hoshiyarSettings() {
  const stored = await chrome.storage.sync.get(HOSHIYAR_DEFAULTS);
  return { ...HOSHIYAR_DEFAULTS, ...stored, apiUrl: String(stored.apiUrl || HOSHIYAR_DEFAULTS.apiUrl).replace(/\/$/, "") };
}

async function hoshiyarCheck(text) {
  const s = await hoshiyarSettings();
  const headers = { "Content-Type": "application/json" };
  if (s.integrationKey) headers["X-Hoshiyar-Key"] = s.integrationKey;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 90000);
  try {
    const res = await fetch(`${s.apiUrl}/api/analyze`, {
      method: "POST",
      headers,
      body: JSON.stringify({ text: text.slice(0, 4000), language: s.language }),
      signal: controller.signal,
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : `HTTP ${res.status}`);
    return body;
  } finally {
    clearTimeout(timer);
  }
}
