# Hoshiyar browser extension (Chrome, Edge, Brave)

* Right-click selected text or a link and choose **Check with Hoshiyar**. The verdict shows on the
  toolbar badge (! scam, ? suspicious, ✓ no red flags) and in the popup.
* A warning bar appears on sites that imitate a bank, wallet or government site, including
  addresses written with look-alike letters (`xn--` punycode). This check runs inside the browser
  against a built-in list; the pages you visit are never sent anywhere.

## Install (developer mode, free)

1. Open `chrome://extensions` and turn on **Developer mode**.
2. Click **Load unpacked** and choose this `extension` folder.
3. Open the extension's **Settings** and enter your Hoshiyar API address
   (for example `https://hoshiyar-api.onrender.com`).
4. If the server has a captcha (`TURNSTILE_SECRET`), also enter its `INTEGRATION_KEY`.

Publishing on the Chrome Web Store costs a one-time developer fee, so it is not needed for this project.

## Tests

```bash
node --test extension/test/*.test.js
```
