import sys
import re
import unittest
from copy import deepcopy
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analytics.config import KeywordConfig, load_keyword_config, load_topic_weights  # noqa: E402
from analytics.youth_keyword_frequency import (  # noqa: E402
    calculate_youth_keyword_frequency,
)


class TestYouthKeywordFrequency(unittest.TestCase):
    def test_keyword_config_declares_cleaning_rules(self):
        config = load_keyword_config(CONFIG_DIR / "youth_keyword_config.json")
        weights = load_topic_weights(CONFIG_DIR / "youth_topic_weights.json")

        self.assertIsNotNone(config.cleaning_rules_path)
        self.assertEqual(config.cleaning_rules_path.name, "youth_keyword_cleaning.json")
        self.assertEqual(config.top_n, 23)
        self.assertEqual(config.candidate_mode, "policy_relevant")
        self.assertEqual(weights.normalization, "global_max")

    def test_aggregates_keywords_across_years_without_year_buckets(self):
        config = KeywordConfig(
            version="test",
            top_n=10,
            min_document_frequency=1,
            min_token_length=2,
            max_token_length=12,
            userdict_path=None,
            stopwords_path=None,
            policy_terms=("居住正義",),
            policy_anchors=("居住",),
        )
        result = calculate_youth_keyword_frequency(
            [
                {
                    "source_record_id": "join-109",
                    "year_roc": "109",
                    "youth_topic_proxy": True,
                    "title": "居住正義",
                    "content": "居住正義",
                    "endorsement_count": 3,
                },
                {
                    "source_record_id": "join-114",
                    "year_roc": "114",
                    "youth_topic_proxy": True,
                    "title": "居住正義",
                    "content": "居住正義 居住正義",
                    "endorsement_count": 5,
                },
            ],
            [],
            config=config,
            weights=load_topic_weights(CONFIG_DIR / "youth_topic_weights.json"),
            tokenizer=lambda text: text.split(),
        )

        self.assertNotIn("years", result)
        self.assertEqual(result["analysis_id"], "youth-keyword-frequency")
        self.assertEqual(result["normalization"], "global_max")
        self.assertEqual(result["source_periods"]["join_proposals"], ["109", "114"])
        terms = {item["term"]: item for item in result["keywords"]}
        self.assertEqual(terms["居住正義"]["term_frequency"], 5)
        self.assertEqual(terms["居住正義"]["document_count"], 2)
        self.assertEqual(terms["居住正義"]["join_mentions"], 2)
        self.assertAlmostEqual(
            terms["居住正義"]["join_support_score"],
            2 + __import__("math").log1p(3) + __import__("math").log1p(5),
            places=6,
        )

    def test_document_ids_are_namespaced_by_source(self):
        config = KeywordConfig(
            version="test",
            top_n=10,
            min_document_frequency=2,
            min_token_length=2,
            max_token_length=12,
            userdict_path=None,
            stopwords_path=None,
        )
        result = calculate_youth_keyword_frequency(
            [
                {
                    "source_record_id": "same-id",
                    "year_roc": "109",
                    "youth_topic_proxy": True,
                    "title": "居住正義",
                    "content": "租金",
                    "endorsement_count": 1,
                }
            ],
            [
                {
                    "source_record_id": "same-id",
                    "year_roc": "114",
                    "source_text": "租金",
                }
            ],
            config=config,
            weights=load_topic_weights(CONFIG_DIR / "youth_topic_weights.json"),
            tokenizer=lambda text: text.split(),
        )

        keyword = next(item for item in result["keywords"] if item["term"] == "租金")
        self.assertEqual(keyword["document_count"], 2)

    def test_policy_compounds_are_protected_from_jieba_splitting(self):
        config = load_keyword_config(CONFIG_DIR / "youth_keyword_config.json")
        result = calculate_youth_keyword_frequency(
            [
                {
                    "source_record_id": "join-policy-1",
                    "year_roc": "109",
                    "youth_topic_proxy": True,
                    "title": "居住正義",
                    "content": "居住正義",
                },
                {
                    "source_record_id": "join-policy-2",
                    "year_roc": "114",
                    "youth_topic_proxy": True,
                    "title": "居住正義",
                    "content": "居住正義",
                },
            ],
            [],
            config=config,
            weights=load_topic_weights(CONFIG_DIR / "youth_topic_weights.json"),
        )

        terms = {item["term"] for item in result["keywords"]}
        self.assertIn("居住正義", terms)

    def test_removes_role_context_names_but_keeps_policy_terms(self):
        config = KeywordConfig(
            version="test",
            top_n=20,
            min_document_frequency=1,
            min_token_length=2,
            max_token_length=12,
            userdict_path=None,
            stopwords_path=None,
            cleaning_rules_path=CONFIG_DIR / "youth_keyword_cleaning.json",
            policy_terms=(),
            policy_anchors=(),
        )
        result = calculate_youth_keyword_frequency(
            [],
            [
                {
                    "source_record_id": "minute-1",
                    "year_roc": "114",
                    "source_text": (
                        "主席：劉副市長和然\n"
                        "紀錄：余帛燦\n"
                        "葉書妤委員\n"
                        "經發局代表王美惠\n"
                        "青年創業代表王美惠\n"
                        "租金 心理健康 居住正義 青年創業"
                    ),
                }
            ],
            config=config,
            weights=load_topic_weights(CONFIG_DIR / "youth_topic_weights.json"),
            tokenizer=lambda text: text.split(),
        )

        terms = {item["term"] for item in result["keywords"]}
        for noise in (
            "劉副市長和然",
            "余帛燦",
            "葉書妤",
            "王美惠",
            "主席",
            "紀錄",
            "委員",
            "代表",
        ):
            self.assertFalse(any(noise in term for term in terms), noise)
        self.assertTrue({"租金", "心理健康", "居住正義", "青年創業"}.issubset(terms))
        self.assertEqual(
            next(item for item in result["keywords"] if item["term"] == "青年創業")[
                "term_frequency"
            ],
            2,
        )

    def test_removes_document_metadata_and_configured_filler_words(self):
        config = KeywordConfig(
            version="test",
            top_n=20,
            min_document_frequency=1,
            min_token_length=2,
            max_token_length=20,
            userdict_path=None,
            stopwords_path=CONFIG_DIR / "youth_keyword_stopwords.txt",
            policy_terms=(),
            policy_anchors=(),
        )
        result = calculate_youth_keyword_frequency(
            [],
            [
                {
                    "source_record_id": "minute-1",
                    "year_roc": "114",
                    "source_text": (
                        "居住正義 https://example.com/p/1 someone@example.com "
                        "民國114年3月 第12頁 案號A-1234 02-1234-5678 "
                        "以及 一個 應該 能夠"
                    ),
                }
            ],
            config=config,
            weights=load_topic_weights(CONFIG_DIR / "youth_topic_weights.json"),
            tokenizer=lambda text: text.split(),
        )

        terms = {item["term"] for item in result["keywords"]}
        self.assertIn("居住正義", terms)
        for noise in (
            "https",
            "example",
            "someone",
            "民國114年3月",
            "第12頁",
            "案號a1234",
            "以及",
            "一個",
            "應該",
            "能夠",
        ):
            self.assertFalse(any(noise in term for term in terms), noise)

    def test_keeps_unknown_period_text_and_preserves_input_records(self):
        config = KeywordConfig(
            version="test",
            top_n=10,
            min_document_frequency=1,
            min_token_length=2,
            max_token_length=12,
            userdict_path=None,
            stopwords_path=None,
            policy_terms=("心理健康",),
            policy_anchors=("心理",),
        )
        join_rows = [
            {
                "source_record_id": "join-unknown-period",
                "youth_topic_proxy": True,
                "title": "心理健康",
                "content": "",
                "endorsement_count": 0,
            }
        ]
        original_join_rows = deepcopy(join_rows)
        result = calculate_youth_keyword_frequency(
            join_rows,
            [],
            config=config,
            weights=load_topic_weights(CONFIG_DIR / "youth_topic_weights.json"),
            tokenizer=lambda text: text.split(),
        )

        self.assertIn("心理健康", {item["term"] for item in result["keywords"]})
        self.assertEqual(result["_quality"]["unknown_period_rows"], 1)
        self.assertEqual(result["source_periods"]["join_proposals"], [])
        self.assertEqual(join_rows, original_join_rows)

    def test_generic_words_are_excluded_even_with_topic_evidence(self):
        config = load_keyword_config(CONFIG_DIR / "youth_keyword_config.json")
        result = calculate_youth_keyword_frequency(
            [
                {
                    "source_record_id": "join-1",
                    "year_roc": "109",
                    "youth_topic_proxy": True,
                    "title": "居住正義",
                    "content": "問題 工作 政策 服務",
                    "endorsement_count": 1,
                }
            ],
            [
                {
                    "source_record_id": "minute-1",
                    "year_roc": "114",
                    "source_text": "問題 工作 政策 服務",
                    "topic_text": "居住正義",
                }
            ],
            config=config,
            weights=load_topic_weights(CONFIG_DIR / "youth_topic_weights.json"),
            tokenizer=lambda text: text.split(),
        )

        terms = {item["term"] for item in result["keywords"]}
        self.assertNotIn("問題", terms)
        self.assertNotIn("工作", terms)
        self.assertNotIn("政策", terms)
        self.assertNotIn("服務", terms)

    def test_policy_selection_excludes_high_frequency_generic_terms(self):
        config = load_keyword_config(CONFIG_DIR / "youth_keyword_config.json")
        result = calculate_youth_keyword_frequency(
            [
                {
                    "source_record_id": "join-1",
                    "year_roc": "109",
                    "youth_topic_proxy": True,
                    "title": "問題 工作 合作 活動 社會住宅",
                    "content": "問題 工作 合作 活動 社會住宅",
                },
                {
                    "source_record_id": "join-2",
                    "year_roc": "114",
                    "youth_topic_proxy": True,
                    "title": "問題 工作 合作 活動 社會住宅",
                    "content": "問題 工作 合作 活動 社會住宅",
                },
            ],
            [
                {
                    "source_record_id": "minute-1",
                    "year_roc": "110",
                    "topic_text": "問題 工作",
                    "source_text": "問題 工作 合作 活動 心理健康",
                },
                {
                    "source_record_id": "minute-2",
                    "year_roc": "112",
                    "topic_text": "問題 工作",
                    "source_text": "問題 工作 合作 活動 心理健康",
                },
            ],
            config=config,
            weights=load_topic_weights(CONFIG_DIR / "youth_topic_weights.json"),
            tokenizer=lambda text: text.split(),
        )

        terms = {item["term"] for item in result["keywords"]}
        self.assertTrue({"社會住宅", "心理健康"}.issubset(terms))
        for generic in ("問題", "工作", "合作", "活動"):
            self.assertNotIn(generic, terms)

    def test_policy_selection_limits_to_23_and_normalizes_selected_weights(self):
        policy_terms = tuple(
            f"議題{character}"
            for character in (
                "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥天地人"
            )
        )
        config = KeywordConfig(
            version="test",
            top_n=23,
            min_document_frequency=1,
            min_token_length=2,
            max_token_length=12,
            userdict_path=None,
            stopwords_path=None,
            policy_terms=policy_terms,
            policy_anchors=(),
        )
        result = calculate_youth_keyword_frequency(
            [
                {
                    "source_record_id": f"join-{index}",
                    "year_roc": "114",
                    "youth_topic_proxy": True,
                    "title": term,
                    "content": " ".join([term] * (index + 1)),
                    "endorsement_count": index,
                }
                for index, term in enumerate(policy_terms)
            ],
            [],
            config=config,
            weights=load_topic_weights(CONFIG_DIR / "youth_topic_weights.json"),
            tokenizer=lambda text: text.split(),
        )

        self.assertEqual(len(result["keywords"]), 23)
        self.assertTrue(all(item["document_count"] >= 1 for item in result["keywords"]))
        weights = [item["weight"] for item in result["keywords"]]
        self.assertEqual(min(weights), 1)
        self.assertEqual(max(weights), 5)


    def test_extracts_terms_outside_fixed_topic_labels(self):
        config = KeywordConfig(
            version="test",
            top_n=10,
            min_document_frequency=1,
            min_token_length=2,
            max_token_length=12,
            userdict_path=None,
            stopwords_path=None,
        )
        result = calculate_youth_keyword_frequency(
            [
                {
                    "source_record_id": "join-1",
                    "year_roc": "114",
                    "youth_topic_proxy": True,
                    "title": "青年租屋 學貸",
                    "content": "租屋 學貸",
                    "endorsement_count": 10,
                }
            ],
            [
                {
                    "source_record_id": "minute-1",
                    "year_roc": "114",
                    "source_text": "心理支持 租屋",
                    "discussion_text": "心理支持",
                    "resolution_text": "租屋",
                    "resolved": True,
                    "escalated": False,
                }
            ],
            config=config,
            weights=load_topic_weights(CONFIG_DIR / "youth_topic_weights.json"),
            tokenizer=lambda text: text.split(),
        )

        terms = {item["term"]: item for item in result["keywords"]}
        self.assertIn("租屋", terms)
        self.assertIn("學貸", terms)
        self.assertIn("心理支持", terms)
        self.assertEqual(terms["租屋"]["document_count"], 2)
        self.assertEqual(terms["租屋"]["join_mentions"], 1)
        self.assertEqual(terms["租屋"]["minutes_mentions"], 1)
        self.assertTrue(terms["租屋"]["resolved"])
        self.assertFalse(terms["心理支持"]["resolved"])

    def test_resolution_signals_apply_only_to_terms_in_resolution_text(self):
        config = KeywordConfig(
            version="test",
            top_n=10,
            min_document_frequency=1,
            min_token_length=2,
            max_token_length=12,
            userdict_path=None,
            stopwords_path=None,
            policy_terms=("青年創業", "社會住宅"),
            policy_anchors=("青年", "住宅"),
        )
        result = calculate_youth_keyword_frequency(
            [],
            [
                {
                    "source_record_id": "minute-1",
                    "year_roc": "114",
                    "source_text": "青年創業 社會住宅 提請市議會",
                    "topic_text": "青年創業",
                    "discussion_text": "青年創業",
                    "resolution_text": "社會住宅 提請市議會",
                    "resolved": True,
                    "escalated": True,
                }
            ],
            config=config,
            weights=load_topic_weights(CONFIG_DIR / "youth_topic_weights.json"),
            tokenizer=lambda text: text.split(),
        )

        terms = {item["term"]: item for item in result["keywords"]}
        self.assertEqual(result["calculation_version"], "7")
        self.assertFalse(terms["青年創業"]["resolved"])
        self.assertFalse(terms["青年創業"]["escalated"])
        self.assertTrue(terms["社會住宅"]["resolved"])
        self.assertTrue(terms["社會住宅"]["escalated"])
        self.assertGreater(terms["社會住宅"]["raw_score"], terms["青年創業"]["raw_score"])

    def test_dynamic_candidate_requires_policy_compound_or_policy_term(self):
        config = load_keyword_config(CONFIG_DIR / "youth_keyword_config.json")
        result = calculate_youth_keyword_frequency(
            [],
            [
                {
                    "source_record_id": "minute-1",
                    "year_roc": "114",
                    "source_text": "階段 青年共居 交通局",
                    "topic_text": "階段 青年共居 交通局",
                    "discussion_text": "階段 青年共居 交通局",
                    "resolution_text": "",
                },
                {
                    "source_record_id": "minute-2",
                    "year_roc": "114",
                    "source_text": "階段 青年共居 交通局",
                    "topic_text": "階段 青年共居 交通局",
                    "discussion_text": "階段 青年共居 交通局",
                    "resolution_text": "",
                },
            ],
            config=config,
            weights=load_topic_weights(CONFIG_DIR / "youth_topic_weights.json"),
            tokenizer=lambda text: text.split(),
        )

        terms = {item["term"]: item for item in result["keywords"]}
        self.assertIn("青年共居", terms)
        self.assertNotIn("階段", terms)
        self.assertNotIn("交通局", terms)
        self.assertGreater(terms["青年共居"]["policy_relevance"], 0)

    def test_unknown_compound_with_source_evidence_is_not_blocked_by_policy_dictionary(self):
        config = KeywordConfig(
            version="test",
            top_n=10,
            min_document_frequency=2,
            min_token_length=2,
            max_token_length=12,
            userdict_path=None,
            stopwords_path=None,
            policy_terms=("青年創業",),
            policy_anchors=("青年",),
        )
        result = calculate_youth_keyword_frequency(
            [
                {
                    "source_record_id": "join-1",
                    "year_roc": "114",
                    "youth_topic_proxy": True,
                    "title": "創意市集",
                    "content": "創意市集",
                    "endorsement_count": 1,
                },
                {
                    "source_record_id": "join-2",
                    "year_roc": "114",
                    "youth_topic_proxy": True,
                    "title": "創意市集",
                    "content": "創意市集",
                    "endorsement_count": 1,
                },
            ],
            [],
            config=config,
            weights=load_topic_weights(CONFIG_DIR / "youth_topic_weights.json"),
            tokenizer=lambda text: text.split(),
        )

        terms = {item["term"]: item for item in result["keywords"]}
        self.assertIn("創意市集", terms)
        self.assertEqual(terms["創意市集"]["policy_relevance"], 0.5)

    def test_term_frequency_contributes_to_raw_score(self):
        config = KeywordConfig(
            version="test",
            top_n=10,
            min_document_frequency=2,
            min_token_length=2,
            max_token_length=12,
            userdict_path=None,
            stopwords_path=None,
            policy_terms=("詞甲", "詞乙"),
            policy_anchors=(),
        )
        result = calculate_youth_keyword_frequency(
            [],
            [
                {
                    "source_record_id": "minute-1",
                    "year_roc": "114",
                    "source_text": "詞甲 詞甲 詞甲 詞乙",
                    "topic_text": "詞甲 詞乙",
                    "discussion_text": "詞甲 詞甲 詞甲 詞乙",
                    "resolution_text": "",
                },
                {
                    "source_record_id": "minute-2",
                    "year_roc": "114",
                    "source_text": "詞甲 詞乙",
                    "topic_text": "詞甲 詞乙",
                    "discussion_text": "詞甲 詞乙",
                    "resolution_text": "",
                },
            ],
            config=config,
            weights=load_topic_weights(CONFIG_DIR / "youth_topic_weights.json"),
            tokenizer=lambda text: text.split(),
        )

        terms = {item["term"]: item for item in result["keywords"]}
        self.assertGreater(terms["詞甲"]["term_frequency"], terms["詞乙"]["term_frequency"])
        self.assertGreater(terms["詞甲"]["raw_score"], terms["詞乙"]["raw_score"])

    def test_repeated_body_word_without_topic_or_cross_source_evidence_is_excluded(self):
        config = KeywordConfig(
            version="test",
            top_n=10,
            min_document_frequency=2,
            min_token_length=2,
            max_token_length=12,
            userdict_path=None,
            stopwords_path=None,
            policy_terms=("青年創業",),
            policy_anchors=("青年",),
        )
        result = calculate_youth_keyword_frequency(
            [],
            [
                {
                    "source_record_id": "minute-1",
                    "year_roc": "114",
                    "source_text": "高風險 高風險 高風險 一般討論",
                    "topic_text": "一般討論",
                    "discussion_text": "高風險 高風險 高風險 一般討論",
                    "resolution_text": "",
                },
                {
                    "source_record_id": "minute-2",
                    "year_roc": "114",
                    "source_text": "高風險 高風險 高風險 一般討論",
                    "topic_text": "一般討論",
                    "discussion_text": "高風險 高風險 高風險 一般討論",
                    "resolution_text": "",
                },
            ],
            config=config,
            weights=load_topic_weights(CONFIG_DIR / "youth_topic_weights.json"),
            tokenizer=lambda text: text.split(),
        )

        terms = {item["term"] for item in result["keywords"]}
        self.assertNotIn("高風險", terms)

    def test_low_frequency_cross_source_word_without_topic_evidence_is_excluded(self):
        config = KeywordConfig(
            version="test",
            top_n=10,
            min_document_frequency=2,
            min_token_length=2,
            max_token_length=12,
            userdict_path=None,
            stopwords_path=None,
            policy_terms=("青年創業",),
            policy_anchors=("青年",),
        )
        result = calculate_youth_keyword_frequency(
            [
                {
                    "source_record_id": "join-1",
                    "year_roc": "114",
                    "youth_topic_proxy": True,
                    "title": "一般議題",
                    "content": "高風險",
                    "endorsement_count": 1,
                }
            ],
            [
                {
                    "source_record_id": "minute-1",
                    "year_roc": "114",
                    "source_text": "高風險",
                    "topic_text": "一般議題",
                    "discussion_text": "高風險",
                    "resolution_text": "",
                }
            ],
            config=config,
            weights=load_topic_weights(CONFIG_DIR / "youth_topic_weights.json"),
            tokenizer=lambda text: text.split(),
        )

        terms = {item["term"] for item in result["keywords"]}
        self.assertNotIn("高風險", terms)

    def test_short_dynamic_policy_term_needs_cross_source_policy_evidence(self):
        config = KeywordConfig(
            version="test",
            top_n=10,
            min_document_frequency=2,
            min_token_length=2,
            max_token_length=12,
            userdict_path=None,
            stopwords_path=None,
            policy_terms=("青年創業",),
            policy_anchors=("就業",),
            min_dynamic_frequency=3,
        )
        result = calculate_youth_keyword_frequency(
            [
                {
                    "source_record_id": "join-1",
                    "year_roc": "114",
                    "youth_topic_proxy": True,
                    "title": "一般議題",
                    "content": "就業 就業",
                    "endorsement_count": 1,
                }
            ],
            [
                {
                    "source_record_id": "minute-1",
                    "year_roc": "114",
                    "source_text": "就業",
                    "topic_text": "一般議題",
                    "discussion_text": "就業",
                    "resolution_text": "",
                }
            ],
            config=config,
            weights=load_topic_weights(CONFIG_DIR / "youth_topic_weights.json"),
            tokenizer=lambda text: text.split(),
        )

        terms = {item["term"]: item for item in result["keywords"]}
        self.assertIn("就業", terms)

    def test_applies_document_frequency_and_top_n(self):
        config = KeywordConfig(
            version="test",
            top_n=1,
            min_document_frequency=2,
            min_token_length=2,
            max_token_length=12,
            userdict_path=None,
            stopwords_path=None,
        )
        result = calculate_youth_keyword_frequency(
            [
                {
                    "source_record_id": "join-1",
                    "year_roc": "114",
                    "youth_topic_proxy": True,
                    "title": "租屋 學貸",
                    "content": "",
                    "endorsement_count": 0,
                },
                {
                    "source_record_id": "join-2",
                    "year_roc": "114",
                    "youth_topic_proxy": True,
                    "title": "租屋",
                    "content": "",
                    "endorsement_count": 0,
                },
            ],
            [],
            config=config,
            weights=load_topic_weights(CONFIG_DIR / "youth_topic_weights.json"),
            tokenizer=lambda text: text.split(),
        )

        keywords = result["keywords"]
        self.assertEqual(len(keywords), 1)
        self.assertEqual(keywords[0]["term"], "租屋")
        self.assertEqual(keywords[0]["document_count"], 2)

    def test_excludes_names_attached_to_meeting_roles(self):
        config = KeywordConfig(
            version="test",
            top_n=10,
            min_document_frequency=1,
            min_token_length=2,
            max_token_length=12,
            userdict_path=None,
            stopwords_path=None,
        )
        result = calculate_youth_keyword_frequency(
            [],
            [
                {
                    "source_record_id": "minute-1",
                    "year_roc": "114",
                    "source_text": "提案委員：楊鈞程 租屋政策",
                }
            ],
            config=config,
            weights=load_topic_weights(CONFIG_DIR / "youth_topic_weights.json"),
            tokenizer=lambda text: re.findall(r"[\u3400-\u9fff]+", text),
        )

        terms = {item["term"] for item in result["keywords"]}
        self.assertNotIn("楊鈞程", terms)
        self.assertIn("租屋政策", terms)

    def test_filters_administrative_terms_and_prioritizes_policy_phrases(self):
        config = load_keyword_config(CONFIG_DIR / "youth_keyword_config.json")
        result = calculate_youth_keyword_frequency(
            [],
            [
                {
                    "source_record_id": "minute-1",
                    "year_roc": "114",
                    "source_text": "平台 參考 資源 教育 政策 參與 公共 一般流程 過渡性教育",
                    "topic_text": "過渡性教育",
                },
                {
                    "source_record_id": "minute-2",
                    "year_roc": "114",
                    "source_text": "平台 參考 資源 教育 政策 參與 公共 一般流程 過渡性教育",
                    "topic_text": "過渡性教育",
                },
            ],
            config=config,
            weights=load_topic_weights(CONFIG_DIR / "youth_topic_weights.json"),
            tokenizer=lambda text: text.split(),
        )

        keywords = result["keywords"]
        terms = {item["term"]: item for item in keywords}
        self.assertNotIn("平台", terms)
        self.assertNotIn("參考", terms)
        self.assertNotIn("資源", terms)
        self.assertNotIn("教育", terms)
        self.assertNotIn("政策", terms)
        self.assertNotIn("參與", terms)
        self.assertNotIn("公共", terms)
        self.assertNotIn("一般流程", terms)
        self.assertIn("過渡性教育", terms)
        self.assertGreater(terms["過渡性教育"]["policy_relevance"], 0)
        self.assertGreater(terms["過渡性教育"]["topic_mentions"], 0)

    def test_default_tokenizer_excludes_procedural_verbs(self):
        config = load_keyword_config(CONFIG_DIR / "youth_keyword_config.json")
        result = calculate_youth_keyword_frequency(
            [],
            [
                {
                    "source_record_id": "minute-1",
                    "year_roc": "114",
                    "source_text": "過渡性教育 同意 研議",
                },
                {
                    "source_record_id": "minute-2",
                    "year_roc": "114",
                    "source_text": "過渡性教育 同意 研議",
                },
            ],
            config=config,
            weights=load_topic_weights(CONFIG_DIR / "youth_topic_weights.json"),
        )

        terms = {item["term"] for item in result["keywords"]}
        self.assertIn("過渡性教育", terms)
        self.assertNotIn("同意", terms)
        self.assertNotIn("研議", terms)


if __name__ == "__main__":
    unittest.main()
