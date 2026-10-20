const LABELS = { likely_scam: "Likely scam", suspicious: "Suspicious", no_red_flags: "No red flags found" };
const box = document.getElementById("result");
const form = document.getElementById("form");
const input = document.getElementById("text");
const button = form.querySelector("button");

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => (k === "class" ? (node.className = v) : node.setAttribute(k, v)));
  children.flat().forEach((c) => c != null && node.append(c));
  return node;
}

async function render(last) {
  box.replaceChildren();
  if (!last) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  box.className = "";
  if (last.state === "checking") {
    box.append(el("p", { class: "muted" }, "Checking… the free server may take up to a minute to wake up."));
    button.disabled = true;
    return;
  }
  button.disabled = false;
  if (last.state === "error") {
    box.append(el("p", { class: "error" }, `Could not check: ${last.error}`), el("p", { class: "muted" }, "Check the server address in Settings."));
    return;
  }
  const r = last.result;
  const lang = r.language || "en";
  box.className = r.verdict;
  box.append(
    el("div", { class: "verdict" }, el("b", {}, LABELS[r.verdict] || r.verdict), el("span", {}, `${r.score}/100 · ${r.category.label[lang] || r.category.label.en}`)),
    el("p", { class: "explain", dir: "auto" }, r.explanation.text),
  );
  const reasons = (r.reasons || []).filter((x) => x.weight > 0).slice(0, 3);
  if (reasons.length) box.append(el("ul", {}, reasons.map((x) => el("li", { dir: "auto" }, x.title[lang] || x.title.en))));
  const steps = (r.next_steps || []).slice(0, 2);
  if (steps.length) box.append(el("ul", { class: "steps" }, steps.map((s) => el("li", { dir: "auto" }, s.text[lang] || s.text.en))));
  const { appUrl } = await hoshiyarSettings();
  if (appUrl) box.append(el("a", { class: "more", href: appUrl, target: "_blank" }, "Open Hoshiyar for the full report"));
}

chrome.storage.session.get("last").then(({ last }) => render(last));
chrome.storage.session.onChanged.addListener((changes) => {
  if (changes.last) render(changes.last.newValue);
});
chrome.action.setBadgeText({ text: "" });

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  button.disabled = true;
  chrome.runtime.sendMessage({ type: "check", text });
});
