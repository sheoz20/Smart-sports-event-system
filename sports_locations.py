"""Sample Chennai sports locations and local search helpers."""

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt


DEMO_CONTACT = "Demo placeholder: +91 44 XXXX XXXX (replace with a verified number)"


@dataclass(frozen=True)
class SportsLocation:
    name: str
    sport: str
    category: str
    area: str
    address: str
    latitude: float
    longitude: float
    facilities: str
    opening_hours: str
    contact: str
    availability: str


SPORTS_LOCATIONS = (
    SportsLocation(
        "Sample Chennai Badminton Arena",
        "Badminton",
        "Indoor",
        "Anna Nagar",
        "Sample listing, 2nd Avenue, Anna Nagar, Chennai, Tamil Nadu 600040",
        13.0840,
        80.2101,
        "Badminton courts, changing rooms, drinking water, equipment rental",
        "6:00 AM - 10:00 PM",
        DEMO_CONTACT,
        "Not live - contact venue to confirm",
    ),
    SportsLocation(
        "Sample T. Nagar Table Tennis Centre",
        "Table Tennis",
        "Indoor",
        "T. Nagar",
        "Sample listing, North Usman Road, T. Nagar, Chennai, Tamil Nadu 600017",
        13.0418,
        80.2341,
        "Table tennis tables, practice area, changing rooms",
        "7:00 AM - 9:30 PM",
        DEMO_CONTACT,
        "Not live - contact venue to confirm",
    ),
    SportsLocation(
        "Sample Nungambakkam Chess Club",
        "Chess",
        "Indoor",
        "Nungambakkam",
        "Sample listing, College Road, Nungambakkam, Chennai, Tamil Nadu 600006",
        13.0569,
        80.2425,
        "Chess tables, coaching area, tournament room",
        "8:00 AM - 8:00 PM",
        DEMO_CONTACT,
        "Not live - contact venue to confirm",
    ),
    SportsLocation(
        "Sample Mylapore Carrom Hall",
        "Carrom",
        "Indoor",
        "Mylapore",
        "Sample listing, Luz Church Road, Mylapore, Chennai, Tamil Nadu 600004",
        13.0330,
        80.2697,
        "Carrom boards, indoor recreation hall, seating",
        "7:00 AM - 9:00 PM",
        DEMO_CONTACT,
        "Not live - contact venue to confirm",
    ),
    SportsLocation(
        "Sample Velachery Indoor Basketball Court",
        "Basketball (Indoor Court)",
        "Indoor",
        "Velachery",
        "Sample listing, 100 Feet Road, Velachery, Chennai, Tamil Nadu 600042",
        12.9750,
        80.2212,
        "Indoor basketball court, changing rooms, spectator seating",
        "6:00 AM - 10:00 PM",
        DEMO_CONTACT,
        "Not live - contact venue to confirm",
    ),
    SportsLocation(
        "Sample Chepauk Cricket Ground",
        "Cricket",
        "Outdoor",
        "Chepauk",
        "Sample listing, Wallajah Road, Chepauk, Chennai, Tamil Nadu 600005",
        13.0627,
        80.2792,
        "Cricket pitch, practice nets, pavilion, changing rooms",
        "6:00 AM - 6:30 PM",
        DEMO_CONTACT,
        "Not live - contact venue to confirm",
    ),
    SportsLocation(
        "Sample Egmore Football Ground",
        "Football",
        "Outdoor",
        "Egmore",
        "Sample listing, Poonamallee High Road, Egmore, Chennai, Tamil Nadu 600008",
        13.0780,
        80.2600,
        "Football pitch, goal posts, changing rooms, drinking water",
        "6:00 AM - 7:00 PM",
        DEMO_CONTACT,
        "Not live - contact venue to confirm",
    ),
    SportsLocation(
        "Sample Marina Volleyball Courts",
        "Volleyball",
        "Outdoor",
        "Marina Beach",
        "Sample listing, Kamarajar Salai, Marina Beach, Chennai, Tamil Nadu 600005",
        13.0500,
        80.2820,
        "Volleyball court, nets, open warm-up area",
        "5:30 AM - 6:30 PM",
        DEMO_CONTACT,
        "Not live - contact venue to confirm",
    ),
    SportsLocation(
        "Sample Egmore Hockey Field",
        "Hockey",
        "Outdoor",
        "Egmore",
        "Sample listing, Pantheon Road, Egmore, Chennai, Tamil Nadu 600008",
        13.0732,
        80.2609,
        "Hockey field, goal cages, changing rooms, first-aid area",
        "6:00 AM - 6:30 PM",
        DEMO_CONTACT,
        "Not live - contact venue to confirm",
    ),
    SportsLocation(
        "Sample Perungudi Kabaddi Ground",
        "Kabaddi",
        "Outdoor",
        "Perungudi",
        "Sample listing, Kandanchavadi, Perungudi, Chennai, Tamil Nadu 600096",
        12.9600,
        80.2460,
        "Kabaddi ground, marked play area, spectator seating",
        "6:00 AM - 6:30 PM",
        DEMO_CONTACT,
        "Not live - contact venue to confirm",
    ),
    SportsLocation(
        "Sample Tambaram Badminton Court",
        "Badminton",
        "Indoor",
        "Tambaram",
        "Sample listing, GST Road, Tambaram, Chengalpattu district, Tamil Nadu",
        12.9249,
        80.1000,
        "Badminton courts, changing rooms, drinking water, equipment rental",
        "6:00 AM - 10:00 PM",
        DEMO_CONTACT,
        "Not live - contact venue to confirm",
    ),
    SportsLocation(
        "Sample Pallavaram Table Tennis Centre",
        "Table Tennis",
        "Indoor",
        "Pallavaram",
        "Sample listing, GST Road, Pallavaram, Chengalpattu district, Tamil Nadu",
        12.9675,
        80.1491,
        "Table tennis tables, practice area, changing rooms",
        "7:00 AM - 9:30 PM",
        DEMO_CONTACT,
        "Not live - contact venue to confirm",
    ),
    SportsLocation(
        "Sample Vandalur Cricket Ground",
        "Cricket",
        "Outdoor",
        "Vandalur",
        "Sample listing, Vandalur, Chengalpattu district, Tamil Nadu",
        12.8924,
        80.0800,
        "Cricket pitch, practice nets, pavilion, changing rooms",
        "6:00 AM - 6:30 PM",
        DEMO_CONTACT,
        "Not live - contact venue to confirm",
    ),
    SportsLocation(
        "Sample Guduvanchery Football Ground",
        "Football",
        "Outdoor",
        "Guduvanchery",
        "Sample listing, GST Road, Guduvanchery, Chengalpattu district, Tamil Nadu",
        12.8452,
        80.0600,
        "Football pitch, goal posts, changing rooms, drinking water",
        "6:00 AM - 7:00 PM",
        DEMO_CONTACT,
        "Not live - contact venue to confirm",
    ),
    SportsLocation(
        "Sample Maraimalai Nagar Hockey Field",
        "Hockey",
        "Outdoor",
        "Maraimalai Nagar",
        "Sample listing, GST Road, Maraimalai Nagar, Chengalpattu district, Tamil Nadu",
        12.7897,
        80.0250,
        "Hockey field, goal cages, changing rooms, first-aid area",
        "6:00 AM - 6:30 PM",
        DEMO_CONTACT,
        "Not live - contact venue to confirm",
    ),
    SportsLocation(
        "Sample Chengalpattu Volleyball Courts",
        "Volleyball",
        "Outdoor",
        "Chengalpattu",
        "Sample listing, Chengalpattu town, Chengalpattu district, Tamil Nadu",
        12.6819,
        79.9888,
        "Volleyball court, nets, open warm-up area",
        "5:30 AM - 6:30 PM",
        DEMO_CONTACT,
        "Not live - contact venue to confirm",
    ),
    SportsLocation(
        "Sample Mahabalipuram Chess Club",
        "Chess",
        "Indoor",
        "Mahabalipuram",
        "Sample listing, East Coast Road, Mahabalipuram, Chengalpattu district, Tamil Nadu",
        12.6269,
        80.1927,
        "Chess tables, coaching area, tournament room",
        "8:00 AM - 8:00 PM",
        DEMO_CONTACT,
        "Not live - contact venue to confirm",
    ),
    SportsLocation(
        "Sample Kelambakkam Kabaddi Ground",
        "Kabaddi",
        "Outdoor",
        "Kelambakkam",
        "Sample listing, Kelambakkam, Chengalpattu district, Tamil Nadu",
        12.7870,
        80.2200,
        "Kabaddi ground, marked play area, spectator seating",
        "6:00 AM - 6:30 PM",
        DEMO_CONTACT,
        "Not live - contact venue to confirm",
    ),
)

