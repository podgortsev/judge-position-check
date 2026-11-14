# Judge Position Check

**How many of a model judge's conclusions survive swapping the order of the
two answers?**

A model asked which of two answers is better favours whichever it saw first,
often by a wide margin, and averaging the two orders does not cancel it,
because an item the judge gives to the first slot in both orders is still one
item decided by the slot. This tool judges every pair in both orders with the
judge you supply, sorts each item by whether the answer or the position won,
and sets the conclusions a single-order study would have reported beside the
ones that hold in both orders.

## Run it

Python 3.8 or later (the tool uses math.comb), tested on 3.11, nothing to install:

    git clone https://github.com/podgortsev/judge-position-check
    cd judge-position-check
    python judge_check.py analyse examples/judged.csv

Output, copied from that run:

    ================================================================================================
    JUDGE POSITION CHECK
    ================================================================================================

      PER ITEM: who wins in both orders
      comparison           items content X content Y  slot A  slot B incompl.  survive
      matched                 22         0         0      20       0        2        0
      x_longer                20        20         0       0       0        0       20

      FIRST SLOT: share of reads that chose A, exact binomial against one half
      matched                40 of   40 = 100.0%  [91.2%, 100.0%]  p 1.82e-12
      x_longer               20 of   40 =  50.0%  [35.2%, 64.8%]  p 1

      CONCLUSIONS: X against Y by sign test, BH across comparisons
      comparison                reported order   p adj      other order       p      both orders   p adj  status
      matched                       X 20 : 0 Y   0.000       X 0 : 20 Y   0.000        X 0 : 0 Y   1.000  does not survive
      x_longer                      X 20 : 0 Y   0.000       X 20 : 0 Y   0.000       X 20 : 0 Y   0.000  survives

    ------------------------------------------------------------------------------------------------
      VERDICT: DOES NOT SURVIVE. 1 of 2 conclusions significant in the reported order hold
      after the swap. The rest belonged to the slot. Report only the both-orders column.
    ------------------------------------------------------------------------------------------------

That judged file was produced by the run step with the simulated judge shipped
here, in about five seconds:

    python judge_check.py run examples/pairs.csv --command "python demo_judge.py" --out judged.csv

`demo_judge.py` is not a model and measures nothing. It prefers the longer
answer and leans to the first slot by a fixed margin, so the example has the
two cases to show: a comparison where the answers are matched in length and
the slot decides every item, and one where the first answer is half again as
long and the answer decides. Both look identical in the reported order. Only
one survives the swap. Replace the command with your judge.

| exit code | meaning |
|---|---|
| 0 | every conclusion significant in the reported order survives the swap, or there was none to test |
| 2 | the judge is position-bound, or at least one single-order conclusion does not survive |
| 1 | the input could not be used, or the judge command failed |

    python judge_check.py analyse judged.csv --json report.json

writes the same report as JSON. The tool itself reads and writes local files
only and makes no network connection. The judge command you pass may, and
that is yours: a local model, a script that calls a hosted one, anything that
reads a prompt on standard input and prints a reply.

## Input

**To `run`:** `pairs.csv`, one row per pair:

| column | meaning |
|---|---|
| `item` | a name for the pair |
| `x`, `y` | the two answers |
| `question` | optional, the question both answers address |
| `comparison` | optional, a name grouping items into one comparison; each is tested and corrected separately |

The judge receives one prompt on standard input per read and must print its
reply. The default prompt shows the question, then Answer A, then Answer B,
and asks for the single letter A or B. `--template FILE` replaces it with a
file containing `{question}`, `{a}` and `{b}`. `--timeout SECONDS` bounds one
call, default 120. The command runs through the shell, so quote it as you
would there.

The run is resumable: reads already in `--out` are not repeated, and every
reply is written as soon as it arrives. A judge that exits non-zero or runs
past the timeout stops the run with exit 1 and the file so far is kept.

The reply is parsed in this order: a reply that is only A or B, with
punctuation; "Answer A" or "Answer B"; otherwise the first standalone A or B.
A reply with no letter gets an empty choice, which counts as incomplete and
is never guessed. Keep the reply short in the prompt, and check the
`incompl.` column.

**To `analyse`:** `judged.csv`, as `run` writes it:

    item,order,reply,choice,comparison

`order` is `xy` when X was shown as A, `yx` when Y was. `choice` is A, B or
empty. A file from another runner works if it has these columns.

## Reading the report

**Per item.** Each pair is judged twice. `content X` and `content Y` are the
items where the same answer wins in both orders. `slot A` and `slot B` are the
items where the same position wins in both orders: the judge did not read the
answers, or read them and still followed the slot. `incompl.` counts items
with a read that produced no letter. `survive` is the content items.

**First slot.** The share of all usable reads that chose A, with a Wilson
interval and an exact binomial test against one half. Fifty percent is given
by the design; anything far from it is the judge.

**Conclusions.** For each comparison, X against Y by sign test on three sets:
the reported order (X shown first, which is what a single-order study would
have run), the other order, and the items that agree in both orders. The
reported-order and both-orders tests are each corrected across comparisons
with Benjamini-Hochberg. A conclusion `survives` when it is significant in
the reported order and significant in the same direction in both orders.

**Verdict**, fixed before any data is read:

| verdict | rule | exit |
|---|---|---|
| POSITION-BOUND | more items decided by the slot than by the answer | 2 |
| DOES NOT SURVIVE | a comparison significant in the reported order is not, same direction, after the swap | 2 |
| SURVIVES | every comparison significant in the reported order is also significant, same direction, after the swap | 0 |
| NOTHING TO TEST | no comparison is significant in the reported order | 0 |

The both-orders column is the one to report. The reported-order column is
there to show what would have been claimed without the swap.

## Where it comes from

Paper 2 of the Average-Fit research programme, *Single Human-AI Fit*
(DOI 10.5281/zenodo.22364497), asked three open language models to pick
between two profiles that differed in one detail. The design gives fifty-fifty
by construction. The first slot won 67, 99 and 92 percent of the time on the
three models, and swapping the order did not cancel it, because a parsed
letter sits at a ceiling. The method was withdrawn and rebuilt on probabilities
instead of letters. The rule it left behind is the one this tool applies: a
result that holds in one order only belongs to the slot, not to the answer.

## Limits

It tests one thing: whether a conclusion depends on the order the answers were
shown in. It does not tell you whether the judge is right about the answers,
whether the prompt is fair to both, or whether the judge meant to answer in
the format being parsed; the probability mass on the letters is the next tool
in this series. A clean swap is necessary for a judged comparison, not
sufficient.

Files are read strictly. A file has to be UTF-8, with or without a byte order
mark. A quote that never closes, or a row with more fields than the header,
stops the run with exit code 1 and the line number: neither is read around.
A row with fewer fields than the header is read with its missing fields
empty. A field may be of any length.

## Tests

    python tests/test_judge_check.py

80 checks, under a minute, no model: the reply parser on fixed cases,
the statistics on hand-computed cases, every verdict on judged data with a
known structure, the run step driven by small judge scripts with known rules
(both orders, resuming after a cut, a judge that prints no letter, one that
fails, one that hangs, a custom template), every refused input, and the
shipped example reproduced byte for byte from the pairs file through the
simulated judge.

## Files

    judge_check.py              the tool: run and analyse
    demo_judge.py               the simulated judge for the example, not a model
    tests/test_judge_check.py   the checks
    make_examples.py            regenerates examples/pairs.csv and examples/judged.csv
    examples/                   the pairs, the judged file, and the expected report
    CHECKLIST.md                the release bar, ticked
    LICENSE                     MIT
