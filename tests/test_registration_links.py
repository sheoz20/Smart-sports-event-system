import os
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from registration_links import get_registration_url


class RegistrationLinkTests(unittest.TestCase):
    def test_explicit_public_base_url_includes_encoded_prefill_details(self):
        with patch.dict(
            os.environ,
            {"APP_BASE_URL": "https://school.example/", "RENDER_EXTERNAL_HOSTNAME": ""},
            clear=True,
        ):
            url = get_registration_url("Asha & Ravi", "123 456", "10/A")

        parsed = urlparse(url)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "school.example")
        self.assertEqual(
            parse_qs(parsed.query),
            {
                "register": ["1"],
                "name": ["Asha & Ravi"],
                "emis": ["123 456"],
                "class": ["10/A"],
            },
        )

    def test_render_hostname_uses_https(self):
        with patch.dict(
            os.environ,
            {"RENDER_EXTERNAL_HOSTNAME": "sports-app.onrender.com"},
            clear=True,
        ):
            url = get_registration_url("Student", "123", "10")

        parsed = urlparse(url)
        self.assertEqual(
            f"{parsed.scheme}://{parsed.netloc}{parsed.path}",
            "https://sports-app.onrender.com/",
        )
        self.assertEqual(
            parse_qs(parsed.query),
            {
                "register": ["1"],
                "name": ["Student"],
                "emis": ["123"],
                "class": ["10"],
            },
        )

if __name__ == "__main__":
    unittest.main()
