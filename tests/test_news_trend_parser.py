"""Pure tests for the AI trend-verdict parser (contract §9.1 bước 5, plan lô L3.1).

``core/trend_verdict_parser.py`` is the registered content authority of a verdict
(contract §11b).  Its contract, verified here:

* a valid answer becomes three typed horizon payloads - direction/confidence from
  the frozen §4.5 value sets, non-empty rationale, citation ids that were printed
  in the prompt;
* the answer is taken WHOLE or refused WHOLE: a missing horizon, an extra key, a
  missing field, a value outside the frozen sets, an empty rationale or a
  fabricated citation leaves ``verdicts`` empty - nothing is ever stored (§9.1:
  "không lưu verdict rác");
* a response that is not a usable JSON document is flagged ``retryable`` (the
  single retry of §9.1 bước 5 belongs to the caller); a document that parses but
  violates the verdict contract is not - the retry is never performed here;
* purity and layering: stdlib + ``core.news_models`` only, ASCII source, no Qt,
  no policy read (the expected horizon keys are a parameter, R4).

Khuôn test: no mock, no Qt, no I/O - the answer under test is a plain string.
"""

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

import pytest

from core import trend_verdict_parser as parser
from core.news_models import VerdictConfidence, VerdictDirection, VerdictHorizon
from core.trend_verdict_parser import (
    HorizonVerdict,
    TrendParseOutcome,
    parse_trend_verdict,
)

PARSER_PY = Path(parser.__file__)
HORIZONS = ("short", "mid", "long")
PROMPT_IDS = (11, 22, 33)
_OMITTED = object()


def _block(
    direction: str = "bullish",
    confidence: str = "high",
    rationale: str = "Fed giữ nguyên lãi suất, đồng USD được hỗ trợ.",
    evidence: object = _OMITTED,
) -> dict[str, object]:
    return {
        "direction": direction,
        "confidence": confidence,
        "rationale": rationale,
        "evidence_item_ids": [11] if evidence is _OMITTED else evidence,
    }


def _answer(**overrides: object) -> str:
    document: dict[str, object] = {
        "short": _block(),
        "mid": _block(direction="neutral", confidence="medium"),
        "long": _block(direction="insufficient_data", confidence="none", evidence=[]),
    }
    document.update(overrides)
    return json.dumps(document, ensure_ascii=False)


def _parse(raw: object, *, with_ids: bool = True) -> TrendParseOutcome:
    return parse_trend_verdict(
        raw,
        horizons=HORIZONS,
        evidence_item_ids=PROMPT_IDS if with_ids else None,
    )


# ---- 1. phản hồi hợp lệ --------------------------------------------------------


class TestValidAnswer:
    def test_three_horizons_are_accepted_in_the_expected_order(self):
        outcome = _parse(_answer())

        assert outcome.ok is True
        assert outcome.error is None
        assert [verdict.horizon for verdict in outcome.verdicts] == list(VerdictHorizon)
        assert all(isinstance(verdict, HorizonVerdict) for verdict in outcome.verdicts)

    def test_frozen_enum_members_are_used_not_bare_strings(self):
        outcome = _parse(_answer())

        short, mid, long = outcome.verdicts
        assert short.direction is VerdictDirection.BULLISH
        assert short.confidence is VerdictConfidence.HIGH
        assert mid.direction is VerdictDirection.NEUTRAL
        assert mid.confidence is VerdictConfidence.MEDIUM
        assert long.direction is VerdictDirection.INSUFFICIENT_DATA
        assert long.confidence is VerdictConfidence.NONE

    def test_rationale_and_evidence_are_carried_typed(self):
        outcome = _parse(_answer(short=_block(rationale="  Lập luận  ", evidence=[11, 22])))

        short = outcome.verdicts[0]
        assert short.rationale == "Lập luận"
        assert short.evidence_item_ids == (11, 22)

    def test_empty_evidence_list_is_allowed(self):
        outcome = _parse(_answer(mid=_block(evidence=[])))

        assert outcome.ok is True
        assert outcome.verdicts[1].evidence_item_ids == ()

    def test_horizon_order_follows_the_caller(self):
        outcome = parse_trend_verdict(
            _answer(), horizons=("mid", "short", "long"), evidence_item_ids=PROMPT_IDS
        )

        assert outcome.ok is True
        assert [verdict.horizon.value for verdict in outcome.verdicts] == [
            "mid",
            "short",
            "long",
        ]

    def test_whitespace_around_a_valid_document_is_tolerated(self):
        outcome = _parse("\n  " + _answer() + "  \n")

        assert outcome.ok is True


