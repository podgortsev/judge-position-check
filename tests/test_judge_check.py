#!/usr/bin/env python3
"""
test_judge_check.py - proves judge_check.py gives the right verdict on judged
data with a known structure, and that the run step drives a judge command
correctly, resumes, and refuses to guess.

    python tests/test_judge_check.py

No model is involved. The judge commands here are small Python scripts
written to a temporary folder, each with a known rule.
"""

import contextlib
import csv
import hashlib
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import judge_check as JC      # noqa: E402

PASS, FAIL = [], []


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)
PY = f'"{sys.executable}"'


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'ok  ' if cond else 'FAIL'}] {name}"
          f"{('  ' + detail) if detail else ''}")


def tmp(name):
    return os.path.join(tempfile.mkdtemp(), name)


def quiet_main(args):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return JC.main(args)


def judged_file(spec):
    """spec: list of (comparison, item, choice_xy, choice_yx); None skips
    that read entirely."""
    p = tmp("judged.csv")
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(JC.JUDGED_COLS + ["comparison"])
        for comp, item, cxy, cyx in spec:
            if cxy is not None:
                w.writerow([item, "xy", cxy, cxy, comp])
            if cyx is not None:
                w.writerow([item, "yx", cyx, cyx, comp])
    return p


def items(comp, n, cxy, cyx, start=0):
    return [(comp, f"{comp}{i + start}", cxy, cyx) for i in range(n)]


def md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def judge_script(body):
    p = tmp("judge.py")
    with open(p, "w", encoding="utf-8") as f:
        f.write("import sys\nprompt = sys.stdin.read()\n" + body + "\n")
    return f'{PY} "{p}"'


# ==========================================================================
print("=" * 70)
print("1. PARSING THE REPLY")
print("=" * 70)
cases = [("A", "A"), ("B.", "B"), (" b ", ""), ("(A)", "A"),
         ("Answer B", "B"), ("Answer B is better.", "B"),
         ("I think answer B is better", "B"), ("B is better than A", "B"),
         ("Neither.", ""), ("", ""), ("ABBA", ""), ("The first.", ""),
         ("A good answer is B", "A")]
for reply, want in cases:
    ok(f"parse {reply!r} -> {want!r}", JC.parse_choice(reply) == want,
       f"got {JC.parse_choice(reply)!r}")
print("   (the last case is the documented order: a bare A before a bare B)")

# ==========================================================================
print()
print("=" * 70)
print("2. STATISTICS")
print("=" * 70)
ok("binomial: 0 of 10 gives p = 2/1024",
   abs(JC.binom_two_sided(0, 10) - 2 / 1024) < 1e-12)
ok("binomial: 5 of 10 gives p = 1", JC.binom_two_sided(5, 10) == 1.0)
ok("binomial: 0 of 0 gives p = 1", JC.binom_two_sided(0, 0) == 1.0)
lo, hi = JC.wilson(50, 100)
ok("Wilson interval for 50 of 100 is about 40 to 60 percent",
   abs(lo - 0.403) < 0.01 and abs(hi - 0.597) < 0.01, f"[{lo:.3f}, {hi:.3f}]")
adj = JC.bh([0.001, 0.02, 0.5])
ok("BH is monotone and never below raw p",
   adj == sorted(adj) and all(a >= b for a, b in zip(adj, [0.001, 0.02, 0.5])))
ok("classify: X in both orders", JC.classify({"xy": "A", "yx": "B"})
   == "content_x")
ok("classify: Y in both orders", JC.classify({"xy": "B", "yx": "A"})
   == "content_y")
ok("classify: first slot in both orders", JC.classify({"xy": "A", "yx": "A"})
   == "slot_a")
ok("classify: second slot in both orders",
   JC.classify({"xy": "B", "yx": "B"}) == "slot_b")
ok("classify: a missing or empty read is incomplete",
   JC.classify({"xy": "A"}) == "incomplete"
   and JC.classify({"xy": "A", "yx": ""}) == "incomplete")

