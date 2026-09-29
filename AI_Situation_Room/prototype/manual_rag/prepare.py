"""Explicit preparation: python -m prototype.manual_rag.prepare --help."""
import argparse
import json
from .corpus import Corpus, DEFAULT_SOURCE


def main():
    parser = argparse.ArgumentParser(description='공개 SAR 로컬 검색 준비 · 앱 실행과 분리')
    sub = parser.add_subparsers(dest='command', required=True)
    model = sub.add_parser('download-model'); model.add_argument('--output', required=True)
    build = sub.add_parser('build-index'); build.add_argument('--source', default=str(DEFAULT_SOURCE))
    build.add_argument('--model', required=True); build.add_argument('--output', required=True)
    audit = sub.add_parser('audit'); audit.add_argument('--source', default=str(DEFAULT_SOURCE))
    args = parser.parse_args()
    if args.command == 'download-model':
        from .embedding import download_model
        result = download_model(args.output)
    elif args.command == 'build-index':
        from .embedding import LocalEmbedder
        from .index import build_index
        result = build_index(Corpus(args.source), LocalEmbedder(args.model), args.output)
    else:
        corpus = Corpus(args.source)
        result = dict(generation=corpus.generation, curated_chunks=len(corpus.items),
                      source_pdfs=len(corpus.sources), original_pages=sum(s['pages'] for s in corpus.sources.values()),
                      scope='선별 한국어 요약 · 원문 전체 파싱/전문 검토 아님')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
