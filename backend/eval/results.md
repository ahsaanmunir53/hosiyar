# Evaluation results

Messages are in English, Urdu and Roman Urdu and reflect common Pakistani SMS and WhatsApp scams. Both sets were written by the project author, so treat the numbers as a sanity check, not a benchmark. Network link checks (domain age, short-link expansion, Safe Browsing) were off.

- **Dev set** (`eval/dev.jsonl`) was used while writing and tuning the rules.
- **Test set** (`eval/test.jsonl`) was written after the rules were frozen and was not used for tuning. Two changes were made after it was written: a bug fix (Urdu letters in patterns were not normalised the same way as the message text) and challan/PSID vocabulary added after a real user report. Later additions (red-team defences, file and email checks, overseas-job and cross-border names) left the test-set numbers unchanged. No weights were tuned to the test set, and its misses are listed below.

*Strict* counts only `likely_scam` as a positive. *Flagged* also counts `suspicious`.

## Test set (held out)

60 messages: 36 scam, 24 legitimate.

| Set-up | Model | Messages | Strict precision | Strict recall | Strict F1 | Flagged recall | False alarms on legit |
|---|---|---|---|---|---|---|---|
| rules only | none | 60 | 100.0% | 77.8% | 87.5% | 97.2% | 0 of 24 (0.0%) |
| rules + pattern memory | none | 60 | 100.0% | 77.8% | 87.5% | 97.2% | 0 of 24 (0.0%) |

Misses and false alarms (rules only):

- missed `t04` → suspicious (45): threat, urgency, claims_government, link_risky_tld
- missed `t13` → suspicious (25): threat, urgency
- missed `t19` → suspicious (30): fee_request
- missed `t20` → suspicious (30): fee_request
- missed `t31` → suspicious (25): threat, urgency
- missed `t32` → no_red_flags (20): login_link
- missed `t33` → suspicious (40): login_link, urgency, link_risky_tld
- missed `t36` → suspicious (30): money_transfer, urgency

Misses and false alarms (rules + pattern memory):

- missed `t04` → suspicious (45): threat, urgency, claims_government, link_risky_tld
- missed `t13` → suspicious (45): memory_match, threat, urgency
- missed `t19` → suspicious (30): fee_request
- missed `t20` → suspicious (30): fee_request
- missed `t31` → suspicious (45): memory_match, threat, urgency
- missed `t32` → no_red_flags (20): login_link
- missed `t33` → suspicious (40): login_link, urgency, link_risky_tld
- missed `t36` → suspicious (30): money_transfer, urgency

## Test set with the AI pipeline

20 messages: 10 scam, 10 legitimate.

| Set-up | Model | Messages | Strict precision | Strict recall | Strict F1 | Flagged recall | False alarms on legit |
|---|---|---|---|---|---|---|---|
| full (AI + memory) | groq/openai/gpt-oss-120b → gemini/gemini-3.5-flash-lite → groq/openai/gpt-oss-20b · local768 embeddings | 20 | 100.0% | 100.0% | 100.0% | 100.0% | 0 of 10 (0.0%) |

Messages read by (full (AI + memory)): `openai/gpt-oss-120b` 20.

Misses and false alarms (full (AI + memory)):

- none

## Dev set (used for tuning)

100 messages: 60 scam, 40 legitimate.

| Set-up | Model | Messages | Strict precision | Strict recall | Strict F1 | Flagged recall | False alarms on legit |
|---|---|---|---|---|---|---|---|
| rules only | none | 100 | 100.0% | 96.7% | 98.3% | 100.0% | 0 of 40 (0.0%) |
| rules + pattern memory | none | 100 | 100.0% | 98.3% | 99.2% | 100.0% | 0 of 40 (0.0%) |

Misses and false alarms (rules only):

- missed `s44` → suspicious (47): link_not_official, link_shortener, delivery_bait
- missed `s48` → suspicious (45): call_request, threat, urgency

Misses and false alarms (rules + pattern memory):

- missed `s44` → suspicious (47): link_not_official, link_shortener, delivery_bait

