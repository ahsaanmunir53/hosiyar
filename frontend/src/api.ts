export type Lang = "en" | "ur" | "roman";
export type I18n = Record<Lang, string>;
export type Verdict = "likely_scam" | "suspicious" | "no_red_flags";

export interface Reason {
  id: string;
  weight: number;
  hard: boolean;
  title: I18n;
  why: I18n;
  evidence: string[];
  sources: string[];
}

export interface Step {
  id: string;
  text: I18n;
  urgent: boolean;
  link?: string | null;
}

export interface LinkReport {
  url: string;
  host?: string;
  homograph_of?: string | null;
  is_punycode?: boolean;
  registered_domain: string;
  final_registered_domain: string;
  expanded_url: string | null;
  is_shortener: boolean;
  official_brand: { key: string; name: string } | null;
  lookalike_brand: { key: string; name: string } | null;
  domain_age_days: number | null;
  safe_browsing_threats: string[];
  risky_tld: boolean;
  is_ip: boolean;
  checks: string[];
  errors: string[];
}

export interface SimilarReport {
  key: string;
  source: "pattern_library" | "community";
  similarity: number;
  verdict: string;
  category: string;
  excerpt: string;
  synthetic: boolean;
}

export interface TraceStep {
  step: string;
  by: "rules" | "ai" | "agent" | "guard";
  detail: Record<string, unknown>;
}

export interface Analysis {
  id: string;
  thread_id: string;
  verdict: Verdict;
  score: number;
  category: { id: string; label: I18n };
  language: Lang;
  explanation: { language: Lang; text: string; source: "ai" | "template"; templates: I18n };
  reasons: Reason[];
  links: LinkReport[];
  similar: SimilarReport[];
  reported_number_count: number;
  next_steps: Step[];
  investigation: TraceStep[];
  redactions: Record<string, number>;
  analyzed_text: string;
  source_kind: SourceKind;
  source_language: string;
  file_info: FileInfo | null;
  reported_account_count: number;
  watchlist: { kind: string; label: string; note?: string | null }[];
  report_status: "approved" | "pending" | null;
  ai_summary: string | null;
  model: string;
  rules_version: string;
  degraded: string[];
  shared: boolean;
}

export type SourceKind = "text" | "image" | "audio" | "qr" | "pdf" | "email";

export interface PaymentQr {
  merchant_name: string | null;
  city: string | null;
  country: string | null;
  amount: string | null;
  currency: string | null;
  dynamic: boolean;
  checksum_ok: boolean | null;
}

export type FileInfo =
  | { kind: "pdf"; pages: number; pages_read: number; links: string[]; active_content: string[]; attachments: string[] }
  | {
      kind: "email";
      from_name: string;
      from_domain: string;
      reply_to_domain: string | null;
      subject: string;
      auth: Record<string, string>;
      attachments: string[];
      links: string[];
    }
  | { kind: "qr"; content_type: string; payment: PaymentQr | null };

export interface FollowupAnswer {
  question: string;
  answer: string;
  language: Lang;
  source: "ai" | "template";
}

export interface Stats {
  window_days: number;
  total_checks: number;
  verdicts: Partial<Record<Verdict, number>>;
  daily: Array<{ date: string } & Record<Verdict, number>>;
  top_categories: { category: string; count: number }[];
  top_brands: { brand: string; count: number }[];
  top_rules: { rule: string; count: number }[];
  recent_reports: { id: string; created_at: string; verdict: Verdict; category: string; excerpt: string; sample: boolean }[];
  includes_sample_data: boolean;
  sample_rows: number;
}

export interface RuleBookEntry {
  id: string;
  weight: number;
  title: I18n;
  why: I18n;
}

export interface Channel {
  name: string;
  url?: string;
  phone?: string;
  sms_shortcode?: string;
  for: string;
  source: string;
}

export const API_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

let memoryClientId: string | null = null;

export function clientId(): string {
  try {
    const existing = localStorage.getItem("ss_client_id");
    if (existing) return existing;
    const id = crypto.randomUUID();
    localStorage.setItem("ss_client_id", id);
    return id;
  } catch {
    memoryClientId ??= crypto.randomUUID();
    return memoryClientId;
  }
}

// --------------------------------------------------------------------------- waking the free server
// Render's free plan stops the API after 15 quiet minutes; the next request starts it again, which
// takes 30-60 seconds. A slow request alone proves nothing (an AI check can take 10 seconds), so
// when one is slow we ask /api/health: if that does not answer within 2 seconds either, the server
// is asleep and the bottom bar shows until health answers.

