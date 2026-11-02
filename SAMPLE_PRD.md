# Telco Voice Central — Agent Development Brief
Functional spec and capability inventory for the engineers who will build the agent.

## Executive Summary
Build a production voice agent that answers a consumer telco's main customer-service line and resolves the six most common contact reasons — billing questions, technical support, sales & equipment, appointment management, account management, and service changes — either self-contained or with a clean escalation to a live representative that carries full session context.

---

## Section 1 — Global Behavioral Requirements
* **Recording notice (BR-TV-001)**: The regional privacy disclosure is emitted verbatim on the initial greeting; if the caller asks whether they are being recorded, the disclosure is re-emitted verbatim.
* **Restricted caller check (BR-TV-002)**: Incoming caller ID is checked against a blocklist before greeting; blocked calls hear a deflection line and disconnect.
* **Regional service alert (BR-TV-003)**: Active regional service alerts prepend an advisory banner to the greeting.
* **Language locking (BR-TV-004)**: The caller's language is determined at the first turn from the area-code prefix plus first utterance and is locked for the remainder of the call. The lock is broken only by an explicit language switch request from the caller ("primary language" / "secondary language" trigger words).
* **Retry-strike escalation (BR-TV-006)**: Three consecutive no-input events or three unresolved no-match events on the same module trigger graceful escalation with reason `no_input_escalation` or `disambig_max_attempts`.
* **PII redaction (BR-TV-009)**: Account numbers, customer reference numbers, and card digits are read back only as the last 4 characters. PINs and OTP codes are never spoken back — the caller enters them; the system confirms success without echoing.
* **After-hours awareness (BR-TV-014)**: Live-agent queues are honored 24/7 for outage and fraud escalations. Sales, plan changes, and appointment booking route to next-business-day when the specialist queue is closed.
* **Malicious utterance handling (BR-TV-016)**: A per-turn classifier must run; on hit, the agent emits a polite closing line and ends the session with reason `malicious_input`.

---

## Section 2 — Capability Modules Overview
* **M1: Session Lifecycle & Routing**: Greet, capture identity, detect language, disambiguate intent, hand off to the right specialist capability, wrap and close. (Entry / exit for all CUJs)
* **M2: Authentication & Identity**: Verify caller via OTP or PIN; manage the auth ladder; escalate on failure. (Precondition for all authenticated CUJs)
* **M3: Billing & Payment**: Bill lookup, dispute cases, autopay, refunds, arrangements, deposits. (CUJ-2, part of CUJ-6, ~25% volume)
* **M4: Technical Support & Virtual Repair**: Outage lookup, sub-type disambiguation, virtual-repair session, SMS-delivered troubleshooting, ticket creation. (CUJ-3, largest volume slice ~30%)
* **M5: Sales & Equipment**: Plan catalog, service coverage, order placement, warranty claims, returns, SIM requests, number-transfer-in. (CUJ-5, ~15% volume)
* **M6: Appointment & Ticket Management**: Availability lookup, book / reschedule / cancel, technician-visit status. (CUJ-4, ~10% volume)
* **M7: Account Management**: Password reset, MFA management, fraud reporting, profile update, suspend / restore. (CUJ-1, part of CUJ-6, ~15% volume)
* **M8: Secondary Language Fallback**: Handle tech-support queries in the secondary language when the primary capability cannot cover them without language degradation. (CUJ-7)

---

## Section 3 & 4 — Call Lifecycle & Intent Coverage Table
### Pre-greeting Call Flow
1. Incoming Call
2. Restricted caller check (`BR-TV-002`) -> Blocked: Play deflection + disconnect. Clear: continue.
3. Regional service alert active? (`BR-TV-003`) -> Yes: Prepend advisory banner to greeting. No: continue.
4. Standard greeting + Verbatim Recording notice (`BR-TV-001`).
5. Language detect from CLID + first utterance (`BR-TV-004`).
6. Open-ended intent capture.

