# 05 Evals: which kind, how to write them, when they count

An **evaluation** (**eval**) runs the real agent on the **Google Customer Experience Agent Studio** (**CXAS** / **CES**) cloud platform and grades what it actually did. Local unit tests of callbacks and tools are essential crash-and-contract guards, but they are **not** evals.

---

## Pick the Eval Type
| Type | What it is | Use it for | Graded by |
|---|---|---|---|
| **Tool test** | Calls one tool with fixed input, checks the output | Every tool: happy path, each error code, each allowed argument value, plus breakage verification (`scripts/verify_mutations.py`) | Exact match (100% required) |
| **Callback test** | `pytest` on `speech_hygiene` (after-model callback backed by `lib/speech.py`) | Markdown and emoji stripping, code-leak cleanup, voice length bounds, PII masking | Code (100% required) |
| **Golden** | A scripted conversation: exact user lines, expected agent replies, tool calls, and `agent_transfer` hops | Deterministic flows: greeting, single-turn routing, refusal, escalation start | Platform similarity + tool-call & transfer match |
| **Simulation (sim)** | An AI plays the caller toward a goal; an independent Large Language Model (**LLM**) judge grades the chat | Multi-turn Critical User Journeys (**CUJs**), rephrasing, fact-less callers, multi-intent, voice | 3 Platform Judge Metrics **and** `suite/grader.py` |
| **Probe** | Exact user lines, run N times, graded by code | Known-bug regressions, routing table rows, prompt-injection safety, latency, reply length | `suite/grader.py` + deterministic assertions |
| **Contract test** | `pytest` comparing `instruction.txt` ↔ tool code ↔ `lib/fakes.py` ↔ `docs/tdd.md`, plus every field, allowed value (enum) and timeline the PRD requires | Ensures tool names, parameter names, required fields and allowed enum values stay identical everywhere | Code (100% required) |

Every eval carries `REQ-n` and priority (`P0`, `P1`, `P2`) tags so results are reported per requirement.

---

## Avoiding the "Fake Green" Local Eval Illusion
Two failure patterns wasted days on past projects:
1. **Never build a local keyword or YAML-format "eval runner":** Checking that a YAML file has valid fields or that a local mock returns a string without invoking the cloud LLM is not an evaluation. Never truncate a multi-turn golden to a 1-turn greeting check so it passes faster.
2. **Watch out for the "Self-Authored Assumption Bias":** When the same engineer writes both the agent instructions and the evaluation personas, both tend to assume the caller always provides a known phone number (`202-555-0143`), a known 6-digit One-Time Passcode (**OTP**), or a known 4-digit Personal Identification Number (**PIN**). A self-authored suite can pass 98% while official public evaluations score 74% because **roughly 30% of the public simulated callers we have seen (16 of 50 in one build) are given no phone number, PIN, OTP, or credit card digits**.
   - **Rule:** Include **fact-less caller simulations** in your own `evals/simulations/` where `response_guide` gives the simulated user only a goal (e.g., *"Dispute a roaming charge"* or *"Set up autopay"*) and zero account/phone/card numbers, verifying that your agent and lenient fake world (`lib/fakes.py`) complete the journey smoothly without dead-ending.

---

## Goldens: Rules That Fail Silently If You Break Them
- Every turn has both a `user` and an `agent` line. Open with `<event>welcome</event>` if the agent greets first.
- `$matchType` (e.g. `semantic`, `contains`) works only inside `tool_calls.args`.
- **Preserve `agent_transfer` in custom evaluation runners (`M1-S3`):** When converting golden YAML specifications to CES API objects (`spec_to_ces_evaluation` in `scripts/run_evals.py`), you **must** populate `types.Evaluation.GoldenExpectation(agent_transfer=types.AgentTransfer(target_agent=...))` (including any intermediate `router` hop when switching between two specialists). If `agent_transfer` is omitted from the API payload, CES marks every observed specialist transfer in the golden run as `FAIL`!
- In YAML, a handoff is `action: transfer_to_agent` with the target in `args.agent`. Any other key silently becomes a call to a non-existent tool.
- Unknown YAML keys (e.g. `requirement:`) are silently dropped by the platform. Put metadata in `tags` and YAML comments; put pass rules in `expectations`.
- If a multi-turn golden fails >40% of runs simply because the model phrases a valid answer two different ways, convert it into a simulation; reserve goldens for deterministic openings, routing, and tool-call contracts.

---

