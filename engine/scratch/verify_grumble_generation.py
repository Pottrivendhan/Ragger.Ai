import asyncio
from pathlib import Path
from ragger_engine.generation.service import GenerationService
from ragger_engine.generation.models import ChatQueryRequest
from ragger_engine.retrieval.service import RetrievalService

async def main():
    retrieval_svc = RetrievalService(workspace_dir=Path('storage'))
    gen_svc = GenerationService(workspace_dir=Path('storage'), retrieval_service=retrieval_svc)

    req = ChatQueryRequest(
        query='The Grumble Family',
        top_k=5,
        temperature=0.1
    )

    print('Starting generation for [The Grumble Family]...')
    tokens = []
    final_resp = None
    async for event in gen_svc.stream_generation(request=req, workspace_id='default', build_id='bld_8706465c', persist_session=False):
        if event['event'] == 'token':
            tokens.append(event['data']['token'])
        elif event['event'] == 'done':
            final_resp = event['data']

    raw_text = ''.join(tokens)
    print('\n=== RAW GENERATED STREAM ===\n' + raw_text)
    print('\n=== FINAL ANSWER IN RESPONSE ===\n' + (final_resp['answer'] if final_resp else 'None'))
    print('\n=== CITATIONS ===')
    if final_resp:
        for c in final_resp.get('valid_citations', []):
            print(f"- {c['chunk_id']}: {c['citation_text']}")

if __name__ == '__main__':
    asyncio.run(main())