### Intent Coverage & Routing Table
| Representative caller utterance | Route to | Auth required |
|---|---|---|
| "my bill is wrong" / "dispute a charge" | M3 | Yes |
| "I want to pay my bill" | M3 | Yes |
| "set up autopay" | M3 | Yes |
| "refund" / "credit back" | M3 | Yes |
| "internet is down" / "no service" | M4 | Yes |
| "TV says no signal" | M4 | Yes |
| "SIM not working" / "phone locked" | M4 | Yes |
| "I want to add TV" / "new plan" / "upgrade" | M5 | Recommended |
| "my phone is defective" / "warranty" | M5 | Yes |
| "transfer my number in" | M5 | Yes |
| "book a technician" / "reschedule my appointment" | M6 | Yes |
| "where is my technician" / "ticket status" | M6 | Yes |
| "forgot my password" / "reset login" | M7 | Identified only (see M2) |
| "disable two-factor" / "enable MFA" | M7 | Yes + step-up |
| "someone used my account" / "fraud" | M7 | Empathy -> escalate (no auth attempt) |
| "restore my suspended service" | M7 | Yes (bounces to M3 via M1 if balance owed) |
| "cancel my service" / "port out my number" | M7 | Yes + verbatim disclosure |
| Caller speaks in secondary language, tech query out of primary coverage | M8 | Yes |
| "I want to talk to a person" | Escalate immediately, reason `user_requested_agent` | — |

Disambiguation: Single targeted question, max 3 disambiguation attempts on same turn before escalation. Mid-call topic switch: agent must re-classify and re-route (`BR-TV-019`).

---

## Section 5 — Session Data Model (~60 Variables)
### Identity
* `clid`: str (10-digit caller ID from telephony)
* `tfn`: str (Toll-free number dialed, per-brand routing)
* `cirn`: str (Customer reference number, PII - echoed last-4 only)
* `billing_account`: str (Billing account number, PII - echoed last-4 only)
* `customer_type`: `New | Existing`
* `user_id`: str (Internal CRM record id)

### Auth State
* `auth_status`: `Pass | Fail` (NEVER mock/override in evals)
* `identification_status`: `Pass | Fail` (NEVER mock/override in evals)
* `business_flag`: `bool-str` (Triggers business-account handoff)

### Routing
* `route`: `enum-str` (Disambiguation output; drives capability module)
* `lob`: `mobility | internet | tv | homephone | smarthome`
* `tv_sub_type`: `streaming | satellite | streaming_only | null`
* `region`: `Region-A | Region-B | Region-C`

### Conversation State
* `language`: `primary | secondary` (Locked at turn 1)
* `utterance`: str (Latest caller intent text)
* `dtmf_digits`: str (DTMF captured during current turn)

### Counters & Flags
* `local_noinput_counter`: int (Per-module no-input retry count; resets on new module; escalates at 3)
* `global_err_count`: int (Cross-module error count; escalates at 3)
* `no_match_confirmation_count`: int (No-match retry budget; escalates at 3)
* `misc_counter`: int (Generic per-flow counter)
* `mock_mode`: str (`"True"` in eval session parameters to return synthetic success)

### Payment / Order
* `last_pmt_amt`: float-str (Last payment amount)
* `amount`: float-str (Currently-discussed amount)
* `ban_type`: str (Billing account type)
* `is_prepaid`: bool-str (Drives prepaid-only paths)
* `loyalty_limit`: int (Loyalty-program adjustment ceiling)

### Virtual-Repair & Ticketing
* `vr_task_count`: int (Virtual-repair iteration counter)
* `ticket_state`: `open | in-progress | closed`
* `item_list`: str (Captured equipment list)
* `intent_type`: str (Sub-intent classification, e.g. Physical Damage vs Defective)
* `api_resp`: str (Last API response payload debug)

### SMS & Misc
* `sms_type`: `Public | Private`
* `sms_content`: str (SMS body text)
* `day_val`, `date_val`, `month_val`, `end_time`, `flag_val`: str (Free-form per-flow temporaries)

---

