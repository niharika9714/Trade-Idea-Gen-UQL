"""Explicit local-only demo credential issuer; NOT a bank login or IdP."""
import argparse
import json
import secrets
from pathlib import Path
from skills.entitlements import issue_test_assertion

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--directory',type=Path,default=Path('demo_auth_13e'))
    p.add_argument('--subject',choices=['analyst-demo','viewer-demo'],default='analyst-demo')
    p.add_argument('--acknowledge-synthetic-only',action='store_true',required=True)
    a=p.parse_args()
    a.directory.mkdir(parents=True,exist_ok=True)
    secret=secrets.token_urlsafe(40).encode('ascii')
    policy={'analyst-demo':{'sources':['market_sql'],'skills':['equity_price_comparison'],
                            'tickers':['D05','O39']},
            'viewer-demo':{'sources':[],'skills':[],'tickers':[]}}
    token=issue_test_assertion(secret,subject=a.subject,lifetime_seconds=900)
    (a.directory/'secret.txt').write_text(secret.decode(),encoding='utf-8')
    (a.directory/'token.txt').write_text(token,encoding='utf-8')
    (a.directory/'policy.json').write_text(json.dumps(policy,indent=2),encoding='utf-8')
    print('Created LOCAL SYNTHETIC DEMO credentials (15-minute token). Never use with production bank data.')
    print('Credential directory:',a.directory)
    print('These files contain secrets: exclude directory from source control and delete after testing.')
if __name__=='__main__':main()
