"""The LLM Quirks case registry.

This is the single place to add a new quirk: append a `CaseDefinition` to
`CASES` below. Everything else (API responses, the case page rendering) is
driven off this data — no other file needs to change.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CaseVariant:
    label: str
    prompt: str
    expected: str | None = None  # only set when a single correct answer is unambiguous


@dataclass(frozen=True)
class CaseDefinition:
    id: str
    title: str
    teaser: str
    description: str
    variants: list[CaseVariant]
    explanation: str
    # Stream each variant's answer as it's generated instead of waiting for the
    # full reply. Opt-in per case — only set this for cases whose answers are
    # slow enough (long chain-of-thought) that a blank wait is a bad UX.
    streaming: bool = False


CASES: list[CaseDefinition] = [
    CaseDefinition(
        id="lollipop-reversal",
        title="Reversing “lollipop”",
        teaser="Two ways of asking for the same reversal give two different answers.",
        description=(
            "Ask the model to reverse the same word two different ways: as a normal "
            "word, and spelled out letter-by-letter with dashes. Click Go to run both "
            "prompts live and compare the results."
        ),
        variants=[
            CaseVariant(label="Plain word", prompt="Take the letters in lollipop and reverse them"),
            CaseVariant(
                label="Spelled out",
                prompt="Take the letters in l-o-l-l-i-p-o-p and reverse them",
            ),
        ],
        explanation=(
            "LLMs don't see individual letters — they see tokens, chunks of text "
            "produced by the model's tokenizer. “lollipop” is usually encoded as a "
            "small number of multi-letter tokens, not eight separate letter tokens. When "
            "asked to reverse it, the model has to reason its way down to individual "
            "letters, reverse them, and then reassemble a token sequence — and that "
            "reassembly step is where it tends to go wrong, even when the letter-by-letter "
            "reasoning above it was correct (you'll often see it spell out the right answer "
            "\"p o p i l l o l\" step by step, then still restate a garbled \"final\" word). "
            "Spelling the word out with dashes changes the tokenization to something much "
            "closer to one-token-per-letter, which is why that version tends to reverse more "
            "reliably. It's also why this is model- and tokenizer-version-dependent: a "
            "vocabulary update that changes how many tokens “lollipop” splits into changes "
            "this behavior even on the same model family. You can see this yourself: go to "
            '<a href="https://platform.openai.com/tokenizer" target="_blank" '
            'rel="noopener noreferrer">platform.openai.com/tokenizer</a> and try the word '
            '"lollipop" against different ChatGPT models — you\'ll see it split into a '
            "different number of tokens depending on which model's tokenizer you pick."
        ),
    ),
    CaseDefinition(
        id="fox-chicken-grain",
        title="The Fox, Chicken & Grain Trap",
        teaser="Two identical puzzles, only one drags in a rule that was never stated.",
        description=(
            "Ask the model to solve the exact same puzzle — three items, a "
            "carry-one-at-a-time limit, and an explicit \"nothing interacts\" rule — "
            "described two different ways: with the classic fox/chicken/grain framing, "
            "and with neutral household items. Click Go to run both prompts live and "
            "compare the results. These answers involve a lot of visible back-and-forth "
            "reasoning and can take a couple of minutes, so the answer streams in as "
            "it's generated rather than making you wait for the whole thing."
        ),
        variants=[
            CaseVariant(
                label="Classic puzzle items",
                prompt=(
                    "I have a fox, a chicken, and a bag of grain, and I need to cross a "
                    "river. My boat can carry me plus only one item at a time. None of "
                    "the items interact with each other in any way — nothing eats "
                    "anything, nothing is dangerous to leave alone together. What is the "
                    "minimum number of trips across the river?"
                ),
            ),
            CaseVariant(
                label="Neutral items",
                prompt=(
                    "I have a lamp, a book, and a plant, and I need to take them from my "
                    "bedroom to my living room. I am tired, I can carry only one item at "
                    "a time. None of the items interact with each other in any way. What "
                    "is the minimum number of trips to move all items to the living room?"
                ),
            ),
        ],
        explanation=(
            "LLMs don't only reason step-by-step from the words you give them — they "
            "also pattern-match a prompt against similar things they saw during "
            "training, and can lean on a memorized \"solution shape\" instead of the "
            "specific rules you actually stated. The fox/chicken/grain river crossing is "
            "one of the most repeated logic puzzles that exists, almost always paired "
            "with the rule that the fox eats the chicken (and the chicken eats the "
            "grain) if left alone. Even though this prompt explicitly rules that out, "
            "you'll often see the model second-guess itself mid-answer — reaching the "
            "direct 3-trip solution, then talking itself into the classic \"carry an "
            "item back across\" maneuver anyway, sometimes landing on 5 trips, sometimes "
            "second-guessing its way back to a \"3\" that's actually inconsistent with "
            "the steps it just wrote. The neutral-item version has the identical "
            "structure and the identical explicit \"no interactions\" rule, but it isn't "
            "a famous puzzle, so there's nothing memorized to pull it off course — the "
            "model just reasons from the stated rules and reaches the direct answer "
            "without inventing a constraint that was never there. Same logic, same "
            "explicit rules, different training-data gravity."
        ),
        streaming=True,
    ),
]


_CASES_BY_ID = {case.id: case for case in CASES}


def get_case_by_id(case_id: str) -> CaseDefinition | None:
    return _CASES_BY_ID.get(case_id)
