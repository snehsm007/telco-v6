# Technical Design Document: telco-v6 (Telco Voice Central)

Source of truth for scope: `prd.md` (the Day 1 brief). Decisions on the brief's open questions: `docs/requirements.md` §Decisions. Layout rules: `docs/DESIGN_RULES.md`, `docs/INSTRUCTION_STYLE.md`.

## 1. Agents (modules ≠ agents, PRD §2)

| Agent | PRD modules | Tools (besides `end_session`) | Children |
|---|---|---|---|
| `router` | M1 | `lookup_account`, `handover_to_person` | billing, tech_support, sales_equipment, account |
| `billing` | M3, M7 restore-from-non-payment (CUJ-6) | auth tools, `lookup_account`, `get_billing_summary`, `process_bill_payment`, `setup_autopay`, `apply_bill_adjustment`, `setup_payment_arrangement`, `verify_payment_and_restore`, `handover_to_person` | router |
| `tech_support` | M4, M6, M8 | auth tools, `lookup_account`, `check_regional_outage`, `run_virtual_repair`, `send_sms_notification`, `get_appointment_and_ticket_status`, `manage_appointment`, `handover_to_person` | router |
| `sales_equipment` | M5 | auth tools, `lookup_account`, `browse_plans`, `place_order`, `file_warranty_claim`, `start_number_transfer`, `handover_to_person` | router |
| `account` | M7 (except restore-from-non-payment) | auth tools, `lookup_account`, `send_password_reset_link`, `manage_mfa`, `execute_suspend_restore`, `cancel_or_port_out_service`, `update_contact_profile`, `handover_to_person` | router |

"Auth tools" = `send_login_code`, `check_login_code`, `check_secret_pin`. The login conversation (offer code or PIN, send, check, wrong code, lockout) and the hand-back to the router are written once, in `cxas_app/global_instruction.txt` subtasks "Verify Caller (specialists)" and "Other Goals (specialists)"; specialist prompts refer to them and never copy them.

Why restore-from-non-payment lives in `billing`: the brief's CUJ-6 path is M7 → M1 → M3 → M7. Clearing the balance and restoring are one atomic operation in `process_bill_payment` / `verify_payment_and_restore` / `setup_payment_arrangement` (DESIGN_RULES rule 34), so the router sends "restore my suspended service" straight to billing. A non-payment restore never transfers M7 → M3 directly, which is the brief's actual constraint. Lost/stolen and travel suspensions belong to `account`.

## 2. Code layout

| File | Contents |
|---|---|
| `lib/fakes.py` | The whole fake world: accounts, bills, ledger, cards, plans, devices, appointments, tickets, outage regions, verbatim lines (`SPOKEN_LINES`), credentials, fixture defaults (§5). Only file with fake records. |
| `lib/core.py` | Shared helpers for every tool: state access, language lock, fixture reads, login gate, error tri-state, mock_mode/mock_error, SMS dispatch helper. No tools. |
| `lib/services.py` | M1/M2/shared tools: `lookup_account`, `send_login_code`, `check_login_code`, `check_secret_pin`, `handover_to_person`, `send_sms_notification`. Re-exports every domain `*_impl` and defines `ALL_TOOLS`. |
| `lib/billing.py` | Billing tool impls. |
| `lib/tech.py` | Tech support + appointments impls. |
| `lib/sales.py` | Sales & equipment impls. |
| `lib/account.py` | Account management impls. |
| `lib/replies.py`, `lib/speech.py`, `lib/dynamic_prompt.py` | Scaffold modules (reply shape, speech hygiene, language sheet). |

Rules for every domain module:
- Top-level names must be unique across `lib/*.py` (the bundler fails on duplicates). Prefix private helpers with the module name, e.g. `_bill_parse_amount`.
- Each tool is `<tool>_impl(<args>, state=None, session_state=None, language="", **kwargs)`. The wrapper in `cxas_app/tools/<tool>/python_function/python_code.py` has the same parameters minus `state`/`session_state`, with union types `str | int | float` on every numeric/code argument (rule 32), no `from __future__ import annotations`.
- Every tool starts with: `state = get_state(state, session_state)`, `lang = session_language(state, language)`, `err = check_mock_error(state, lang, "<tool>")`.
- Account-reading and account-mutating tools call `require_login(state, lang, "<tool>")` and return its reply when not logged in (`NOT_LOGGED_IN`).
- Validation errors go through `validation_error(...)` (counts `global_err_count`; at 3 it returns `TOO_MANY_ERRORS`).
- Tools return data, never sentences. Money: `amount` + `amount_display` + `currency: "CAD"`. Dates: ISO plus a localized `*_display` string built by `core.display_date`.

