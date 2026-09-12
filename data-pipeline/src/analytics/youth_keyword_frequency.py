"""Extract dynamic all-period youth keywords from curated source text."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .config import KeywordConfig, TopicWeights
from .io import atomic_json_write


Tokenizer = Callable[[str], Iterable[str]]

_CJK_NAME = r"[\u3400-\u9fff]{2,4}"
_MEETING_ROLE_MARKERS = (
    "主任委員",
    "副市長",
    "提案人",
    "聯絡人",
    "局長",
    "處長",
    "科長",
    "主任",
    "組長",
    "代表",
    "委員",
    "主席",
    "紀錄",
)
_MEETING_ROLE_ALTERNATION = "|".join(
    sorted(
        (re.escape(role) for role in _MEETING_ROLE_MARKERS),
        key=len,
        reverse=True,
    )
)
_ROLE_CONTEXT_PREFIX = (
    r"[\u3400-\u9fff]{2,8}"
    r"(?:委員會|政府|機關|單位|中心|局|處|科|室|會|部)"
)
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
    re.compile(
        rf"(?m)^\s*(?:{_MEETING_ROLE_ALTERNATION})\s*[:：]\s*[^\n]*$"
    ),
    re.compile(
        rf"(?:{_ROLE_CONTEXT_PREFIX})?(?:{_MEETING_ROLE_ALTERNATION})\s*{_CJK_NAME}"
        rf"(?=\s|[()（）\[\]［］:：、，,。；;\-－]|$)"
    ),
    re.compile(
        rf"{_CJK_NAME}\s*(?:{_MEETING_ROLE_ALTERNATION})"
        rf"(?=\s|[()（）\[\]［］:：、，,。；;\-－]|$)"
    ),
    re.compile(
        rf"(?<![\u3400-\u9fff])(?:{_MEETING_ROLE_ALTERNATION})(?![\u3400-\u9fff])"
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
_URL_PATTERN = re.compile(r"(?i)(?:https?|ftp)://[^\s<>'\"]+|www\.[^\s<>'\"]+")
_EMAIL_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:0\d{1,2}[-－]?\d{3,4}[-－]?\d{3,4}|09\d{2}[-－]?\d{3}[-－]?\d{3})(?!\d)"
)
_DATE_PATTERN = re.compile(
    r"(?:民國\s*)?\d{2,4}\s*年\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*[日號])?"
    r"|(?<!\d)\d{4}[-/.]\d{1,2}[-/.]\d{1,2}(?!\d)"
)
_PAGE_PATTERN = re.compile(r"(?i)(?:第\s*)?\d+\s*(?:頁|page)\b")
_IDENTIFIER_PATTERN = re.compile(
    r"(?:案號|序號|編號|文號|字號|案次)\s*[:：#\-]?\s*[A-Za-z0-9一二三四五六七八九零〇\-_/]+"
)
_METADATA_PATTERNS = (
    _URL_PATTERN,
    _EMAIL_PATTERN,
    _PHONE_PATTERN,
    _DATE_PATTERN,
    _PAGE_PATTERN,
    _IDENTIFIER_PATTERN,
)


@dataclass(frozen=True, slots=True)
class _CleaningRules:
    version: str
    role_markers: tuple[str, ...]
    administrative_terms: frozenset[str]
    soft_stopwords: frozenset[str]
    role_name_patterns: tuple[re.Pattern[str], ...]


_DEFAULT_CLEANING_RULES = _CleaningRules(
    version="builtin",
    role_markers=_MEETING_ROLE_MARKERS,
    administrative_terms=frozenset(),
    soft_stopwords=frozenset({"問題", "工作", "政策", "服務"}),
    role_name_patterns=_MEETING_ROLE_NAME_PATTERNS,
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
    cleaning_rules = _load_cleaning_rules(config.cleaning_rules_path)
    stopwords.update(
        _normalize_token(term)
        for term in _ADMINISTRATIVE_TERMS | cleaning_rules.administrative_terms
        if _normalize_token(term)
    )

    source_periods: dict[str, set[str]] = {
        "join_proposals": set(),
        "youth_council_minutes": set(),
    }
    term_frequency: Counter[str] = Counter()
    join_documents: defaultdict[str, set[str]] = defaultdict(set)
    minute_documents: defaultdict[str, set[str]] = defaultdict(set)
    topic_documents: defaultdict[str, set[str]] = defaultdict(set)
    join_support: Counter[str] = Counter()
    resolved: set[str] = set()
    escalated: set[str] = set()
    eligible_join_rows = 0
    eligible_minutes_rows = 0
    unknown_period_rows = 0
    cleaning_stats: Counter[str] = Counter()

    for index, row in enumerate(join_rows):
        if row.get("youth_topic_proxy") is not True:
            continue
        eligible_join_rows += 1
        year = _row_year(row)
        if year is None:
            unknown_period_rows += 1
        else:
            source_periods["join_proposals"].add(str(year))
        cleaned_fields: dict[str, str] = {}
        for key in ("title", "content", "interest_impact", "category"):
            cleaned_value, metadata_count, role_count = _clean_analytics_text(
                row.get(key), cleaning_rules=cleaning_rules
            )
            cleaned_fields[key] = cleaned_value
            cleaning_stats["removed_metadata_count"] += metadata_count
            cleaning_stats["removed_role_name_count"] += role_count
        text = " ".join(cleaned_fields.values())
        title = cleaned_fields["title"]
        record_id = _record_id(row, index, "join")
        terms = _filtered_tokens(
            tokenize(text),
            stopwords=stopwords,
            protected_terms=policy_terms,
            config=config,
            stats=cleaning_stats,
        )
        topic_terms = set(
            _filtered_tokens(
                tokenize(title),
                stopwords=stopwords,
                protected_terms=policy_terms,
                config=config,
                stats=cleaning_stats,
            )
        )
        for term, count in Counter(terms).items():
            term_frequency[term] += count
            join_documents[term].add(record_id)
            join_support[term] += 1.0 + math.log1p(
                _non_negative_number(row.get("endorsement_count"))
            )
            if term in topic_terms:
                topic_documents[term].add(record_id)

    for index, row in enumerate(minute_rows):
        eligible_minutes_rows += 1
        year = _row_year(row)
        if year is None:
            unknown_period_rows += 1
        else:
            source_periods["youth_council_minutes"].add(str(year))
        source_text = str(row.get("source_text") or "")
        discussion_text = str(row.get("discussion_text") or "")
        resolution_text = str(row.get("resolution_text") or "")
        if not discussion_text and not resolution_text:
            discussion_text = source_text
        topic_text = str(row.get("topic_text") or "")
        if not topic_text:
            source_lines = discussion_text.splitlines()
            topic_text = source_lines[0] if source_lines else ""
        cleaned_discussion, metadata_count, role_count = _clean_analytics_text(
            discussion_text, cleaning_rules=cleaning_rules
        )
        cleaning_stats["removed_metadata_count"] += metadata_count
        cleaning_stats["removed_role_name_count"] += role_count
        cleaned_resolution, metadata_count, role_count = _clean_analytics_text(
            resolution_text, cleaning_rules=cleaning_rules
        )
        cleaning_stats["removed_metadata_count"] += metadata_count
        cleaning_stats["removed_role_name_count"] += role_count
        text = "\n".join(
            part for part in (cleaned_discussion, cleaned_resolution) if part
        )
        topic_text, metadata_count, role_count = _clean_analytics_text(
            topic_text, cleaning_rules=cleaning_rules
        )
        cleaning_stats["removed_metadata_count"] += metadata_count
        cleaning_stats["removed_role_name_count"] += role_count
        record_id = _record_id(row, index, "minutes")
        terms = _filtered_tokens(
            tokenize(text),
            stopwords=stopwords,
            protected_terms=policy_terms,
            config=config,
            stats=cleaning_stats,
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
                tokenize(cleaned_resolution),
                stopwords=stopwords,
                protected_terms=policy_terms,
                config=config,
            )
        )
        for term, count in Counter(terms).items():
            term_frequency[term] += count
            minute_documents[term].add(record_id)
            if term in topic_terms:
                topic_documents[term].add(record_id)
            if term in resolution_terms:
                resolved.add(term)
                if row.get("escalated") is True:
                    escalated.add(term)

    candidate_terms = {
        term
        for term in term_frequency
        if len(join_documents[term] | minute_documents[term])
        >= config.min_document_frequency
        and (
            not policy_terms
            or _is_policy_candidate(
                term,
                key=term,
                policy_terms=policy_terms,
                term_frequency=term_frequency,
                topic_documents=topic_documents,
                join_documents=join_documents,
                minute_documents=minute_documents,
                policy_anchors=policy_anchors,
                soft_stopwords=cleaning_rules.soft_stopwords,
                min_dynamic_frequency=config.min_dynamic_frequency,
                candidate_mode=config.candidate_mode,
            )
        )
    }
    join_max = max((join_support[term] for term in candidate_terms), default=0.0)
    minutes_max = max(
        (len(minute_documents[term]) for term in candidate_terms), default=0
    )
    frequency_max = max(
        (math.log1p(term_frequency[term]) for term in candidate_terms), default=0.0
    )
    scores: dict[str, float] = {}
    ranking_scores: dict[str, float] = {}
    policy_relevance: dict[str, float] = {}
    frequency_scores: dict[str, float] = {}
    for term in candidate_terms:
        normalized_join = join_support[term] / join_max if join_max else 0.0
        minute_mentions = len(minute_documents[term])
        normalized_minutes = minute_mentions / minutes_max if minutes_max else 0.0
        normalized_frequency = (
            math.log1p(term_frequency[term]) / frequency_max
            if frequency_max
            else 0.0
        )
        raw_score = (
            config.frequency_weight * normalized_frequency
            + weights.w_join * normalized_join
            + weights.w_minutes * normalized_minutes
            + weights.w_resolved * (1.0 if term in resolved else 0.0)
            + weights.w_escalated * (1.0 if term in escalated else 0.0)
        )
        document_count = len(join_documents[term] | minute_documents[term])
        topic_ratio = (
            len(topic_documents[term]) / document_count if document_count else 0.0
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
        frequency_scores[term] = normalized_frequency
        policy_relevance[term] = relevance
        ranking_scores[term] = raw_score + config.policy_relevance_bonus * relevance

    ranked_terms = sorted(
        candidate_terms,
        key=lambda item: (
            ranking_scores[item],
            len(join_documents[item] | minute_documents[item]),
            term_frequency[item],
            item,
        ),
        reverse=True,
    )[: config.top_n]
    selected_scores = [ranking_scores[term] for term in ranked_terms]
    min_selected_score = min(selected_scores, default=0.0)
    max_selected_score = max(selected_scores, default=0.0)
    rows: list[dict[str, Any]] = []
    for term in ranked_terms:
        join_mentions = len(join_documents[term])
        minutes_mentions = len(minute_documents[term])
        raw_score = scores[term]
        ranking_score = ranking_scores[term]
        if max_selected_score <= min_selected_score:
            weight = 3
        else:
            score_ratio = (ranking_score - min_selected_score) / (
                max_selected_score - min_selected_score
            )
            weight = max(
                1,
                min(5, math.floor(1.0 + 4.0 * score_ratio + 0.5)),
            )
        if term in escalated:
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
                "term_frequency": term_frequency[term],
                "document_count": len(join_documents[term] | minute_documents[term]),
                "join_mentions": join_mentions,
                "minutes_mentions": minutes_mentions,
                "resolved": term in resolved,
                "escalated": term in escalated,
                "join_support_score": round(join_support[term], 6),
                "frequency_score": round(frequency_scores[term], 6),
                "raw_score": round(raw_score, 6),
                "ranking_score": round(ranking_score, 6),
                "policy_relevance": round(policy_relevance[term], 6),
                "topic_mentions": len(topic_documents[term]),
            }
        )

    return {
        "metric_id": "youth_keyword_frequency",
        "analysis_id": "youth-keyword-frequency",
        "calculation_version": "7",
        "source_datasets": ["join_proposals", "youth_council_minutes"],
        "config_version": config.version,
        "normalization": "global_max",
        "weight_normalization": "selected_min_max",
        "candidate_mode": config.candidate_mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period_scope": "all_available",
        "source_periods": {
            dataset: sorted(periods, key=lambda value: int(value))
            for dataset, periods in source_periods.items()
        },
        "keywords": rows,
        "_quality": {
            "join_input_rows": len(join_rows),
            "minutes_input_rows": len(minute_rows),
            "eligible_join_rows": eligible_join_rows,
            "eligible_minutes_rows": eligible_minutes_rows,
            "unknown_period_rows": unknown_period_rows,
            "period_scope": "all_available",
            "period_strategy": "all_available",
            "geo_level": "county",
            "normalization": "global_max",
            "weight_normalization": "selected_min_max",
            "candidate_mode": config.candidate_mode,
            "cleaning_rules_version": cleaning_rules.version,
            "source_periods": {
                dataset: sorted(periods, key=lambda value: int(value))
                for dataset, periods in source_periods.items()
            },
            "tokenizer": tokenizer_name,
            "candidate_keyword_count": len(candidate_terms),
            "output_keyword_count": len(rows),
            "coverage": {
                "eligible_join_rows": eligible_join_rows,
                "eligible_minutes_rows": eligible_minutes_rows,
                "candidate_keyword_count": len(candidate_terms),
                "output_keyword_count": len(rows),
            },
            **cleaning_stats,
            "status": (
                "observed"
                if eligible_join_rows and eligible_minutes_rows
                else "partial"
                if eligible_join_rows or eligible_minutes_rows
                else "unavailable"
            ),
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
        "analysis_id": result.get("analysis_id", "youth-keyword-frequency"),
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
    for term in config.policy_terms:
        if term:
            jieba.add_word(term)
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
    stats: Counter[str] | None = None,
) -> list[str]:
    filtered: list[str] = []
    for value in tokens:
        token = _normalize_token(value)
        if not token:
            continue
        if token in stopwords and token not in protected_terms:
            if stats is not None:
                stats["removed_stopword_count"] += 1
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
    key: str,
    policy_terms: set[str],
    term_frequency: Counter[str],
    topic_documents: Mapping[str, set[str]],
    join_documents: Mapping[str, set[str]],
    minute_documents: Mapping[str, set[str]],
    policy_anchors: set[str],
    soft_stopwords: set[str] | frozenset[str],
    min_dynamic_frequency: int,
    candidate_mode: str = "dynamic",
) -> bool:
    normalized = _normalize_token(term)
    if normalized in policy_terms:
        return True
    topic_mentions = len(topic_documents[key])
    source_count = int(bool(join_documents[key])) + int(bool(minute_documents[key]))
    frequency = term_frequency[key]
    if candidate_mode == "policy_relevant":
        if normalized in soft_stopwords or _is_administrative_term(normalized):
            return False
        if len(normalized) >= 3:
            return topic_mentions >= 1 or (
                source_count >= 2
                and frequency >= min_dynamic_frequency
                and _has_policy_anchor(normalized, policy_anchors)
            )
        return _has_policy_anchor(normalized, policy_anchors) and (
            topic_mentions >= 1
            or (source_count >= 2 and frequency >= min_dynamic_frequency)
        )
    if normalized in soft_stopwords:
        return topic_mentions >= 1 or (
            source_count >= 2 and frequency >= min_dynamic_frequency
        )
    if not policy_terms:
        return True
    if _is_administrative_term(normalized):
        return False
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


def _build_role_name_patterns(
    role_markers: Iterable[str],
) -> tuple[re.Pattern[str], ...]:
    markers = tuple(
        sorted(
            {str(marker).strip() for marker in role_markers if str(marker).strip()},
            key=len,
            reverse=True,
        )
    )
    if not markers:
        return ()
    alternation = "|".join(re.escape(marker) for marker in markers)
    return (
        re.compile(rf"(?m)^\s*(?:{alternation})\s*[:：]\s*[^\n]*$"),
        re.compile(
            rf"(?:{_ROLE_CONTEXT_PREFIX})?(?:{alternation})\s*{_CJK_NAME}"
            rf"(?=\s|[()（）\[\]［］:：、，,。；;\-－]|$)"
        ),
        re.compile(
            rf"{_CJK_NAME}\s*(?:{alternation})"
            rf"(?=\s|[()（）\[\]［］:：、，,。；;\-－]|$)"
        ),
        re.compile(
            rf"(?<![\u3400-\u9fff])(?:{alternation})(?![\u3400-\u9fff])"
        ),
    )


def _load_cleaning_rules(path: Path | None) -> _CleaningRules:
    if path is None:
        return _DEFAULT_CLEANING_RULES
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read keyword cleaning rules: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid keyword cleaning rules JSON: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("keyword cleaning rules must be a JSON object")
    version = payload.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("keyword cleaning rules require a non-empty version")
    role_markers = payload.get("role_markers")
    if not isinstance(role_markers, list) or not role_markers:
        raise ValueError("keyword cleaning rules require role_markers")
    normalized_markers = tuple(
        str(marker).strip() for marker in role_markers if str(marker).strip()
    )
    if not normalized_markers:
        raise ValueError("keyword cleaning rules require non-empty role_markers")
    administrative_terms = payload.get("administrative_terms", [])
    if not isinstance(administrative_terms, list):
        raise ValueError("keyword cleaning rules administrative_terms must be an array")
    normalized_admin = frozenset(
        _normalize_token(term)
        for term in administrative_terms
        if _normalize_token(term)
    )
    soft_stopwords = payload.get("soft_stopwords", [])
    if not isinstance(soft_stopwords, list):
        raise ValueError("keyword cleaning rules soft_stopwords must be an array")
    normalized_soft = frozenset(
        _normalize_token(term)
        for term in soft_stopwords
        if _normalize_token(term)
    )
    return _CleaningRules(
        version=version.strip(),
        role_markers=normalized_markers,
        administrative_terms=normalized_admin,
        soft_stopwords=normalized_soft,
        role_name_patterns=_build_role_name_patterns(normalized_markers),
    )


def _clean_analytics_text(
    value: Any,
    *,
    cleaning_rules: _CleaningRules | None = None,
) -> tuple[str, int, int]:
    """Remove document metadata and role-scoped names before tokenization."""

    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(
        character for character in text if unicodedata.category(character) != "Cf"
    )
    removed_metadata = 0
    for pattern in _METADATA_PATTERNS:
        text, count = pattern.subn(" ", text)
        removed_metadata += count

    removed_role_names = 0
    rules = cleaning_rules or _DEFAULT_CLEANING_RULES
    for pattern in rules.role_name_patterns:
        text, count = pattern.subn(" ", text)
        removed_role_names += count
    return text, removed_metadata, removed_role_names


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
        return f"{prefix}:{value}"
    payload = json.dumps(dict(row), ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"{prefix}:{index}:{hashlib.sha256(payload).hexdigest()[:16]}"


def _non_negative_number(value: Any) -> float:
    if value is None or isinstance(value, bool):
        return 0.0
    try:
        return max(0.0, float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return 0.0
