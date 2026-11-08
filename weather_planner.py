"""Explainable sport-specific planning guidance for outdoor event forecasts."""

from collections.abc import Mapping
from typing import TypedDict


class WeatherAssessment(TypedDict):
    readiness_score: int
    risk_score: int
    risk_level: str
    risk_factors: list[str]
    recommendations: list[str]


_SPORT_SENSITIVITY = {
    "athletics": {"rain": 0.30, "wind": 0.22, "heat": 0.85},
    "basketball": {"rain": 0.22, "wind": 0.20, "heat": 0.78},
    "cricket": {"rain": 0.36, "wind": 0.28, "heat": 0.72},
    "football": {"rain": 0.28, "wind": 0.23, "heat": 0.78},
    "volleyball": {"rain": 0.27, "wind": 0.25, "heat": 0.75},
}
_SEVERE_WEATHER_CODES = {56, 57, 65, 66, 67, 75, 82, 86, 95, 96, 99}
_SNOW_OR_ICE_CODES = {56, 57, 66, 67, 71, 73, 75, 77, 85, 86}
_THUNDERSTORM_CODES = {95, 96, 99}


def assess_weather_readiness(
    forecast: Mapping[str, float | int], event_type: str
) -> WeatherAssessment:
    """Return a transparent, sport-specific weather readiness estimate."""
    sport = event_type.strip().casefold()
    if sport not in _SPORT_SENSITIVITY:
        raise ValueError(f"Weather planning is not configured for {event_type!r}.")

    try:
        temperature = float(forecast["temperature_max"])
        precipitation = float(forecast["precipitation_probability"])
        wind_speed = float(forecast["wind_speed"])
        weather_code = int(forecast["weather_code"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("The forecast is missing valid weather planning values.") from exc

    if not 0 <= precipitation <= 100 or wind_speed < 0:
        raise ValueError("Forecast rain probability or wind speed is outside its valid range.")

    sensitivity = _SPORT_SENSITIVITY[sport]
    rain_points = round(precipitation * sensitivity["rain"])
    wind_points = round(min(wind_speed / 60, 1) * sensitivity["wind"] * 100)
    heat_points = round(min(max(temperature - 30, 0) / 10, 1) * sensitivity["heat"] * 30)
    hazard_points = 50 if weather_code in _SEVERE_WEATHER_CODES else 0
    risk_score = min(100, rain_points + wind_points + heat_points + hazard_points)
    readiness_score = 100 - risk_score

    if risk_score >= 60:
        risk_level = "Severe"
    elif risk_score >= 40:
        risk_level = "High"
    elif risk_score >= 20:
        risk_level = "Moderate"
    else:
        risk_level = "Low"

    factors = []
    if rain_points:
        factors.append(
            f"Rain: {precipitation:g}% chance contributes {rain_points} risk points "
            f"for {event_type}."
        )
    if wind_points:
        factors.append(
            f"Wind: {wind_speed:g} km/h contributes {wind_points} risk points."
        )
    if heat_points:
        factors.append(
            f"Heat: {temperature:g} °C maximum contributes {heat_points} risk points."
        )
    if hazard_points:
        factors.append(
            "Hazardous weather code adds 50 risk points; treat official warnings as decisive."
        )
    if not factors:
        factors.append("No elevated rain, wind, heat, or severe-weather signal was detected.")

    recommendations = []
    if weather_code in _THUNDERSTORM_CODES:
        recommendations.append(
            "Pause outdoor play and follow local lightning and severe-weather guidance."
        )
    elif weather_code in _SNOW_OR_ICE_CODES:
        recommendations.append(
            "Inspect the playing surface and postpone if snow or ice makes it unsafe."
        )
    if precipitation >= 30:
        recommendations.append("Prepare a rain-delay plan and inspect surface drainage.")
    if wind_speed >= 30:
        recommendations.append("Secure temporary equipment, signage, and goal or net structures.")
    if temperature >= 32:
        recommendations.append(
            "Provide water, shaded recovery breaks, and a heat-response contact."
        )
    if risk_level in {"High", "Severe"}:
        recommendations.append("Identify an indoor backup or a postponement decision point.")
    if sport == "cricket" and precipitation >= 30:
        recommendations.append("Keep pitch covers ready and reassess the outfield before play.")
    elif sport == "athletics" and temperature >= 32:
        recommendations.append("Consider moving endurance events to a cooler time of day.")
    if not recommendations:
        recommendations.append("Use the normal event safety checklist and keep monitoring updates.")
    recommendations.append(
        "Recheck the local forecast shortly before the event; conditions can change."
    )

    return {
        "readiness_score": readiness_score,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_factors": factors,
        "recommendations": recommendations,
    }
