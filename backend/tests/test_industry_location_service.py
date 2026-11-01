import asyncio
import unittest

from services.industry_location_service import load_industry_locations, search_industry_locations


class IndustryLocationServiceTests(unittest.TestCase):
    def test_catalogue_loads_expected_shape(self):
        locations = load_industry_locations()
        self.assertGreater(len(locations), 100)
        self.assertTrue({"name", "state", "district", "sector", "land_available_hectares"}.issubset(locations[0]))

    def test_location_query_prioritises_requested_district(self):
        result = asyncio.run(search_industry_locations("textile park in Surat", limit=5, enrich=False))
        self.assertEqual(result["google_places_enrichment"], "not_configured")
        self.assertEqual(len(result["results"]), 5)
        self.assertTrue(all(item["district"].lower() == "surat" for item in result["results"]))
        self.assertTrue(all(item["maps_url"].startswith("https://www.google.com/maps/") for item in result["results"]))


if __name__ == "__main__":
    unittest.main()