## 3. Reply shape (unchanged from the scaffold)

`{"status": "ok"|"error", "data": {...}, "error_message": str, "tracking_id": str}`; errors add `error` (code in `lib/replies.ERROR_CODES`) and `agent_action` (≤ 120 chars, never read aloud).

Error tri-state (BR-TV-010):
- System: `SYSTEM_UNAVAILABLE`, `SYSTEM_DOWN`, `INTERNAL_ERROR`, `AUTH_SERVICE_UNAVAILABLE` → agent_action "Hand over with reason system_unavailable."
- Business: `NOT_ELIGIBLE`, `ALREADY_APPLIED`, `INSUFFICIENT_FUNDS`, `CARD_DECLINED`, `REFUND_THRESHOLD_EXCEEDED`, `TECHNICIAN_EN_ROUTE`, `NO_AVAILABILITY`, `STEP_UP_REQUIRED`, `NO_PAYMENT_FOUND`, `CONFIRMATION_REQUIRED`, … → model explains and offers the alternative.
- Validation: `INVALID_INPUT`, `MALFORMED_REQUEST` → re-ask; 3 in a call → `TOO_MANY_ERRORS` → handover `too_many_errors`.

## 4. Tool contracts

Args in `code` font are tool parameters; every tool also takes `language`.

### Shared (lib/services.py)
- **`lookup_account(phone_or_account)`** — identify the caller. Blocked number → `PERMISSION_DENIED` with `blocked: true` (deflect + end). Malformed or structurally invalid number (fails NANP checks, repeated digits, wrong length) → `NOT_FOUND`. Well-formed unknown numbers resolve to a synthetic record (fact-less simulated callers). Returns `account_id_last4`, `phone_last4`, `identification_status: "Pass"`, `business_flag`, `customer_type`, `lines_of_business`, `region`, `service_status`, `preferred_language`. Switching accounts keeps the call's failed-login count (no lockout reset).
- **`send_login_code(channel="sms"|"email")`** — sends a 6-digit code to the phone (sms) or email on file. Returns `sent`, `channel`, `destination_last4` or `email_masked`, `expires_in_sec`. `channel="email"` is the MFA step-up channel. Never returns the code.
- **`check_login_code(code)`** / **`check_secret_pin(pin)`** — shared 3-strike counter. Sets `auth_status="pass"`, `logged_in=true` on success; step-up purpose (email code after `STEP_UP_REQUIRED`) sets `step_up_verified=true` instead of re-logging in. Third failure → `TOO_MANY_ATTEMPTS` (hand over `auth_failure_handoff`). Acceptance rule in §6.
- **`handover_to_person(reason, summary)`** — reason is one of the PRD reason codes (§7). Returns `handoff_message` (the verbatim line(s) for that reason, in the call language), `queue`, `handover_id`, and writes `handoff_context` (session variables for the live agent, BR-TV-015). Sets `handover_complete`.
- **`send_sms_notification(purpose)`** — purpose ∈ `outage_updates`, `troubleshooting_guide`, `slot_available_callback`, `registration_link`. Needs an identified account (any `account_id`); no login needed because the text goes only to the number on file. Returns `sent`, `destination_last4`, `purpose`.

