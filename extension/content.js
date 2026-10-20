/* Look-alike site warning. Runs locally: the page address is compared with a built-in list of
 * official bank, wallet and government sites. Nothing is sent anywhere. */
(async function () {
  if (window.top !== window) return;
  try {
    const { banner } = await chrome.storage.sync.get({ banner: true });
    if (!banner) return;
  } catch {
    /* storage unavailable: show the warning anyway */
  }
  const verdict = globalThis.HoshiyarLookalike && globalThis.HoshiyarLookalike.assess(location.hostname);
  if (!verdict) return;
  // Sandboxed pages make sessionStorage throw; that must never stop the warning.
  let dismissed = false;
  try {
    dismissed = Boolean(sessionStorage.getItem("hoshiyar-dismissed-" + location.hostname));
  } catch {
    dismissed = false;
  }
  if (dismissed) return;

  const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const host = document.createElement("div");
  host.setAttribute("data-hoshiyar", "");
  const shadow = host.attachShadow({ mode: "closed" });
  const why =
    verdict.reason === "homograph"
      ? `This address looks like ${esc(verdict.official)} but is really ${esc(verdict.ascii)}: it uses look-alike letters to imitate ${esc(verdict.brand.name)}.`
      : `This site looks like ${esc(verdict.brand.name)}, but it is not its official site.`;
  shadow.innerHTML = `
    <style>
      .bar { position: fixed; inset: 0 0 auto 0; z-index: 2147483647; display: flex; gap: 14px; align-items: center;
        padding: 12px 18px; background: #0c2420; color: #e7eee6; font: 15px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif;
        border-bottom: 3px solid #f2668c; box-shadow: 0 10px 30px rgba(0,0,0,.45); }
      .mark { flex: none; width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center;
        background: #f2668c; color: #0c2420; font-weight: 700; font-size: 20px; }
      .text { flex: 1; }
      .text b { color: #ffd0dc; }
      .real { color: #9fe3c8; }
      button { flex: none; border: 1px solid rgba(231,238,230,.3); background: transparent; color: #e7eee6;
        border-radius: 999px; padding: 6px 14px; font: inherit; cursor: pointer; }
      button:hover { border-color: #9fe3c8; }
    </style>
    <div class="bar" role="alert">
      <span class="mark">!</span>
      <span class="text"><b>Hoshiyar warning:</b> ${why} Do not enter passwords, PINs, OTPs or card details here.
        The real site is <span class="real">${esc(verdict.official)}</span>.</span>
      <button type="button">Dismiss</button>
    </div>`;
  shadow.querySelector("button").addEventListener("click", () => {
    try {
      sessionStorage.setItem("hoshiyar-dismissed-" + location.hostname, "1");
    } catch {
      /* not remembered on sandboxed pages */
    }
    host.remove();
  });
  document.documentElement.appendChild(host);
})();
