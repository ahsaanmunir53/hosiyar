/* Hoshiyar look-alike detector. Runs entirely in the browser: nothing about the pages you visit
 * is sent anywhere. A port of the backend's lookalike_brand() for the most imitated names.
 * Loaded as a classic script (content script) and as a CommonJS module (tests). */
(function (root) {
  "use strict";

  const BRANDS = [
    ["hbl", "HBL", "bank", ["hbl.com"], ["hbl", "habibbank"]],
    ["ubl", "UBL", "bank", ["ubldigital.com"], ["ubl", "unitedbank"]],
    ["mcb", "MCB", "bank", ["mcb.com.pk"], ["mcb"]],
    ["meezan", "Meezan Bank", "bank", ["meezanbank.com"], ["meezan"]],
    ["nbp", "National Bank", "bank", ["nbp.com.pk"], ["nbp", "nationalbank"]],
    ["alfalah", "Bank Alfalah", "bank", ["bankalfalah.com"], ["alfalah", "bankalfalah"]],
    ["abl", "Allied Bank", "bank", ["abl.com"], ["alliedbank", "abl"]],
    ["faysal", "Faysal Bank", "bank", ["faysalbank.com"], ["faysalbank", "faysal"]],
    ["bankislami", "BankIslami", "bank", ["bankislami.com.pk"], ["bankislami"]],
    ["jazzcash", "JazzCash", "wallet", ["jazzcash.com.pk"], ["jazzcash"]],
    ["easypaisa", "Easypaisa", "wallet", ["easypaisa.com.pk"], ["easypaisa"]],
    ["nayapay", "NayaPay", "wallet", ["nayapay.com"], ["nayapay"]],
    ["sadapay", "SadaPay", "wallet", ["sadapay.pk"], ["sadapay"]],
    ["bisp", "BISP", "government", ["bisp.gov.pk"], ["bisp", "benazir", "ehsaas", "ehsas"]],
    ["nadra", "NADRA", "government", ["nadra.gov.pk"], ["nadra"]],
    ["fbr", "FBR", "government", ["fbr.gov.pk"], ["fbr"]],
    ["pta", "PTA", "government", ["pta.gov.pk"], ["pta"]],
    ["sbp", "State Bank of Pakistan", "government", ["sbp.org.pk"], ["statebank", "sbp"]],
    ["psca", "Punjab Safe Cities Authority", "government", ["psca.gop.pk"], ["psca", "punjabsafecity"]],
    ["epay_punjab", "ePay Punjab", "platform", ["epay.punjab.gov.pk"], ["epaypunjab"]],
    ["beoe", "Bureau of Emigration", "government", ["beoe.gov.pk"], ["beoe", "bureauofemigration"]],
    ["pakpost", "Pakistan Post", "courier", ["pakpost.gov.pk"], ["pakistanpost", "pakpost"]],
    ["tcs", "TCS", "courier", ["tcsexpress.com"], ["tcs"]],
    ["leopards", "Leopards Courier", "courier", ["leopardscourier.com"], ["leopards"]],
    ["daraz", "Daraz", "platform", ["daraz.pk"], ["daraz"]],
    ["whatsapp", "WhatsApp", "platform", ["whatsapp.com", "whatsapp.net", "wa.me"], ["whatsapp"]],
    ["facebook", "Facebook", "platform", ["facebook.com", "fb.com", "messenger.com"], ["facebook"]],
    ["google", "Google", "platform", ["google.com", "google.com.pk", "googleusercontent.com", "youtube.com"], ["google"]],
    ["jazz", "Jazz", "telecom", ["jazz.com.pk"], ["jazz", "mobilink"]],
    ["zong", "Zong", "telecom", ["zong.com.pk"], ["zong"]],
    ["ufone", "Ufone", "telecom", ["ufone.com"], ["ufone"]],
    ["telenor", "Telenor", "telecom", ["telenor.com.pk"], ["telenor"]],
    ["lesco", "LESCO", "utility", ["lesco.gov.pk"], ["lesco"]],
    ["kelectric", "K-Electric", "utility", ["ke.com.pk"], ["kelectric"]],
    ["sngpl", "SNGPL", "utility", ["sngpl.com.pk"], ["sngpl", "suigas"]],
    ["sg_mom", "Ministry of Manpower Singapore", "government", ["mom.gov.sg"], ["ministryofmanpower"], false],
    ["sg_police", "Singapore Police Force", "government", ["police.gov.sg"], ["singaporepolice"], false],
    ["sa_absher", "Absher", "government", ["absher.sa"], ["absher"]],
  ].map(([key, name, kind, domains, aliases, loose = true]) => ({ key, name, kind, domains, aliases, loose }));

  const GOVERNMENT_SUFFIXES = ["gov.pk", "gop.pk", "gov.sg", "gov.ae", "gov.sa"];
  const TWO_LEVEL = new Set([
    "com.pk", "gov.pk", "gop.pk", "org.pk", "net.pk", "edu.pk", "web.pk", "biz.pk", "fam.pk",
    "co.uk", "org.uk", "gov.uk", "ac.uk", "com.sg", "gov.sg", "edu.sg", "org.sg", "net.sg",
    "co.ae", "gov.ae", "com.sa", "gov.sa", "com.my", "co.in", "com.au", "com.tr", "com.bd",
  ]);
  const SUBSTRING_KINDS = new Set(["bank", "wallet", "government", "utility", "courier"]);
  const HOMOGLYPHS = { 0: "o", 1: "l", 3: "e", 4: "a", 5: "s", 7: "t", "@": "a", $: "s" };
  const CONFUSABLES = {
    а: "a", е: "e", о: "o", р: "p", с: "c", у: "y", х: "x", і: "i", ј: "j", ѕ: "s", һ: "h", ԁ: "d", ӏ: "l",
    α: "a", ο: "o", ρ: "p", ν: "v", τ: "t", ι: "i", κ: "k",
  };

  function levenshtein(a, b) {
    if (a === b) return 0;
    let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
    for (let i = 1; i <= a.length; i++) {
      const cur = [i];
      for (let j = 1; j <= b.length; j++) {
        cur.push(Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1)));
      }
      prev = cur;
    }
    return prev[b.length];
  }

  // RFC 3492 Punycode decoding, so "xn--bl-3wc.com" can be read as "һbl.com".
  function punyDecode(input) {
    const base = 36, tMin = 1, tMax = 26, skew = 38, damp = 700;
    let n = 128, i = 0, bias = 72;
    const out = [];
    const b = input.lastIndexOf("-");
    for (let j = 0; j < Math.max(b, 0); j++) out.push(input.charCodeAt(j));
    const adapt = (delta, numPoints, first) => {
      delta = first ? Math.floor(delta / damp) : delta >> 1;
      delta += Math.floor(delta / numPoints);
      let k = 0;
      while (delta > ((base - tMin) * tMax) >> 1) {
        delta = Math.floor(delta / (base - tMin));
        k += base;
      }
      return k + Math.floor(((base - tMin + 1) * delta) / (delta + skew));
    };
    for (let idx = b > 0 ? b + 1 : 0; idx < input.length; ) {
      const oldi = i;
      for (let w = 1, k = base; ; k += base) {
        if (idx >= input.length) throw new Error("bad punycode");
        const c = input.charCodeAt(idx++);
        const digit = c - 48 < 10 ? c - 22 : c - 65 < 26 ? c - 65 : c - 97 < 26 ? c - 97 : base;
        if (digit >= base) throw new Error("bad punycode");
        i += digit * w;
        const t = k <= bias ? tMin : k >= bias + tMax ? tMax : k - bias;
        if (digit < t) break;
        w *= base - t;
      }
      bias = adapt(i - oldi, out.length + 1, oldi === 0);
      n += Math.floor(i / (out.length + 1));
      i %= out.length + 1;
      out.splice(i++, 0, n);
    }
    return String.fromCodePoint(...out);
  }

  function toUnicode(host) {
    return host
      .split(".")
      .map((label) => {
        if (!label.startsWith("xn--")) return label;
        try {
          return punyDecode(label.slice(4));
        } catch {
          return label;
        }
      })
      .join(".");
  }

  function foldConfusables(text) {
    return Array.from(text, (ch) => CONFUSABLES[ch] || ch).join("");
  }

  function registeredDomain(host) {
    const parts = host.toLowerCase().replace(/\.$/, "").split(".");
    if (parts.length < 2) return host;
    const lastTwo = parts.slice(-2).join(".");
    return TWO_LEVEL.has(lastTwo) && parts.length >= 3 ? parts.slice(-3).join(".") : lastTwo;
  }

  function officialBrand(host) {
    const h = host.toLowerCase();
    const reg = registeredDomain(h);
    for (const b of BRANDS) {
      for (const d of b.domains) if (reg === d || h === d || h.endsWith("." + d)) return b;
    }
    return null;
  }

  function isGovernment(host) {
    return GOVERNMENT_SUFFIXES.some((s) => host.toLowerCase().endsWith("." + s));
  }

  function lookalike(host) {
    const hostL = host.toLowerCase();
    const reg = registeredDomain(hostL);
    if (!reg || officialBrand(hostL) || isGovernment(hostL)) return null;
    const label = reg.split(".")[0];
    const compact = label.replace(/-/g, "");
    const folded = Array.from(compact, (c) => HOMOGLYPHS[c] || c).join("").replace(/rn/g, "m").replace(/vv/g, "w");
    const tokens = new Set(label.split(/[-_]/));
    const subTokens = new Set(hostL.slice(0, -reg.length).replace(/\.$/, "").split(/[-_.]/).filter((x) => x && x !== "www"));
    const foldedTokens = new Set([...tokens].map((t) => Array.from(t, (c) => HOMOGLYPHS[c] || c).join("")));
    for (const b of BRANDS) {
      const names = new Set([b.key, ...b.aliases]);
      for (const t of [...tokens, ...foldedTokens]) if (names.has(t)) return b;
      for (const t of foldedTokens) {
        if (t.length >= 6) for (const n of names) if (n.length >= 6 && levenshtein(t, n) === 1) return b;
      }
      if (b.kind !== "platform") for (const n of names) if (n !== b.key && n.length >= 8 && compact.includes(n)) return b;
      if (SUBSTRING_KINDS.has(b.kind)) for (const t of subTokens) if (names.has(t)) return b;
      for (const official of b.domains) {
        const officialLabel = official.split(".")[0];
        if (officialLabel.length < 3) continue;
        if (hostL.startsWith(official + ".") || hostL.includes("." + official + ".")) return b;
        if (!b.loose) continue;
        if (compact === officialLabel || folded === officialLabel) return b;
        if (SUBSTRING_KINDS.has(b.kind)) {
          if (officialLabel.length >= 4 && compact.includes(officialLabel)) return b;
          if (officialLabel.length === 3 && (label.startsWith(officialLabel + "-") || label.endsWith("-" + officialLabel))) return b;
        }
        const limit = officialLabel.length >= 8 ? 2 : officialLabel.length >= 5 ? 1 : 0;
        if (limit) {
          const d1 = levenshtein(compact, officialLabel);
          const d2 = levenshtein(folded, officialLabel);
          if ((d1 > 0 && d1 <= limit) || (d2 > 0 && d2 <= limit)) return b;
        }
      }
    }
    return null;
  }

  /** What to tell the user about a hostname, or null when there is nothing to say. */
  function assess(hostname) {
    const ascii = hostname.toLowerCase();
    const unicode = toUnicode(ascii);
    if (unicode !== ascii) {
      const folded = foldConfusables(unicode);
      if (folded !== unicode && /^[\x00-\x7f]+$/.test(folded)) {
        const brand = officialBrand(folded) || lookalike(folded);
        if (brand) return { brand, reason: "homograph", shown: unicode, ascii, official: brand.domains[0] };
      }
    }
    const brand = lookalike(ascii);
    if (brand && (SUBSTRING_KINDS.has(brand.kind) || brand.kind === "telecom" || brand.kind === "platform")) {
      return { brand, reason: "lookalike", shown: ascii, ascii, official: brand.domains[0] };
    }
    return null;
  }

  const api = { assess, lookalike, officialBrand, registeredDomain, toUnicode, foldConfusables, BRANDS };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.HoshiyarLookalike = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