const SLOW_MS = 3500;
type WakeListener = (waking: boolean) => void;
const wakeListeners = new Set<WakeListener>();
let probing = false;

export function onWaking(fn: WakeListener): () => void {
  wakeListeners.add(fn);
  return () => void wakeListeners.delete(fn);
}

function emitWaking(waking: boolean) {
  wakeListeners.forEach((fn) => fn(waking));
}

/** Ask the health endpoint; show the bar if it is slow too, hide it when it answers. Resolves true if it answered. */
function probeHealth(showAfterMs: number): Promise<boolean> {
  if (probing) return Promise.resolve(true);
  probing = true;
  let shown = false;
  const show = setTimeout(() => {
    shown = true;
    emitWaking(true);
  }, showAfterMs);
  const controller = new AbortController();
  const giveUp = setTimeout(() => controller.abort(), 150_000);
  return fetch(`${API_URL}/api/health`, { cache: "no-store", signal: controller.signal })
    .then((r) => r.ok, () => false)
    .finally(() => {
      clearTimeout(show);
      clearTimeout(giveUp);
      probing = false;
      if (shown) emitWaking(false);
    });
}

async function request<T>(path: string, init?: RequestInit, timeoutMs = 90_000): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const slowTimer = setTimeout(() => void probeHealth(2000), SLOW_MS);
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, signal: controller.signal });
  } catch {
    throw new ApiError("network", 0);
  } finally {
    clearTimeout(timer);
    clearTimeout(slowTimer);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep status text */
    }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export function analyzeText(input: {
  text: string;
  sender?: string;
  share: boolean;
  language: Lang;
  sourceKind?: "text" | "qr";
  captcha?: string | null;
}) {
  return request<Analysis>(
    "/api/analyze",
    json({
      text: input.text,
      sender: input.sender || null,
      share: input.share,
      language: input.language,
      source_kind: input.sourceKind ?? "text",
      captcha_token: input.captcha ?? null,
      client_id: clientId(),
    }),
  );
}

export function analyzeEmail(input: { raw: string; share: boolean; language: Lang; captcha?: string | null }) {
  return request<Analysis>(
    "/api/analyze/email",
    json({ raw: input.raw, share: input.share, language: input.language, captcha_token: input.captcha ?? null, client_id: clientId() }),
  );
}

export function analyzeFile(input: {
  file: Blob;
  filename: string;
  sender?: string;
  share: boolean;
  language: Lang;
  note?: string;
  captcha?: string | null;
}) {
  const form = new FormData();
  form.append("file", input.file, input.filename);
  if (input.sender) form.append("sender", input.sender);
  if (input.note) form.append("note", input.note);
  if (input.captcha) form.append("captcha_token", input.captcha);
  form.append("share", String(input.share));
  form.append("language", input.language);
  form.append("client_id", clientId());
  return request<Analysis>("/api/analyze/upload", { method: "POST", body: form });
}

export function askFollowup(threadId: string, question: string, language: Lang) {
  return request<{ thread_id: string; answer: FollowupAnswer }>("/api/followup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id: threadId, question, language, client_id: clientId() }),
  });
}

// --- Tools -------------------------------------------------------------------

export interface LookupResult {
  kind: "phone" | "link" | "account";
  display: string;
  status: "known_scam" | "reported" | "no_reports" | "official" | "lookalike";
  message: I18n;
  confirmed_reports: number;
  watchlist: { label: string; note: string | null } | null;
  sender_kind?: string;
  shortcode_note?: I18n | null;
  link_report?: LinkReport;
}

export const lookupValue = (value: string, captcha?: string | null) =>
  request<LookupResult>("/api/lookup", json({ value, kind: "auto", captcha_token: captcha ?? null }));

export interface TakedownInfo {
  url: string;
  domain: string;
  official: { name: string } | null;
  registrar: string | null;
  abuse_email: string | null;
  registered: string | null;
  rdap_url: string | null;
  google_report_url: string;
  email?: { subject: string; body: string };
  mailto?: string;
  errors: string[];
}

export const getTakedown = (url: string) => request<TakedownInfo>("/api/takedown", json({ url }));

export interface ReceiptResult {
  experimental: true;
  fields: Record<string, string | string[] | null>;
  findings: { id: string; severity: "high" | "medium" | "low"; text: I18n; source?: string }[];
  // Never "real": a screenshot cannot prove a payment.
  assessment?: "likely_fake" | "suspicious" | "no_signs";
  image?: { width: number | null; height: number | null };
  advice: I18n[];
  unavailable?: string;
}

