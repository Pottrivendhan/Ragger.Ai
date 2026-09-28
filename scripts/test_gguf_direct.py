import asyncio
import time
from ragger_engine.generation.providers.gguf import LocalGGUFLLMProvider

async def main():
    model_ref = 'qwen2.5-1.5b-instruct:gguf:q4_k_m-v1'
    p = LocalGGUFLLMProvider(model_ref)
    p.validate_availability()
    print("✓ Model availability validated:", p._resolve_model_path())

    prompt = "User: Say hello in 3 words.\nAssistant:"
    print("✓ Running test inference...")
    tokens = []
    cancel = asyncio.Event()
    t0 = time.time()
    async for token in p.generate_stream(prompt, max_tokens=15, temperature=0.1, cancel_event=cancel):
        tokens.append(token)
        print(f"Token: {repr(token)}")
    full_text = "".join(tokens)
    print(f"\n✓ Generated in {time.time() - t0:.2f}s: {full_text}")

if __name__ == "__main__":
    asyncio.run(main())
