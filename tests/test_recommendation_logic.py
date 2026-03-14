import unittest
from types import SimpleNamespace

from main import (
    UserRequest,
    build_fallback_recommendations,
    build_why_this,
    normalize_title,
    select_recommendations,
)


def make_prefs():
    return SimpleNamespace(
        favorite_categories="аниме, приключения",
        disliked_categories="",
        favorite_platforms="",
        preferred_language="ru",
        age_rating="any",
        discovery_mode="balanced",
        onboarding_completed=True,
    )


class RecommendationLogicTests(unittest.TestCase):
    def test_select_recommendations_avoids_disliked_and_recent(self):
        candidates = [
            {"title": "Наруто", "year_genre": "2002, сёнэн", "description": "A", "category": "Аниме", "why_this": "x"},
            {"title": "Атака титанов", "year_genre": "2013, экшен", "description": "B", "category": "Аниме", "why_this": "y"},
            {"title": "Берсерк", "year_genre": "1997, драма", "description": "C", "category": "Аниме", "why_this": "z"},
            {"title": "Ковбой Бибоп", "year_genre": "1998, sci-fi", "description": "D", "category": "Аниме", "why_this": "w"},
        ]
        feedback = {
            "disliked_titles": {normalize_title("Берсерк")},
            "watched_titles": set(),
            "preferred_categories": [],
            "avoid_categories": [],
        }
        selected = select_recommendations(candidates, recent_titles=["Наруто"], feedback_summary=feedback, limit=3)
        titles = [item["title"] for item in selected]
        self.assertNotIn("Берсерк", titles)
        self.assertIn("Атака титанов", titles)
        self.assertLessEqual(len(selected), 3)

    def test_build_fallback_recommendations_returns_three_unique(self):
        request = UserRequest(query="аниме на вечер", session_id="s1")
        feedback = {
            "disliked_titles": set(),
            "watched_titles": set(),
            "preferred_categories": [],
            "avoid_categories": [],
        }
        selected = build_fallback_recommendations(
            request=request,
            prefs=make_prefs(),
            recent_titles=["Охотник x Охотник"],
            feedback_summary=feedback,
            limit=3,
        )
        self.assertEqual(len(selected), 3)
        self.assertEqual(len({item["title"] for item in selected}), 3)

    def test_build_why_this_contains_context(self):
        request = UserRequest(
            query="что посмотреть",
            session_id="s1",
            mood="relax",
            company="friends",
            time_minutes=45,
        )
        reason = build_why_this({"title": "Аркейн", "category": "Сериал"}, request, make_prefs())
        self.assertIn("настроением", reason)
        self.assertIn("45 минут", reason)
        self.assertTrue(reason.endswith("."))


if __name__ == "__main__":
    unittest.main()
