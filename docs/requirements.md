# Requirements: telco-v6 (Telco Voice Central)

Every `BR-TV-*` in `prd.md` §18 is a requirement here, plus the module rules from §8–§15. P0 = launch-blocking.

## Requirements register

| REQ | Source | Priority | Requirement | Where enforced |
|---|---|---|---|---|
| REQ-1 | BR-TV-001 | P0 | Recording notice verbatim on the greeting, re-said verbatim when asked | router prompt, global instruction |
| REQ-2 | BR-TV-002 | P0 | Blocked caller numbers hear a deflection line and the call ends | `lookup_account` (`BLOCKED_CALLER_NUMBERS`), router prompt |
| REQ-3 | BR-TV-003 | P1 | Active regional alert is mentioned with the greeting once the region is known | `check_regional_outage`, tech prompt |
| REQ-4 | BR-TV-004, BR-TV-020 | P0 | Language detected on turn 1 and locked; switches only on explicit request; no mixed-language calls | `core.session_language` (asymmetric lock), language sheet callback, global instruction |
| REQ-5 | BR-TV-005, BR-TV-019 | P0 | Every §4 intent reaches the right module; mid-call topic switches re-route | router taxonomy, specialist "Different Goal" steps |
| REQ-6 | BR-TV-006 | P0 | 3 silent turns or 3 unresolved clarifications on one module → handover (`no_input_escalation` / `disambig_max_attempts`) | global instruction |
| REQ-7 | BR-TV-007 | P1 | Keypad digits normalized; tools read `dtmf_digits` | `fakes.normalize_code`, auth/payment tools |
| REQ-8 | BR-TV-008 | P0 | Guest → Identified → Authenticated; account reads/changes need login | `core.require_login` in every account tool |
| REQ-9 | BR-TV-009 | P0 | Last 4 only for account/card/phone numbers; PINs/codes never echoed | tools return last-4 only, `speech_hygiene` |
| REQ-10 | BR-TV-010, §16 | P0 | Tool-error tri-state; 3 validation errors → `too_many_errors` | `core.validation_error`, `check_mock_error`, global instruction |
| REQ-11 | BR-TV-011, §7 | P0 | Verbatim copy library in both languages | prompts + `SPOKEN_LINES` |
| REQ-12 | BR-TV-012, §12 | P0 | Business accounts: verbatim business handoff, no self-serve | `handover_to_person(reason=business_handoff)`, every agent |
| REQ-13 | BR-TV-013, §14 | P0 | Fraud: empathy line + immediate escalation, no login attempt | `handover_to_person(reason=fraud_escalation)`, every agent |
| REQ-14 | BR-TV-014 | P2 | After-hours: sales/plan/appointment queues route to next business day | `handover_to_person` queue hours |
| REQ-15 | BR-TV-015 | P0 | Every escalation carries session context | `handover_to_person` writes `handoff_context` |
| REQ-16 | BR-TV-016 | P0 | Malicious input → polite closing, end session (`malicious_input`) | guardrails + global instruction |
| REQ-17 | BR-TV-017, §16 | P0 | No invented data; account facts only from successful tool replies | global instruction, tools |
| REQ-18 | BR-TV-018 | P1 | Audio recording of every call | `app.json` logging settings (eval audio bucket) |
| REQ-19 | §9 | P0 | OTP and PIN flows, 3 strikes → `auth_failure_handoff` | auth tools |
| REQ-20 | §10 | P0 | Self-serve adjustments up to the limit, escalate above (`refund_threshold_exceeded`, `transfer_to_specialist`); refund confirmation pattern | `apply_bill_adjustment` |
| REQ-21 | §10 | P0 | Payment-method preamble before any payment-method step | billing prompt |
| REQ-22 | §11 | P0 | Outage check before diagnostics; TV sub-type before TV steps; SMS for >2 steps | tech tools + prompt |
| REQ-23 | §12 | P0 | ≤3 plan options; order number + ETA + SMS receipt | `browse_plans`, `place_order` |
| REQ-24 | §13 | P0 | Appointment rules: 2–3 slots, same-day cancel confirmed twice, en-route cannot cancel, SMS confirmation | `manage_appointment` |
| REQ-25 | §14 | P0 | Password reset link (30 min, identified only), MFA step-up, lost/stolen suspend first, cancel/port-out disclosure + two-step confirm | account tools |
| REQ-26 | §15 | P1 | Secondary-language tech fallback, `secondary_language_live_agent` | tech prompt |
| REQ-27 | CUJ-6 | P0 | Never restore before the balance is cleared or a payment is verified | `process_bill_payment`, `verify_payment_and_restore`, `setup_payment_arrangement` |

## Decisions on the brief's open questions (prd.md Appendix A)