# ==========================================================================
print()
print("=" * 70)
print("3. VERDICTS ON JUDGED DATA WITH A KNOWN STRUCTURE")
print("=" * 70)
p = judged_file(items("c", 40, "A", "A"))
res = JC.analyse(JC.read_judged(p))
c = res["comparisons"][0]
ok("a judge that always picks the first slot is POSITION-BOUND",
   res["verdict"] == "POSITION-BOUND" and c["slot"] == 40
   and c["survive"] == 0)
ok("its first-slot rate is 100 percent and significant",
   c["first_slot"]["rate"] == 1.0 and c["first_slot"]["p"] < 1e-9)
ok("the reported order alone would have called X the winner",
   c["reported_order"]["x"] == 40 and c["reported_order"]["p_adj"] < 0.001)
ok("exit code 2", quiet_main(["analyse", p]) == 2)

p = judged_file(items("c", 35, "A", "B") + items("c", 5, "B", "A", 35))
res = JC.analyse(JC.read_judged(p))
c = res["comparisons"][0]
ok("a judge that reads the answer: 40 of 40 survive, X wins, SURVIVES",
   res["verdict"] == "SURVIVES" and c["survive"] == 40
   and c["consistent"]["x"] == 35 and c["consistent"]["p_adj"] < 0.001)
ok("its first-slot rate is one half",
   c["first_slot"]["rate"] == 0.5 and c["first_slot"]["p"] == 1.0)
ok("exit code 0", quiet_main(["analyse", p]) == 0)

p = judged_file(items("real", 30, "A", "B")
                + items("slot", 24, "A", "A") + items("slot", 6, "B", "A", 24))
res = JC.analyse(JC.read_judged(p))
by = {c["comparison"]: c for c in res["comparisons"]}
ok("two comparisons: one survives, one was the slot: DOES NOT SURVIVE",
   res["verdict"] == "DOES NOT SURVIVE" and by["real"]["survives"]
   and not by["slot"]["survives"] and by["slot"]["significant_reported"],
   f"slot reported p {by['slot']['reported_order']['p_adj']:.4f}, both "
   f"orders {by['slot']['consistent']['x']}:{by['slot']['consistent']['y']}")
ok("the summary counts 1 of 2", res["survived"] == 1
   and res["significant_reported"] == 2)
ok("not POSITION-BOUND: content 36 outnumbers slot 24",
   res["content_total"] == 36 and res["slot_total"] == 24)
ok("BH across comparisons: adjusted p is never below raw p",
   all(c[k]["p_adj"] >= c[k]["p"] for c in res["comparisons"]
       for k in ("reported_order", "consistent")))
ok("exit code 2", quiet_main(["analyse", p]) == 2)

p = judged_file(items("c", 15, "A", "B") + items("c", 15, "B", "A", 15))
res = JC.analyse(JC.read_judged(p))
ok("no significant single-order conclusion: NOTHING TO TEST, exit 0",
   res["verdict"] == "NOTHING TO TEST" and quiet_main(["analyse", p]) == 0)

p = judged_file(items("c", 30, "A", "B") + items("c", 6, "A", None, 30)
                + items("c", 4, "", "B", 36))
res = JC.analyse(JC.read_judged(p))
c = res["comparisons"][0]
ok("a missing read or an empty choice is incomplete, not guessed",
   c["categories"]["incomplete"] == 10 and c["survive"] == 30)
ok("more than a fifth incomplete is warned about",
   any("no usable letter" in w for w in res["warnings"]))
ok("a one-sided sign test at the same direction still survives there",
   res["verdict"] == "SURVIVES")
p = judged_file(items("c", 8, "A", "B"))
res = JC.analyse(JC.read_judged(p))
ok("few items is warned about",
   any("little power" in w for w in res["warnings"]))
jp = tmp("report.json")
quiet_main(["analyse", p, "--json", jp])
ok("--json writes the verdict",
   read_json(jp)["verdict"] in
   ("SURVIVES", "NOTHING TO TEST"))

# ==========================================================================
print()
print("=" * 70)
print("4. THE RUN STEP, with a judge command that has a known rule")
print("=" * 70)
pairs = tmp("pairs.csv")
with open(pairs, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["item", "question", "x", "y"])
    for i in range(10):
        w.writerow([f"i{i}", f"q{i}", "the marked one ZZZ", "the plain one"])