### Billing (lib/billing.py) — all require login
- **`get_billing_summary()`** — `balance_due`, `past_due_amount`, `due_date`, `service_status`, `suspension_reason`, `card_on_file_last4`, `card_on_file_brand`, `autopay_enrolled`, `recent_bills[]` with `line_items[] {charge_id, description, amount, amount_display, lob, date}`, `recent_payments[]`.
- **`process_bill_payment(amount, payment_method, card_number, dtmf_digits)`** — `payment_method` ∈ `card_on_file`, `new_card`, `bank_account`. `amount` empty or "full" = balance due. Validates card digits (13–19) for `new_card`. Card on file declined when fixture says so → `CARD_DECLINED` (clears `card_last4`, keeps `declined_card_last4`). Success returns `payment_id`, `amount_paid_display`, `card_last4` (of the card actually charged), `remaining_balance_display`, `receipt_sms_sent`; and when the payment covers the past-due amount on a non-payment suspension, restores service in the same call (`service_restored: true`, `new_service_status: "active"`, `restore_sms_sent: true`). A partial payment never restores service and never zeroes the balance.
- **`setup_autopay(payment_method, card_number)`** — `card_on_file` / `new_card` / `bank_account`. Returns `autopay_enrolled`, `method`, `card_last4`, `first_charge_date_display`. Already enrolled → `ALREADY_ENROLLED`. The prompt speaks `payment_method_preamble` verbatim before any step that reads a payment method.
- **`apply_bill_adjustment(adjustment_type, amount, description, outage_days, charge_id)`** — `adjustment_type` ∈ `unrecognized_charge`, `incorrect_charge`, `duplicate_payment`, `outage_credit`. Order of checks: (1) amount > `SELF_SERVE_ADJUSTMENT_LIMIT` (25.00) → `REFUND_THRESHOLD_EXCEEDED` (hand over `refund_threshold_exceeded` with `transfer_to_specialist`); (2) charge/amount matches a line item on the latest bill → credit; (3) duplicate payment verified in the ledger → refund of the duplicate; (4) outage credit = monthly price of the affected service ÷ 30 × days, rounded to cents, auto-applied if ≤ limit; (5) no match → opens a dispute case (`dispute_ticket_id`, `eta_business_days`). Credits return `amount_display`, `refund_window_business_days` (`{days}` for `refund_confirmation_pattern`), `credit_id`. Same input twice → `ALREADY_APPLIED`.
- **`setup_payment_arrangement(first_payment_amount)`** — splits the balance into 2 instalments (first today or within 7 days, second 30 days later), restores a non-payment suspension, one arrangement per 12 months (`NOT_ELIGIBLE`). Returns the schedule with display amounts/dates and `service_restored`.
- **`verify_payment_and_restore()`** — for "I already paid": searches the ledger for a posted payment since the suspension that covers the past-due amount. Found → restores, returns `verified_payment_date_display`, `verified_payment_amount_display`, `service_restored`, `restore_sms_sent`. Not found → `NO_PAYMENT_FOUND` with `past_due_amount_display` (offer payment or arrangement). Never restores on the caller's word.

### Tech support & appointments (lib/tech.py)
- **`check_regional_outage(postal_code, lob)`** — no login needed (public area status). Validates Canadian postal code format (`A1A 1A1`, spaces optional) or 5-digit ZIP. Returns `region`, `outage_active`, `affected_services`, `restoration_eta_display`, `outage_id`.
- **`run_virtual_repair(lob, symptom, tv_sub_type)`** — requires login; `lob` ∈ mobility, internet, tv, homephone, smarthome; `tv_sub_type` required when lob=tv (`streaming`, `satellite`, `streaming_only`), else `TV_SUB_TYPE_REQUIRED`. Returns `session_id`, `remote_reset_sent`, `steps[]` (localized step text, data not speech), `step_count`, `sms_recommended` (step_count > 2), `known_issue` notes (e.g. satellite error codes). Symptom matching is by category keywords, never exact eval sentences.
- **`get_appointment_and_ticket_status()`** — requires login. Returns `appointments[] {appointment_id, service_type, date_display, window_display, status: scheduled|en_route|delayed|completed, technician_eta_display, delay_minutes, can_reschedule, can_cancel}`, `tickets[] {ticket_id, lob, issue, status, last_update_display, next_step}`, and `available_slots[]` (3 slots, `slot_id`, localized `date_display`, `window_display`) so a reschedule needs no extra lookup (rule 34).
- **`manage_appointment(action, appointment_id, slot_id, confirmed)`** — `action` ∈ reschedule, cancel, book, add_note. Same-day cancel needs `confirmed=true` on a second call (`CONFIRMATION_REQUIRED` first). Technician en route → cancel refused (`TECHNICIAN_EN_ROUTE`, offer note). Delayed visits can be rescheduled. Returns `new_date_display`, `new_window_display`, `sms_confirmation_sent`.