## Section 6 — Per-Turn Preprocessing Requirements
Execution order every turn:
1. **DTMF capture**: Normalize into `dtmf_digits`.
2. **No-input accounting**: Increment `local_noinput_counter`. On 3rd consecutive miss on same module, emit polite handoff line and end session with reason `no_input_escalation`. On misses 1-2, ask caller to repeat.
3. **Tool-error classification**:
   - `System` (`SYSTEM_DOWN`, `INTERNAL_ERROR`, `AUTH_SERVICE_UNAVAILABLE`): end session with reason `system_unavailable` (or live agent transfer per GEMINI.md).
   - `Business` (`INSUFFICIENT_FUNDS`, `NOT_ELIGIBLE`, `ALREADY_APPLIED`, ...): surface to model to apologize and offer alternative.
   - `Validation` (`INVALID_INPUT`, `MALFORMED_REQUEST`): ask caller to repeat/clarify; increment `global_err_count`.
4. **Module-specific pre-checks**: E.g., check active outage advisory before response.
Post-turn: Massage tool response payloads into flat session variables. Follow-up variables set immediately.

---

## Section 7 — Verbatim Copy Library
* `greeting_main`: `"Welcome to Telco. I can help with billing, technical support, or managing your account. To get started, could you tell me the phone number or account number associated with your service?"`
* `recording_notice`: `"This call may be recorded for quality and training purposes."`
* `id_verification_otp`: `"For your security, I just sent a 6-digit code to that number — please read it back to me."`
* `id_verification_pin`: `"For your security, I'll need to verify your identity. Please enter the 4-digit PIN you set up."`
* `live_agent_handoff`: `"I'll connect you to a representative who can help. Please hold."`
* `business_handoff`: `"To get you the best support for your business account, I'll transfer you to an agent. You'll need to use your phone keypad instead of talking to the virtual assistant. Just a moment while I connect you."`
* `payment_method_preamble`: PCI compliance text.
* `contract_cancellation_fee_disclosure`: Contract cancellation terms.
* `refund_confirmation_pattern`: `"Your refund of ${amount} will appear on your next statement within {days} business days."`
* `empathy_protocol`: `"I'm very sorry to hear that you are facing challenges. I will ensure we handle your request with the utmost care."`
* `outage_active`: `"I see there's an active outage in your area. We're working on it. Would you like me to text you when it's restored?"`
* `transfer_to_specialist`: `"I'll connect you to a billing specialist now — they'll have everything we've already discussed."`

---

## Section 8–15 — Module Specifications
* **M1: Session Lifecycle & Routing**:
  - Emits greeting + recording notice verbatim.
  - Locks language. Resolves caller identity.
  - Dispatches to M2 for auth if mutation required.
  - Accepts re-entries on topic switch (`BR-TV-019`).
  - "Talk to person" -> verbatim `live_agent_handoff`, reason `user_requested_agent`.
* **M2: Authentication & Identity**:
  - Ladder: Guest -> Identified -> Authenticated.
  - OTP: Confirm last-4 callback number, send OTP, verbatim `id_verification_otp`, accept voice/DTMF, validate tool. 3 strikes -> `auth_failure_handoff`.
  - PIN: Verbatim `id_verification_pin`, DTMF only (voice PINs refused). 3 strikes -> `auth_failure_handoff`.
  - Fraud claims: Empathy line (`empathy_protocol`), immediate escalation `fraud_escalation` (NO auth attempt).
  - Credentials never echoed. Never fabricate `auth_status = Pass`.
* **M3: Billing & Payment**:
  - Look up recent bills. Identify charges.
  - Small-dollar auto-eligible adjustments (<= $25.00) confirmed with `refund_confirmation_pattern`.
  - Exceeding threshold -> escalate `refund_threshold_exceeded`.
  - Autopay setup requires verbatim `payment_method_preamble`.
* **M4: Technical Support & Virtual Repair**:
  - Always check `check_regional_outage` first. If outage active -> verbatim `outage_active`, offer SMS callback, end session.
  - Disambiguate `tv_sub_type` (streaming / satellite / streaming_only).
  - Virtual repair session. Troubleshooting chains > 2 steps must offer SMS delivery.
  - Unresolved: offer technician visit (route through M1 to M6) or ticket.