content_judge = judge_script(
    'a = prompt.split("Answer A:")[1].split("Answer B:")[0]\n'
    'print("Answer A" if "ZZZ" in a else "Answer B")')
out = tmp("judged.csv")
with contextlib.redirect_stdout(io.StringIO()):
    n = JC.run(pairs, content_judge, out)
data = JC.read_judged(out)
ok("every pair is judged in both orders", n == 20
   and all(set(o) == {"xy", "yx"} for o in data["all"].values()))
ok("the choices follow the judge's rule, so X wins in both orders",
   all(o["xy"] == "A" and o["yx"] == "B" for o in data["all"].values()))
first = md5(out)
with contextlib.redirect_stdout(io.StringIO()):
    n = JC.run(pairs, content_judge, out)
ok("a second run finds nothing to do and leaves the file unchanged",
   n == 0 and md5(out) == first)
with open(out, encoding="utf-8") as f:
    lines = f.read().splitlines(True)
with open(out, "w", encoding="utf-8") as f:
    f.writelines(lines[:-3])
with contextlib.redirect_stdout(io.StringIO()):
    n = JC.run(pairs, content_judge, out)
ok("after three rows are removed, a run redoes exactly those three",
   n == 3 and len(JC.read_judged(out)["all"]) == 10
   and all(set(o) == {"xy", "yx"} for o in JC.read_judged(out)["all"]
           .values()))
res = JC.analyse(JC.read_judged(out))
ok("and the analysis on the run output says SURVIVES",
   res["verdict"] == "SURVIVES" and res["comparisons"][0]["survive"] == 10)

garbage = judge_script('print("I would rather not say.")')
out2 = tmp("judged.csv")
with contextlib.redirect_stdout(io.StringIO()):
    JC.run(pairs, garbage, out2)
ok("a reply with no letter is kept with an empty choice",
   all(o == {"xy": "", "yx": ""} for o in JC.read_judged(out2)["all"]
       .values()))
failing = judge_script('sys.exit(3)')
out3 = tmp("judged.csv")
rc = quiet_main(["run", pairs, "--command", failing, "--out", out3])
ok("a judge that exits non-zero stops the run with exit 1", rc == 1)
slow = judge_script('import time\ntime.sleep(5)\nprint("A")')
rc = quiet_main(["run", pairs, "--command", slow, "--out", tmp("j.csv"),
                 "--timeout", "0.5"])
ok("a judge slower than --timeout stops the run with exit 1", rc == 1)
tpl = tmp("template.txt")
with open(tpl, "w", encoding="utf-8") as f:
    f.write("First:\n{a}\nSecond:\n{b}\nPick one.")
echo = judge_script('print("A" if prompt.startswith("First:") else "B")')
out4 = tmp("judged.csv")
rc = quiet_main(["run", pairs, "--command", echo, "--out", out4,
                 "--template", tpl])
ok("--template replaces the prompt",
   rc == 0 and all(o == {"xy": "A", "yx": "A"}
                   for o in JC.read_judged(out4)["all"].values()))
bad_tpl = tmp("template.txt")
with open(bad_tpl, "w", encoding="utf-8") as f:
    f.write("Only {a} here.")
rc = quiet_main(["run", pairs, "--command", echo, "--out", tmp("j.csv"),
                 "--template", bad_tpl])
ok("a template without {b} is refused", rc == 1)

# ==========================================================================
print()
print("=" * 70)
print("5. BAD INPUT IS REFUSED, NOT GUESSED AT")
print("=" * 70)


def bad_pairs(rows_, header=("item", "x", "y")):
    p = tmp("pairs.csv")
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows_)
    return quiet_main(["run", p, "--command", echo, "--out", tmp("j.csv")])


def bad_judged(rows_, header=tuple(JC.JUDGED_COLS)):
    p = tmp("judged.csv")
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows_)
    return quiet_main(["analyse", p])


ok("pairs: missing column: exit 1",
   bad_pairs([["i", "x"]], header=("item", "x")) == 1)