# ---- 2. JSON không dùng được ⇒ tín hiệu retry ----------------------------------


class TestUnusableResponse:
    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "   ",
            None,
            123,
            {"short": {}},
            "not json at all",
            '{"short": ',
            '```json\n{"short": {}}\n```',
            "Here is the answer: " + _answer(),
            _answer() + " Hope this helps!",
            "[]",
            '["short", "mid", "long"]',
        ],
    )
    def test_response_that_is_not_a_bare_json_object_is_retryable(self, raw):
        outcome = _parse(raw)

        assert outcome.ok is False
        assert outcome.verdicts == ()
        assert outcome.error is not None
        assert outcome.error.retryable is True
        assert outcome.error.error_type in ("InvalidResponse", "InvalidJson")

    def test_markdown_fence_is_refused_rather_than_unwrapped(self):
        """Prompt đòi JSON trần; câu trả lời cần bóc vỏ là câu trả lời hỏng → retry."""
        fenced = "```json\n" + _answer() + "\n```"

        outcome = _parse(fenced)

        assert outcome.error is not None
        assert outcome.error.error_type == "InvalidJson"
        assert outcome.error.retryable is True


# ---- 3. tài liệu hợp lệ nhưng sai hợp đồng ⇒ từ chối toàn bộ -------------------


class TestContractViolations:
    def test_missing_horizon_refuses_the_whole_answer(self):
        document = json.loads(_answer())
        del document["mid"]

        outcome = _parse(json.dumps(document))

        assert outcome.verdicts == ()
        assert outcome.error is not None
        assert outcome.error.error_type == "MissingHorizon"
        assert "mid" in outcome.error.detail
        assert outcome.error.retryable is False

    def test_extra_horizon_refuses_the_whole_answer(self):
        outcome = _parse(_answer(weekly=_block()))

        assert outcome.verdicts == ()
        assert outcome.error is not None
        assert outcome.error.error_type == "UnexpectedHorizon"
        assert "weekly" in outcome.error.detail
        assert outcome.error.retryable is False

    @pytest.mark.parametrize(
        "field", ["direction", "confidence", "rationale", "evidence_item_ids"]
    )
    def test_missing_field_refuses_the_whole_answer(self, field):
        block = _block()
        del block[field]

        outcome = _parse(_answer(short=block))

        assert outcome.verdicts == ()
        assert outcome.error is not None
        assert outcome.error.error_type == "MissingField"
        assert field in outcome.error.detail
        assert outcome.error.retryable is False

    def test_non_object_horizon_block_is_refused(self):
        outcome = _parse(_answer(mid="bullish"))

        assert outcome.verdicts == ()
        assert outcome.error is not None
        assert outcome.error.error_type == "InvalidHorizonBlock"
        assert outcome.error.retryable is False

    @pytest.mark.parametrize(
        "value", ["Bullish", "up", "", "bull", 1, None, True]
    )
    def test_direction_outside_the_frozen_set_is_refused(self, value):
        outcome = _parse(_answer(short=_block(direction=value)))  # type: ignore[arg-type]

        assert outcome.verdicts == ()
        assert outcome.error is not None
        assert outcome.error.error_type == "InvalidEnumValue"
        assert outcome.error.retryable is False

    def test_surrounding_whitespace_on_an_enum_value_is_tolerated(self):
        outcome = _parse(_answer(short=_block(direction=" neutral ", confidence=" high ")))

        assert outcome.ok is True
        assert outcome.verdicts[0].direction is VerdictDirection.NEUTRAL

    @pytest.mark.parametrize("value", ["HIGH", "very high", "", 0.8, None])
    def test_confidence_outside_the_frozen_set_is_refused(self, value):
        outcome = _parse(_answer(mid=_block(confidence=value)))  # type: ignore[arg-type]

        assert outcome.verdicts == ()
        assert outcome.error is not None
        assert outcome.error.error_type == "InvalidEnumValue"
        assert outcome.error.retryable is False

    @pytest.mark.parametrize("value", ["", "   ", None, 7, ["lý do"]])
    def test_empty_or_untyped_rationale_is_refused(self, value):
        outcome = _parse(_answer(long=_block(rationale=value)))  # type: ignore[arg-type]

        assert outcome.verdicts == ()
        assert outcome.error is not None
        assert outcome.error.error_type == "InvalidRationale"
        assert outcome.error.retryable is False

    @pytest.mark.parametrize("value", ["11", 11, {"11": 1}, None])
    def test_evidence_that_is_not_a_list_is_refused(self, value):
        outcome = _parse(_answer(short=_block(evidence=value)))

        assert outcome.verdicts == ()
        assert outcome.error is not None
        assert outcome.error.error_type == "InvalidEvidenceIds"
        assert outcome.error.retryable is False

    @pytest.mark.parametrize("entry", ["11", 11.5, True, None, [11]])
    def test_evidence_entry_that_is_not_an_integer_id_is_refused(self, entry):
        outcome = _parse(_answer(short=_block(evidence=[entry])))

        assert outcome.verdicts == ()
        assert outcome.error is not None
        assert outcome.error.error_type == "InvalidEvidenceIds"
        assert outcome.error.retryable is False

    def test_citation_outside_the_prompt_refuses_the_whole_answer(self):
        """Doctrine §9.1 bước 3: dẫn chứng không có trong prompt = bịa."""
        outcome = _parse(_answer(long=_block(evidence=[999])))

        assert outcome.verdicts == ()
        assert outcome.error is not None
        assert outcome.error.error_type == "InvalidEvidenceIds"
        assert "999" in outcome.error.detail
        assert outcome.error.retryable is False

    def test_citation_check_is_skipped_when_the_caller_supplies_no_id_set(self):
        outcome = _parse(_answer(mid=_block(evidence=[999])), with_ids=False)

        assert outcome.ok is True
        assert outcome.verdicts[1].evidence_item_ids == (999,)

    def test_one_bad_horizon_refuses_the_other_two_as_well(self):
        outcome = _parse(_answer(long=_block(direction="sideways")))

        assert outcome.verdicts == ()
        assert outcome.error is not None
        assert outcome.error.error_type == "InvalidEnumValue"

    def test_unknown_horizon_key_for_the_caller_is_a_programming_error(self):
        """Chân trời lạ ngoài tập đóng băng §4.5 = lỗi người gọi, không phải lỗi AI."""
        with pytest.raises(ValueError):
            parse_trend_verdict(_answer(), horizons=("weekly",), evidence_item_ids=None)


