"""Step 13E: guarded research using service-issued token; prototype only."""
import argparse
import json
import os
from pathlib import Path
from skills.binding import load_metadata_snapshot
from skills.guarded import run_guarded


def main():
    p=argparse.ArgumentParser(description='Step 13E guarded research (prototype trust adapter)')
    p.add_argument('query',nargs='+')
    p.add_argument('--as-of',required=True)
    p.add_argument('--source-db',type=Path,required=True)
    p.add_argument('--metadata-db',type=Path)
    p.add_argument('--metadata-snapshot',type=Path)
    p.add_argument('--documents-dir',type=Path)
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    # Secrets, grants and assertions must be injected by a trusted launcher.
    # These environment variables are NOT a bank identity integration.
    secret=os.environ.get('UQL_AUTH_SECRET','').encode()
    token=os.environ.get('UQL_AUTH_ASSERTION','')
    policy_file=os.environ.get('UQL_SERVICE_POLICY_FILE','')
    if len(secret)<32 or not token or not policy_file:
        result={'schema_version':'13E.1','status':'BLOCKED_TRUST_CONFIGURATION',
                'execution_authorized':False,'investment_recommendation_authorized':False}
    else:
        policy=json.loads(Path(policy_file).read_text(encoding='utf-8'))
        result=run_guarded(' '.join(args.query),load_metadata_snapshot(args.metadata_snapshot),
                    as_of=args.as_of,market_db=str(args.source_db),token=token,
                    signing_secret=secret,service_policy=policy,metadata_db=str(args.metadata_db) if args.metadata_db else None,
                    documents_dir=str(args.documents_dir) if args.documents_dir else None)
    payload=json.dumps(result,indent=2,ensure_ascii=False)
    print(payload)
    if args.output:
        args.output.write_text(payload,encoding='utf-8')
if __name__=='__main__':main()
