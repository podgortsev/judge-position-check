#!/usr/bin/env python3
"""
judge_check.py - how many of a model judge's conclusions survive swapping the
order of the two answers.

    python judge_check.py run pairs.csv --command "<your judge>" --out judged.csv
    python judge_check.py analyse judged.csv [--json report.json]

Exit codes, so it can sit in a pipeline:
    0   the conclusions in the reported order survive the swap, or there was
        no significant conclusion to test
    2   the judge is position-bound, or at least one conclusion that was
        significant in the reported order is not after the swap
    1   the input could not be used, or the judge command failed

No dependencies beyond the Python standard library. The tool itself makes no
network connection; the judge command you pass may, and that is yours.

THE PROBLEM
-----------
A model asked "which of these two answers is better, A or B" favours whichever
answer it saw first. The preference can run far above fifty percent and it
does not cancel when the two orders are averaged, because a parsed choice sits
at a ceiling: a read that is A in both orders is one item decided by the slot,
and averaging it with itself gives the slot again. A result that holds in one
order only belongs to the position, not to the answer.

THE TEST
--------
Every pair is judged twice, X first and then Y first. Per item:

    content X    X wins in both orders
    content Y    Y wins in both orders
    slot A       the first slot wins in both orders: the item is decided by
                 position, not by the answer
    slot B       the second slot wins in both orders
    incomplete   at least one read had no usable letter

The conclusions a single-order study would have reported are then set beside
what survives: the sign test on X against Y in the reported order (X shown
first), the same in the other order, and the same on the items that agree in
both orders. The first-slot win rate is reported with an exact binomial test
against one half. Several comparisons in one file are corrected with
Benjamini-Hochberg, separately for the reported-order tests and the
swap-consistent tests.

VERDICT, fixed before any data is read
--------------------------------------
    POSITION-BOUND      more items are decided by the slot than by the answer
    DOES NOT SURVIVE    a comparison significant in the reported order is not
                        significant in the same direction after the swap
    SURVIVES            every comparison significant in the reported order is
                        also significant, same direction, after the swap
    NOTHING TO TEST     no comparison is significant in the reported order

INPUT TO run: pairs.csv
-----------------------
    item,x,y                 required
    question,comparison      optional: the question both answers address, and
                             a name grouping items into one comparison

The judge is a shell command. It receives one prompt on standard input and
must print its reply on standard output. The prompt is built from a template
with {question}, {a} and {b}; the default one is below, --template names a
file holding another. The run is resumable: rows already in --out are not
judged again.

The reply is parsed in this order: a reply that is just A or B; "Answer A" or
"Answer B"; otherwise the first standalone A or B. No letter gives an empty
choice, which counts as incomplete and is never guessed.

INPUT TO analyse: judged.csv, as written by run
-----------------------------------------------
    item,order,reply,choice,comparison
    order    xy (X was shown as A) or yx (Y was shown as A)
    choice   A, B or empty
"""

import csv
import json
import math
import os
import re
import subprocess
import sys

PAIR_COLS = ["item", "x", "y"]
JUDGED_COLS = ["item", "order", "reply", "choice"]
ORDERS = ("xy", "yx")
ALPHA = 0.05
MIN_ITEMS = 20
INCOMPLETE_WARN = 0.2
DEFAULT_TEMPLATE = ("Here are two answers to the same question.\n\n"
                    "Question: {question}\n\n"
                    "Answer A:\n{a}\n\n"
                    "Answer B:\n{b}\n\n"
                    "Which answer is better? Reply with the single letter A "
                    "or B.")


_WRAP = 118
_print = print


