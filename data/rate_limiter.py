"""
Token Bucket Rate Limiter
==========================
Thread-safe rate limiter for API calls using the token bucket algorithm.
Tokens refill at a constant rate up to a maximum capacity.
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token bucket rate limiter for API calls.

    Tokens refill at a constant rate (calls_per_minute / 60 per second).
    When tokens are depleted, acquire() blocks until enough refill.

    Usage:
        limiter = RateLimiter(200)  # 200 calls/min
        limiter.acquire()           # blocks if no tokens
        # make API call...
    """

    def __init__(self, calls_per_minute: int):
        """Initialize rate limiter.

        Args:
            calls_per_minute: Maximum API calls allowed per minute.
        """
        self.max_tokens = float(calls_per_minute)
        self.tokens = float(calls_per_minute)
        self.rate = self.max_tokens / 60.0  # tokens per second
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()
        logger.debug(f"Rate limiter initialized: {calls_per_minute} calls/min")

    def acquire(self, tokens: int = 1) -> float:
        """Acquire tokens, blocking if necessary.

        Args:
            tokens: Number of tokens to consume (default 1).

        Returns:
            Time spent waiting in seconds.
        """
        waited = 0.0
        with self._lock:
            self._refill()

            while self.tokens < tokens:
                deficit = tokens - self.tokens
                wait_time = deficit / self.rate
                logger.debug(f"Rate limit: waiting {wait_time:.2f}s for {deficit:.0f} tokens")
                self._lock.release()
                time.sleep(wait_time)
                self._lock.acquire()
                waited += wait_time
                self._refill()

            self.tokens -= tokens
            return waited

    def _refill(self):
        """Refill tokens based on elapsed time. Must be called with lock held."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        new_tokens = elapsed * self.rate
        self.tokens = min(self.max_tokens, self.tokens + new_tokens)
        self.last_refill = now

    @property
    def available_tokens(self) -> float:
        """Current number of available tokens (read-only, approximate)."""
        with self._lock:
            self._refill()
            return self.tokens