export function checkReceipt(
  file: Blob,
  filename: string,
  captcha?: string | null,
  extra?: { expectedAmount?: string; myAccount?: string },
) {
  const form = new FormData();
  form.append("file", file, filename);
  if (captcha) form.append("captcha_token", captcha);
  if (extra?.expectedAmount?.trim()) form.append("expected_amount", extra.expectedAmount.trim().slice(0, 40));
  if (extra?.myAccount?.trim()) form.append("my_account", extra.myAccount.trim().slice(0, 40));
  form.append("client_id", clientId());
  return request<ReceiptResult>("/api/receipt", { method: "POST", body: form });
}

export const familyCode = () =>
  request<{ code: string; expires_hours: number; bot: string | null }>("/api/family/code", json({ client_id: clientId() }));
export const familyStatus = () =>
  request<{ guardians: number; pending_code: string | null; available: boolean; bot: string | null }>(
    "/api/family/status",
    json({ client_id: clientId() }),
  );
export const familyRemove = () => request<{ removed: number }>("/api/family/remove", json({ client_id: clientId() }));
export const forgetMe = () => request<{ deleted: Record<string, number> }>("/api/me/forget", json({ client_id: clientId() }));

export interface Campaign {
  id: string;
  label: string;
  category: string;
  report_count: number;
  brands: string[];
  first_seen: string;
  last_seen: string;
  indicators: { kind: string; value: string }[];
}

export const getCampaigns = () => request<{ campaigns: Campaign[] }>("/api/campaigns");

export interface WeeklyAlert {
  created_at: string;
  from: string;
  to: string;
  checks: number;
  flagged: number;
  top_categories: { category: string; count: number }[];
  top_brands: { brand: string; count: number }[];
  domains: string[];
}

export const getLatestAlert = () => request<{ alert: WeeklyAlert | null }>("/api/alerts/latest");

export interface EvalRun {
  name: string;
  model: string;
  messages: number;
  strict: { precision: number; recall: number; f1: number; fp: number; tp: number; fn: number; tn: number };
  flagged: { precision: number; recall: number; fp: number; fpr: number };
  ai_failed: number;
  missed: string[];
  false_alarms: string[];
  by_category: Record<string, { n: number; caught: number; flagged: number }>;
  by_language: Record<string, { n: number; caught: number; flagged: number }>;
}

export interface EvalSet {
  messages: number;
  scam: number;
  legit: number;
  runs: EvalRun[];
}

export interface Quality {
  eval: { generated_at: string; rules_version: string; test: EvalSet; dev: EvalSet; test_ai?: EvalSet } | null;
  redteam: {
    generated_at: string;
    runs: {
      name: string;
      passed: number;
      total: number;
      cases: { id: string; attack: string; expect: string; verdict: Verdict; score: number; passed: boolean }[];
    }[];
  } | null;
}

export const getQuality = () => request<Quality>("/api/quality");

export interface PrivacyInfo {
  retention_days: Record<string, number>;
  providers: Record<string, boolean>;
}

export const getPrivacy = () => request<PrivacyInfo>("/api/privacy");

// --- Review panel ------------------------------------------------------------------

export function authed(token: string, init: RequestInit = {}): RequestInit {
  return { ...init, headers: { ...(init.headers as Record<string, string> | undefined), Authorization: `Bearer ${token}` } };
}

export const login = (email: string, password: string) =>
  request<{ token: string; email: string; role: "admin" | "analyst"; expires_in_hours: number }>(
    "/api/auth/login",
    json({ email, password }),
  );

export const adminGet = <T,>(token: string, path: string) => request<T>(path, authed(token));
export const adminPost = <T,>(token: string, path: string, body: unknown = {}) => request<T>(path, authed(token, json(body)));
export const adminDelete = <T,>(token: string, path: string) => request<T>(path, authed(token, { method: "DELETE" }));

export const getStats = () => request<Stats>("/api/stats");
export const getRules = () => request<{ version: string; rules: RuleBookEntry[] }>("/api/rules");
export const getChannels = () => request<Record<string, Channel>>("/api/channels");
export const getHealth = () =>
  request<{
    status: string;
    llm: string | false;
    model: string;
    embeddings: string;
    screenshots: boolean;
    voice_notes: boolean;
    telegram: boolean;
    captcha: boolean;
  }>("/api/health", undefined, 90_000);

/** Called once when the site opens, so the API starts waking before the visitor presses anything. */
export function warmUp(): Promise<boolean> {
  return probeHealth(3000);
}
