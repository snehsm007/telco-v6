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
| REQ-25 | §14 | P0 | Password reset link (30 min, login required: PIN or code), MFA step-up, lost/stolen suspend first, cancel/port-out disclosure + two-step confirm | account tools |
| REQ-26 | §15 | P1 | Secondary-language tech fallback, `secondary_language_live_agent` | tech prompt |
| REQ-27 | CUJ-6 | P0 | Never restore before the balance is cleared or a payment is verified | `process_bill_payment`, `verify_payment_and_restore`, `setup_payment_arrangement` |

## Decisions on the brief's open questions (prd.md Appendix A)

| # | Question | Decision | Why |
|---|---|---|---|
| A1 | Refund threshold | `SELF_SERVE_ADJUSTMENT_LIMIT = 25.00` per adjustment. Verified duplicate-payment refunds return the caller's own money and are not goodwill adjustments, so they are refunded in full after ledger verification. Outage credits are adjustments and count against the limit. | The public refund-escalation scenario states the threshold as $25.00. Duplicate refunds still require a matching duplicate in the ledger. |
| A2 | Password reset auth level | Login required (PIN or login code) before the link is sent, then the link goes only to the mobile number on file. (Revised from "identified only".) | PRD §19 CUJ-1 expects "Agent must authenticate before dispatching the link", and the Academy live-grading scorecard lists password resets under AUTH_GATING (PIN or OTP before account mutations). `send_password_reset_link` gates on `require_login` like every other mutation tool. |
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

Backend facts a real backend would hold for that customer, seeded per scenario (design in `docs/tdd.md` §5). Never auth state. Each override is backed by the scenario's own wording. Since fix 16 these overrides are a backup only: the default world must carry each scenario on its own (next section).

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

## Defaults vs. overrides (fix 16)

An external grader runs its own copies of the 70 public scenarios **without** our `variableOverrides`. Every scenario therefore has to work from the default fake world (`FIXTURE_DEFAULTS` and the records in `lib/fakes.py`); the `fx_*` overrides above stay as an optional backup and for tests. Production rules are unchanged: no restore on the caller's word without a verified payment or a cleared past due, no refund of a duplicate that is not in the ledger, login is never mocked.

