import unittest
from unittest.mock import patch, MagicMock
from fastapi import Request
from starlette.testclient import TestClient
import dashboard
from dashboard import (
    app,
    get_client_ip,
    is_loopback_request,
    is_trusted_proxy,
    parse_trusted_proxies,
    rate_limit_records,
    rate_limit_lock,
)


def make_mock_request(client_host="198.51.100.50", headers=None):
    mock = MagicMock(spec=Request)
    mock.client = MagicMock()
    mock.client.host = client_host
    mock.headers = headers or {}
    return mock


class TestClientIPSpoofingSecurity(unittest.TestCase):
    def setUp(self):
        with rate_limit_lock:
            rate_limit_records.clear()

    def test_direct_remote_cannot_spoof_ip(self):
        """A direct remote client setting X-Forwarded-For is ignored when no trusted proxy is configured."""
        with patch.object(dashboard, "TRUSTED_PROXY_NETWORKS", []), \
             patch.object(dashboard, "TRUSTED_PROXY_NAMES", set()):
            req = make_mock_request(
                client_host="198.51.100.50",
                headers={"x-forwarded-for": "127.0.0.1"}
            )
            self.assertEqual(get_client_ip(req), "198.51.100.50")
            self.assertFalse(is_loopback_request(req))

    def test_direct_remote_cannot_spoof_x_real_ip(self):
        """A direct remote client setting X-Real-IP is ignored."""
        with patch.object(dashboard, "TRUSTED_PROXY_NETWORKS", []), \
             patch.object(dashboard, "TRUSTED_PROXY_NAMES", set()):
            req = make_mock_request(
                client_host="198.51.100.50",
                headers={"x-real-ip": "127.0.0.1"}
            )
            self.assertEqual(get_client_ip(req), "198.51.100.50")
            self.assertFalse(is_loopback_request(req))

    def test_trusted_proxy_right_to_left_parsing(self):
        """
        When behind a trusted reverse proxy, X-Forwarded-For is parsed from right to left,
        ignoring spoofed leftmost entries injected by the client.
        """
        networks, names = parse_trusted_proxies("10.0.0.1")
        with patch.object(dashboard, "TRUSTED_PROXY_NETWORKS", networks), \
             patch.object(dashboard, "TRUSTED_PROXY_NAMES", names):
            # Attacker injected '127.0.0.1', proxy appended real IP '203.0.113.99'
            req = make_mock_request(
                client_host="10.0.0.1",
                headers={"x-forwarded-for": "127.0.0.1, 203.0.113.99"}
            )
            self.assertEqual(get_client_ip(req), "203.0.113.99")
            self.assertFalse(is_loopback_request(req))

    def test_trusted_proxy_chain_parsing(self):
        """Multiple trusted proxies in chain are skipped from right to left until first untrusted client IP."""
        networks, names = parse_trusted_proxies("10.0.0.1,10.0.0.2")
        with patch.object(dashboard, "TRUSTED_PROXY_NETWORKS", networks), \
             patch.object(dashboard, "TRUSTED_PROXY_NAMES", names):
            # Format: <client>, <proxy1>, <direct_peer=proxy2>
            req = make_mock_request(
                client_host="10.0.0.2",
                headers={"x-forwarded-for": "198.51.100.77, 10.0.0.1"}
            )
            self.assertEqual(get_client_ip(req), "198.51.100.77")

    def test_local_reverse_proxy_untrusted_rejects_loopback(self):
        """If a local proxy forwards a request but 127.0.0.1 is NOT in TRUSTED_PROXIES, reject loopback trust."""
        with patch.object(dashboard, "TRUSTED_PROXY_NETWORKS", []), \
             patch.object(dashboard, "TRUSTED_PROXY_NAMES", set()):
            req = make_mock_request(
                client_host="127.0.0.1",
                headers={"x-forwarded-for": "203.0.113.5"}
            )
            self.assertFalse(is_loopback_request(req))

    def test_legitimate_loopback_without_proxy_headers(self):
        """A genuine direct connection on loopback with no proxy headers is accepted."""
        req = make_mock_request(
            client_host="127.0.0.1",
            headers={}
        )
        self.assertEqual(get_client_ip(req), "127.0.0.1")
        self.assertTrue(is_loopback_request(req))


