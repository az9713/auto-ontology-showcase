"""P8 arm R: plain embedding search over the definition text (same hosted embedding model as auto-ontology).

  python -I search.py --build          # embed the L3 definitions + the 4 P7 term descriptions once (r_index.npy, r_ids.json)
  python -I search.py L1 "words ..."   # top 10 definitions of level L1 for the words (the agent's command)

Text per definition = the text auto-ontology embeds for a SQL attribute (dal/sql_attributes.py:742-747), without the term.
input_type passage for definitions, query for the search words, as auto-ontology does. Fixed before any run: top 10.
"""
import json, re, sys, time, urllib.error, urllib.request
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
TOP = 10
ENV = {k: v.split(" #")[0].strip().strip('"') for k, v in
       re.findall(r"^(EMBED_\w+)=(.*)$", (HERE.parent / "auto-ontology" / ".env").read_text(encoding="utf-8"), re.M)}


def embed(texts: list[str], input_type: str) -> np.ndarray:
    body = json.dumps({"model": ENV["EMBED_MODEL"].strip('"'), "input": texts, "encoding_format": "float",
                       "input_type": input_type, "truncate": "END"}).encode()
    req = urllib.request.Request(ENV["EMBED_ENDPOINT"].strip('"').rstrip("/") + "/embeddings", body,
                                 {"Content-Type": "application/json", "Authorization": "Bearer " + ENV["EMBED_API_KEY"].strip('"')})
    for attempt in range(6):
        try:
            data = json.load(urllib.request.urlopen(req, timeout=120))["data"]
            return np.array([d["embedding"] for d in sorted(data, key=lambda d: d["index"])], dtype=np.float32)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            if attempt == 5 or (isinstance(e, urllib.error.HTTPError) and e.code not in (408, 429, 500, 502, 503, 504)):
                raise
            time.sleep(5 * (attempt + 1))


def corpus() -> list[dict]:
    """L3 definitions + the 4 P7 term descriptions (fixed corpus entries in every level)."""
    pool = {d["id"]: d for d in json.loads((HERE / "pool.json").read_text(encoding="utf-8"))}
    ids = json.loads((HERE / "levels.json").read_text(encoding="utf-8"))["L3"]
    out = [dict(id=i, name=pool[i]["name"], description=pool[i]["description"], sql=pool[i]["sql"],
                text=f"sql_attribute: {pool[i]['name']}, description: {pool[i]['description']}, sql: {pool[i]['sql']}") for i in ids]
    sys.path.insert(0, str(HERE.parent / "p7"))
    import certify
    for k, (name, desc) in enumerate(certify.TERMS.values()):
        out.append(dict(id=f"t{k}", name=name, description=desc, sql=None, text=f"term: {name}, description: {desc}"))
    return out


if __name__ == "__main__":
    if sys.argv[1] == "--build":
        docs = corpus()
        vecs = np.concatenate([embed([d["text"] for d in docs[i:i + 32]], "passage") for i in range(0, len(docs), 32)])
        np.save(HERE / "r_index.npy", vecs)
        (HERE / "r_ids.json").write_text(json.dumps([d["id"] for d in docs]))
        print(f"embedded {len(docs)} texts, dim {vecs.shape[1]}")
        sys.exit()
    level, words = sys.argv[1], " ".join(sys.argv[2:])
    allowed = set(json.loads((HERE / "levels.json").read_text(encoding="utf-8"))[level])
    docs = {d["id"]: d for d in corpus()}
    ids = json.loads((HERE / "r_ids.json").read_text())
    vecs = np.load(HERE / "r_index.npy")
    keep = [k for k, i in enumerate(ids) if i in allowed or i.startswith("t")]
    v = vecs[keep]
    q = embed([words], "query")[0]
    sims = (v @ q) / (np.linalg.norm(v, axis=1) * np.linalg.norm(q))
    for rank, k in enumerate(np.argsort(-sims)[:TOP], 1):
        d = docs[ids[keep[k]]]
        print(f"{rank}. {d['name']} (score {sims[k]:.3f})\n   {d['description']}" + (f"\n   SQL: {d['sql']}" if d["sql"] else ""))