# ---- 4. ranh giới lớp + hàm thuần (L1/L2/L3) -----------------------------------


class TestPurityAndLayerBoundary:
    @classmethod
    def _source(cls) -> str:
        return PARSER_PY.read_text(encoding="utf-8")

    def test_module_imports_nothing_from_services_ui_controllers_or_qt(self):
        source = self._source()
        for forbidden in (
            "import services",
            "from services",
            "import ui",
            "from ui",
            "import controllers",
            "from controllers",
            "import workers",
            "from workers",
            "PyQt6",
            "requests",
            "sqlite3",
        ):
            assert forbidden not in source, f"{forbidden!r} must not appear"

    def test_module_imports_only_stdlib_and_core(self):
        tree = ast.parse(self._source())
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
            elif isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
        modules.discard("__future__")

        assert modules == {
            "json",
            "collections.abc",
            "dataclasses",
            "enum",
            "typing",
            "core.news_models",
        }

    def test_module_source_is_ascii_no_vietnamese_display_strings(self):
        assert self._source().isascii(), (
            "core/trend_verdict_parser.py must stay pure ASCII - every error is a "
            "typed report; Vietnamese text belongs to the presentation tier"
        )

    def test_module_reads_no_policy_and_never_retries(self):
        source = self._source()
        assert "load_news_policy" not in source
        assert "CONFIG_DIR" not in source
        assert "ai_window_days" not in source
        assert "ai_min_items" not in source

    def test_parser_is_a_pure_function_with_no_state(self):
        assert list(inspect.signature(parse_trend_verdict).parameters) == [
            "raw",
            "horizons",
            "evidence_item_ids",
        ]
        assert getattr(parse_trend_verdict, "__self__", None) is None

    def test_error_vocabulary_is_frozen(self):
        assert {
            parser._INVALID_RESPONSE,
            parser._INVALID_JSON,
            parser._MISSING_HORIZON,
            parser._UNEXPECTED_HORIZON,
            parser._INVALID_HORIZON_BLOCK,
            parser._MISSING_FIELD,
            parser._INVALID_ENUM_VALUE,
            parser._INVALID_RATIONALE,
            parser._INVALID_EVIDENCE_IDS,
        } == {
            "InvalidResponse",
            "InvalidJson",
            "MissingHorizon",
            "UnexpectedHorizon",
            "InvalidHorizonBlock",
            "MissingField",
            "InvalidEnumValue",
            "InvalidRationale",
            "InvalidEvidenceIds",
        }

    def test_the_retryable_set_covers_the_document_level_failures_only(self):
        assert parser._RETRYABLE == {"InvalidResponse", "InvalidJson"}
