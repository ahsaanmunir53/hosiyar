import type { FileInfo } from "../api";
import { useLang } from "../i18n";

function AuthBadge({ name, value }: { name: string; value: string }) {
  const tone = value === "pass" ? "tag--good" : value === "fail" || value === "softfail" ? "tag--bad" : "tag--muted";
  return (
    <span className={`tag ${tone}`} dir="ltr">
      {name.toUpperCase()} {value}
    </span>
  );
}

/** What the file reader found: email sender checks, PDF contents, or a payment QR code. */
export default function FileInfoPanel({ info }: { info: FileInfo }) {
  const { t } = useLang();
  if (info.kind === "email") {
    return (
      <section className="panel">
        <h3>{t("file_email_title")}</h3>
        <dl className="facts">
          <dt>{t("file_from")}</dt>
          <dd dir="ltr">
            {info.from_name && <span>{info.from_name} </span>}
            <code>{info.from_domain || "—"}</code>
          </dd>
          {info.reply_to_domain && (
            <>
              <dt>{t("file_reply_to")}</dt>
              <dd dir="ltr">
                <code>{info.reply_to_domain}</code>
              </dd>
            </>
          )}
          <dt>{t("file_checks")}</dt>
          <dd className="facts__tags">
            {Object.keys(info.auth).length ? (
              Object.entries(info.auth).map(([k, v]) => <AuthBadge key={k} name={k} value={v} />)
            ) : (
              <span className="muted">{t("file_none")}</span>
            )}
          </dd>
          <dt>{t("file_attachments")}</dt>
          <dd dir="ltr">{info.attachments.length ? info.attachments.join(", ") : <span className="muted">{t("file_none")}</span>}</dd>
        </dl>
      </section>
    );
  }
  if (info.kind === "pdf") {
    return (
      <section className="panel">
        <h3>{t("file_pdf_title")}</h3>
        <dl className="facts">
          <dt>{t("file_pages")}</dt>
          <dd>
            {info.pages_read} / {info.pages}
          </dd>
          <dt>{t("file_active")}</dt>
          <dd className="facts__tags">
            {info.active_content.length ? (
              info.active_content.map((a) => (
                <span key={a} className="tag tag--bad">
                  {a}
                </span>
              ))
            ) : (
              <span className="muted">{t("file_none")}</span>
            )}
          </dd>
          <dt>{t("file_attachments")}</dt>
          <dd dir="ltr">{info.attachments.length ? info.attachments.join(", ") : <span className="muted">{t("file_none")}</span>}</dd>
          <dt>{t("file_links")}</dt>
          <dd>{info.links.length}</dd>
        </dl>
      </section>
    );
  }
  if (info.kind === "qr" && info.payment) {
    const p = info.payment;
    return (
      <section className="panel panel--alert">
        <h3>{t("qr_payment_title")}</h3>
        <p>{t("qr_payment_body")}</p>
        <dl className="facts">
          <dt>{t("qr_merchant")}</dt>
          <dd>
            <strong>{p.merchant_name ?? "—"}</strong>
            {p.city && <span className="muted"> · {p.city}</span>}
          </dd>
          {p.amount && (
            <>
              <dt>{t("qr_amount")}</dt>
              <dd dir="ltr">
                {p.currency} {p.amount}
              </dd>
            </>
          )}
        </dl>
        {p.checksum_ok === false && <p className="notice notice--bad">{t("qr_checksum_bad")}</p>}
      </section>
    );
  }
  return null;
}
