"""Port-type reordering and the GTool per-request scoring protocol."""
import itertools
import json
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split
from .reference_rules import ROOT


def f1(pred, target):
    tp = sum(x in target for x in pred)
    fp = sum(x not in target for x in pred)
    fn = sum(x not in pred for x in target)
    return 2 * tp / (2 * tp + fp + fn) if tp else 0


def lcs(p, q):
    row = [0] * (1 + len(q))
    for a in p:
        previous = row.copy()
        for j, b in enumerate(q, 1):
            row[j] = previous[j - 1] + 1 if a == b else max(previous[j], row[j - 1])
    return row[-1]


def evaluate(a, b):
    return [
        f1(a, b),
        f1(list(zip(a, a[1:])), list(zip(b, b[1:]))),
        1 - 2 * lcs(a, b) / (len(a) + len(b)),
    ]


def evaluate_split(dataset):
    raw = [
        json.loads(line)
        for line in dataset.read_text(encoding="utf8").splitlines()
        if line.strip()
    ]
    tools = json.loads((ROOT / "tools.json").read_text(encoding="utf8"))["nodes"]
    names = [t["id"].lower() for t in tools]
    ins = [set(t["input-type"]) for t in tools]
    outs = [set(t["output-type"]) for t in tools]
    # Use the evaluation split specified by GTool.
    train, rest = train_test_split(np.arange(len(raw)), test_size=0.4, random_state=42)
    val, test = train_test_split(rest, test_size=0.5, random_state=42)
    # Only tool catalogue texts are fitted.
    v = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
    cat = v.fit_transform(t["id"] + " " + t["desc"] for t in tools)
    scores = (v.transform(raw[i]["user_request"] for i in test) @ cat.T).toarray()
    rows = []
    for idx, ss in zip(test, scores):
        r = raw[idx]
        links = {e["source"]: e["target"] for e in r["task_links"]}
        start = next(n for n in links if n not in links.values())
        label = [start]
        while label[-1] in links:
            label.append(links[label[-1]])
        assert len(label) == len(links) + 1
        label = [s.lower() for s in label]
        cand = sorted(range(len(names)), key=lambda i: (-ss[i], names[i]))
        cand = [i for i in cand if ss[i] >= max(0.08, 0.6 * ss[cand[0]])][:4]
        loc = {t: p for p, t in enumerate(cand)}

        def key(order):
            incompatible = sum(
                not bool(outs[i] & ins[j]) for i, j in zip(order, order[1:])
            )
            inversions = sum(
                loc[i] > loc[j] for i, j in itertools.combinations(order, 2)
            )
            return (incompatible, inversions, tuple(loc[i] for i in order))

        best = min(itertools.permutations(cand), key=key)
        a = [names[i] for i in cand]
        b = [names[i] for i in best]
        rows.append((a != b, evaluate(a, label), evaluate(b, label)))
    return dict(
        split_sizes=[len(train), len(val), len(test)],
        changed=sum(row[0] for row in rows),
        lexical=np.mean([row[1] for row in rows], axis=0).tolist(),
        typed=np.mean([row[2] for row in rows], axis=0).tolist(),
    )