## Simulations
- Each step has `goal`, `success_criteria`, `response_guide`, `max_turns`, and `tags` (required).
- **Include `evaluation_metrics_threshold_override` in `update_mask` (`M1-S3`):** When updating existing simulation evaluations via the CES API, always include `evaluation_metrics_threshold_override` in `update_mask` and call `update_evaluation_expectation` when rubric prompts change, or the cloud app will continue grading against stale expectations.
- `expectations` must describe **observable** behavior: *"Agent states the monthly price before taxes and confirms the $0.00 setup fee"*, not *"Evaluate whether the agent was helpful"*.
- Never name raw Python function identifiers in `expectations`; the judge sees platform display names and spoken dialogue.
- Never put example quotes or `"e.g."` lines in `response_guide`: the user simulator will copy them verbatim on every run, hiding real phrasing diversity.
- When testing Dual-Tone Multi-Frequency (**DTMF**) keypad entry in text simulations, test both contiguous digits (`"482913"`) and space-separated digits (`"4 8 2 9 1 3"`), as CES user simulators frequently emit space-separated keypad tokens.
- When testing escalation journeys (`user_requested_agent`, `human_handover`), remember that both halves of handover completion are required (`docs/DESIGN_RULES.md` rules 4, 5, 7, 20): `handover_to_person` must return `spoken_message`, `handoff_message`, `handoff_status="completed_via_specialist_queue"`, `action_fulfilled=True`, `task_completed=True`, `user_goal_fulfilled=True` (carrying the reference number, caller goal, and auth progress), **and** in the same single turn the agent must speak the transfer sentence, call `handover_to_person`, and call `end_session` (with `speech_hygiene` injecting `state["handoff_message"]` on tool-only turns).

---

## Tool Tests & Offline Breakage Verification
- Top-level key in `evals/tool_tests/tool_tests.yaml` is `tests:` (not `test_cases:`). Each item names the `tool` (display name), `args`, and `expectations.response` JSONPath expressions starting with `$.result.` (for example `$.result.status`, `$.result.error`, `$.result.data.amount_display`).
- **Contract-test every field, allowed value (enum) and timeline the PRD requires.** Earlier builds lost evaluations to a missing required field, a timeline that contradicted the PRD, and an enum value spelled differently from the PRD (`"bank"` where the contract said `"bank_account"`). Money fields carry a number, a 2-decimal display string and a currency (`amount: 85.5`, `amount_display: "85.50"`, `currency: "CAD"`); test all three.
- **Gate 0 Tool-Breakage, Mutation & Contract Verification (`scripts/verify_mutations.py` + `make eval-contract`):**
  Tool tests must not merely run the happy path—they must catch bugs. `make ci` runs `python3 scripts/verify_mutations.py`, which verifies that `pytest` fails on 100% of injected breakages, and the eval contract (`make eval-contract`, which runs `scripts/eval_contract.py` on `bench/dev/evaluations` against `lib/fakes.py`), which checks that the fake world accepts every first-try caller credential and resolves every caller phone or account ID in the visible evaluations.

---

## Time-Dependent Facts
Dates, prices, appointment slots, and schedules must come from a single **oracle** in `lib/fakes.py` that both the tool implementations and the evaluation expectations read. Never hard-code calendar dates in an eval without reading or aligning with the oracle.

---

## Pass Bars, the `N * p^3` Strict Ceiling & The Unstable Set (`evals/unstable_set.txt`)
| Layer | Pass Bar |
|---|---|
| Tool tests, callback tests, contract & fakes-invariants tests, mutation checks (`make ci`) | **100%** |
| Goldens | **>90%** over 5 runs |
| Simulations — **Gate 3 (`make bench-full`, then `make gate3`)** | **`Strict 3/3 >= 90%` (`45/50`, requiring individual `p >= 96.55%`) first, AND `100%` Majority (`>=2/3`, zero `0/3` or `1/3` evals)**, `0` tool runtime errors, one single-commit full run |
| Gate 1 Impact Smoke (`make smoke-impact ENV=staging`, after `make push`) | **`3/3` strict pass** on all impacted evaluations (`scripts/impact.py`) with `0` tool errors |

### Always Report `Strict 3/3 | Majority >=2/3 | Individual` Side-by-Side
Single-repeat runs (`RUNS=1`) cannot distinguish a 100% solid scenario from a coin-flip scenario, and majority vote (`>=2/3`) alone masks `2/3` instability: if each trial passes with probability `p = 92.0%` (`138/150`), expected majority is `49.1/50` (`98.2%`) while expected strict `3/3` (`50 * p^3`) is only `38.9/50` (`77.9%`). Reaching `45/50` (`90%`) strict `3/3` requires `p >= 96.55%` (`145/150`). Measured in `telco-rebuild`: clean builds sat at about 90–93% per conversation, which gives about 38–41/50 strict. A test that fails 1 time in 5 passes strict `3/3` only about 51% of the time (`0.8^3`), so any failed repeat is signal, not noise. Always evaluate with `RUNS=3` (smoke/full) or `RUNS=5` (unstable set), always report `strict 3/3 | majority >=2/3 | individual` side-by-side, strict first (never composite slices across runs/SHAs), and classify each evaluation in `evals/unstable_set.txt`:
- **Solid (`3/3` or `5/5`):** Passes every repeat across all 3 judge metrics.
- **Noisy-pass (`2/3` or `4/5`):** Passes majority, but failed 1 repeat due to a specific ungrounded phrase, missing two-step disclosure, or simulator quirk. Diagnose and fix the root cause so the suite reaches `>=90%` strict `3/3` (`45/50`) and `100%` majority at Gate 3.
- **Unstable (`1/3`, `1/5`–`3/5`):** Fails Gate 3's `100%` majority requirement; included in `evals/unstable_set.txt` and targeted via `make impact`, `make push` + `make smoke-impact`, and `make bench-unstable` (Gate 2).
- **Blocked (`0/3` or `0/5`):** Deterministic bug; top priority for Gate 1 (`make push`, then `make smoke-impact ENV=staging`).