ok("pairs: empty answer: exit 1", bad_pairs([["i", "", "y"]]) == 1)
ok("pairs: duplicated item: exit 1",
   bad_pairs([["i", "x", "y"], ["i", "x", "y"]]) == 1)
ok("pairs: no rows: exit 1", bad_pairs([]) == 1)
ok("judged: missing column: exit 1",
   bad_judged([["i", "xy", "A"]], header=("item", "order", "reply")) == 1)
ok("judged: unknown order: exit 1", bad_judged([["i", "ab", "A", "A"]]) == 1)
ok("judged: unknown choice: exit 1", bad_judged([["i", "xy", "C", "C"]]) == 1)
ok("judged: an order twice for one item: exit 1",
   bad_judged([["i", "xy", "A", "A"], ["i", "xy", "B", "B"]]) == 1)
ok("judged: no rows: exit 1", bad_judged([]) == 1)
ok("a missing file: exit 1", quiet_main(["analyse", "does_not_exist.csv"])
   == 1)
ok("no mode: exit 1", quiet_main([]) == 1)
ok("unknown mode: exit 1", quiet_main(["judge", "x.csv"]) == 1)
ok("run without --command: exit 1",
   quiet_main(["run", pairs, "--out", tmp("j.csv")]) == 1)
bom = tmp("judged.csv")
with open(bom, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(JC.JUDGED_COLS)
    for i in range(25):
        w.writerow([f"i{i}", "xy", "A", "A"])
        w.writerow([f"i{i}", "yx", "B", "B"])
ok("a byte order mark before the header is not a missing column",
   quiet_main(["analyse", bom]) == 0)

# ==========================================================================
print()
print("=" * 70)
print("6. THE SHIPPED EXAMPLES REPRODUCE")
print("=" * 70)
demo = f'{PY} "{os.path.join(ROOT, "demo_judge.py")}"'
out5 = tmp("judged.csv")
with contextlib.redirect_stdout(io.StringIO()):
    JC.run(os.path.join(ROOT, "examples", "pairs.csv"), demo, out5)
ok("judging examples/pairs.csv with demo_judge.py reproduces "
   "examples/judged.csv byte for byte",
   md5(out5) == md5(os.path.join(ROOT, "examples", "judged.csv")))
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = JC.main(["analyse", os.path.join(ROOT, "examples", "judged.csv")])
got = buf.getvalue().rstrip().splitlines()
with open(os.path.join(ROOT, "examples", "judged.expected.txt"),
          encoding="utf-8") as f:
    exp = f.read().rstrip().splitlines()
ok("examples/judged.csv exits with 2", rc == 2, f"got {rc}")
first_diff = next((i for i, (g, e) in enumerate(zip(got, exp)) if g != e),
                  None if len(got) == len(exp) else min(len(got), len(exp)))
ok("its report matches examples/judged.expected.txt", first_diff is None,
   "" if first_diff is None else f"first difference at line {first_diff + 1}")

# ==========================================================================
print()
print("=" * 70)
print("KNOWN ANSWERS AND EDGES, added after mutation testing")
print("=" * 70)
import re as _re            # noqa: E402
import subprocess as _sp2   # noqa: E402

_root2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_tool2 = os.path.join(_root2, "judge_check.py")
with open(_tool2, encoding="utf-8") as _f:
    _flags = sorted(set(_re.findall(r'"(--[a-z][a-z-]+)"', _f.read())))
_bad_flags = []
for _flag in _flags:
    _p = _sp2.run([sys.executable, _tool2] + ["analyse", os.path.join(_root2, "examples", "judged.csv")] + [_flag],
                  stdout=_sp2.PIPE, stderr=_sp2.PIPE)
    if b"Traceback" in _p.stderr or _p.returncode not in (0, 1, 2):
        _bad_flags.append(_flag)
ok(f"each of the {len(_flags)} options, given last with no value, ends in "
   f"exit 0, 1 or 2 and no traceback", not _bad_flags, " ".join(_bad_flags))
_pu = _sp2.run([sys.executable, _tool2], stdout=_sp2.PIPE, stderr=_sp2.PIPE)
ok("with no arguments: the usage line, exit 1, nothing on standard output",
   _pu.returncode == 1 and _pu.stderr.decode().lower().startswith("usage")
   and not _pu.stdout.strip())
_miss = [a + ".missing" if os.path.isfile(a) else a for a in ["analyse", os.path.join(_root2, "examples", "judged.csv")]]
if _miss != ["analyse", os.path.join(_root2, "examples", "judged.csv")]:
    _pm = _sp2.run([sys.executable, _tool2] + _miss, stdout=_sp2.PIPE,
                   stderr=_sp2.PIPE)
    ok("a file that is not there: 'input not usable', exit 1, no usage "
       "line in its place",
       _pm.returncode == 1
       and _pm.stderr.decode().startswith("input not usable")
       and b"Traceback" not in _pm.stderr)

# ==========================================================================
print()
print("=" * 70)
print("HOSTILE INPUT, through the command line")
print("=" * 70)
import subprocess as _sp   # noqa: E402
import tempfile as _tf     # noqa: E402

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ex = os.path.join(_root, "examples")
_d = _tf.mkdtemp()


def _cli(*args):
    p = _sp.run([sys.executable, os.path.join(_root, "judge_check.py"), *args],
                stdout=_sp.PIPE, stderr=_sp.PIPE)
    return (p.returncode, p.stdout.decode("utf-8", "replace"),
            p.stderr.decode("utf-8", "replace"))


_bad = os.path.join(_d, "latin1.csv")
with open(_bad, "wb") as _f:
    _f.write(b"name,value\ncaf\xe9,1\n\xff\xfe,2\n")
_rc, _out, _err = _cli("analyse", _bad)
ok("a file that is not UTF-8 is refused in one line, with no traceback",
   _rc == 1 and "UTF-8" in _err and "Traceback" not in _err
   and len(_err.strip().splitlines()) == 1)
_huge = os.path.join(_d, "huge.csv")
with open(_huge, "w", encoding="utf-8") as _f:
    _f.write("name,value\n" + "x" * 200000 + ",1\n")
_rc, _out, _err = _cli("analyse", _huge)
ok("a field of 200,000 characters is data: read, not refused as too long",
   "Traceback" not in _err and "field larger" not in _err
   and "read as CSV" not in _err)
with open(os.path.join(_ex, "judged.csv"), encoding="utf-8-sig", newline="") as _f:
    _lines = _f.read().replace("\r\n", "\n").split("\n")
_open = os.path.join(_d, "open.csv")
with open(_open, "w", encoding="utf-8", newline="") as _f:
    _f.write("\n".join(_lines[:3] + ['"' + _lines[3]] + _lines[4:]))
_rc, _out, _err = _cli("analyse", _open)
ok("a quote that never closes is refused, not read as one long field",
   _rc == 1 and "read as CSV" in _err and "Traceback" not in _err)
_long = os.path.join(_d, "long.csv")
with open(_long, "w", encoding="utf-8", newline="") as _f:
    _f.write("\n".join(_lines[:3] + [_lines[3] + ",EXTRA"] + _lines[4:]))
_rc, _out, _err = _cli("analyse", _long)
ok("a row with more fields than the header is refused, with its line",
   _rc == 1 and "Traceback" not in _err and "line 4" in _err
   and ("more fields" in _err or "cells" in _err))
_rc, _out, _err = _cli("analyse", os.path.join(_ex, "judged.csv"), "--json",
                       os.path.join(_d, "no", "such", "folder", "r.json"))
ok("a report that cannot be written is refused, with no traceback",
   _rc == 1 and "Traceback" not in _err)
for _v in ("abc", "nan", "0", "-5"):
    _rc, _out, _err = _cli("run", os.path.join(_ex, "pairs.csv"), "--command",
                           "x", "--out", os.path.join(_d, "j.csv"),
                           "--timeout", _v)
    ok(f"--timeout {_v} is refused", _rc == 1 and "Traceback" not in _err)

# ==========================================================================
print()
print("=" * 70)
print(f"{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    for f in FAIL:
        print(f"  FAILED: {f}")
    sys.exit(1)
print("judge_check.py gives the right verdicts.")
print("=" * 70)