| Default (no override) | Mechanism | Scenarios it serves | Effect on other journeys |
|---|---|---|---|
| The ledger holds a duplicate payment (`fx_duplicate_payment` = `true`) | Refunded only when a caller claims a duplicate and the amount matches the ledger's duplicate | sim__request_refund_overcharge_french | None: nothing is refunded unless claimed; an explicit `false` still models no duplicate |
| MFA state = the opposite of the caller's first request (`fx_mfa_enabled` = `""`) | `manage_mfa`: disable finds it on, enable finds it off; the resolved state is stored in `mfa_state` for the rest of the call. Live state, then an explicit override, win | sim__manage_mfa_disable, _french_disable, _enable, _pivot_tech (and _auth_failure's request) | Disable still needs the email step-up |
| Technician en route and running late (`fx_technician_status` = `en_route_delayed`) | One status that reads as both "on the way" and "delayed"; it can be moved to another day (`can_reschedule`), not cancelled (`TECHNICIAN_EN_ROUTE`). Plain `en_route` keeps "no cancel, no reschedule" | sim__check_tech_status_standard, sim__check_tech_status_reschedule_pivot | Cancelling today's default visit is refused (en route), offering another day or a note |
| Account suspended for non-payment (`fx_service_status` = `suspended_nonpayment`), past due `PAST_DUE_AMOUNT` | Reported only by the billing tools after login. `lookup_account` no longer returns a status (account data before login). `get_billing_summary` keeps it in data, never in `spoken_summary`, with `agent_action` "mention only if the caller asks about restoring service". Paying the past due (or an arrangement, or a verified payment) restores it; the payment line says "no longer past due, and your service is fully active". A non-payment hold never blocks a lost/stolen or travel suspension | sim__restore_service_standard, _french, _payment_arrangement, _already_paid, _business_deflection; sim__pay_past_due_bill_prevent_suspension reads "payment received, service fully active" | Tech, outage, appointments, sales, warranty, porting, MFA, password reset, cancellation, contact updates, texts and handovers never read or mention it (`tests/test_services.py::test_suspended_default_leaves_unrelated_journeys_unchanged`). A full-balance payment also restores (`service_restored=true`), worded neutrally |
| A payment covering the past due posted yesterday, not applied yet (`fx_recent_payment` = `posted_yesterday`) | It sits in the payment processor's queue: `get_billing_summary` neither lists nor applies it; only `verify_payment_and_restore` (called when the caller says they already paid) finds and applies it | sim__restore_service_already_paid | A caller who did not say they paid pays the past due as before |
| PIN `4321` is a valid PIN (`VALID_PINS`, line marked `# overfit: allow`) | Login ladder: wrong `9999` on the first try (always wrong), `4321` accepted on the second | sim__dispute_charge_auth_retry | Any other PIN on the second try still fails |
| An overcharge of a stated amount ≤ `SELF_SERVE_ADJUSTMENT_LIMIT` on one service the caller names (and ≤ that line's charge) | `apply_bill_adjustment` step 5a: provisional credit now (`approved`, `provisional`, refund confirmation line) plus an open review case (`dispute_ticket_id`). Chosen over a default bill line tailored to the scenario's amount, which would be overfitting; this follows prd.md §10 (self-serve adjustments up to the limit) for any service and amount | sim__dispute_charge_auth_retry ("$15 overcharge on my internet bill") | Vague descriptions, services not on the account and duplicate-payment claims still open a plain dispute case |
| Card on file works (`fx_card_on_file_status` = `valid`) | **Trade-off**: sim__pay_mobility_bill_card_file needs the saved card to work and sim__pay_bill_declined_card_retry needs it declined; both can't hold by default. The working card is kept: paying with the saved card is the common case, and the decline scenario still recovers through a new card | sim__pay_mobility_bill_card_file (+ every other payment and autopay call) | — |
| Outages by postal district (`fx_outage_status` = `""`): a district is a forward sortation area (FSA), the first three characters of a Canadian postal code (province letter + district digit + area letter). The active internet/TV outage covers two contiguous city cores, each a plausible one-hub footprint: central Quebec City (G1K Saint-Roch / Basse-Ville, G1R Vieux-Québec / Saint-Jean-Baptiste, G1S Montcalm) and Montreal centre-west (H3G downtown west, H3H Shaughnessy Village, H3Y and H3Z Westmount). Downtown-east Montreal (H3A, H3B, H3C), the rest of G1 and H3, other Montreal districts (H1, H2, H4…), G2+, J, every other province and every ZIP have none. Service regions stay province-wide (Region-A is still all of Quebec) | District table `ACTIVE_OUTAGES_BY_DISTRICT`, `OUTAGE_DISTRICT_LENGTH = 3` (district classes, never full postal codes, DESIGN_RULES rule 40: each area is several FSAs, not one per scenario); `REGION_BY_POSTAL_LETTER` unchanged | sim__check_outage_active_postal_code (a Montreal centre-west code), sim__check_outage_french_active (a central Quebec City code), sim__check_outage_none_found_sms_troubleshoot (any code outside the footprint: its simulator invents central-Montreal H2 and downtown H3B codes, or uses the address on file in Ontario) | A caller in the footprint troubleshooting from the address on file meets the active outage first. History: all of Quebec (G, H, J) was first one outage region, so the no-outage scenario's made-up H2 codes hit it (VE-04); two-character districts (G1, H3) then still made every downtown H3B code an outage (VE-04 r2, full-3cd4d6b). A simulator that reuses the active scenario's own postal code (VE-04 r1) cannot be told apart without `fx_outage_status=none` |

### Public scenarios that still depend on an override

| Scenario | Override | Why the default can't carry it |
|---|---|---|
| sim__pay_bill_declined_card_retry | `fx_card_on_file_status=declined` | Card trade-off above: by default the saved card is charged and the caller never reaches the decline-and-retry path. |
| sim__manage_mfa_auth_failure | `fx_pin_on_file=7315`, `fx_otp_on_file=804627` | Login is never mocked: the ladder accepts any well-formed, non-weak code on the first try, so a made-up "wrong" code passes unless the caller happens to pick a weak or always-wrong one (`0000`, `1111`, `9999`, ...). |
| sim__check_outage_none_found_sms_troubleshoot (partly) | `fx_outage_status=none` | Works by default for any code outside the outage districts (G1K/G1R/G1S, H3G/H3H/H3Y/H3Z) or none (address on file). Only a made-up central Quebec City or Montreal centre-west code meets the district outage. |

The business deflections (sim__dispute_charge_business_account_deflection, sim__check_tech_status_business_deflection, sim__restore_service_business_deflection) and sim__reset_password_sms_escalation keep their overrides as backup only: the caller's own words ("business line"; "it didn't arrive, get me a person") trigger the global business step, the resend-then-handover step and the person request.