class TestTriggerMergeAccessControl(unittest.TestCase):
    def setUp(self):
        with rate_limit_lock:
            rate_limit_records.clear()

    @patch("dashboard.compile_master_dataset")
    def test_remote_spoofed_xff_blocked(self, mock_compile):
        """Simulate remote client sending XFF: 127.0.0.1 via TestClient with remote client address."""
        client = TestClient(app, client=("198.51.100.22", 50000))
        with patch.object(dashboard, "ADMIN_API_KEY", None), \
             patch.object(dashboard, "TRUSTED_PROXY_NETWORKS", []), \
             patch.object(dashboard, "TRUSTED_PROXY_NAMES", set()):
            response = client.post(
                "/api/trigger-merge",
                headers={"X-Forwarded-For": "127.0.0.1"}
            )
            # Must be 403 Forbidden because caller is remote and no ADMIN_API_KEY configured
            self.assertEqual(response.status_code, 403)
            mock_compile.assert_not_called()

    @patch("dashboard.compile_master_dataset")
    def test_remote_spoofed_xff_with_admin_key_set_blocked(self, mock_compile):
        """When ADMIN_API_KEY is configured, remote spoofed XFF without key returns 401 Unauthorized."""
        client = TestClient(app, client=("198.51.100.22", 50000))
        with patch.object(dashboard, "ADMIN_API_KEY", "super_secret_token_123"), \
             patch.object(dashboard, "TRUSTED_PROXY_NETWORKS", []), \
             patch.object(dashboard, "TRUSTED_PROXY_NAMES", set()):
            response = client.post(
                "/api/trigger-merge",
                headers={"X-Forwarded-For": "127.0.0.1"}
            )
            self.assertEqual(response.status_code, 401)
            mock_compile.assert_not_called()

    @patch("dashboard.compile_master_dataset")
    def test_remote_with_valid_admin_key_succeeds(self, mock_compile):
        """Remote client providing valid X-Admin-Key succeeds."""
        import pandas as pd
        mock_compile.return_value = pd.DataFrame([{"id": 1}])
        client = TestClient(app, client=("198.51.100.22", 50000))
        with patch.object(dashboard, "ADMIN_API_KEY", "super_secret_token_123"), \
             patch.object(dashboard, "TRUSTED_PROXY_NETWORKS", []), \
             patch.object(dashboard, "TRUSTED_PROXY_NAMES", set()):
            response = client.post(
                "/api/trigger-merge",
                headers={"X-Admin-Key": "super_secret_token_123"}
            )
            self.assertEqual(response.status_code, 200)
            mock_compile.assert_called_once()

    def test_remote_rotating_xff_cannot_bypass_rate_limit(self):
        """
        Remote client rotating X-Forwarded-For header values cannot bypass rate limits
        because rate limits are keyed on verified client IP (request.client.host).
        """
        client = TestClient(app, client=("198.51.100.22", 50000))
        with patch.object(dashboard, "TRUSTED_PROXY_NETWORKS", []), \
             patch.object(dashboard, "TRUSTED_PROXY_NAMES", set()):
            # / has a limit of 60 req/min
            for i in range(60):
                resp = client.get("/", headers={"X-Forwarded-For": f"10.0.0.{i}"})
                self.assertNotEqual(resp.status_code, 429)
            
            # The 61st request should be rate-limited despite a new spoofed X-Forwarded-For
            resp = client.get("/", headers={"X-Forwarded-For": "10.0.0.99"})
            self.assertEqual(resp.status_code, 429)


if __name__ == "__main__":
    unittest.main()