* **M5: Sales & Equipment**:
  - Coverage check. Shortlist 2-3 plans max (never full catalog).
  - Place order -> return order number and delivery ETA -> SMS receipt.
  - Business callers (`business_flag == true`): verbatim `business_handoff`, reason `business_handoff`, no self-serve.
* **M6: Appointment & Ticket Management**:
  - Look up active appointments. Offer 2-3 availability slots.
  - Reschedule / cancel commit -> SMS confirmation.
  - Same-day cancel: confirm twice. Technician en-route: cannot cancel, leave note. No slots: offer SMS callback.
* **M7: Account Management**:
  - Password reset SMS link: enforce 30-minute validity, do not reset password directly, do not echo link.
  - MFA enable/disable: requires step-up auth.
  - Fraud: verbatim `empathy_protocol`, escalate `fraud_escalation`.
  - Suspend/restore: If non-payment -> route through M1 to M3 to pay balance -> return to M7. Lost/stolen -> suspend immediately.
* **M8: Secondary Language Fallback**:
  - Route here if `language == secondary` AND `route == tech` AND M4 primary lacks coverage.
  - Unsupported issue: verbatim `live_agent_handoff` (secondary language), reason `secondary_language_live_agent`.
  - Zero language degradation mid-call (no half-primary / half-secondary transcripts).

---

## Section 16 & 17 — Error Recovery & Tool Catalog
### Error Thresholds
* `local_noinput_counter >= 3` -> escalate with reason `no_input_escalation`.
* `no_match_confirmation_count >= 3` -> escalate with reason `disambig_max_attempts`.
* `global_err_count >= 3` -> end session with reason `too_many_errors`.

### Core Tool Inventory (15 Approved Endpoints)
1. `fetch_customer_profile`: `{ clid: str }` -> `{ identification_status, customer_type, business_flag, is_prepaid, ... }`
2. `send_authentication_otp`: `{ clid: str }` -> `{ sent: bool, expires_in_sec: int }`
3. `validate_authentication_otp`: `{ code: str }` -> `{ auth_status: "Pass"|"Fail", attempts_remaining: int }`
4. `validate_authentication_pin`: `{ pin: str }` -> `{ auth_status: "Pass"|"Fail", attempts_remaining: int }`
5. `evaluate_routing_rules`: `{ utterance: str, entities: object }` -> `{ route: str, confidence: float, requires_auth: bool }`
6. `fetch_recent_bills`: `{ billing_account: str }` -> `{ bills: [{ id, date, amount, line_items }] }`
7. `create_dispute_ticket`: `{ charge_id, reason, notes }` -> `{ ticket_id: str, eta_business_days: int }`
8. `check_regional_outage`: `{ region: str, lob: str }` -> `{ active: bool, restoration_eta_iso: str|null }`
9. `start_virtual_repair`: `{ cirn, lob, symptom }` -> `{ session_id, first_diagnostic_question }`
10. `fetch_availability_slots`: `{ zip, service_type }` -> `{ slots: [{ date, window, technician_id }] }`
11. `commit_appointment_reschedule`: `{ appt_id, new_slot }` -> `{ confirmed: bool, new_date: str }`
12. `fetch_plan_catalog`: `{ lob, customer_type }` -> `{ plans: [{ id, name, price, key_features }] }`
13. `send_password_reset_sms`: `{ cirn }` -> `{ sent: bool, valid_minutes: int }`
14. `execute_suspend_restore`: `{ cirn, action: "suspend"|"restore", reason }` -> `{ new_state: str, effective_iso: str }`
15. `execute_live_agent_handover`: `{ reason: str, session_context: object }` -> `{ handover_id: str, queue: str }`

All tools must implement `mock_mode` branch (`mock_mode == "True"`), standardized error envelopes (`{ "error": "<CODE>", "message": "<human>" }`), idempotency, and PII handling.

---

