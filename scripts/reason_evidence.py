"""Run permission-gated financial calculations on Step 8 JSON."""
import argparse
from reasoning.engine import reason_file

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',required=True,help='Step 8 JSON')
    parser.add_argument('--output',required=True,help='Reasoning output JSON')
    parser.add_argument('--as-of',dest='as_of',default=None,help='YYYY-MM-DD observation cutoff')
    args=parser.parse_args()
    result=reason_file(args.input,args.output,args.as_of)
    print(f'Status: {result["assessment_status"]}; findings: {len(result["findings"])}; output: {args.output}')

if __name__=='__main__': main()
