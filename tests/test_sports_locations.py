import unittest

from sports_locations import (
    CHENNAI_AREAS,
    SPORTS_LOCATIONS,
    distance_km,
    filter_locations,
)


class SportsLocationsTests(unittest.TestCase):
    def test_sample_directory_has_requested_ten_sports(self):
        self.assertEqual(len(SPORTS_LOCATIONS), 18)
        self.assertEqual(
            {location.sport for location in SPORTS_LOCATIONS},
            {
                "Badminton",
                "Table Tennis",
                "Chess",
                "Carrom",
                "Basketball (Indoor Court)",
                "Cricket",
                "Football",
                "Volleyball",
                "Hockey",
                "Kabaddi",
            },
        )
        self.assertEqual(sum(location.category == "Indoor" for location in SPORTS_LOCATIONS), 8)
        self.assertEqual(sum(location.category == "Outdoor" for location in SPORTS_LOCATIONS), 10)

    def test_search_matches_venue_name_and_area_case_insensitively(self):
        by_name = filter_locations(query="chess club")
        by_area = filter_locations(query="MARINA")
        punctuation = filter_locations(query="T Nagar")

        self.assertEqual(
            {location.area for location, _ in by_name},
            {"Nungambakkam", "Mahabalipuram"},
        )
        self.assertEqual([location.sport for location, _ in by_area], ["Volleyball"])
        self.assertEqual([location.sport for location, _ in punctuation], ["Table Tennis"])

    def test_search_includes_tambaram_and_chengalpattu_district_areas(self):
        tambaram = filter_locations(query="Tambaram")
        district = filter_locations(query="Chengalpattu")
        selected_place = filter_locations(area="Maraimalai Nagar")

        self.assertEqual([location.area for location, _ in tambaram], ["Tambaram"])
        self.assertEqual(
            [location.area for location, _ in selected_place],
            ["Maraimalai Nagar"],
        )
        self.assertEqual(
            {location.area for location, _ in district},
            {
                "Tambaram",
                "Pallavaram",
                "Vandalur",
                "Guduvanchery",
                "Maraimalai Nagar",
                "Chengalpattu",
                "Mahabalipuram",
                "Kelambakkam",
            },
        )
        self.assertIn("Tambaram", CHENNAI_AREAS)

    def test_category_and_sport_filters_can_be_combined(self):
        results = filter_locations(category="Outdoor", sport="Football")

        self.assertEqual(
            {location.area for location, _ in results},
            {"Egmore", "Guduvanchery"},
        )

    def test_nearby_results_are_sorted_and_limited_to_radius(self):
        center = CHENNAI_AREAS["Chepauk"]
        results = filter_locations(center=center, radius_km=3)

        self.assertTrue(results)
        self.assertEqual(results[0][0].area, "Chepauk")
        self.assertTrue(all(distance is not None and distance <= 3 for _, distance in results))

    def test_distance_is_zero_for_identical_points_and_rejects_negative_radius(self):
        self.assertEqual(distance_km((13.0, 80.0), (13.0, 80.0)), 0)
        with self.assertRaisesRegex(ValueError, "Radius cannot be negative"):
            filter_locations(radius_km=-1)


if __name__ == "__main__":
    unittest.main()
