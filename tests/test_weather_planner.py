import unittest

from weather_planner import assess_weather_readiness


class WeatherPlannerTests(unittest.TestCase):
    def test_clear_mild_forecast_has_high_readiness(self):
        result = assess_weather_readiness(
            {
                "temperature_max": 24,
                "precipitation_probability": 5,
                "wind_speed": 8,
                "weather_code": 1,
            },
            "Football",
        )

        self.assertEqual(result["readiness_score"], 96)
        self.assertEqual(result["risk_level"], "Low")
        self.assertEqual(len(result["recommendations"]), 2)

    def test_cricket_rain_and_thunderstorm_produce_actionable_severe_risk(self):
        result = assess_weather_readiness(
            {
                "temperature_max": 28,
                "precipitation_probability": 90,
                "wind_speed": 45,
                "weather_code": 95,
            },
            "Cricket",
        )

        self.assertEqual(result["risk_level"], "Severe")
        self.assertLessEqual(result["readiness_score"], 40)
        self.assertTrue(
            any("lightning" in recommendation for recommendation in result["recommendations"])
        )
        self.assertTrue(
            any("pitch covers" in recommendation for recommendation in result["recommendations"])
        )

    def test_sport_sensitivity_changes_rain_impact(self):
        forecast = {
            "temperature_max": 25,
            "precipitation_probability": 60,
            "wind_speed": 10,
            "weather_code": 61,
        }

        cricket = assess_weather_readiness(forecast, "Cricket")
        basketball = assess_weather_readiness(forecast, "Basketball")

        self.assertLess(cricket["readiness_score"], basketball["readiness_score"])
        self.assertIn("Cricket", cricket["risk_factors"][0])

    def test_rejects_unknown_sports_and_invalid_forecast_values(self):
        with self.assertRaisesRegex(ValueError, "not configured"):
            assess_weather_readiness({}, "Swimming")
        with self.assertRaisesRegex(ValueError, "valid range"):
            assess_weather_readiness(
                {
                    "temperature_max": 24,
                    "precipitation_probability": 101,
                    "wind_speed": 8,
                    "weather_code": 1,
                },
                "Football",
            )


if __name__ == "__main__":
    unittest.main()