def print(*args, **kwargs):
    """No report line runs past the report's width: a longer one is wrapped
    at spaces, and what follows is indented under it."""
    if len(args) != 1 or kwargs.get("file") is not None:
        return _print(*args, **kwargs)
    for line in str(args[0]).split("\n"):
        if len(line) <= _WRAP:
            _print(line, **kwargs)
            continue
        lead = line[:len(line) - len(line.lstrip(" "))][:_WRAP // 2]
        pad = lead + "  "
        cur = lead
        for word in line[len(lead):].split(" "):
            if len(cur) + len(word) > _WRAP and cur.strip():
                _print(cur.rstrip(), **kwargs)
                cur = pad
            while len(cur) + len(word) > _WRAP:
                room = _WRAP - len(cur)
                _print(cur + word[:room], **kwargs)
                word, cur = word[room:], pad
            cur += word + " "
        if cur.strip():
            _print(cur.rstrip(), **kwargs)


def finite(o):
    """JSON has no NaN or Infinity: a number that is not finite is written
    as null."""
    if isinstance(o, float):
        return o if o == o and o not in (float("inf"), float("-inf")) else None
    if isinstance(o, dict):
        return {k: finite(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [finite(v) for v in o]
    return o


csv.field_size_limit(2 ** 31 - 1)     # a long field is data, not an error


class Rows(csv.DictReader):
    """csv.DictReader that refuses what it would otherwise hide: a quote
    that never closes, and a row with more fields than the header, whose
    extra fields it would drop."""

    def __init__(self, f):
        super().__init__(f, strict=True)

    def __next__(self):
        row = super().__next__()
        if None in row:
            raise csv.Error(f"line {self.line_num} has more fields than "
                            f"the header")
        return row


class InputError(ValueError):
    pass


# ------------------------------------------------------------------ reading

def open_csv(path):
    try:
        return open(path, newline="", encoding="utf-8-sig")
    except OSError as e:
        raise InputError(f"cannot open {path}: {e}")


def read_pairs(path):
    with open_csv(path) as f:
        rd = Rows(f)
        missing = [c for c in PAIR_COLS if c not in (rd.fieldnames or [])]
        if missing:
            raise InputError(f"missing columns: {', '.join(missing)}. "
                             f"Expected: {','.join(PAIR_COLS)} with optional "
                             f"question and comparison")
        rows, seen = [], set()
        for line, r in enumerate(rd, start=2):
            item = (r["item"] or "").strip()
            comp = (r.get("comparison") or "").strip() or "all"
            if not item:
                raise InputError(f"line {line}: item cannot be empty")
            if (comp, item) in seen:
                raise InputError(f"line {line}: item {item} appears twice in "
                                 f"comparison {comp}")
            if not (r["x"] or "").strip() or not (r["y"] or "").strip():
                raise InputError(f"line {line}: x and y cannot be empty")
            seen.add((comp, item))
            rows.append({"item": item, "x": r["x"], "y": r["y"],
                         "question": r.get("question") or "",
                         "comparison": comp})
    if not rows:
        raise InputError("the pairs file has no rows")
    return rows


def read_judged(path):
    """Returns {comparison: {item: {order: choice}}} in file order."""
    with open_csv(path) as f:
        rd = Rows(f)
        missing = [c for c in JUDGED_COLS if c not in (rd.fieldnames or [])]
        if missing:
            raise InputError(f"missing columns: {', '.join(missing)}. "
                             f"Expected: {','.join(JUDGED_COLS)} with "
                             f"optional comparison")
        data = {}
        for line, r in enumerate(rd, start=2):
            item = (r["item"] or "").strip()
            order = (r["order"] or "").strip().lower()
            choice = (r["choice"] or "").strip().upper()
            comp = (r.get("comparison") or "").strip() or "all"
            if not item:
                raise InputError(f"line {line}: item cannot be empty")
            if order not in ORDERS:
                raise InputError(f"line {line}: order must be xy or yx, got "
                                 f"{r['order']!r}")
            if choice not in ("A", "B", ""):
                raise InputError(f"line {line}: choice must be A, B or "
                                 f"empty, got {r['choice']!r}")
            entry = data.setdefault(comp, {}).setdefault(item, {})
            if order in entry:
                raise InputError(f"line {line}: item {item} has order {order} "
                                 f"twice in comparison {comp}")
            entry[order] = choice
    if not data:
        raise InputError("the judged file has no rows")
    return data


# ---------------------------------------------------------------- the judge

def parse_choice(reply):
    text = reply.strip()
    if re.fullmatch(r"[\"'(\[]*([AB])[\"')\].:!]*", text):
        return re.fullmatch(r"[\"'(\[]*([AB])[\"')\].:!]*", text).group(1)
    m = re.search(r"\bAnswer ([AB])\b", text)
    if m:
        return m.group(1)
    m = re.search(r"(?<![A-Za-z])([AB])(?![A-Za-z])", text)
    return m.group(1) if m else ""


def build_prompt(template, row, order):
    a, b = (row["x"], row["y"]) if order == "xy" else (row["y"], row["x"])
    return template.format(question=row["question"], a=a, b=b)


def ask(command, prompt, timeout):
    try:
        done = subprocess.run(command, shell=True, input=prompt,
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        raise InputError(f"the judge command took longer than {timeout} "
                         f"seconds")
    if done.returncode != 0:
        err = (done.stderr or "").strip().splitlines()
        raise InputError(f"the judge command exited with {done.returncode}"
                         + (f": {err[-1]}" if err else ""))
    return done.stdout


def run(pairs_path, command, out_path, template=None, timeout=120,
        log=print):
    rows = read_pairs(pairs_path)
    template = template or DEFAULT_TEMPLATE
    for key in ("{a}", "{b}"):
        if key not in template:
            raise InputError(f"the template must contain {key}")
    done = set()
    if os.path.exists(out_path):
        for comp, items in read_judged(out_path).items():
            for item, orders in items.items():
                for order in orders:
                    done.add((comp, item, order))
    new = not os.path.exists(out_path) or os.path.getsize(out_path) == 0
    todo = [(r, o) for r in rows for o in ORDERS
            if (r["comparison"], r["item"], o) not in done]
    log(f"{len(rows)} pairs, {len(todo)} reads to do, {len(done)} already in "
        f"{out_path}")
    with open(out_path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(JUDGED_COLS + ["comparison"])
        for n, (r, order) in enumerate(todo, start=1):
            reply = ask(command, build_prompt(template, r, order), timeout)
            w.writerow([r["item"], order, reply.strip(), parse_choice(reply),
                        r["comparison"]])
            f.flush()
            if n % 20 == 0 or n == len(todo):
                log(f"  {n} of {len(todo)}")
    return len(todo)


# ---------------------------------------------------------------- statistics

def binom_two_sided(k, n):
    """Exact two-sided binomial test of k successes in n against one half."""
    if n == 0:
        return 1.0
    kk = min(k, n - k)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(kk + 1)) / 2 ** n)


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def bh(pvals):
    n = len(pvals)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: pvals[i])
    adj = [0.0] * n
    prev = 1.0
    for rank, i in enumerate(reversed(order)):
        prev = min(prev, pvals[i] * n / (n - rank))
        adj[i] = prev
    return adj


def sign_test(x_wins, y_wins):
    n = x_wins + y_wins
    return {"x": x_wins, "y": y_wins, "n": n,
            "x_share": x_wins / n if n else float("nan"),
            "p": binom_two_sided(x_wins, n),
            "direction": "X" if x_wins > y_wins else "Y" if y_wins > x_wins
            else ""}


# ------------------------------------------------------------------ analysis

def classify(orders):
    cxy, cyx = orders.get("xy", ""), orders.get("yx", "")
    if cxy not in ("A", "B") or cyx not in ("A", "B"):
        return "incomplete"
    wxy = "X" if cxy == "A" else "Y"
    wyx = "X" if cyx == "B" else "Y"
    if wxy == wyx:
        return "content_x" if wxy == "X" else "content_y"
    return "slot_a" if cxy == "A" else "slot_b"


def analyse(data):
    comps = []
    for comp, items in data.items():
        cats = {k: 0 for k in ("content_x", "content_y", "slot_a", "slot_b",
                               "incomplete")}
        a_reads = reads = 0
        xy_x = xy_y = yx_x = yx_y = 0
        for orders in items.values():
            cats[classify(orders)] += 1
            for order, c in orders.items():
                if c in ("A", "B"):
                    reads += 1
                    a_reads += c == "A"
                    x_won = (c == "A") == (order == "xy")
                    if order == "xy":
                        xy_x += x_won
                        xy_y += not x_won
                    else:
                        yx_x += x_won
                        yx_y += not x_won
        comps.append({
            "comparison": comp, "items": len(items), "categories": cats,
            "survive": cats["content_x"] + cats["content_y"],
            "slot": cats["slot_a"] + cats["slot_b"],
            "first_slot": {"a": a_reads, "reads": reads,
                           "rate": a_reads / reads if reads else float("nan"),
                           "ci": wilson(a_reads, reads),
                           "p": binom_two_sided(a_reads, reads)},
            "reported_order": sign_test(xy_x, xy_y),
            "other_order": sign_test(yx_x, yx_y),
            "consistent": sign_test(cats["content_x"], cats["content_y"]),
        })
    for key in ("reported_order", "consistent"):
        for c, a in zip(comps, bh([c[key]["p"] for c in comps])):
            c[key]["p_adj"] = a
    for c in comps:
        rep, con = c["reported_order"], c["consistent"]
        c["significant_reported"] = rep["p_adj"] < ALPHA
        c["survives"] = (c["significant_reported"] and con["p_adj"] < ALPHA
                         and con["direction"] == rep["direction"])
        c["status"] = ("survives" if c["survives"]
                       else "does not survive" if c["significant_reported"]
                       else "no conclusion in the reported order")

    slot_total = sum(c["slot"] for c in comps)
    content_total = sum(c["survive"] for c in comps)
    sig = [c for c in comps if c["significant_reported"]]
    survived = [c for c in sig if c["survives"]]
    if slot_total > content_total:
        verdict = "POSITION-BOUND"
    elif not sig:
        verdict = "NOTHING TO TEST"
    elif len(survived) == len(sig):
        verdict = "SURVIVES"
    else:
        verdict = "DOES NOT SURVIVE"

    warnings = []
    for c in comps:
        if c["items"] < MIN_ITEMS:
            warnings.append(f"{c['comparison']} has {c['items']} items; "
                            f"below {MIN_ITEMS} the sign test has little "
                            f"power")
        inc = c["categories"]["incomplete"]
        if c["items"] and inc / c["items"] > INCOMPLETE_WARN:
            warnings.append(f"{c['comparison']}: {inc} of {c['items']} items "
                            f"have a read with no usable letter. The judge "
                            f"did not answer in the format on those; they "
                            f"are counted, not guessed")
    return {"verdict": verdict, "comparisons": comps,
            "slot_total": slot_total, "content_total": content_total,
            "significant_reported": len(sig), "survived": len(survived),
            "warnings": warnings,
            "passed": verdict in ("SURVIVES", "NOTHING TO TEST")}


# -------------------------------------------------------------------- report

def print_report(res):
    w = 96
    print("=" * w)
    print("JUDGE POSITION CHECK")
    print("=" * w)
    print()
    print("  PER ITEM: who wins in both orders")
    print(f"  {'comparison':20}{'items':>6}{'content X':>10}{'content Y':>10}"
          f"{'slot A':>8}{'slot B':>8}{'incompl.':>9}{'survive':>9}")
    for c in res["comparisons"]:
        k = c["categories"]
        print(f"  {c['comparison'][:19]:20}{c['items']:6}{k['content_x']:10}"
              f"{k['content_y']:10}{k['slot_a']:8}{k['slot_b']:8}"
              f"{k['incomplete']:9}{c['survive']:9}")
    print()
    print("  FIRST SLOT: share of reads that chose A, exact binomial against "
          "one half")
    for c in res["comparisons"]:
        fs = c["first_slot"]
        lo, hi = fs["ci"]
        if not fs["reads"]:
            print(f"  {c['comparison'][:19]:20}no read chose A or B")
            continue
        print(f"  {c['comparison'][:19]:20}{fs['a']:5} of {fs['reads']:4} = "
              f"{fs['rate']:6.1%}  [{lo:5.1%}, {hi:5.1%}]  p {fs['p']:.3g}")
    print()
    print("  CONCLUSIONS: X against Y by sign test, BH across comparisons")
    print(f"  {'comparison':20}{'reported order':>20}{'p adj':>8}"
          f"{'other order':>17}{'p':>8}{'both orders':>17}{'p adj':>8}"
          f"  status")
    for c in res["comparisons"]:
        r, o, k = c["reported_order"], c["other_order"], c["consistent"]
        print(f"  {c['comparison'][:19]:20}"
              f"{'X ' + str(r['x']) + ' : ' + str(r['y']) + ' Y':>20}"
              f"{r['p_adj']:8.3f}"
              f"{'X ' + str(o['x']) + ' : ' + str(o['y']) + ' Y':>17}"
              f"{o['p']:8.3f}"
              f"{'X ' + str(k['x']) + ' : ' + str(k['y']) + ' Y':>17}"
              f"{k['p_adj']:8.3f}  {c['status']}")
    print()
    print("-" * w)
    v = res["verdict"]
    if v == "POSITION-BOUND":
        print(f"  VERDICT: POSITION-BOUND. {res['slot_total']} items are "
              f"decided by the slot, {res['content_total']} by the answer.")
        print("  This judge's choice belongs to the position more often than "
              "to the content. No")
        print("  conclusion read from it in one order is about the answers.")
    elif v == "NOTHING TO TEST":
        print("  VERDICT: NOTHING TO TEST. No comparison is significant in "
              "the reported order, so")
        print("  there is no single-order conclusion for the swap to "
              "confirm or remove.")
    elif v == "SURVIVES":
        print(f"  VERDICT: SURVIVES. {res['survived']} of "
              f"{res['significant_reported']} conclusions significant in the "
              f"reported order hold, same")
        print("  direction, on the items that agree in both orders.")
    else:
        print(f"  VERDICT: DOES NOT SURVIVE. {res['survived']} of "
              f"{res['significant_reported']} conclusions significant in the "
              f"reported order hold")
        print("  after the swap. The rest belonged to the slot. Report only "
              "the both-orders column.")
    for msg in res["warnings"]:
        print(f"  WARNING: {msg}")
    print("-" * w)


# ---------------------------------------------------------------------- main

def take(args, flag, default=None):
    if flag in args:
        i = args.index(flag)
        if i + 1 >= len(args):
            raise InputError(f"{flag} needs a value")
        val = args[i + 1]
        del args[i:i + 2]
        return val
    return default


USAGE = ("usage: judge_check.py run pairs.csv --command CMD --out judged.csv "
         "[--template FILE] [--timeout SECONDS]\n"
         "       judge_check.py analyse judged.csv [--json report.json]")


def run_main(argv):
    args = list(argv)
    try:
        if not args:
            raise InputError(USAGE)
        mode = args.pop(0)
        if mode == "run":
            command = take(args, "--command")
            out = take(args, "--out")
            template_path = take(args, "--template")
            traw = take(args, "--timeout", "120")
            try:
                timeout = float(traw)
            except ValueError:
                raise InputError(f"--timeout must be a number of seconds, "
                                 f"got {traw!r}")
            if not 0 < timeout <= 86400:
                raise InputError("--timeout must be above 0 and at most "
                                 "86400 seconds")
            if len(args) != 1 or not command or not out:
                raise InputError(USAGE)
            template = None
            if template_path:
                with open_csv(template_path) as f:
                    template = f.read()
            run(args[0], command, out, template, timeout)
            return 0
        if mode == "analyse":
            json_out = take(args, "--json")
            if len(args) != 1:
                raise InputError(USAGE)
            res = analyse(read_judged(args[0]))
            print_report(res)
            if json_out:
                with open(json_out, "w", encoding="utf-8") as f:
                    json.dump(finite(res), f, indent=2)
            return 0 if res["passed"] else 2
        raise InputError(USAGE)
    except UnicodeDecodeError as e:
        print(f"input not usable: a file is not UTF-8 text (byte {e.start}); "
              f"save it as UTF-8 and run again", file=sys.stderr)
        return 1
    except csv.Error as e:
        print(f"input not usable: a file cannot be read as CSV: {e}",
              file=sys.stderr)
        return 1
    except InputError as e:
        print(f"input not usable: {e}" if str(e) != USAGE else USAGE,
              file=sys.stderr)
        return 1


def main(argv):
    try:
        return run_main(argv)
    except OSError as e:
        print(f"input not usable: a file cannot be read or written: {e}",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    sys.exit(main(sys.argv[1:]))
