#!/usr/bin/env python3
"""
make_examples.py - writes examples/pairs.csv, then judges it with the
simulated judge to write examples/judged.csv.

    python make_examples.py
    python judge_check.py analyse examples/judged.csv

The pairs are synthetic: a generic question and two answers made of neutral
filler sentences, counted by words. Two comparisons:

    matched     x and y within a few words of each other, so the simulated
                judge's lean to slot A decides them; two items have identical
                answers, which the judge declines to rank
    x_longer    x half again as long as y, so the answer decides them

Deterministic: the same files every time.
"""

import csv
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "examples")
SENTENCES = ["Start with the simplest version that works.",
             "Check the result against a case you already know.",
             "Write down what you expect before you look.",
             "Keep the steps small enough to undo.",
             "Measure once more after the change.",
             "Leave a note for whoever reads this next.",
             "Prefer the boring option when two look equal.",
             "Stop when the question is answered, not before."]


def answer(rng, words):
    out = []
    while sum(len(s.split()) for s in out) < words:
        out.append(rng.choice(SENTENCES))
    return " ".join(out)


def main():
    os.makedirs(OUT, exist_ok=True)
    rng = random.Random(2026)
    pairs = os.path.join(OUT, "pairs.csv")
    with open(pairs, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["item", "question", "x", "y", "comparison"])
        for i in range(22):
            q = f"What is a sensible way to approach task {i + 1}?"
            if i < 2:
                x = y = answer(rng, 30)
            else:
                x, y = answer(rng, 28 + rng.randrange(5)), \
                    answer(rng, 28 + rng.randrange(5))
            w.writerow([f"m{i + 1:02d}", q, x, y, "matched"])
        for i in range(20):
            q = f"What is a sensible way to approach task {i + 23}?"
            w.writerow([f"l{i + 1:02d}", q, answer(rng, 45), answer(rng, 28),
                        "x_longer"])
    print(f"wrote {pairs}")
    judged = os.path.join(OUT, "judged.csv")
    if os.path.exists(judged):
        os.remove(judged)
    cmd = [sys.executable, os.path.join(HERE, "judge_check.py"), "run", pairs,
           "--command", f'"{sys.executable}" "{os.path.join(HERE, "demo_judge.py")}"',
           "--out", judged]
    subprocess.run(cmd, check=True)
    print(f"wrote {judged}")


if __name__ == "__main__":
    main()
