from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from tonetool import cli
from tonetool.api.app import SESSION_COOKIE, create_app
from tonetool.api.auth import (
    Authenticator,
    LoginFailed,
    LoginThrottle,
    PasswordHasher,
    SessionTokens,
    TooManyAttempts,
    require_auth_for_public_host,
)
from tonetool.api.config import AuthConfig, ServerConfig

PASSWORD = "correct horse battery"
SECRET = "s" * 40


@pytest.fixture(scope="session")
def password_hash() -> str:
    return PasswordHasher.hash(PASSWORD)


@pytest.fixture
def auth_config(password_hash: str) -> AuthConfig:
    return AuthConfig(username="kamber", password_hash=password_hash, secret=SECRET)


@pytest.fixture
def client(auth_config: AuthConfig, tmp_path: Path) -> TestClient:
    # https, so that cookies marked Secure are sent back
    return TestClient(create_app(ServerConfig(auth=auth_config, library=tmp_path / "lib")), base_url="https://testserver")


def login(client: TestClient, username: str = "kamber", password: str = PASSWORD):
    return client.post("/api/session", json={"username": username, "password": password})


# -- passwords ----------------------------------------------------------------------------------


def test_a_password_hashes_and_verifies(password_hash: str):
    assert password_hash.startswith("scrypt:") and "$" not in password_hash
    assert PasswordHasher.verify(PASSWORD, password_hash)
    assert not PasswordHasher.verify("wrong", password_hash)
    assert not PasswordHasher.verify(PASSWORD + " ", password_hash)


def test_every_hash_has_its_own_salt(password_hash: str):
    other = PasswordHasher.hash(PASSWORD)
    assert other != password_hash
    assert PasswordHasher.verify(PASSWORD, other)


def test_passwords_are_compared_in_a_normalised_form():
    stored = PasswordHasher.hash("blåbærgrød-æøå")
    decomposed = "blåbæ" + "rgrød-æøå"  # å written as a + combining ring
    assert PasswordHasher.verify(decomposed, stored)


@pytest.mark.parametrize("stored", ["", "x", "scrypt:1:2", "bcrypt:1:2:3:aa:bb", "scrypt:a:b:c:d:e", "scrypt:16384:8:1:!!:!!"])
def test_a_malformed_hash_never_verifies_and_never_raises(stored: str):
    assert not PasswordHasher.verify(PASSWORD, stored)
    assert not PasswordHasher.is_valid(stored)


# -- session tokens -----------------------------------------------------------------------------


def test_tokens_are_signed_and_expire():
    now = [1000.0]
    tokens = SessionTokens(SECRET, 60, clock=lambda: now[0])
    token = tokens.issue("kamber")
    assert tokens.verify(token) == "kamber"
    now[0] = 1059.0
    assert tokens.verify(token) == "kamber"
    now[0] = 1060.0
    assert tokens.verify(token) is None  # expired


def test_tokens_from_another_secret_or_tampered_with_are_refused():
    tokens = SessionTokens(SECRET, 60)
    token = tokens.issue("kamber")
    assert SessionTokens("t" * 40, 60).verify(token) is None
    body, _, signature = token.partition(".")
    flipped = signature[:-1] + ("A" if signature[-1] != "A" else "B")
    assert tokens.verify(f"{body}.{flipped}") is None
    other_body = SessionTokens(SECRET, 60).issue("root").partition(".")[0]
    assert tokens.verify(f"{other_body}.{signature}") is None  # a signature does not carry over to another payload


@pytest.mark.parametrize("token", ["", ".", "abc", "a.b", "a.b.c", "💥", "e30.e30"])
def test_garbage_is_not_a_token(token: str):
    assert SessionTokens(SECRET, 60).verify(token) is None


# -- throttle -----------------------------------------------------------------------------------


def test_the_throttle_blocks_after_five_failures_and_recovers():
    now = [0.0]
    throttle = LoginThrottle(max_failures=5, window_seconds=300, clock=lambda: now[0])
    for _ in range(4):
        throttle.record_failure("a")
    assert throttle.retry_after("a") == 0
    throttle.record_failure("a")
    assert 290 <= throttle.retry_after("a") <= 301
    assert throttle.retry_after("b") == 0  # another client is unaffected
    now[0] = 301.0
    assert throttle.retry_after("a") == 0


def test_a_success_clears_the_failures():
    throttle = LoginThrottle()
    for _ in range(4):
        throttle.record_failure("a")
    throttle.clear("a")
    for _ in range(4):
        throttle.record_failure("a")
    assert throttle.retry_after("a") == 0


