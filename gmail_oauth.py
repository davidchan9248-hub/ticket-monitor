#!/usr/bin/env python3
"""
Gmail OAuth 授权 + 读取球票邮件
"""
import os
import sys
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
TOKEN_FILE = '/Users/dv/.openclaw/workspace/ticket-monitor/gmail_token.pickle'
CREDS_FILE = '/Users/dv/.openclaw/workspace/ticket-monitor/credentials.json'

CLIENT_ID = 'YOUR_CLIENT_ID.apps.googleusercontent.com'
CLIENT_SECRET = 'YOUR_CLIENT_SECRET'

# 如果还没有 credentials.json，先创建（手动填入）
if not os.path.exists(CREDS_FILE):
    print("需要先创建 credentials.json")
    print(f"请创建文件: {CREDS_FILE}")
    print(f"内容:\n{{\"web\":{{\"client_id\":\"{CLIENT_ID}\",\"client_secret\":\"{CLIENT_SECRET}\",\"auth_uri\":\"https://accounts.google.com/o/oauth2/auth\",\"token_uri\":\"https://oauth2.googleapis.com/token\"}}}}")
    sys.exit(1)

def get_gmail_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDS_FILE, SCOPES,
                redirect_uri='http://localhost:8080'
            )
            # 使用手动授权模式（不自动打开浏览器）
            auth_url, _ = flow.authorization_url(access_type='offline', prompt='consent')
            print(f"\n请在浏览器打开以下链接授权：\n{auth_url}\n")
            code = input("授权完成后，浏览器会跳转到 localhost，把地址栏里的 code 参数复制到这里粘贴：").strip()
            flow.fetch_token(code=code)
            creds = flow.credentials

        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)
        print("Token 已保存！\n")

    return build('gmail', 'v1', credentials=creds)

def search_ticket_emails(service):
    clubs = {
        'arsenal': 'from:(arsenal.com OR arsenal.london)',
        'chelsea': 'from:(chelseafc.com OR chelseafootballclub.com)',
        'man_u': 'from:(manutd.com OR manchesterunited.com)',
        'tottenham': 'from:(tottenhamhotspur.com)',
        'man_city': 'from:(mancity.com OR manchester-city.com)',
        'newcastle': 'from:(nufc.co.uk OR newcastleunited.com)',
    }

    all_results = {}

    for club, query in clubs.items():
        try:
            results = service.users().messages().list(
                userId='me',
                q=f'{query} subject:(ticket OR sale OR ballot OR 票)',
                maxResults=5
            ).execute()
            msgs = results.get('messages', [])
            all_results[club] = msgs
            print(f"[{club}] 找到 {len(msgs)} 封邮件")
        except Exception as e:
            print(f"[{club}] 搜索失败: {e}")
            all_results[club] = []

    return all_results

def fetch_email_details(service, msg_id):
    try:
        msg = service.users().messages().get(userId='me', id=msg_id, format='metadata').execute()
        headers = msg['payload']['headers']
        subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '')
        date = next((h['value'] for h in headers if h['name'].lower() == 'date'), '')
        snippet = msg.get('snippet', '')
        return {'subject': subject, 'date': date, 'snippet': snippet}
    except Exception as e:
        return {'error': str(e)}

if __name__ == '__main__':
    print("=" * 50)
    print("Gmail 球票邮件监控")
    print("=" * 50)

    service = get_gmail_service()
    print("\n读取邮件中...\n")

    results = search_ticket_emails(service)

    print("\n" + "=" * 50)
    print("邮件详情：")
    print("=" * 50)

    club_names = {
        'arsenal': '阿森纳',
        'chelsea': '切尔西',
        'man_u': '曼联',
        'tottenham': '热刺',
        'man_city': '曼城',
        'newcastle': '纽卡斯尔',
    }

    for club, msgs in results.items():
        print(f"\n{club_names.get(club, club)} ({club}):")
        if not msgs:
            print("  无新邮件")
        for m in msgs[:3]:
            detail = fetch_email_details(service, m['id'])
            print(f"  📧 [{detail.get('date','')}] {detail.get('subject','无标题')}")
            print(f"     {detail.get('snippet','')[:100]}")
