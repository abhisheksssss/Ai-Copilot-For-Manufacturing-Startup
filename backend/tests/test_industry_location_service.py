import asyncio
import os
import sys
import unittest

os.environ["TESTING"] = "1"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.industry_location_service import (
    load_industry_locations,
    search_industry_locations_sync,
    list_all_states,
    detect_user_specified_location,
    get_optimal_location_recommendation,
)


class IndustryLocationServiceTests(unittest.TestCase):
    def test_catalogue_loads_expected_shape(self):
        locations = load_industry_locations()
        self.assertGreater(len(locations), 100)
        self.assertTrue({"name", "state", "district", "sector", "land_available_hectares"}.issubset(locations[0]))

    def test_list_all_states(self):
        states = list_all_states()
        self.assertGreaterEqual(len(states), 30)
        self.assertIn("Maharashtra", states)
        self.assertIn("Gujarat", states)

    def test_detect_user_specified_location(self):
        loc1 = detect_user_specified_location("Textile park in Surat")
        self.assertIsNotNone(loc1)
        self.assertEqual(loc1["district"], "Surat")
        self.assertEqual(loc1["state"], "Gujarat")

        loc2 = detect_user_specified_location("I want to start a 500 units/day EV battery plant with 25 workers")
        self.assertIsNone(loc2)

    def test_optimal_location_recommendation_ev_battery(self):
        rec = get_optimal_location_recommendation("EV lithium-ion battery pack assembly plant")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["recommended_state"], "Maharashtra")
        self.assertEqual(rec["recommended_district"], "Pune")
        self.assertIn("Chakan", rec["recommended_cluster"])
        self.assertGreaterEqual(rec["suitability_score"], 90)
        self.assertIn("supply_chain_ecosystem", rec["key_advantages"])
        self.assertIn("state_subsidies_policy", rec["key_advantages"])
        self.assertIn("logistics_connectivity", rec["key_advantages"])
        self.assertIn("spcb_clearance_siting", rec["key_advantages"])
        self.assertIn("skilled_workforce", rec["key_advantages"])

    def test_location_query_prioritises_requested_district(self):
        result = search_industry_locations_sync("textile park in Surat", limit=5)
        self.assertEqual(result["google_places_enrichment"], "not_configured")
        self.assertEqual(len(result["results"]), 5)
        self.assertTrue(all(item["district"].lower() == "surat" for item in result["results"]))
        self.assertTrue(all(item["maps_url"].startswith("https://www.google.com/maps/") for item in result["results"]))
        self.assertEqual(result["user_specified_location"], "Surat, Gujarat")
        self.assertIsNone(result["recommendation"])

    def test_unspecified_query_attaches_recommendation(self):
        result = search_industry_locations_sync(
            "500 units/day EV battery pack assembly plant with 25 workers",
            limit=3
        )
        self.assertIsNone(result["user_specified_location"])
        self.assertIsNotNone(result["recommendation"])
        self.assertEqual(result["recommendation"]["recommended_state"], "Maharashtra")
        self.assertGreater(len(result["results"]), 0)


if __name__ == "__main__":
    unittest.main()
