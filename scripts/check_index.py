"""One-shot proof script for index.json — mirrors the proof one-liner
in plan.md step 2, but written as a file so PowerShell doesn't have to
fight with nested quotes.
"""
import json
import sys

with open("index.json", encoding="utf-8") as f:
    d = json.load(f)

assert d["embedding_model"] == "openai/text-embedding-3-small", (
    f"wrong model: {d['embedding_model']}"
)
assert d["embedding_dim"] == 1536, f"wrong dim: {d['embedding_dim']}"

cs = d["chunks"]
assert isinstance(cs, list) and len(cs) > 0, "empty or wrong shape"

r = cs[0]
need = {"file_path", "section_heading", "text", "embedding"}
missing = need - set(r.keys())
assert not missing, f"missing keys: {missing}"
assert isinstance(r["embedding"], list) and len(r["embedding"]) == 1536, (
    f"wrong dim {len(r['embedding'])}"
)

print(
    f"{len(cs)} chunks; "
    f"first file_path={r['file_path']!r}; "
    f"first heading={r['section_heading']!r}"
)

# Spot-check a few more records so we know the heading attachment is consistent.
for r in cs[:5]:
    assert isinstance(r["text"], str) and r["text"], f"empty text in {r}"
    print(f"  {r['file_path']!r} > {r['section_heading']!r} ({len(r['text'])} chars)")
