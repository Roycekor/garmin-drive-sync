"""
일회용 스크립트: 브라우저로 Garmin 로그인 후 garth 토큰 저장.
SSO 429 차단 우회용. 한 번만 실행하면 이후 토큰 캐시로 동작.

사용법:
  python scripts/garmin_browser_auth.py
"""

import json
import re
import stat
import sys
from pathlib import Path
from urllib.parse import urlencode

import requests
from requests_oauthlib import OAuth1Session
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import os

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

WORKDIR = Path(os.environ.get("WORKDIR", Path.home() / "garmin-drive-sync"))
TOKEN_DIR = WORKDIR / ".garmin_tokens"

SSO_EMBED_URL = "https://sso.garmin.com/sso/embed"
SSO_SIGNIN_URL = "https://sso.garmin.com/sso/signin"

OAUTH1_URL = "https://connectapi.garmin.com/oauth-service/oauth"
OAUTH2_URL = "https://connectapi.garmin.com/oauth-service/oauth"


def fetch_consumer_credentials() -> tuple[str, str]:
    """garth S3 버킷에서 OAuth consumer key/secret 가져오기"""
    resp = requests.get("https://thegarth.s3.amazonaws.com/oauth_consumer.json")
    resp.raise_for_status()
    data = resp.json()
    print("Consumer credentials 획득")
    return data["consumer_key"], data["consumer_secret"]


def get_sso_ticket_via_browser() -> str:
    """브라우저를 열어 사용자가 직접 로그인 → SSO 티켓 추출"""
    params = urlencode({
        "id": "gauth-widget",
        "embedWidget": "true",
        "gauthHost": SSO_EMBED_URL,
        "service": SSO_EMBED_URL,
        "source": SSO_EMBED_URL,
        "redirectAfterAccountLoginUrl": SSO_EMBED_URL,
        "redirectAfterAccountCreationUrl": SSO_EMBED_URL,
    })
    login_url = f"{SSO_SIGNIN_URL}?{params}"
    ticket = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        def on_response(response):
            nonlocal ticket
            url = response.url
            if "ticket=ST-" in url:
                match = re.search(r"ticket=(ST-[\w-]+)", url)
                if match:
                    ticket = match.group(1)

        page.on("response", on_response)
        page.goto(login_url)

        print("브라우저에서 Garmin 로그인을 완료하세요...")
        # 티켓이 나올 때까지 대기 (최대 5분)
        page.wait_for_url("**/embed*ticket=ST-*", timeout=300_000)

        if not ticket:
            match = re.search(r"ticket=(ST-[\w-]+)", page.url)
            if match:
                ticket = match.group(1)

        browser.close()

    if not ticket:
        print("SSO 티켓을 가져오지 못했습니다.")
        sys.exit(1)

    print(f"SSO 티켓 획득: {ticket[:20]}...")
    return ticket


def exchange_ticket_for_oauth1(consumer_key: str, consumer_secret: str, ticket: str) -> tuple[str, str]:
    """SSO 티켓 → OAuth1 토큰"""
    oauth = OAuth1Session(consumer_key, client_secret=consumer_secret)
    resp = oauth.fetch_request_token(
        f"{OAUTH1_URL}/preauthorized?ticket={ticket}&login-url={SSO_EMBED_URL}"
    )
    oauth_token = resp["oauth_token"]
    oauth_secret = resp["oauth_token_secret"]
    print("OAuth1 토큰 획득 완료")
    return oauth_token, oauth_secret


def exchange_oauth1_for_oauth2(consumer_key: str, consumer_secret: str, oauth_token: str, oauth_secret: str) -> dict:
    """OAuth1 → OAuth2 토큰"""
    oauth = OAuth1Session(
        consumer_key,
        client_secret=consumer_secret,
        resource_owner_key=oauth_token,
        resource_owner_secret=oauth_secret,
    )
    resp = oauth.post(
        f"{OAUTH2_URL}/exchange/user/2.0",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp.raise_for_status()
    token_data = resp.json()
    print(f"OAuth2 토큰 획득 (expires_in={token_data.get('expires_in', '?')}s)")
    return token_data


def save_garth_tokens(oauth1_token: str, oauth1_secret: str, oauth2_data: dict):
    """garth 포맷으로 토큰 저장 (.garmin_tokens/)"""
    import time
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)

    oauth1_path = TOKEN_DIR / "oauth1_token.json"
    oauth1_path.write_text(json.dumps({
        "oauth_token": oauth1_token,
        "oauth_token_secret": oauth1_secret,
    }, indent=2))
    oauth1_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    # garth가 요구하는 expires_at 필드 계산
    now = int(time.time())
    oauth2_data["expires_at"] = now + oauth2_data.get("expires_in", 3600)
    oauth2_data["refresh_token_expires_at"] = now + oauth2_data.get("refresh_token_expires_in", 2592000)

    oauth2_path = TOKEN_DIR / "oauth2_token.json"
    oauth2_path.write_text(json.dumps(oauth2_data, indent=2))
    oauth2_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    print(f"토큰 저장 완료: {TOKEN_DIR}")


def verify_token():
    """저장된 토큰으로 garth 로드 테스트"""
    try:
        import garth
        garth.resume(str(TOKEN_DIR))
        display_name = garth.client.username
        print(f"토큰 검증 성공! (user: {display_name})")
    except Exception as e:
        print(f"토큰 검증 실패: {e}")
        print("토큰 파일은 저장되었으니 main.py 실행으로 확인해보세요.")


if __name__ == "__main__":
    print("=== Garmin 브라우저 인증 (429 우회) ===\n")

    consumer_key, consumer_secret = fetch_consumer_credentials()
    ticket = get_sso_ticket_via_browser()
    oauth1_token, oauth1_secret = exchange_ticket_for_oauth1(consumer_key, consumer_secret, ticket)
    oauth2_data = exchange_oauth1_for_oauth2(consumer_key, consumer_secret, oauth1_token, oauth1_secret)
    save_garth_tokens(oauth1_token, oauth1_secret, oauth2_data)
    verify_token()

    print("\n이제 main.py를 실행하면 저장된 토큰으로 로그인됩니다.")
