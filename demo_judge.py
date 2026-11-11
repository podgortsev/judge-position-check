#!/usr/bin/env python3
"""
demo_judge.py - a simulated judge, so judge_check.py can be tried without a
model. It is not a model and it measures nothing.

Reads one prompt on standard input and prints A or B. It prefers the longer
answer, and it leans to slot A by a fixed margin of a quarter, the way a real
judge leans to the first answer it sees. So two answers of similar length are
decided by the slot, two answers of clearly different length by the answer,
and two identical answers get no letter at all. Deterministic: the same
prompt always gets the same reply.

Replace it with your judge: any command that reads the prompt on standard
input and prints its reply.
"""

import re
import sys

SLOT_A_LEAN = 1.25


def main():
    prompt = sys.stdin.read()
    m = re.search(r"Answer A:\n(.*?)\n\nAnswer B:\n(.*?)\n\nWhich", prompt,
                  re.S)
    if not m:
        print("I cannot find two answers in this prompt.")
        return
    a, b = m.group(1), m.group(2)
    if a.strip() == b.strip():
        print("Both answers are the same, so neither is better.")
        return
    print("A" if len(a.split()) * SLOT_A_LEAN >= len(b.split()) else "B")


if __name__ == "__main__":
    main()