# -- the Authenticator --------------------------------------------------------------------------


def test_wrong_username_and_wrong_password_are_the_same_failure(auth_config: AuthConfig):
    authenticator = Authenticator(auth_config)
    with pytest.raises(LoginFailed):
        authenticator.login("nobody", PASSWORD, "c")
    with pytest.raises(LoginFailed):
        authenticator.login("kamber", "wrong", "c")
    token = authenticator.login("kamber", PASSWORD, "c")
    assert authenticator.user_for(token) == "kamber"
    assert authenticator.user_for(None) is None and authenticator.user_for("junk") is None


def test_a_throttled_client_cannot_log_in_even_with_the_right_password(auth_config: AuthConfig):
    authenticator = Authenticator(auth_config)
    for _ in range(5):
        with pytest.raises(LoginFailed):
            authenticator.login("kamber", "wrong", "c")
    with pytest.raises(TooManyAttempts):
        authenticator.login("kamber", PASSWORD, "c")
    assert authenticator.user_for(authenticator.login("kamber", PASSWORD, "someone else")) == "kamber"


def test_a_malformed_password_hash_is_refused_at_start(auth_config: AuthConfig):
    bad = auth_config.model_copy(update={"password_hash": "plaintext"})
    with pytest.raises(ValueError, match="password_hash"):
        Authenticator(bad)


# -- over HTTP ----------------------------------------------------------------------------------


def test_health_and_session_status_are_open(client: TestClient):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/session").json() == {"auth_required": True, "authenticated": False, "username": None}


@pytest.mark.parametrize(
    "method, path",
    [("get", "/api/pieces"), ("get", "/api/pieces/x"), ("put", "/api/pieces/x"), ("delete", "/api/pieces/x"), ("post", "/api/pieces"), ("post", "/api/pieces/x/score")],
)
def test_the_library_needs_a_login(client: TestClient, method: str, path: str):
    response = getattr(client, method)(path)
    assert response.status_code == 401
    assert response.json()["detail"] == "login required"


def test_logging_in_gives_a_cookie_that_opens_the_library(client: TestClient):
    response = login(client)
    assert response.status_code == 200
    assert response.json() == {"auth_required": True, "authenticated": True, "username": "kamber"}
    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    for flag in ("httponly", "secure", "samesite=strict", "path=/", "max-age=43200"):
        assert flag in cookie
    assert client.get("/api/pieces").status_code == 200
    assert client.get("/api/session").json()["username"] == "kamber"


def test_bad_credentials_are_refused_without_saying_which_was_wrong(client: TestClient):
    wrong_user = login(client, username="nobody")
    wrong_password = login(client, password="nope nope nope")
    assert wrong_user.status_code == wrong_password.status_code == 401
    assert wrong_user.json() == wrong_password.json() == {"detail": "wrong username or password"}
    assert "set-cookie" not in wrong_user.headers
    assert client.get("/api/pieces").status_code == 401


def test_logging_out_removes_the_session(client: TestClient):
    login(client)
    response = client.delete("/api/session")
    assert response.status_code == 204
    assert "max-age=0" in response.headers["set-cookie"].lower()
    assert client.get("/api/pieces").status_code == 401


def test_a_tampered_or_foreign_cookie_is_refused(client: TestClient):
    token = login(client).cookies[SESSION_COOKIE]
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, token[:-2] + "xx")
    assert client.get("/api/pieces").status_code == 401
    client.cookies.set(SESSION_COOKIE, SessionTokens("z" * 40, 3600).issue("kamber"))  # signed with another secret
    assert client.get("/api/pieces").status_code == 401


def test_an_expired_cookie_is_refused(client: TestClient):
    client.cookies.set(SESSION_COOKIE, SessionTokens(SECRET, 60, clock=lambda: 0).issue("kamber"))
    assert client.get("/api/pieces").status_code == 401


def test_five_wrong_passwords_lock_the_client_out_for_a_while(client: TestClient):
    for _ in range(5):
        assert login(client, password="nope nope nope").status_code == 401
    blocked = login(client)  # even the right password
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
    assert "try again" in blocked.json()["detail"]


def test_without_a_login_configured_everything_is_open(tmp_path: Path):
    client = TestClient(create_app(ServerConfig(library=tmp_path / "lib")))
    assert client.get("/api/session").json() == {"auth_required": False, "authenticated": True, "username": None}
    assert client.get("/api/pieces").status_code == 200
    assert login(client).status_code == 409


