from datetime import date, datetime, time, timedelta
from itertools import combinations
from math import ceil, log2


def build_matchups(participants, competition_format):
    cleaned = [participant.strip() for participant in participants if participant.strip()]
    if len(cleaned) < 2:
        raise ValueError("Enter at least two competitors.")
    if len({participant.casefold() for participant in cleaned}) != len(cleaned):
        raise ValueError("Competitor names must be unique.")

    matchups = []
    match_number = 1
    if competition_format == "Round-robin":
        rotation = cleaned + ([None] if len(cleaned) % 2 else [])
        for round_number in range(1, len(rotation)):
            midpoint = len(rotation) // 2
            for index in range(midpoint):
                first = rotation[index]
                second = rotation[-(index + 1)]
                if first is None or second is None:
                    continue
                if round_number % 2 == 0:
                    first, second = second, first
                matchups.append(
                    {
                        "match_number": match_number,
                        "round_number": round_number,
                        "participant_a": first,
                        "participant_b": second,
                    }
                )
                match_number += 1
            rotation = [rotation[0], rotation[-1], *rotation[1:-1]]
        return matchups

    if competition_format != "Knockout":
        raise ValueError("Choose Round-robin or Knockout.")

    bracket_size = 2 ** ceil(log2(len(cleaned)))
    entrants = cleaned + [None] * (bracket_size - len(cleaned))
    round_number = 1
    while len(entrants) > 1:
        advancing = []
        for index in range(0, len(entrants), 2):
            first, second = entrants[index:index + 2]
            if first is None:
                advancing.append(second)
            elif second is None:
                advancing.append(first)
            else:
                matchups.append(
                    {
                        "match_number": match_number,
                        "round_number": round_number,
                        "participant_a": first,
                        "participant_b": second,
                    }
                )
                advancing.append(f"Winner of Match {match_number}")
                match_number += 1
        entrants = advancing
        round_number += 1
    return matchups


def schedule_matchups(matchups, venues, event_date, start_time, end_time,
                      match_duration_minutes, rest_minutes):
    venue_names = [venue.strip() for venue in venues if venue.strip()]
    if not venue_names:
        raise ValueError("Enter at least one available venue.")
    if len({venue.casefold() for venue in venue_names}) != len(venue_names):
        raise ValueError("Venue names must be unique.")
    if end_time <= start_time:
        raise ValueError("The finish time must be later than the start time.")
    if match_duration_minutes < 1:
        raise ValueError("Match duration must be at least one minute.")
    if rest_minutes < 0:
        raise ValueError("Rest time cannot be negative.")

    slot_interval = timedelta(minutes=match_duration_minutes + rest_minutes)
    match_duration = timedelta(minutes=match_duration_minutes)
    current_start = datetime.combine(event_date, start_time)
    window_end = datetime.combine(event_date, end_time)
    if event_date == date.today() and current_start <= datetime.now():
        raise ValueError("The first match start time must be later than the current time.")
    round_groups = {}
    for matchup in matchups:
        round_groups.setdefault(matchup["round_number"], []).append(matchup)

    scheduled = []
    conflicts = []
    for round_number in sorted(round_groups):
        round_matches = round_groups[round_number]
        for batch_start in range(0, len(round_matches), len(venue_names)):
            batch = round_matches[batch_start:batch_start + len(venue_names)]
            if current_start + match_duration > window_end:
                for matchup in batch:
                    conflicts.append(
                        {
                            **matchup,
                            "venue": "",
                            "event_date": event_date.isoformat(),
                            "start_time": "",
                            "end_time": "",
                            "status": "Unscheduled",
                            "conflict_reason": (
                                "No remaining slot fits the match duration. "
                                "Extend the event window or reduce match/rest time."
                            ),
                        }
                    )
                continue

            end_time_at = current_start + match_duration
            for index, matchup in enumerate(batch):
                scheduled.append(
                    {
                        **matchup,
                        "venue": venue_names[(batch_start + index) % len(venue_names)],
                        "event_date": event_date.isoformat(),
                        "start_time": current_start.strftime("%H:%M"),
                        "end_time": end_time_at.strftime("%H:%M"),
                        "status": "Scheduled",
                        "conflict_reason": "",
                    }
                )
            current_start += slot_interval

    return scheduled, conflicts
