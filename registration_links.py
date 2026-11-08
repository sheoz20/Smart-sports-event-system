import os
import socket
import urllib.parse


def get_registration_url(student_name="", emis_number="", class_section=""):
    base_url = os.environ.get("APP_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        render_hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
        if render_hostname:
            base_url = f"https://{render_hostname}"
    if not base_url:
        host = None
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect(("8.8.8.8", 80))
                host = probe.getsockname()[0]
        except OSError:
            pass
        if not host:
            try:
                host = socket.gethostbyname(socket.gethostname())
            except OSError:
                host = "127.0.0.1"
        base_url = f"http://{host}:8501"

    query = urllib.parse.urlencode(
        {
            "register": "1",
            "name": student_name,
            "emis": emis_number,
            "class": class_section,
        }
    )
    return f"{base_url}/?{query}"