### Sales & equipment (lib/sales.py)
- **`browse_plans(lob, budget, need)`** — login recommended, not required. Checks coverage at the service address (`coverage_available`, `max_speed_display`), returns at most 3 plans (`plan_id`, `name`, `price_display`, `key_features[]`, `data_display` / `speed_display`), filtered by `budget` (monthly, inclusive) and ranked by `need` keywords; TV add-on packs (e.g. sports) when `lob="tv"` and need mentions a pack. Includes Turn-N+1 fields: `current_plan`, `price_difference_display`, `activation_display`, `contract_terms`.
- **`place_order(plan_id, confirmed)`** — requires login; `confirmed=false` returns the quote (`CONFIRMATION_REQUIRED` with price and effective date); `confirmed=true` places it. Returns `order_id`, `effective_date_display` or `delivery_eta_display`, `new_monthly_total_display`, `sms_receipt_sent`.
- **`file_warranty_claim(device, issue, physical_damage, water_damage)`** — requires login. Uses the device on file (`device_model`, `purchase_date_display`, `warranty_end_display`, `in_warranty`). Physical/water damage or out of warranty → `NOT_ELIGIBLE` with `repair_options`. Safety keywords (swollen/battery bulging/smoke/heat) → `urgent: true`, `safety_advice_key: "battery_safety"`, expedited shipping. Returns `claim_id`, `replacement_eta_display`, `shipping_address_last_line`, `return_instructions`.
- **`start_number_transfer(number_to_transfer, current_provider, current_account_number, transfer_pin, target_line)`** — port-in, requires login. Empty inputs allowed → returns `required_port_checklist` and `status: "pending_details"` (rule 34). With a valid 10-digit number → `transfer_id`, `estimated_completion_display`, `temporary_number_last4` when target is a new line, `sms_updates`. Never returns any PIN.
- Implementation notes (lib/sales.py, fixtures in the `SALES_*` block of lib/fakes.py):
  - `browse_plans`: coverage is checked only once the account is identified (`coverage_checked`); unidentified callers get the catalogue and `coverage_note`. Mobility/internet show only tiers above the current plan; internet plans above the region's `SALES_COVERAGE_MAX_MBPS` are dropped. Capacity needs keep the biggest tiers, price needs the cheapest; options are listed by price. Every option has `new_monthly_total_display` (service) and `new_account_monthly_total_display`.
  - `place_order`: a `confirmed=true` call with no quote read on this call still returns the quote first (`pending_confirmation`). Same plan twice → same `order_id`, `already_placed: true`. Add-on without that service, or an internet speed above coverage → `NOT_ELIGIBLE`. Unknown plan → `INVALID_INPUT` with `valid_plan_ids`.
  - `file_warranty_claim`: with either damage answer empty it is a coverage check (`claim_filed: false`, `damage_check_needed: true`). A safety issue without login returns `NOT_LOGGED_IN` carrying `safety_advice` (generic advice, no account data); the claim is filed only after login. `device_matched: false` when the caller's words match no device on file (most recent device used).
  - `start_number_transfer`: the checklist path (empty or placeholder number) needs no login (decision A3) and carries no account data. Starting needs `current_provider` and `current_account_number`; otherwise `pending_details` with `missing_details` and no `transfer_id`. `target_line`: `new_line` / words like new, add, family → new line with `temporary_number_last4`; a phone number → that existing line (`target_line_last4`); `landline_to_mobile` or landline words → `number_type: "landline"` (longer ETA). A provider name is never read as a port-out.
  - Session variables: `sales_orders`, `sales_claims`, `sales_transfers` (idempotency lists).

### Account (lib/account.py)
- **`send_password_reset_link()`** — needs identification only (PRD §4 routing table), sends a link to the mobile number on file. Returns `sent`, `destination_last4`, `valid_minutes: 30`. Never returns the link. Fixture `fx_sms_delivery="failed"` makes the second request report `delivery_failed`.
- **`manage_mfa(action)`** — `enable` / `disable`, requires login. `disable` requires step-up: first call returns `STEP_UP_REQUIRED` (agent sends an email code with `send_login_code(channel="email")` and checks it); after `step_up_verified` it applies. Returns `mfa_enabled`, `method`, `effective_display`. Already in requested state → `ALREADY_APPLIED`.
- **`execute_suspend_restore(action, reason)`** — `suspend` / `restore`; reasons `lost_stolen`, `travel`. Lost/stolen suspends immediately. Restore of a non-payment suspension → `NOT_ELIGIBLE` with `agent_action` to route to billing. Returns `new_state`, `effective_display`, `sms_confirmation_sent`.
- **`cancel_or_port_out_service(lob, mode, reason, confirmed)`** — `mode` ∈ cancel, port_out; requires login. First call (`confirmed=false`) returns `CONFIRMATION_REQUIRED` with `early_termination_fee_display`, `final_bill_estimate_display`, `effective_date_display`; the prompt speaks `contract_cancellation_fee_disclosure` verbatim, then asks for confirmation. `confirmed=true` returns `cancellation_id` and, for port_out, `transfer_authorization_sent_by_sms: true` (the transfer PIN is texted, never spoken).
- **`update_contact_profile(field, value)`** — `email` / `mobile_number` / `mailing_address`, requires login. Returns `field`, masked `new_value_masked`.

## 5. Fixtures and per-eval overrides

