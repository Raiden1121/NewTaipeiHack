"""Extract dynamic annual youth keywords from curated source text."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .config import KeywordConfig, TopicWeights
from .io import atomic_json_write


Tokenizer = Callable[[str], Iterable[str]]

_CJK_NAME = r"[\u3400-\u9fff]{2,4}"
_MEETING_ROLE_NAME_PATTERNS = (
    re.compile(
        rf"(?:提案)?委員\s*[:：]\s*{_CJK_NAME}"
        rf"(?=\s|[()（）\[\]［］:：、，,。\-－]|$)"
    ),
    re.compile(
        rf"提案委員\s*{_CJK_NAME}"
        rf"(?=\s|[()（）\[\]［］:：、，,。\-－]|$)"
    ),
    re.compile(
        rf"{_CJK_NAME}\s*委員"
        rf"(?=\s*(?:[:：()（）\[\]［］、，,。\-－]|$))"
    ),
)
_ADMINISTRATIVE_SUFFIXES = (
    "局",
    "處",
    "科",
    "室",
    "會",
    "部",
    "委員會",
    "政府",
    "機關",
    "單位",
    "中心",
)
_ADMINISTRATIVE_TERMS = frozenset(
    {"主席", "紀錄", "散會", "動議", "議程", "提案", "業務報告"}
)


def calculate_youth_keyword_frequency(
    join_records: Iterable[Mapping[str, Any]],
    minute_records: Iterable[Mapping[str, Any]],
    *,
    config: KeywordConfig,
    weights: TopicWeights,
    tokenizer: Tokenizer | None = None,
) -> dict[str, Any]:
    """Calculate dynamic keywords without restricting output to a topic list."""

    join_rows = [dict(row) for row in join_records]
    minute_rows = [dict(row) for row in minute_records]
    tokenize, tokenizer_name = _build_tokenizer(config, tokenizer)
    stopwords = _load_stopwords(config.stopwords_path)
    policy_terms = {
        _normalize_token(term) for term in config.policy_terms if _normalize_token(term)
    }
    policy_anchors = {
        _normalize_token(term)
        for term in config.policy_anchors
        if _normalize_token(term)
    }

    years: set[int] = set()
    term_frequency: Counter[tuple[int, str]] = Counter()
    join_documents: defaultdict[tuple[int, str], set[str]] = defaultdict(set)
    minute_documents: defaultdict[tuple[int, str], set[str]] = defaultdict(set)
    topic_documents: defaultdict[tuple[int, str], set[str]] = defaultdict(set)
    join_support: Counter[tuple[int, str]] = Counter()
    resolved: set[tuple[int, str]] = set()
    escalated: set[tuple[int, str]] = set()

    for index, row in enumerate(join_rows):
        if row.get("youth_topic_proxy") is not True:
            continue
        year = _row_year(row)
        if year is None:
            continue
        years.add(year)
        text = " ".join(
            str(row.get(key) or "")
            for key in ("title", "content", "interest_impact", "category")
        )
        text = _remove_meeting_role_names(text)
        title = _remove_meeting_role_names(str(row.get("title") or ""))
        record_id = _record_id(row, index, "join")
        terms = _filtered_tokens(
            tokenize(text),
            stopwords=stopwords,
            protected_terms=policy_terms,
            config=config,
        )
        topic_terms = set(
            _filtered_tokens(
                tokenize(title),
                stopwords=stopwords,
                protected_terms=policy_terms,
                config=config,
            )
        )
        for term, count in Counter(terms).items():
            key = (year, term)
            term_frequency[key] += count
            join_documents[key].add(record_id)
            join_support[key] += 1.0 + math.log1p(_non_negative_number(row.get("endorsement_count")))
            if term in topic_terms:
                topic_documents[key].add(record_id)

    for index, row in enumerate(minute_rows):
        year = _row_year(row)
        if year is None:
            continue
        years.add(year)
        source_text = str(row.get("source_text") or "")
        discussion_text = str(row.get("discussion_text") or "")
        resolution_text = str(row.get("resolution_text") or "")
        if not discussion_text and not resolution_text:
            discussion_text = source_text
        topic_text = str(row.get("topic_text") or "")
        if not topic_text:
            source_lines = discussion_text.splitlines()
            topic_text = source_lines[0] if source_lines else ""
        text = _remove_meeting_role_names(
            "\n".join(part for part in (discussion_text, resolution_text) if part)
        )
        topic_text = _remove_meeting_role_names(topic_text)
        record_id = _record_id(row, index, "minutes")
        terms = _filtered_tokens(
            tokenize(text),
            stopwords=stopwords,
            protected_terms=policy_terms,
            config=config,
        )
        topic_terms = set(
            _filtered_tokens(
                tokenize(topic_text),
                stopwords=stopwords,
                protected_terms=policy_terms,
                config=config,
            )
        )
        resolution_terms = set(
            _filtered_tokens(
                tokenize(_remove_meeting_role_names(resolution_text)),
                stopwords=stopwords,
                protected_terms=policy_terms,
                config=config,
            )
        )
        for term, count in Counter(terms).items():
            key = (year, term)
            term_frequency[key] += count
            minute_documents[key].add(record_id)
            if term in topic_terms:
                topic_documents[key].add(record_id)
            if term in resolution_terms:
                resolved.add(key)
                if row.get("escalated") is True:
                    escalated.add(key)

    output_years: list[dict[str, Any]] = []
    output_keyword_count = 0
    for year in sorted(years):
        candidate_terms = {
            term
            for row_year, term in term_frequency
            if row_year == year
            and len(join_documents[(row_year, term)] | minute_documents[(row_year, term)])
            >= config.min_document_frequency
            and (
                not policy_terms
                or _is_policy_candidate(
                    term,
                    key=(row_year, term),
                    policy_terms=policy_terms,
                    term_frequency=term_frequency,
                    topic_documents=topic_documents,
                    join_documents=join_documents,
                    minute_documents=minute_documents,
                    policy_anchors=policy_anchors,
                    min_dynamic_frequency=config.min_dynamic_frequency,
                )
            )
        }
        join_max = max(
            (join_support[(year, term)] for term in candidate_terms),
            default=0.0,
        )
        minutes_max = max(
            (len(minute_documents[(year, term)]) for term in candidate_terms),
            default=0,
        )
        frequency_max = max(
            (
                math.log1p(term_frequency[(year, term)])
                for term in candidate_terms
            ),
            default=0.0,
        )
        scores: dict[str, float] = {}
        ranking_scores: dict[str, float] = {}
        policy_relevance: dict[str, float] = {}
        for term in candidate_terms:
            key = (year, term)
            normalized_join = join_support[key] / join_max if join_max else 0.0
            minute_mentions = len(minute_documents[key])
            normalized_minutes = minute_mentions / minutes_max if minutes_max else 0.0
            normalized_frequency = (
                math.log1p(term_frequency[key]) / frequency_max
                if frequency_max
                else 0.0
            )
            raw_score = (
                config.frequency_weight * normalized_frequency
                + weights.w_join * normalized_join
                + weights.w_minutes * normalized_minutes
                + weights.w_resolved * (1.0 if key in resolved else 0.0)
                + weights.w_escalated * (1.0 if key in escalated else 0.0)
            )
            document_count = len(join_documents[key] | minute_documents[key])
            topic_ratio = (
                len(topic_documents[key]) / document_count if document_count else 0.0
            )
            normalized_term = _normalize_token(term)
            is_known_policy_term = normalized_term in policy_terms
            relevance = 1.0 if is_known_policy_term else 0.0
            if not is_known_policy_term and _has_policy_anchor(
                normalized_term, policy_anchors
            ):
                relevance += 0.25
            if not is_known_policy_term and len(normalized_term) >= 3 and topic_ratio:
                relevance += 0.25
            relevance += 0.25 * topic_ratio
            scores[term] = raw_score
            policy_relevance[term] = relevance
            ranking_scores[term] = raw_score + config.policy_relevance_bonus * relevance

        max_score = max(ranking_scores.values(), default=0.0)
        rows: list[dict[str, Any]] = []
        for term in sorted(
            candidate_terms,
            key=lambda item: (
                ranking_scores[item],
                len(join_documents[(year, item)] | minute_documents[(year, item)]),
                term_frequency[(year, item)],
                item,
            ),
            reverse=True,
        )[: config.top_n]:
            key = (year, term)
            join_mentions = len(join_documents[key])
            minutes_mentions = len(minute_documents[key])
            raw_score = scores[term]
            ranking_score = ranking_scores[term]
            if max_score <= 0:
                weight = 1
            else:
                weight = max(
                    1,
                    min(5, math.floor(1.0 + 4.0 * ranking_score / max_score + 0.5)),
                )
            if minutes_mentions > 0:
                weight = max(weight, 3)
            if key in escalated:
                weight = 5
            if key in escalated:
                signal = "escalated"
            elif minutes_mentions > 0:
                signal = "minutes"
            else:
                signal = "join"
            rows.append(
                {
                    "term": term,
                    "weight": weight,
                    "signal": signal,
                    "term_frequency": term_frequency[key],
                    "document_count": len(join_documents[key] | minute_documents[key]),
                    "join_mentions": join_mentions,
                    "minutes_mentions": minutes_mentions,
                    "resolved": key in resolved,
                    "escalated": key in escalated,
                    "join_support_score": round(join_support[key], 6),
                    "frequency_score": round(normalized_frequency, 6),
                    "raw_score": round(raw_score, 6),
                    "ranking_score": round(ranking_score, 6),
                    "policy_relevance": round(policy_relevance[term], 6),
                    "topic_mentions": len(topic_documents[key]),
                }
            )
        output_keyword_count += len(rows)
        output_years.append({"year_roc": year, "keywords": rows})

    return {
        "metric_id": "youth_keyword_frequency",
        "calculation_version": "5",
        "source_datasets": ["join_proposals", "youth_council_minutes"],
        "config_version": config.version,
        "normalization": weights.normalization,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "years": output_years,
        "_quality": {
            "join_input_rows": len(join_rows),
            "minutes_input_rows": len(minute_rows),
            "years": [item["year_roc"] for item in output_years],
            "tokenizer": tokenizer_name,
            "output_keyword_count": output_keyword_count,
        },
    }


def write_youth_keyword_frequency(
    result: Mapping[str, Any], *, output_dir: str | Path
) -> tuple[Path, Path]:
    root = Path(output_dir)
    output = {key: value for key, value in result.items() if key != "_quality"}
    output_path = atomic_json_write(
        root / "analytics" / "youth_keyword_frequency" / "all.json", output
    )
    quality = {
        "metric_id": "youth_keyword_frequency",
        "calculation_version": result.get("calculation_version"),
        "config_version": result.get("config_version"),
        "source_datasets": result.get("source_datasets"),
        **dict(result.get("_quality") or {}),
    }
    quality_path = atomic_json_write(
        root / "quality" / "analytics_youth_keyword_frequency.json", quality
    )
    return output_path, quality_path


def _build_tokenizer(
    config: KeywordConfig, tokenizer: Tokenizer | None
) -> tuple[Tokenizer, str]:
    if tokenizer is not None:
        return tokenizer, "injected"
    try:
        import jieba  # type: ignore
    except ImportError:
        protected_terms = tuple(
            term for term in config.policy_terms if term and term not in {"青年"}
        )

        def fallback_tokenize(text: str) -> list[str]:
            tokens = _fallback_tokenize(text)
            tokens.extend(term for term in protected_terms if term in text)
            return tokens

        return fallback_tokenize, "fallback_char_ngrams"
    if config.userdict_path and config.userdict_path.exists():
        with config.userdict_path.open("rb") as userdict:
            jieba.load_userdict(userdict)
    return jieba.lcut, "jieba"


def _fallback_tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for chunk in re.findall(r"[A-Za-z][A-Za-z0-9_-]*|[\u3400-\u9fff]+", text):
        if re.fullmatch(r"[\u3400-\u9fff]+", chunk):
            for size in (2, 3, 4):
                if len(chunk) < size:
                    continue
                tokens.extend(chunk[index : index + size] for index in range(len(chunk) - size + 1))
        else:
            tokens.append(chunk)
    return tokens


def _filtered_tokens(
    tokens: Iterable[str],
    *,
    stopwords: set[str],
    protected_terms: set[str],
    config: KeywordConfig,
) -> list[str]:
    filtered: list[str] = []
    for value in tokens:
        token = _normalize_token(value)
        if not token or (token in stopwords and token not in protected_terms):
            continue
        if token.isdigit() or not re.search(r"[A-Za-z\u3400-\u9fff]", token):
            continue
        if not config.min_token_length <= len(token) <= config.max_token_length:
            continue
        filtered.append(token)
    return filtered


def _is_policy_candidate(
    term: str,
    *,
    key: tuple[int, str],
    policy_terms: set[str],
    term_frequency: Counter[tuple[int, str]],
    topic_documents: Mapping[tuple[int, str], set[str]],
    join_documents: Mapping[tuple[int, str], set[str]],
    minute_documents: Mapping[tuple[int, str], set[str]],
    policy_anchors: set[str],
    min_dynamic_frequency: int,
) -> bool:
    normalized = _normalize_token(term)
    if not policy_terms:
        return True
    if normalized in policy_terms:
        return True
    if _is_administrative_term(normalized):
        return False
    topic_mentions = len(topic_documents[key])
    source_count = int(bool(join_documents[key])) + int(bool(minute_documents[key]))
    frequency = term_frequency[key]
    if len(normalized) >= 3:
        return topic_mentions >= 1 or (
            source_count >= 2
            and frequency >= min_dynamic_frequency
            and _has_policy_anchor(normalized, policy_anchors)
        )
    return topic_mentions >= 2 or (
        source_count >= 2
        and frequency >= min_dynamic_frequency
        and _has_policy_anchor(normalized, policy_anchors)
    )


def _has_policy_anchor(term: str, policy_anchors: set[str]) -> bool:
    return any(anchor == term or anchor in term for anchor in policy_anchors)


def _is_policy_compound(term: str, policy_anchors: set[str]) -> bool:
    return len(term) >= 3 and _has_policy_anchor(term, policy_anchors)


def _is_administrative_term(term: str) -> bool:
    return term in _ADMINISTRATIVE_TERMS or any(
        term.endswith(suffix) for suffix in _ADMINISTRATIVE_SUFFIXES
    )


def _load_stopwords(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    return {
        _normalize_token(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if _normalize_token(line)
    }


def _normalize_token(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    return re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE)


def _remove_meeting_role_names(text: str) -> str:
    """Remove personal names when meeting text identifies them by role."""

    for pattern in _MEETING_ROLE_NAME_PATTERNS:
        text = pattern.sub(" ", text)
    return text


def _row_year(row: Mapping[str, Any]) -> int | None:
    value = row.get("year_roc")
    if value is not None:
        try:
            year = int(str(value).strip())
            return year - 1911 if year > 1911 else year
        except (TypeError, ValueError):
            return None
    period_start = row.get("period_start")
    if isinstance(period_start, str):
        try:
            return datetime.fromisoformat(period_start[:10]).year - 1911
        except ValueError:
            return None
    return None


def _record_id(row: Mapping[str, Any], index: int, prefix: str) -> str:
    value = row.get("source_record_id")
    if value is not None:
        return str(value)
    payload = json.dumps(dict(row), ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"{prefix}:{index}:{hashlib.sha256(payload).hexdigest()[:16]}"


def _non_negative_number(value: Any) -> float:
    if value is None or isinstance(value, bool):
        return 0.0
    try:
        return max(0.0, float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return 0.0
