/** Decode a QR code from a photo, entirely in the browser (jsQR is loaded only when needed). */
export async function decodeQr(file: Blob): Promise<string | null> {
  const { default: jsQR } = await import("jsqr");
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
  const w = Math.max(1, Math.round(bitmap.width * scale));
  const h = Math.max(1, Math.round(bitmap.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return null;
  ctx.drawImage(bitmap, 0, 0, w, h);
  bitmap.close();
  const { data } = ctx.getImageData(0, 0, w, h);
  return jsQR(data, w, h, { inversionAttempts: "attemptBoth" })?.data ?? null;
}

/** EMVCo payment QR (Raast and most wallets): who would be paid. The server checks the same thing. */
export function previewPaymentQr(payload: string): { merchant: string | null; amount: string | null } | null {
  if (!payload.startsWith("000201")) return null;
  const fields: Record<string, string> = {};
  let i = 0;
  while (i + 4 <= payload.length) {
    const tag = payload.slice(i, i + 2);
    const len = Number(payload.slice(i + 2, i + 4));
    if (!/^\d\d$/.test(tag) || Number.isNaN(len)) break;
    fields[tag] = payload.slice(i + 4, i + 4 + len);
    i += 4 + len;
  }
  return { merchant: fields["59"] ?? null, amount: fields["54"] ?? null };
}
