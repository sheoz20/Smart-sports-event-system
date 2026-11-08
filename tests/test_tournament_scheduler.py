import unittest
from datetime import date, time, timedelta

from tournament_scheduler import build_matchups, schedule_matchups


class TournamentSchedulerTests(unittest.TestCase):
    def test_round_robin_pairs_each_competitor_once(self):
        names = ["Falcons", "Tigers", "Eagles", "Sharks"]

        matchups = build_matchups(names, "Round-robin")
        pairs = {
            frozenset((match["participant_a"], match["participant_b"]))
            for match in matchups
        }

        self.assertEqual(len(matchups), 6)
        self.assertEqual(len(pairs), 6)
        for round_number in {match["round_number"] for match in matchups}:
            round_names = [
                name
                for match in matchups
                if match["round_number"] == round_number
                for name in (match["participant_a"], match["participant_b"])
            ]
            self.assertEqual(len(round_names), len(set(round_names)))

    def test_round_robin_with_odd_competitor_count_has_bye(self):
        matchups = build_matchups(["A", "B", "C"], "Round-robin")

        self.assertEqual(len(matchups), 3)
        self.assertEqual(
            {name for match in matchups for name in (match["participant_a"], match["participant_b"])},
            {"A", "B", "C"},
        )

    def test_knockout_advances_byes_and_builds_winner_placeholders(self):
        matchups = build_matchups(["A", "B", "C", "D", "E"], "Knockout")

        self.assertEqual(len(matchups), 4)
        self.assertEqual(sorted({match["round_number"] for match in matchups}), [1, 2, 3])
        self.assertTrue(
            any(
                participant.startswith("Winner of Match ")
                for match in matchups
                for participant in (match["participant_a"], match["participant_b"])
            )
        )

    def test_parallel_fixtures_use_distinct_venues_and_respect_rest_slots(self):
        event_date = date.today() + timedelta(days=1)
        matchups = build_matchups(["A", "B", "C", "D"], "Round-robin")

        scheduled, conflicts = schedule_matchups(
            matchups,
            ["Court 1", "Court 2"],
            event_date,
            time(9, 0),
            time(11, 0),
            30,
            15,
        )

        self.assertEqual(len(scheduled), 6)
        self.assertEqual(conflicts, [])
        first_slot = [match for match in scheduled if match["start_time"] == "09:00"]
        self.assertEqual({match["venue"] for match in first_slot}, {"Court 1", "Court 2"})
        self.assertEqual(len(first_slot), 2)

    def test_insufficient_window_returns_explained_conflicts(self):
        event_date = date.today() + timedelta(days=1)
        matchups = build_matchups(["A", "B", "C", "D"], "Round-robin")

        scheduled, conflicts = schedule_matchups(
            matchups,
            ["Main Court"],
            event_date,
            time(9, 0),
            time(10, 0),
            30,
            15,
        )

        self.assertEqual(len(scheduled), 1)
        self.assertEqual(len(conflicts), 5)
        self.assertTrue(all(match["status"] == "Unscheduled" for match in conflicts))
        self.assertTrue(all(match["conflict_reason"] for match in conflicts))

    def test_invalid_duplicate_competitors_and_venues_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "must be unique"):
            build_matchups(["Falcons", "falcons"], "Round-robin")

        matchups = build_matchups(["A", "B"], "Knockout")
        with self.assertRaisesRegex(ValueError, "Venue names must be unique"):
            schedule_matchups(
                matchups,
                ["Court", "court"],
                date.today() + timedelta(days=1),
                time(9, 0),
                time(12, 0),
                30,
                15,
            )


if __name__ == "__main__":
    unittest.main()
