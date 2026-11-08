
import os
import urllib.parse

PUBLIC_URL = "https://smart-sports-event-system-bkdq4n4rdxpgw8xf8vrvjx.streamlit.app"


def get_registration_url(
    student_name="", emis_number="", class_section="", base_url=None
):
    if base_url is None:
        base_url = os.environ.get("APP_BASE_URL", "").strip().rstrip("/")

    if not base_url:
        base_url = PUBLIC_URL

    query = urllib.parse.urlencode({
        "register": "1",
        "name": student_name,
        "emis": emis_number,
        "class": class_section,
    })

    return f"{base_url}/?{query}"
