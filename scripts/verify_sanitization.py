from ragger_engine.generation.service import GenerationService

text_dirty = 'The author was left with his grandmother in the village because his parents moved to the city for work. [chk_src_be62_sub37_00001_8f6bfee2] rag="11th General English EM Book 2019" version="v1" page="36"'
clean = GenerationService.sanitize_clean_answer(text_dirty)
print("CLEAN OUTPUT:", clean)
assert "[chk_" not in clean
assert "rag=" not in clean
assert "version=" not in clean
assert "page=" not in clean
assert "The author was left with his grandmother" in clean
print("SANITIZATION AUDIT: PASS")
