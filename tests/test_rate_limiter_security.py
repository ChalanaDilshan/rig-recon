import unittest
import time
import threading
from unittest.mock import patch
import dashboard
from dashboard import (
    check_rate_limit,
    rate_limit_records,
    rate_limit_lock,
    MAX_RATE_LIMIT_KEYS,
)


class TestRateLimiterSecurity(unittest.TestCase):
    def setUp(self):
        with rate_limit_lock:
            rate_limit_records.clear()
            dashboard.last_rate_limit_cleanup = 0.0

    def test_sliding_window_limit_and_reset(self):
        """Verify that requests exceeding the limit are blocked, and permitted after window expires."""
        ip = "192.0.2.1"
        bucket = "test_bucket"
        limit = 3
        window = 2

        # First 3 requests must succeed
        for _ in range(limit):
            self.assertTrue(check_rate_limit(ip, bucket, limit=limit, window_seconds=window))

        # 4th request must be rejected
        self.assertFalse(check_rate_limit(ip, bucket, limit=limit, window_seconds=window))

        # Wait for window to expire
        time.sleep(2.1)

        # Subsequent request should now succeed
        self.assertTrue(check_rate_limit(ip, bucket, limit=limit, window_seconds=window))

    def test_capacity_bounding_and_lru_eviction(self):
        """Verify that rate_limit_records is strictly capped and evicts the least recently used keys in O(1)."""
        test_cap = 50
        with patch.object(dashboard, "MAX_RATE_LIMIT_KEYS", test_cap):
            # Insert 100 unique IP keys
            for i in range(100):
                check_rate_limit(f"192.0.2.{i}", "test", limit=10, window_seconds=60)

            # Total keys tracked must NEVER exceed test_cap
            with rate_limit_lock:
                self.assertEqual(len(rate_limit_records), test_cap)
                # First 50 keys (0-49) should have been evicted by LRU
                for i in range(50):
                    self.assertNotIn((f"192.0.2.{i}", "test"), rate_limit_records)
                # Last 50 keys (50-99) should be present
                for i in range(50, 100):
                    self.assertIn((f"192.0.2.{i}", "test"), rate_limit_records)

    def test_no_cleanup_churn_performance_at_scale(self):
        """
        Verify that having thousands of active keys does NOT trigger synchronous table sweeps
        under the lock on every request. Performance must remain O(1) in sub-milliseconds.
        """
        # Populate table with 2,000 active keys
        for i in range(2000):
            check_rate_limit(f"10.1.{i // 256}.{i % 256}", "api", limit=100, window_seconds=60)

        # Run 500 checks on existing and new keys while tracking execution duration
        start = time.perf_counter()
        for i in range(500):
            check_rate_limit(f"10.1.0.{i % 200}", "api", limit=100, window_seconds=60)
        duration = time.perf_counter() - start

        # 500 checks in O(1) must take well under 0.1 seconds (typically < 0.005s)
        self.assertLess(duration, 0.1, f"Execution took {duration:.4f}s - cleanup churn detected!")

    def test_concurrent_multithreaded_safety(self):
        """Verify thread-safety and consistent rate limiting under high concurrent load."""
        shared_ip = "192.0.2.99"
        bucket = "concurrent_test"
        limit = 50
        results = []
        threads = []

        def worker():
            for _ in range(10):
                res = check_rate_limit(shared_ip, bucket, limit=limit, window_seconds=60)
                results.append(res)

        # 10 threads x 10 requests = 100 total requests against a limit of 50
        for _ in range(10):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        successes = sum(1 for r in results if r is True)
        failures = sum(1 for r in results if r is False)
        self.assertEqual(len(results), 100)
        self.assertEqual(successes, limit)
        self.assertEqual(failures, 50)


if __name__ == "__main__":
    unittest.main()