def test_every_response_carries_security_headers(client: TestClient):
    for response in (client.get("/api/health"), client.get("/api/pieces")):
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "same-origin"
        assert "default-src 'self'" in response.headers["content-security-policy"]
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert response.headers["cache-control"] == "no-store"


# -- the built frontend -------------------------------------------------------------------------


def test_the_frontend_is_served_to_everyone_but_the_api_is_not(auth_config: AuthConfig, tmp_path: Path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Tonetool</title>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    client = TestClient(create_app(ServerConfig(auth=auth_config, static_dir=dist)), base_url="https://testserver")
    page = client.get("/")  # the login page has to load before anyone can log in
    assert page.status_code == 200 and "Tonetool" in page.text
    assert page.headers["x-frame-options"] == "DENY"
    assert "cache-control" not in page.headers
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/api/pieces").status_code == 401
    assert client.get("/api/nothing-here").status_code == 404
    assert client.get("/../secret").status_code in (404, 400)


def test_a_missing_frontend_folder_is_an_error_not_a_silent_404(tmp_path: Path):
    with pytest.raises(ValueError, match="static_dir"):
        create_app(ServerConfig(static_dir=tmp_path / "nope"))


# -- configuration ------------------------------------------------------------------------------


def write_config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "tonetool.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_login_can_come_from_the_environment(tmp_path: Path, password_hash: str):
    path = write_config(tmp_path, 'library = "lib"\nstatic_dir = "dist"\n')
    config = ServerConfig.load(
        path,
        environ={"TONETOOL_USERNAME": "kamber", "TONETOOL_PASSWORD_HASH": password_hash, "TONETOOL_SECRET": SECRET,
                 "TONETOOL_SESSION_HOURS": "2", "TONETOOL_COOKIE_SECURE": "false"},
    )
    assert config.auth == AuthConfig(username="kamber", password_hash=password_hash, secret=SECRET, session_hours=2, cookie_secure=False)
    assert config.library == tmp_path / "lib" and config.static_dir == tmp_path / "dist"


def test_the_environment_wins_over_the_file(tmp_path: Path, password_hash: str):
    path = write_config(tmp_path, f'[auth]\nusername = "file"\npassword_hash = "{password_hash}"\nsecret = "{SECRET}"\n')
    assert ServerConfig.load(path, environ={}).auth.username == "file"  # type: ignore[union-attr]
    assert ServerConfig.load(path, environ={"TONETOOL_USERNAME": "env"}).auth.username == "env"  # type: ignore[union-attr]


def test_no_credentials_means_no_login_even_if_options_are_set(tmp_path: Path):
    assert ServerConfig.load(write_config(tmp_path, ""), environ={"TONETOOL_COOKIE_SECURE": "false"}).auth is None


def test_a_half_configured_login_is_an_error(tmp_path: Path):
    with pytest.raises(ValidationError):
        ServerConfig.load(write_config(tmp_path, ""), environ={"TONETOOL_USERNAME": "kamber"})


def test_a_short_secret_is_refused(password_hash: str):
    with pytest.raises(ValidationError):
        AuthConfig(username="kamber", password_hash=password_hash, secret="short")


# -- serving on a public address ----------------------------------------------------------------


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_loopback_needs_no_login(host: str):
    require_auth_for_public_host(host, ServerConfig())


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.5", "example.com"])
def test_other_addresses_are_refused_without_a_login(host: str, auth_config: AuthConfig):
    with pytest.raises(ValueError, match="without a login"):
        require_auth_for_public_host(host, ServerConfig())
    require_auth_for_public_host(host, ServerConfig(auth=auth_config))


# -- the command line ---------------------------------------------------------------------------


def test_hash_password_prints_a_working_hash(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    answers = iter(["a long enough password", "a long enough password"])
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(answers))
    cli.main(["hash-password"])
    assert PasswordHasher.verify("a long enough password", capsys.readouterr().out.strip())


@pytest.mark.parametrize("answers, message", [(["long enough password", "different one"], "differ"), (["short", "short"], "at least 10")])
def test_hash_password_refuses_mismatches_and_short_passwords(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], answers: list[str], message: str):
    queue = iter(answers)
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(queue))
    with pytest.raises(SystemExit):
        cli.main(["hash-password"])
    assert message in capsys.readouterr().err


def test_make_secret_is_long_and_random(capsys: pytest.CaptureFixture[str]):
    cli.main(["make-secret"])
    first = capsys.readouterr().out.strip()
    cli.main(["make-secret"])
    assert len(first) >= 48 and first != capsys.readouterr().out.strip()