| # | Question | Decision | Why |
|---|---|---|---|
| A1 | Refund threshold | `SELF_SERVE_ADJUSTMENT_LIMIT = 25.00` per adjustment. Verified duplicate-payment refunds return the caller's own money and are not goodwill adjustments, so they are refunded in full after ledger verification. Outage credits are adjustments and count against the limit. | The public refund-escalation scenario states the threshold as $25.00. Duplicate refunds still require a matching duplicate in the ledger. |
| A2 | Password reset auth level | Identified only, link sent to the mobile number on file. | PRD §4 routing table; the public password scenarios identify by phone number only. Sending only to the number on file keeps it safe. |
| A3 | Auth before outage check | Outage status by postal code is public and needs no login. Diagnostics, tickets and account data need login. Port-in checklist (what to bring) needs no login; starting a transfer does. | Area outage status contains no account data. |
| A4 | Languages | Primary `en-US`, secondary `fr-CA`. | All 70 public scenarios are English or Canadian French. |
| A5 | M8 trigger | French tech calls are served by `tech_support` in French when the symptom is in the repair catalogue; anything else → `live_agent_handoff` in French with `secondary_language_live_agent`. | No symptom list in the brief. |
| A6 | Legal texts | Interim wording written for `payment_method_preamble` and `contract_cancellation_fee_disclosure`, and French translations of every §7 line, all marked **pending Legal approval** in `lib/fakes.py`. | Placeholders in the brief. |
| A7 | Refund window `{days}` | Returned by the tool: 2 business days for card refunds and bill credits (matches the brief's sample transcript). | Brief sample. |
| A8 | Business hours | Specialist queues Mon–Fri 08:00–20:00, Sat 09:00–17:00 ET; outage and fraud queues 24/7. | Not defined in the brief. |
| A9 | Payment rules | Restore after non-payment needs the past-due amount covered by a payment, a verified posted payment, or an accepted payment arrangement. Arrangement = 2 instalments, max one per 12 months. Partial payments reduce the balance but never restore. | Not defined in the brief. |
| A10 | Blocked-caller line | Deflection wording in `SPOKEN_LINES["restricted_caller"]`; call ends with reason `blocked_caller`. | Not defined in the brief. |
| A11 | Tool catalogue | 22 tools named after the brief's representative contracts and categories (see `docs/tdd.md`). | Only 15 representative contracts given. |
| A12 | Truncated CUJ text | CUJs implemented from the legible parts. | PDF truncation. |
| A13 | Test suite | The 70 public scenarios in `bench/dev/` are the measured suite. | Brief supplies no eval data. |

## Eval fixtures (scenario `variableOverrides`)

Backend facts a real backend would hold for that customer, seeded per scenario (design in `docs/tdd.md` §5). Never auth state. Each override is backed by the scenario's own wording.

| Scenario | Overrides | Reason (from the scenario text) |
|---|---|---|
| sim__dispute_charge_auth_retry | `fx_pin_on_file=4321`, `fx_extra_bill_line=Internet service overcharge|15.00|internet` | Scenario states the caller's correct PIN and a $15 internet overcharge on the bill. |
| sim__manage_mfa_auth_failure | `fx_pin_on_file=7315`, `fx_otp_on_file=804627`, `fx_mfa_enabled=true` | Caller deliberately gives wrong codes; the account needs real credentials so made-up codes fail. |
| sim__pay_bill_declined_card_retry | `fx_card_on_file_status=declined` | Scenario states the card on file is declined. |
| sim__request_refund_overcharge_french | `fx_duplicate_payment=true` | Caller paid the bill twice. |
| sim__restore_service_standard, sim__restore_service_french, sim__restore_service_payment_arrangement | `fx_service_status=suspended_nonpayment` | Service suspended for non-payment. |
| sim__restore_service_already_paid | `fx_service_status=suspended_nonpayment`, `fx_recent_payment=posted_yesterday` | Caller paid yesterday; service still suspended. |
| sim__restore_service_business_deflection | `fx_service_status=suspended_nonpayment`, `fx_business_account=true` | Suspended business line. |
| sim__dispute_charge_business_account_deflection, sim__check_tech_status_business_deflection | `fx_business_account=true` | Business account. |
| sim__check_outage_active_postal_code, sim__check_outage_french_active | `fx_outage_status=active` | Active outage in the caller's area. |
| sim__check_outage_none_found_sms_troubleshoot | `fx_outage_status=none` | No outage in the caller's area. |
| sim__check_tech_status_standard | `fx_technician_status=en_route` | Technician en route. |
| sim__check_tech_status_reschedule_pivot | `fx_technician_status=delayed` | Technician delayed. |
| sim__manage_mfa_disable, sim__manage_mfa_french_disable | `fx_mfa_enabled=true` | Caller has MFA on and wants it off. |
| sim__reset_password_sms_escalation | `fx_sms_delivery=failed` | Reset text never arrives. |
