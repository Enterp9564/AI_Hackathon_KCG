"""Measured retrieval only; passing this does not certify model advice."""
import argparse
import json
import math
from pathlib import Path
import socket
import time
from unittest.mock import patch
from .retrieval import ManualSearch


def summarize(rows):
    relevant = [r for r in rows if r['expected']]
    recall = sum(len(set(r['expected']) & set(r['found']))/len(set(r['expected'])) for r in relevant)/max(len(relevant),1)
    false_positives = sum(bool(r['found']) for r in rows if not r['expected'])
    failures = sum(r['status'] in ('error','unavailable') for r in rows)
    degraded = sum('degraded' in r.get('warnings',[]) for r in rows)
    times = sorted(r['latency_ms'] for r in rows)
    p95 = times[max(0, math.ceil(len(times)*.95)-1)] if times else 0
    return dict(cases=len(rows), recall=round(recall,4), false_positive_queries=false_positives,
                failures=failures, degraded=degraded, p95_ms=round(p95,2),
                passed=bool(rows and relevant) and recall>=.9 and not false_positives and not failures and not degraded and p95<=2000)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases',required=True); parser.add_argument('--mode',choices=('lexical','hybrid'),required=True)
    parser.add_argument('--index'); parser.add_argument('--output',required=True)
    parser.add_argument('--offline',action='store_true')
    args=parser.parse_args()
    def deny(*a,**k): raise OSError('network blocked for retrieval evaluation')
    from contextlib import nullcontext
    with (patch.object(socket.socket,'connect',deny) if args.offline else nullcontext()):
        started=time.monotonic()
        search=ManualSearch(mode=args.mode,index_dir=args.index)
        cold_ms=(time.monotonic()-started)*1000
        try:
            rows=[]
            for case in json.loads(Path(args.cases).read_text()):
                result=search.retrieve(case['query'],role='sar')
                rows.append(dict(**case,found=sorted({x['document_id'] for x in result['items']}),
                    ids=[x['chunk_id'] for x in result['items']],status=result['status'],
                    latency_ms=result['latency_ms'],warnings=result['warnings']))
            report=dict(mode=args.mode,offline=args.offline,generation=search.generation,
                ready_vector=search.ready_vector,cold_start_ms=round(cold_ms,2),metrics=summarize(rows),results=rows)
        finally:search.close()
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
