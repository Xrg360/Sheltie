import unittest
from unittest.mock import MagicMock, patch

import requests

from monitors.actions import ActionService
from monitors.alerts import parse_duration
from monitors.sites import check_sites, read_capped_text


class FakeState:
    def __init__(self) -> None:
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        return True


class FakeAlerts:
    def __init__(self) -> None:
        self.conditions = []

    def condition(self, **kwargs):
        self.conditions.append(kwargs)


def fake_response(status=200, body=b"hello"):
    response = MagicMock()
    response.status_code = status
    response.encoding = "utf-8"
    response.iter_content.return_value = [body]
    response.__enter__.return_value = response
    return response


class ParseDurationTests(unittest.TestCase):
    def test_long_suffixes(self):
        self.assertEqual(parse_duration("5minutes"), 300)
        self.assertEqual(parse_duration("2 hours"), 7200)
        self.assertEqual(parse_duration("10seconds"), 10)

    def test_days(self):
        self.assertEqual(parse_duration("1d"), 86400)
        self.assertEqual(parse_duration("2days"), 172800)

    def test_short_suffixes_still_work(self):
        self.assertEqual(parse_duration("30s"), 30)
        self.assertEqual(parse_duration("15m"), 900)
        self.assertEqual(parse_duration("1h"), 3600)


class AddSiteValidationTests(unittest.TestCase):
    def setUp(self):
        self.state = FakeState()
        self.service = ActionService({}, self.state, history=None)

    def add(self, **site):
        site.setdefault("name", "Portfolio")
        site.setdefault("url", "https://portfolio.simplewebsite.in")
        return self.service.add_site(site)

    def test_accepts_and_normalizes_a_valid_site(self):
        result = self.add(expected_status="301", timeout="5")
        self.assertTrue(result["ok"], result)
        stored = self.state.get("sites.custom")[0]
        self.assertEqual(stored["expected_status"], [301])
        self.assertEqual(stored["timeout"], 5.0)

    def test_rejects_bad_status_codes(self):
        self.assertFalse(self.add(expected_status="ok")["ok"])
        self.assertFalse(self.add(expected_status=[200, 999])["ok"])

    def test_rejects_bad_timeouts(self):
        self.assertFalse(self.add(timeout=-1)["ok"])
        self.assertFalse(self.add(timeout="soon")["ok"])
        self.assertFalse(self.add(timeout=600)["ok"])

    def test_rejects_bad_duration_and_severity(self):
        self.assertFalse(self.add(duration="forever")["ok"])
        self.assertFalse(self.add(severity="panic")["ok"])

    def test_rejects_names_that_could_break_html_or_metrics(self):
        self.assertFalse(self.add(name="x');alert(1);('")["ok"])
        self.assertFalse(self.add(name='a"b')["ok"])
        self.assertFalse(self.add(name="line\nbreak")["ok"])
        self.assertFalse(self.add(name="x" * 65)["ok"])

    def test_rejects_bad_urls(self):
        self.assertFalse(self.add(url="ftp://example.com")["ok"])
        self.assertFalse(self.add(url="https://exa mple.com")["ok"])

    def test_rejects_non_object_body(self):
        self.assertFalse(self.service.add_site(["not", "a", "dict"])["ok"])  # type: ignore[arg-type]

    def test_nothing_is_saved_on_error(self):
        self.add(timeout=-1)
        self.assertIsNone(self.state.get("sites.custom"))


class CheckSitesTests(unittest.TestCase):
    def test_bad_stored_site_does_not_stop_other_checks(self):
        state = FakeState()
        state.set(
            "sites.custom",
            [
                {"name": "broken", "url": "https://broken.example", "expected_status": "200", "timeout": "soon"},
                {"name": "good", "url": "https://good.example"},
            ],
        )
        alerts = FakeAlerts()
        with patch("monitors.sites.requests.get", return_value=fake_response()), self.assertLogs(level="ERROR"):
            check_sites({}, state, alerts)

        results = state.get("sites.status")
        self.assertEqual([site["name"] for site in results], ["good"])
        self.assertTrue(results[0]["up"])

    def test_keyword_check_reads_capped_body(self):
        state = FakeState()
        config = {"sites": [{"name": "kw", "url": "https://kw.example", "keyword": "hello"}]}
        with patch("monitors.sites.requests.get", return_value=fake_response(body=b"say hello")) as get:
            check_sites(config, state, FakeAlerts())
        self.assertTrue(get.call_args.kwargs["stream"])
        self.assertTrue(state.get("sites.status")[0]["up"])

    def test_request_errors_mark_site_down(self):
        state = FakeState()
        config = {"sites": [{"name": "down", "url": "https://down.example"}]}
        with patch("monitors.sites.requests.get", side_effect=requests.ConnectionError("refused")):
            check_sites(config, state, FakeAlerts())
        self.assertFalse(state.get("sites.status")[0]["up"])

    def test_read_capped_text_stops_at_limit(self):
        response = fake_response()
        response.iter_content.return_value = iter([b"a" * 10, b"b" * 10, b"c" * 10])
        self.assertEqual(read_capped_text(response, limit=15), "a" * 10 + "b" * 5)


if __name__ == "__main__":
    unittest.main()
