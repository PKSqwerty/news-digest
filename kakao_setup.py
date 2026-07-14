"""
ONE-TIME SETUP: get your Kakao refresh token for "나에게 보내기".

Prerequisites (do once at https://developers.kakao.com):
1. 내 애플리케이션 -> 애플리케이션 추가하기 (any name, e.g. "news-digest")
2. In the app: 앱 설정 > 플랫폼 > Web 플랫폼 등록 -> site domain: http://localhost:5000
3. 제품 설정 > 카카오 로그인 -> 활성화 ON
   Redirect URI: http://localhost:5000/callback
4. 제품 설정 > 카카오 로그인 > 동의항목 -> "카카오톡 메시지 전송 (talk_message)" -> 선택 동의
5. Copy your REST API 키 from 앱 설정 > 앱 키

Then run:  python kakao_setup.py YOUR_REST_API_KEY
"""

import sys
import requests
from urllib.parse import urlencode

if len(sys.argv) < 2:
    print(__doc__)
    sys.exit(1)

REST_KEY = sys.argv[1]
REDIRECT = "http://localhost:5000/callback"

auth_url = "https://kauth.kakao.com/oauth/authorize?" + urlencode({
    "client_id": REST_KEY,
    "redirect_uri": REDIRECT,
    "response_type": "code",
    "scope": "talk_message",
})

print("\n1) Open this URL in your browser and log in / agree:\n")
print(auth_url)
print("\n2) You'll be redirected to a localhost URL that fails to load — that's fine.")
print("   Copy the value of ?code=... from the address bar.\n")
code = input("Paste the code here: ").strip()

resp = requests.post("https://kauth.kakao.com/oauth/token", data={
    "grant_type": "authorization_code",
    "client_id": REST_KEY,
    "redirect_uri": REDIRECT,
    "code": code,
})
resp.raise_for_status()
tokens = resp.json()

print("\n================ SUCCESS ================")
print("Add these as GitHub repo secrets:\n")
print(f"KAKAO_REST_API_KEY = {REST_KEY}")
print(f"KAKAO_REFRESH_TOKEN = {tokens['refresh_token']}")
print("\n(refresh token is valid ~2 months; the daily job auto-refreshes it)")
