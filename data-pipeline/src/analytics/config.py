"""Validated configuration and matching helpers for youth topic analytics."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


_REQUIRED_WEIGHTS = ("w_join", "w_minutes", "w_resolved", "w_escalated")
_SUPPORTED_NORMALIZATIONS = frozenset({"yearly_max"})


@dataclass(frozen=True, slots=True)
class TopicDefinition:
    label: str
    aliases: tuple[str, ...]
    exclude_terms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class YouthTopicRules:
    version: str
    topics: tuple[TopicDefinition, ...]
    proxy_agencies: tuple[str, ...]
    proxy_keywords: tuple[str, ...]
    section_headers: Mapping[str, tuple[str, ...]]
    escalated_phrases: tuple[str, ...]
    userdict_path: Path | None = None
    stopwords_path: Path | None = None

    @property
    def by_label(self) -> dict[str, TopicDefinition]:
        return {topic.label: topic for topic in self.topics}


@dataclass(frozen=True, slots=True)
class TopicWeights:
    version: str
    w_join: float
    w_minutes: float
    w_resolved: float
    w_escalated: float
    normalization: str


@dataclass(frozen=True, slots=True)
class KeywordConfig:
    version: str
    top_n: int
    min_document_frequency: int
    min_token_length: int
    max_token_length: int
    userdict_path: Path | None = None
    stopwords_path: Path | None = None
    policy_terms: tuple[str, ...] = ()
    policy_anchors: tuple[str, ...] = ()
    policy_relevance_bonus: float = 0.8
    frequency_weight: float = 1.0
    min_dynamic_frequency: int = 5


def load_topic_rules(path: str | Path) -> YouthTopicRules:
    config_path = Path(path)
    payload = _load_object(config_path)
    version = _required_text(payload, "version")
    raw_topics = payload.get("topics")
    if not isinstance(raw_topics, list) or not raw_topics:
        raise ValueError("topic rules must contain a non-empty topics array")

    topics: list[TopicDefinition] = []
    labels: set[str] = set()
    for raw in raw_topics:
        if not isinstance(raw, Mapping):
            raise ValueError("each topic definition must be an object")
        label = _required_text(raw, "label")
        if label in labels:
            raise ValueError(f"duplicate topic label: {label}")
        raw_aliases = raw.get("aliases", [])
        if not isinstance(raw_aliases, list):
            raise ValueError(f"aliases for {label!r} must be an array")
        aliases = _unique_texts([label, *raw_aliases], field=f"aliases for {label}")
        excludes = _unique_texts(raw.get("exclude_terms", []), field=f"exclude_terms for {label}")
        topics.append(TopicDefinition(label, aliases, excludes))
        labels.add(label)

    proxy_agencies = _unique_texts(payload.get("proxy_agencies", []), field="proxy_agencies")
    proxy_keywords = _unique_texts(payload.get("proxy_keywords", []), field="proxy_keywords")
    section_headers = payload.get("section_headers", {})
    if not isinstance(section_headers, Mapping):
        raise ValueError("section_headers must be an object")
    sections = {
        key: _unique_texts(section_headers.get(key, []), field=f"section_headers.{key}")
        for key in ("discussed", "resolved")
    }
    escalated_phrases = _unique_texts(
        payload.get("escalated_phrases", []), field="escalated_phrases"
    )
    return YouthTopicRules(
        version=version,
        topics=tuple(topics),
        proxy_agencies=proxy_agencies,
        proxy_keywords=proxy_keywords,
        section_headers=sections,
        escalated_phrases=escalated_phrases,
        userdict_path=_resolve_optional_path(config_path, payload.get("jieba_userdict")),
        stopwords_path=_resolve_optional_path(config_path, payload.get("stopwords")),
    )


def load_topic_weights(path: str | Path) -> TopicWeights:
    payload = _load_object(Path(path))
    missing = [key for key in _REQUIRED_WEIGHTS if key not in payload]
    if missing:
        raise ValueError(f"topic weights missing required keys: {', '.join(missing)}")
    normalization = _required_text(payload, "normalization")
    if normalization not in _SUPPORTED_NORMALIZATIONS:
        raise ValueError(f"unsupported topic normalization: {normalization}")
    values: dict[str, float] = {}
    for key in _REQUIRED_WEIGHTS:
        value = payload[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"topic weight coefficient {key} must be non-negative")
        values[key] = float(value)
    return TopicWeights(
        version=_required_text(payload, "version"),
        normalization=normalization,
        **values,
    )


def load_keyword_config(path: str | Path) -> KeywordConfig:
    config_path = Path(path)
    payload = _load_object(config_path)
    top_n = _positive_int(payload, "top_n")
    min_document_frequency = _positive_int(payload, "min_document_frequency")
    min_token_length = _positive_int(payload, "min_token_length")
    max_token_length = _positive_int(payload, "max_token_length")
    if max_token_length < min_token_length:
        raise ValueError("max_token_length must be greater than or equal to min_token_length")
    policy_relevance_bonus = payload.get("policy_relevance_bonus", 0.8)
    if (
        isinstance(policy_relevance_bonus, bool)
        or not isinstance(policy_relevance_bonus, (int, float))
        or policy_relevance_bonus < 0
    ):
        raise ValueError("keyword config policy_relevance_bonus must be non-negative")
    frequency_weight = payload.get("frequency_weight", 1.0)
    if (
        isinstance(frequency_weight, bool)
        or not isinstance(frequency_weight, (int, float))
        or frequency_weight < 0
    ):
        raise ValueError("keyword config frequency_weight must be non-negative")
    min_dynamic_frequency = payload.get("min_dynamic_frequency", 5)
    if (
        isinstance(min_dynamic_frequency, bool)
        or not isinstance(min_dynamic_frequency, int)
        or min_dynamic_frequency <= 0
    ):
        raise ValueError("keyword config min_dynamic_frequency must be a positive integer")
    policy_terms_path = _resolve_optional_path(config_path, payload.get("policy_terms"))
    policy_anchors = _unique_texts(
        payload.get("policy_anchors", []), field="policy_anchors"
    )
    return KeywordConfig(
        version=_required_text(payload, "version"),
        top_n=top_n,
        min_document_frequency=min_document_frequency,
        min_token_length=min_token_length,
        max_token_length=max_token_length,
        userdict_path=_resolve_optional_path(config_path, payload.get("jieba_userdict")),
        stopwords_path=_resolve_optional_path(config_path, payload.get("stopwords")),
        policy_terms=_load_policy_terms(policy_terms_path),
        policy_anchors=policy_anchors,
        policy_relevance_bonus=float(policy_relevance_bonus),
        frequency_weight=float(frequency_weight),
        min_dynamic_frequency=min_dynamic_frequency,
    )


def normalize_topic_text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).lower()
    return re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE)


def match_topic_labels(text: Any, rules: YouthTopicRules) -> set[str]:
    normalized = normalize_topic_text(text)
    if not normalized:
        return set()
    matched: set[str] = set()
    for topic in rules.topics:
        if any(normalize_topic_text(exclude) in normalized for exclude in topic.exclude_terms):
            continue
        if any(normalize_topic_text(alias) in normalized for alias in topic.aliases):
            matched.add(topic.label)
    return matched


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read topic config: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid topic config JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("topic config must be a JSON object")
    return payload


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"topic config requires non-empty {key}")
    return value.strip()


def _positive_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"keyword config {key} must be a positive integer")
    return value


def _unique_texts(values: Any, *, field: str) -> tuple[str, ...]:
    if not isinstance(values, list):
        raise ValueError(f"{field} must be an array")
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} cannot contain empty values")
        text = unicodedata.normalize("NFKC", value).strip()
        if text not in seen:
            output.append(text)
            seen.add(text)
    return tuple(output)


def _resolve_optional_path(config_path: Path, value: Any) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("topic dictionary paths must be non-empty strings")
    return (config_path.parent / value).resolve()


def _load_policy_terms(path: Path | None) -> tuple[str, ...]:
    if path is None:
        return ()
    payload = _load_object(path)
    return _unique_texts(payload.get("terms", []), field="policy_terms")
