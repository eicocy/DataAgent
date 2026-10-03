"""Resolve typed facts without evaluating model supplied expressions."""
import math
import re
import string
from decimal import Decimal, ROUND_HALF_UP
from numbers import Real
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FactReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
    step_id: str
    path: list[str | int] = Field(min_length=1, max_length=12)
    format: Literal["number", "percent", "text"] = "number"
    decimals: int | None = Field(default=None, ge=0, le=8)


class ReportContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template: str = Field(min_length=1, max_length=12000)
    facts: list[FactReference] = Field(min_length=1, max_length=64)
    evidence_refs: list[str] = Field(min_length=1, max_length=8)


def _has_unbound_number(literal: str) -> bool:
    if any(character.isnumeric() for character in literal if character not in '零〇一二三四五六七八九十百千万亿两壹贰叁肆伍陆柒捌玖拾佰仟萬億'):
        return True
    numerals = '零〇一二三四五六七八九十百千万亿两壹贰叁肆伍陆柒捌玖拾佰仟萬億'
    # Common non-quantitative words must not turn ordinary prose into a number.
    for word in ('进一步', '一定', '一般', '一直', '一共', '一致', '唯一', '万一', '一点点'):
        literal = literal.replace(word, '')
    return bool(re.search(f'[{numerals}]', literal))


def render_report(content: ReportContent, results: dict) -> str:
    if not set(content.evidence_refs) <= results.keys():
        raise ValueError("Unknown evidence step")
    values = {}
    for fact in content.facts:
        if fact.key in values or fact.step_id not in content.evidence_refs:
            raise ValueError("Invalid fact binding")
        value = results[fact.step_id]
        for part in fact.path:
            if isinstance(value, dict) and isinstance(part, str) and part in value:
                value = value[part]
            elif isinstance(value, list) and type(part) is int and 0 <= part < len(value):
                value = value[part]
            else:
                raise ValueError("Invalid fact path")
        if fact.format == "text":
            # Digit bearing categories and dates must be explicitly bound as text facts.
            if not isinstance(value, str) or fact.decimals is not None:
                raise ValueError("Expected a text label")
            values[fact.key] = value
        else:
            if isinstance(value, bool) or not isinstance(value, (Real, Decimal)) or not math.isfinite(value):
                raise ValueError("Expected a finite numeric fact")
            number = Decimal(str(value)) * (100 if fact.format == "percent" else 1)
            if fact.decimals is not None:
                number = number.quantize(Decimal(1).scaleb(-fact.decimals), rounding=ROUND_HALF_UP)
            values[fact.key] = format(number, "f") + ("%" if fact.format == "percent" else "")
    output, used = [], set()
    for literal, key, spec, conversion in string.Formatter().parse(content.template):
        if _has_unbound_number(literal):
            raise ValueError("Unbound numeric assertion")
        output.append(literal)
        if key is not None:
            if key not in values or spec or conversion:
                raise ValueError("Unsupported template binding")
            output.append(values[key])
            used.add(key)
    if used != values.keys():
        raise ValueError("Unused facts")
    answer = "".join(output)
    if len(answer) > 12000:
        raise ValueError("Report exceeds budget")
    return answer
