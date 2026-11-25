"""Single-user login: password hashing, signed session cookies, and a throttle on failed logins."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import unicodedata
from collections import deque
from collections.abc import Callable

from .config import AuthConfig, ServerConfig

LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    """Strict: anything that is not base64url is an error (the lenient decoder skips such characters)."""
    return base64.b64decode(text + "=" * (-len(text) % 4), altchars=b"-_", validate=True)


class PasswordHasher:
    """Passwords as ``scrypt:N:r:p:salt:hash`` (base64url), with a fresh random salt each time.

    The separators avoid ``$``, which shells and ``.env`` files like to expand.
    """

    N = 2**15
    R = 8
    P = 1
    SALT_BYTES = 16
    KEY_BYTES = 32

    @classmethod
    def hash(cls, password: str) -> str:
        """The stored form of ``password``."""
        salt = secrets.token_bytes(cls.SALT_BYTES)
        key = cls._derive(password, salt, cls.N, cls.R, cls.P, cls.KEY_BYTES)
        return ":".join(["scrypt", str(cls.N), str(cls.R), str(cls.P), _b64(salt), _b64(key)])

    @classmethod
    def verify(cls, password: str, stored: str) -> bool:
        """Whether ``password`` matches ``stored`` (False, never an error, if ``stored`` is malformed)."""
        parsed = cls._parse(stored)
        if parsed is None:
            return False
        n, r, p, salt, expected = parsed
        try:
            actual = cls._derive(password, salt, n, r, p, len(expected))
        except ValueError:
            return False
        return hmac.compare_digest(actual, expected)

    @classmethod
    def is_valid(cls, stored: str) -> bool:
        """Whether ``stored`` has the form ``hash`` writes."""
        return cls._parse(stored) is not None

    @staticmethod
    def _parse(stored: str) -> tuple[int, int, int, bytes, bytes] | None:
        try:
            prefix, n, r, p, salt_text, key_text = stored.split(":")
            salt, key = _unb64(salt_text), _unb64(key_text)
            if prefix != "scrypt" or len(salt) < 8 or len(key) < 16:
                return None
            return int(n), int(r), int(p), salt, key
        except ValueError:
            return None

    @staticmethod
    def _derive(password: str, salt: bytes, n: int, r: int, p: int, length: int) -> bytes:
        normal = unicodedata.normalize("NFKC", password).encode("utf-8")
        return hashlib.scrypt(normal, salt=salt, n=n, r=r, p=p, dklen=length, maxmem=256 * n * r * p)


class SessionTokens:
    """Stateless login tokens: ``payload.signature``, signed with HMAC-SHA256 and expiring."""

    def __init__(self, secret: str, lifetime_seconds: float, clock: Callable[[], float] = time.time) -> None:
        """``lifetime_seconds`` is how long a token is good for."""
        self._key = secret.encode("utf-8")
        self._lifetime = lifetime_seconds
        self._clock = clock

    def issue(self, username: str) -> str:
        """A token for ``username``, good for the lifetime."""
        payload = json.dumps({"u": username, "exp": int(self._clock() + self._lifetime)}, separators=(",", ":"))
        body = _b64(payload.encode("utf-8"))
        return f"{body}.{self._sign(body)}"

    def verify(self, token: str) -> str | None:
        """The username in a genuine, unexpired token, else None."""
        body, dot, signature = token.partition(".")
        if not dot or not hmac.compare_digest(signature, self._sign(body)):
            return None
        try:
            payload = json.loads(_unb64(body))
            username, expires = payload["u"], payload["exp"]
        except (ValueError, KeyError, TypeError):
            return None
        if not isinstance(username, str) or not isinstance(expires, int) or expires <= self._clock():
            return None
        return username

    def _sign(self, body: str) -> str:
        return _b64(hmac.new(self._key, body.encode("ascii", "replace"), hashlib.sha256).digest())


class LoginThrottle:
    """Refuses further attempts from one client after too many failures in a short time."""

    def __init__(
        self, max_failures: int = 5, window_seconds: float = 300, clock: Callable[[], float] = time.time
    ) -> None:
        """Allow ``max_failures`` failed logins per client within ``window_seconds``."""
        self._max = max_failures
        self._window = window_seconds
        self._clock = clock
        self._failures: dict[str, deque[float]] = {}

    def retry_after(self, client: str) -> int:
        """Seconds to wait before this client may try again; 0 if it may try now."""
        recent = self._recent(client)
        if len(recent) < self._max:
            return 0
        return max(1, int(recent[0] + self._window - self._clock()) + 1)

    def record_failure(self, client: str) -> None:
        """Count a failed login."""
        self._recent(client).append(self._clock())

    def clear(self, client: str) -> None:
        """Forget a client's failures (after a successful login)."""
        self._failures.pop(client, None)

    def _recent(self, client: str) -> deque[float]:
        """The failures still inside the window (older ones are dropped)."""
        if len(self._failures) > 10_000:  # a flood of different clients must not grow memory forever
            self._failures = {k: v for k, v in self._failures.items() if v and v[-1] > self._clock() - self._window}
        failures = self._failures.setdefault(client, deque())
        while failures and failures[0] <= self._clock() - self._window:
            failures.popleft()
        return failures


class LoginFailed(Exception):
    """Wrong username or password (deliberately not saying which)."""


class TooManyAttempts(Exception):
    """The client has failed too often recently."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(f"too many failed attempts; try again in {retry_after} seconds")
        self.retry_after = retry_after


class Authenticator:
    """Logs the one configured user in and recognises the session cookie afterwards."""

    def __init__(
        self,
        config: AuthConfig,
        throttle: LoginThrottle | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Check the configuration is usable; ``ValueError`` if the password hash is malformed."""
        if not PasswordHasher.is_valid(config.password_hash):
            raise ValueError("auth.password_hash is not a hash made by `tonetool hash-password`")
        self.config = config
        self._tokens = SessionTokens(config.secret, config.session_hours * 3600, clock)
        self._throttle = throttle or LoginThrottle(clock=clock)
        # checked when the username is wrong, so that a wrong user takes as long as a wrong password
        self._dummy_hash = PasswordHasher.hash(secrets.token_urlsafe(12))

    def login(self, username: str, password: str, client: str) -> str:
        """A session token if the credentials are right; ``LoginFailed`` or ``TooManyAttempts`` if not."""
        wait = self._throttle.retry_after(client)
        if wait:
            raise TooManyAttempts(wait)
        user_ok = hmac.compare_digest(username.encode("utf-8"), self.config.username.encode("utf-8"))
        password_ok = PasswordHasher.verify(password, self.config.password_hash if user_ok else self._dummy_hash)
        if user_ok and password_ok:
            self._throttle.clear(client)
            return self._tokens.issue(self.config.username)
        self._throttle.record_failure(client)
        raise LoginFailed

    def user_for(self, token: str | None) -> str | None:
        """The logged-in user a session cookie stands for, or None."""
        if not token:
            return None
        username = self._tokens.verify(token)
        return username if username == self.config.username else None


def require_auth_for_public_host(host: str, config: ServerConfig) -> None:
    """Refuse to serve on an address other machines can reach without a login. ``ValueError`` if so."""
    if host not in LOOPBACK_HOSTS and config.auth is None:
        raise ValueError(
            f"refusing to listen on {host!r} without a login: add an [auth] section to the config "
            "or set TONETOOL_USERNAME, TONETOOL_PASSWORD_HASH and TONETOOL_SECRET"
        )
