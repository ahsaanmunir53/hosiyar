/* Context menu checks. Only text you choose to check is sent to your Hoshiyar server. */
importScripts("settings.js");

const BADGE = {
  likely_scam: { text: "!", color: "#f2668c" },
  suspicious: { text: "?", color: "#e7b54c" },
  no_red_flags: { text: "✓", color: "#5ccfa5" },
};

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: "hoshiyar-text", title: "Check \"%s\" with Hoshiyar", contexts: ["selection"] });
  chrome.contextMenus.create({ id: "hoshiyar-link", title: "Check this link with Hoshiyar", contexts: ["link"] });
});

async function runCheck(text, source) {
  await chrome.storage.session.set({ last: { state: "checking", text, source, at: Date.now() } });
  chrome.action.setBadgeText({ text: "…" });
  chrome.action.setBadgeBackgroundColor({ color: "#84998f" });
  try {
    const result = await hoshiyarCheck(text);
    await chrome.storage.session.set({ last: { state: "done", text, source, result, at: Date.now() } });
    const badge = BADGE[result.verdict] || BADGE.suspicious;
    chrome.action.setBadgeText({ text: badge.text });
    chrome.action.setBadgeBackgroundColor({ color: badge.color });
  } catch (err) {
    await chrome.storage.session.set({ last: { state: "error", text, source, error: String(err.message || err), at: Date.now() } });
    chrome.action.setBadgeText({ text: "×" });
    chrome.action.setBadgeBackgroundColor({ color: "#84998f" });
  }
}

chrome.contextMenus.onClicked.addListener((info) => {
  const text = info.menuItemId === "hoshiyar-link" ? `Link: ${info.linkUrl}` : info.selectionText || "";
  if (!text.trim()) return;
  // Opening the popup from a menu click works in recent Chrome; otherwise the badge shows the verdict.
  if (chrome.action.openPopup) chrome.action.openPopup().catch(() => undefined);
  runCheck(text, info.menuItemId === "hoshiyar-link" ? "link" : "selection");
});

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg && msg.type === "check" && typeof msg.text === "string") {
    runCheck(msg.text, "popup").then(() => reply({ ok: true }));
    return true;
  }
  return false;
});
