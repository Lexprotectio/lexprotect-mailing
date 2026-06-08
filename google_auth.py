"""
🔐 Antigravity — Proje Seviyesi Google OAuth Yardımcısı
===================================================
Bu modül hem yerelde hem de Railway/Cloud ortamında Google API erişimi sağlar.
"""

import os
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

OAUTH_DIR = os.path.dirname(os.path.abspath(__file__))

TOKEN_FILES = {
    "account1": "gmail-account1-token.json",
    "account2": "gmail-account2-token.json",
    "outreach": "gmail-account1-token.json",
    "swc": "gmail-account2-token.json",
    "ikincil": "gmail-account2-token.json",
}

TOKEN_ENV_VARS = {
    "account1": "GOOGLE_ACCOUNT1_TOKEN_JSON",
    "account2": "GOOGLE_ACCOUNT2_TOKEN_JSON",
    "outreach": "GOOGLE_ACCOUNT1_TOKEN_JSON",
    "swc": "GOOGLE_ACCOUNT2_TOKEN_JSON",
    "ikincil": "GOOGLE_ACCOUNT2_TOKEN_JSON",
}

ALL_SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/spreadsheets',
]

def _get_credentials(account: str = "account1") -> Credentials:
    if account not in TOKEN_FILES:
        raise ValueError(f"Bilinmeyen hesap: '{account}'")

    env_var = TOKEN_ENV_VARS[account]
    
    # 1) Token dosyasını ara (hem yerel dizinde hem de _knowledge dizininde)
    token_path = os.path.join(OAUTH_DIR, TOKEN_FILES[account])
    if not os.path.exists(token_path):
        # Arama yapmak için üst klasörleri tara
        curr = OAUTH_DIR
        for _ in range(5):
            candidate = os.path.join(curr, "_knowledge", "credentials", "oauth", TOKEN_FILES[account])
            if os.path.exists(candidate):
                token_path = candidate
                break
            curr = os.path.dirname(curr)

    loaded_from = None
    creds = None

    # 2) Dosya varsa oradan yükle
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, ALL_SCOPES)
        loaded_from = "file"
    # 3) Yoksa env variable'dan yükle (Railway/Cloud)
    elif os.environ.get(env_var):
        token_json = json.loads(os.environ[env_var])
        creds = Credentials.from_authorized_user_info(token_json, ALL_SCOPES)
        loaded_from = "env"
    else:
        raise FileNotFoundError(
            f"Token bulunamadı: Ne dosya ({token_path}) ne de env ({env_var}) mevcut."
        )

    # Token yenileme kontrolü
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            if loaded_from == "file":
                _save_token(creds, token_path)
        else:
            raise RuntimeError("Token geçersiz ve yenilenemiyor.")

    return creds

def _save_token(creds: Credentials, token_path: str):
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else ALL_SCOPES,
        "universe_domain": "googleapis.com",
        "account": "",
        "expiry": creds.expiry.isoformat() + "Z" if creds.expiry else None,
    }
    with open(token_path, 'w') as f:
        json.dump(token_data, f, indent=2)

def get_gmail_service(account: str = "account1"):
    return build('gmail', 'v1', credentials=_get_credentials(account))

def get_sheets_service(account: str = "account1"):
    return build('sheets', 'v4', credentials=_get_credentials(account))

def get_drive_service(account: str = "account1"):
    return build('drive', 'v3', credentials=_get_credentials(account))
