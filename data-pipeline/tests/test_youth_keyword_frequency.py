import sys
import re
import unittest
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

        year = result["years"][0]
        terms = {item["term"]: item for item in year["keywords"]}
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

        terms = {item["term"]: item for item in result["years"][0]["keywords"]}
        self.assertEqual(result["calculation_version"], "5")
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

        terms = {item["term"]: item for item in result["years"][0]["keywords"]}
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

        terms = {item["term"]: item for item in result["years"][0]["keywords"]}
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

        terms = {item["term"]: item for item in result["years"][0]["keywords"]}
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

        terms = {item["term"] for item in result["years"][0]["keywords"]}
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

        terms = {item["term"] for item in result["years"][0]["keywords"]}
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

        terms = {item["term"]: item for item in result["years"][0]["keywords"]}
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

        keywords = result["years"][0]["keywords"]
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

        terms = {item["term"] for item in result["years"][0]["keywords"]}
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

        keywords = result["years"][0]["keywords"]
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

        terms = {item["term"] for item in result["years"][0]["keywords"]}
        self.assertIn("過渡性教育", terms)
        self.assertNotIn("同意", terms)
        self.assertNotIn("研議", terms)


if __name__ == "__main__":
    unittest.main()