Backend facts that differ per customer are session variables prefixed `fx_` (STRING, default `""`), read only through `core.fixture(state, name)`. In production a real backend supplies them; in evals, the scenario's `variableOverrides` seeds them. An empty value means the fake world's default from `lib/fakes.py` `FIXTURE_DEFAULTS`. Overrides never touch `auth_status`, `identification_status` or `logged_in` (PRD §5: never mock auth in evals).

| Fixture | Values (default first) | Used by |
|---|---|---|
| `fx_pin_on_file` | "" = login ladder (§6) / exact 4-digit PIN | `check_secret_pin` |
| `fx_otp_on_file` | "" = ladder / exact 6-digit code the "SMS" carried | `check_login_code` |
| `fx_card_on_file_status` | `valid` / `declined` / `expired` | `process_bill_payment`, `setup_autopay` |
| `fx_service_status` | `active` / `suspended_nonpayment` / `suspended_lost_stolen` / `suspended_travel` | lookup, billing, account |
| `fx_recent_payment` | `none` / `posted_yesterday` (covers past due, not yet applied) | `verify_payment_and_restore` |
| `fx_business_account` | `false` / `true` | `lookup_account` |
| `fx_outage_status` | "" = regional table / `active` / `none` | `check_regional_outage` |
| `fx_technician_status` | `scheduled` / `en_route` / `delayed` | appointments |
| `fx_duplicate_payment` | `false` / `true` | `apply_bill_adjustment`, billing summary |
| `fx_extra_bill_line` | "" / `description|amount|lob` | billing summary, adjustments |
| `fx_device_warranty` | `in_warranty` / `out_of_warranty` | `file_warranty_claim` |
| `fx_mfa_enabled` | `false` / `true` | `manage_mfa` |
| `fx_sms_delivery` | `delivered` / `failed` | password reset |

Which evals carry overrides is listed in `docs/requirements.md` §Eval fixtures, each with its reason.

## 6. Login acceptance (DESIGN_RULES rule 21, extended)

- When `fx_pin_on_file` / `fx_otp_on_file` is set, only that exact value passes, on any attempt.
- Otherwise the ladder: attempt 1 accepts any well-formed code (4 digits for PIN, 4–8 for codes) that is not weak; attempt 2 accepts only `VALID_PINS | VALID_OTPS`; attempt 3 always fails.
- Weak codes (all one repeated digit) always fail.
- Formats are enforced with the patterns in `lib/fakes.py`: a verification code is exactly 6 digits (`OTP_RE`), a PIN exactly 4 (`PIN_RE`). Anything else is a validation error (re-ask, never a strike). A 4-digit value given to `check_login_code` is checked as a PIN; a 6-digit value given to `check_secret_pin` after a code was sent is checked as the code.
- Caller identifiers must match `PHONE_NANP_RE`, `PHONE_LOCAL_PAIRS_RE`, `PHONE_INTL_RE`, `ACCOUNT_NUMBER_RE` (6–15 digits) or `ACCOUNT_REFERENCE_RE` (letters + at least 4 digits); one repeated digit and dummy runs are rejected.
- One shared failure counter for codes and PINs per call; it survives account switches.
- PIN entry: in text the caller's typed digits count as keypad entry; in voice, PIN capture uses DTMF (`dtmf_digits`). Tools read `dtmf_digits` when the argument is empty.

## 7. Handover reasons and verbatim lines

| Reason code | Line spoken (verbatim, call language) |
|---|---|
| `user_requested_agent`, `auth_failure_handoff`, `no_input_escalation`, `disambig_max_attempts`, `system_unavailable`, `too_many_errors`, `secondary_language_live_agent`, `sms_delivery_failed` | `live_agent_handoff` |
| `business_handoff` | `business_handoff` |
| `fraud_escalation` | `empathy_protocol` then `live_agent_handoff` |
| `refund_threshold_exceeded` | `transfer_to_specialist` |

`malicious_input` is not a handover: polite closing + `end_session`.

## 8. Session variables

Scaffold variables plus: `language` (""), `dtmf_digits`, `local_noinput_counter`, `global_err_count`, `no_match_confirmation_count`, `misc_counter`, `mock_mode`, `mock_error`, `business_flag`, `identification_status`, `customer_type`, `lob`, `tv_sub_type`, `region`, `route`, `utterance`, `step_up_verified`, `service_status`, `card_last4`, `declined_card_last4`, `last_payment_method`, `last_pmt_amt`, `amount`, `ticket_state`, `vr_task_count`, `handoff_context`, `handoff_reason`, `handover_complete`, `handoff_message`, `applied_adjustments` (comma list), `pending_confirmation`, plus every `fx_*` fixture. Every key a tool reads or writes is declared in `cxas_app/app.json` (lint V100).