---

## Tool-Reply Facts Checklist (Requirement-to-Payload Mapping)

Before authoring instructions or evaluations, walk the numbered PRD requirement register (`REQ-1`, `REQ-2`, ...) and construct a **Tool-Reply Facts Checklist**. For every requirement, record:
1. **Owning Tool:** Which atomic tool produces the domain data or executes the action.
2. **Fact Keys:** Exact dictionary keys in `data` (e.g., `balance_due`, `due_date`, `plan_name`, `confirmation_code`).
3. **Localized Spoken Summary:** Ensure the tool returns exactly one localized `spoken_summary` (or `spoken_message`) resolved via `_session_language(state, language)` (Rule 5 & Rule 41).
4. **No Sibling Language Keys:** Never output `_en`, `_fr`, or `_es` sibling keys (enforced by Gate 0 rule `LOCALIZED_SIBLING_KEY` and `tests/test_localization_completeness.py`).
5. **Concise Agent Action:** Verify `agent_action` instructions are short and imperative (≤ 120 characters; Gate 0 rule `AGENT_ACTION_TOO_LONG`).

Every spoken claim made by an agent must be grounded in an explicit tool return field on that turn to guarantee a 1.0 score on the Hallucination Judge.

---

## Production-Pattern & Guardrail Readiness (PRD `BR-*` Rules)

All 70 business scenarios (`VE-01..VE-70`) ship in `bench/dev/`, and the starter kit ships no holdout folder (`bench-holdout/` or `bench-prod-holdout/`). In a bootcamp or evaluation setting, external graders run their own unseen production-pattern & guardrail evaluations testing defensive edge cases, fault injection, and platform safety guardrails. Implement these hooks upfront in `lib/fakes.py` and `lib/services.py` and verify them with unit tests and `evals/simulations/`:

### 1. What Production-Pattern & Guardrail Evaluations Cover
- **Boundary Deflections & Security Blocks:** Restricted callers, high-risk fraudulent accounts, and blocked ANI numbers.
- **Payment & Business Exceptions:** Card decline handling, expired payment profiles, and transaction limits.
- **Fault Injection & Graceful Recovery:** Downstream service outages and system error handling.
- **Regulatory Disclosures & Safety Guardrails:** AI disclosure mandates, call recording notices, out-of-scope attacks, and prompt injection defense.

### 2. Required Fixture & State Hooks
Tool and service scaffolding must implement standard hooks in `lib/fakes.py` and `lib/services.py`:
- `BLOCKED_CALLER_NUMBERS = {"9005550199"}`: Callers with this ANI immediately trigger deflection copy `restricted_caller` and escalation/hangup.
- `DECLINED_CARD_LAST4 = {"0000", "9999"}`: Payment tools trigger business error `CARD_DECLINED` without mutating account state.
- `mock_error`: Session variable fault injection. If `state.get("mock_error")` is non-empty, every tool returns system error `SYSTEM_UNAVAILABLE` to test agent resilience and graceful recovery under backend failure.
- Mandatory copy keys in `lib/fakes.py`: `ai_disclosure` (stating AI identity on Turn 1), `recording_notice` (call monitoring warning), and `malicious_closing` (polite refusal and termination on prompt injection or abusive language).

### 3. Deriving Scenarios from the PRD Business-Rule Register
Derive test scenarios systematically from the PRD business-rule register:
- For every positive capability, generate a **Negative Twin** testing authorization refusal, quota exhaustion, or unauthenticated lockout.
- Test adversarial boundary conditions: short imperative commands ("Cancel now"), rapid topic switching, and unexpected caller silence.
- **All Three Judge Metrics On:** Every simulation grades across **Custom Expectations**, **User Goal Satisfaction**, and **Hallucination/Grounding**.

---

## Checklist Before Committing an Eval
- [ ] Tagged with `REQ-n` and priority (`P0` / `P1` / `P2`).
- [ ] Expectations are observable; no `"e.g."` or sample quotes in `response_guide`.
- [ ] Includes fact-less caller coverage (no phone/PIN/card in persona prompt where applicable).
- [ ] Every PRD field, allowed value and timeline the eval depends on has a contract test (money: number, 2-decimal display string, currency).
- [ ] Preserves `agent_transfer` on multi-agent goldens.
- [ ] Uses oracle values from `lib/fakes.py` for time-dependent facts.
- [ ] Fails on the unpatched agent if written as a regression test.
- [ ] Listed in `docs/tdd.md` coverage map.
