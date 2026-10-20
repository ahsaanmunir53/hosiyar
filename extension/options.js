const fields = ["apiUrl", "appUrl", "integrationKey", "language"];

hoshiyarSettings().then((s) => {
  fields.forEach((f) => (document.getElementById(f).value = s[f] || ""));
  document.getElementById("banner").checked = s.banner;
});

document.getElementById("save").addEventListener("click", async () => {
  const values = Object.fromEntries(fields.map((f) => [f, document.getElementById(f).value.trim()]));
  values.banner = document.getElementById("banner").checked;
  try {
    const origin = new URL(values.apiUrl).origin;
    if (!/\.onrender\.com$|^http:\/\/(localhost|127\.0\.0\.1):8000$/.test(origin)) {
      await chrome.permissions.request({ origins: [`${origin}/*`] });
    }
  } catch {
    /* invalid URL: saved anyway, the popup will show the error */
  }
  await chrome.storage.sync.set(values);
  const saved = document.getElementById("saved");
  saved.hidden = false;
  setTimeout(() => (saved.hidden = true), 1500);
});
