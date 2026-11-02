import lib.speech as speech
from lib.speech import (
    clean_agent_speech,
    clean_speech,
    enforce_handover_utterance,
    mask_long_numbers,
    strip_markdown,
)


def test_long_numbers_keep_only_their_last_4_digits() -> None:
    assert mask_long_numbers("Call 2025550186 now") == "Call 0186 now"
    assert mask_long_numbers("It is (202) 555-0186.") == "It is 0186."
    assert mask_long_numbers("Card 7742 8888 9999 7742 is on file") == "Card 7742 is on file"


def test_short_numbers_dates_and_amounts_are_left_alone() -> None:
    text = "Reference R271846, due 2026-10-08 14:30, amount $7,742.56, code 271846."
    assert mask_long_numbers(text) == text


def test_speakable_numbers_are_kept(monkeypatch) -> None:
    monkeypatch.setattr(speech, "SPEAKABLE_NUMBERS", frozenset({"18005550186"}))
    assert mask_long_numbers("Call 1-800-555-0186.") == "Call 1-800-555-0186."


def test_strip_markdown() -> None:
    assert strip_markdown("**Done.** Use `code`.\n## Next") == "Done. Use code.\nNext"
    assert strip_markdown("Press # to finish") == "Press # to finish"


def test_clean_speech_and_caller_last4_preference() -> None:
    assert clean_speech("**Your number is 2025550186.**") == "Your number is 0186."
    params = {"phone_last4": "0186", "caller_provided_phone_last4": "0199"}
    assert (
        clean_agent_speech("Your number ending in 0186 is verified.", params)
        == "Your number ending in 0199 is verified."
    )
    msg = "I'm transferring you to a member of our team now. Thank you for your patience."
    handover_state = {"handover_complete": True, "handoff_message": msg}
    assert enforce_handover_utterance("", handover_state) == msg
    assert enforce_handover_utterance("Hold on.", handover_state) == "Hold on."
    step_line = "I'm transferring you to a billing specialist now."
    assert enforce_handover_utterance(step_line, handover_state) == step_line
    assert enforce_handover_utterance("", {"handover_complete": False, "handoff_message": msg}) == ""


PHONE_SWAP = {"phone_last4": "0186", "caller_provided_phone_last4": "0199"}


def test_profile_phone_ending_becomes_the_callers_phone_ending() -> None:
    assert clean_agent_speech("I sent a code to the number ending in 0186.", PHONE_SWAP) == (
        "I sent a code to the number ending in 0199."
    )
    assert clean_agent_speech("Your number is 514-555-0186.", PHONE_SWAP) == "Your number is 0199."
    fr = "J'ai envoyé un code au numéro se terminant par 0186."
    assert clean_agent_speech(fr, PHONE_SWAP) == "J'ai envoyé un code au numéro se terminant par 0199."


def test_no_swap_when_caller_phone_matches_or_is_missing() -> None:
    text = "Your number ending in 0186 is verified."
    assert clean_agent_speech(text, {"phone_last4": "0186", "caller_provided_phone_last4": "0186"}) == text
    assert clean_agent_speech(text, {"phone_last4": "0186", "caller_provided_phone_last4": ""}) == text
    assert clean_agent_speech(text, {"phone_last4": "", "caller_provided_phone_last4": "0199"}) == text
    assert clean_agent_speech(text, None) == text


def test_temporary_number_ending_is_never_rewritten() -> None:
    # VE-66: start_number_transfer returned temporary_number_last4 "2538"; the reply must keep it.
    text = "Your temporary number ending in 2538 is active until the transfer completes."
    assert clean_agent_speech(text, PHONE_SWAP) == text
    same = {"phone_last4": "0199", "caller_provided_phone_last4": "0199"}
    assert clean_agent_speech(text, same) == text
    fr = "Votre numéro temporaire se terminant par 3014 est actif."
    assert clean_agent_speech(fr, PHONE_SWAP) == fr
    assert clean_agent_speech("The number to transfer is 4471.", PHONE_SWAP) == "The number to transfer is 4471."


def test_other_endings_are_never_rewritten() -> None:
    for text in (
        "Your Visa card ending in 4242 was charged.",
        "The bank account ending in 7781 is on file.",
        "Your ticket number is 5521.",
        "Your claim ending in 9034 is open.",
        "Order ending in 6120 has shipped.",
        "La carte se terminant par 4242 a été débitée.",
        "Le compte bancaire se terminant par 7781 est enregistré.",
        "Su tarjeta termina en 4242.",
    ):
        assert clean_agent_speech(text, PHONE_SWAP) == text


def test_card_bank_or_account_ending_equal_to_profile_phone_is_kept() -> None:
    for text in (
        "Your card ending in 0186 was charged.",
        "The bank account ending in 0186 is on file.",
        "Votre carte se terminant par 0186 a été débitée.",
    ):
        assert clean_agent_speech(text, PHONE_SWAP) == text
    with_card = {**PHONE_SWAP, "card_last4": "0186"}
    assert clean_agent_speech("Payment ending in 0186 went through.", with_card) == (
        "Payment ending in 0186 went through."
    )