CHENNAI_AREAS = {
    location.area: (location.latitude, location.longitude)
    for location in SPORTS_LOCATIONS
}


def distance_km(origin: tuple[float, float], destination: tuple[float, float]) -> float:
    """Return straight-line distance between two latitude/longitude pairs."""
    origin_latitude, origin_longitude = origin
    destination_latitude, destination_longitude = destination
    latitude_delta = radians(destination_latitude - origin_latitude)
    longitude_delta = radians(destination_longitude - origin_longitude)
    haversine = (
        sin(latitude_delta / 2) ** 2
        + cos(radians(origin_latitude))
        * cos(radians(destination_latitude))
        * sin(longitude_delta / 2) ** 2
    )
    return 6371 * 2 * asin(sqrt(haversine))


def filter_locations(
    locations: tuple[SportsLocation, ...] = SPORTS_LOCATIONS,
    query: str = "",
    category: str = "All",
    sport: str = "All",
    center: tuple[float, float] | None = None,
    radius_km: float | None = None,
    area: str = "All",
) -> list[tuple[SportsLocation, float | None]]:
    """Filter sample listings and optionally order/filter by nearby distance."""
    if radius_km is not None and radius_km < 0:
        raise ValueError("Radius cannot be negative.")

    def normalize(value: str) -> str:
        return " ".join(
            "".join(
                character.casefold() if character.isalnum() else " "
                for character in value
            ).split()
        )

    search_text = normalize(query)
    matches = []
    for location in locations:
        searchable = normalize(" ".join(
            (location.name, location.sport, location.category, location.area, location.address)
        ))
        if search_text and search_text not in searchable:
            continue
        if area != "All" and normalize(location.area) != normalize(area):
            continue
        if category != "All" and location.category != category:
            continue
        if sport != "All" and location.sport != sport:
            continue
        distance = (
            distance_km(center, (location.latitude, location.longitude))
            if center is not None
            else None
        )
        if radius_km is not None and distance is not None and distance > radius_km:
            continue
        matches.append((location, distance))
    if center is not None:
        matches.sort(key=lambda result: result[1])
    return matches