## Section 18 — Requirements Register (BR-TV-001 ... BR-TV-020)
* BR-TV-001: Recording notice (verbatim, locked language)
* BR-TV-002: Restricted caller check (blocklist -> deflection + disconnect)
* BR-TV-003: Regional service alert (prepends banner)
* BR-TV-004: Language locking (turn 1 sticky lock)
* BR-TV-005: Module coverage (all intents route to correct module)
* BR-TV-006: Retry strikes (3 no-input or 3 no-match -> escalation)
* BR-TV-007: DTMF capture (normalized into `dtmf_digits`)
* BR-TV-008: Auth ladder (Guest -> Identified -> Authenticated)
* BR-TV-009: PII redaction (last-4 only; PIN/OTP never echoed)
* BR-TV-010: Tool-error tri-state (system escalates, business surfaces, validation retries)
* BR-TV-011: Verbatim compliance (assert exact equality on Section 7 strings)
* BR-TV-012: Business handoff (business_flag == true -> verbatim business_handoff)
* BR-TV-013: Fraud escalation (empathy line + immediate escalation, no auth)
* BR-TV-014: After-hours awareness (outage/fraud 24/7; sales/plan/appts route next-business-day)
* BR-TV-015: Session-context handoff (carry session variables on escalation)
* BR-TV-016: Malicious utterance (classifier -> end session `malicious_input`)
* BR-TV-017: No invented data (condition account generation on tool response)
* BR-TV-018: Audio recording (.wav recorded in session-audio bucket)
* BR-TV-019: Topic switch mid-call (re-classify and re-route)
* BR-TV-020: Language non-degradation (never mix languages)

---

## Section 19 — Core User Journeys (CUJ 1–7)
1. **CUJ-1 (M7, 15%)**: `cuj_1_account_password_reset`: Max 8 turns. Identify caller, dispatch SMS reset link, state 30-min window, do not reset password directly, do not echo link.
2. **CUJ-2 (M3, 25%)**: `cuj_2_billing_dispute_auto_eligible`: Max 10 turns. Look up bill, identify charge, apply auto-adjustment, state refund and business days per `refund_confirmation_pattern`, do not open dispute case.
3. **CUJ-3 (M4, 30%)**: `cuj_3_tech_support_tv_signal`: Max 12 turns. Check regional outage first, disambiguate `tv_sub_type`, start VR session, offer SMS steps for > 2 sequential steps.
4. **CUJ-4 (M6, 10%)**: `cuj_4_appointment_reschedule`: Max 8 turns. Find appointment, offer 2-3 slots, commit reschedule, state new date/time, send SMS confirmation.
5. **CUJ-5 (M5, 15%)**: `cuj_5_sales_add_tv_existing`: Max 10 turns. Check coverage, present 2-3 plans, place order, state order number, send SMS receipt.
6. **CUJ-6 (M7+M3, 5%)**: `cuj_6_restore_service_from_non_payment`: Max 14 turns. Detect non-payment, route through M1 to M3 to clear balance, return to M7 to restore, send SMS confirmation.
7. **CUJ-7 (M8, subset of CUJ-3)**: `cuj_7_secondary_language_tech_fallback`: Max 10 turns. M1 routes to M8, entire conversation in secondary language, if unresolved escalate `secondary_language_live_agent`.

---

## Section 20 — Priority Hierarchy (Turn-level conflict resolution)
1. Safety signals (self-harm, threat, malicious input -> empathy line + escalation/end)
2. Fraud claim (`fraud_escalation`, no auth, no self-serve)
3. System-error escalation (`SYSTEM_DOWN` -> immediate handoff)
4. Explicit "talk to a person" (`user_requested_agent`)
5. Business-account handoff (`business_flag == true` -> `business_handoff`)
6. Retry-strike escalation (3x no-input or 3x no-match)
7. Compliance-locked verbatim turns (Section 7)
8. Authenticated account actions
9. Disambiguation (max 3 attempts)
10. Small talk / recap / closing

---

## Section 21 — Definition of Done
* In-agent resolution: >= 60%
* Average handle time: <= 4 min
* Verbatim compliance: 100% on audited strings
* PII disclosures: Zero
* Audio-recording coverage: 100% (.wav in session-audio bucket)
* Regressions: No regressions on P0 golden set for two consecutive deploys.
