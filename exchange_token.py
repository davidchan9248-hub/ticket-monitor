#!/usr/bin/env python3
"""
直接用 auth code 换 token
"""
import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
TOKEN_FILE = '/Users/dv/.openclaw/workspace/ticket-monitor/gmail_token.pickle'
CREDS_FILE = '/Users/dv/.openclaw/workspace/ticket-monitor/credentials.json'

CLIENT_ID = 'YOUR_CLIENT_ID.apps.googleusercontent.com'
CLIENT_SECRET = 'YOUR_CLIENT_SECRET'

# 手动构造 creds 对象并换 token
from google.oauth2.credentials import Credentials

code = input("请粘贴 Google 返回的 code（?code=后面那串）: ").strip()

creds = Credentials.from_authorized_user_info(
    info={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "token_uri": "https://oauth2.googleapis.com/token",
        "refresh_uri": "https://oauth2.googleapis.com/token",
        "redirect_uri": "http://localhost",
    },
    scopes=SCOPES
)

# 用 code 换 token
import requests
resp = requests.post(
    "https://oauth2.googleapis.com/token",
    data={
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": "http://localhost",
        "grant_type": "authorization_code",
    }
)
print(resp.json())

if resp.status_code == 200:
    token_data = resp.json()
    creds.token = token_data.get("access_token")
    creds.refresh_token = token_data.get("refresh_token")
    creds._id_token = token_data.get("id_token")
    creds.expiry = None

    with open(TOKEN_FILE, 'wb') as f:
        pickle.dump(creds, f)
    print(f"\n✅ Token 已保存到 {TOKEN_FILE}")
    print(f"Access token: {token_data.get('access_token', '')[:30]}...")
