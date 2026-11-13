# Release bar

The eight lines a tool has to pass before it is published. Checked 2026-11-10,
Python 3.11.9 on Windows, from a clean clone of this repository. A line is
ticked only with the evidence beside it.

| | line | evidence |
|---|---|---|
| [x] | 1. Installs and runs from a clean clone, with one command written in the README | `python judge_check.py analyse examples/judged.csv`, standard library only, nothing to install |
| [x] | 2. The README opens with the problem in two sentences, then the command, then the output of that command, copied from a real run | the output block is `examples/judged.expected.txt`, written by the tool; test section 6 fails if the tool's output ever differs from that file |
| [x] | 3. One worked example a stranger can run in under a minute | the analyse step runs in under a second; the run step with the simulated judge, 84 reads, in about five seconds |
| [x] | 4. Tests pass, and they test the logic, not that the file imports | 78 checks pass: parser cases, hand-computed statistics, every verdict on known structures, the run step against judge scripts with known rules, resuming, refusals, the example reproduced byte for byte |
| [x] | 5. Fails loudly on bad input rather than returning a plausible number | exit 1 with the line for a missing column, empty answer, duplicated item, unknown order or choice, duplicated read, no rows, missing file, a template without both slots, a judge that fails or hangs; a reply with no letter is an empty choice, never a guess; tested in sections 4 and 5; a file that is not UTF-8, a quote that never closes, a row with more fields than the header and a report that cannot be written stop the run in one line, with no traceback, tested through the command line in the hostile-input section |
| [x] | 6. Does nothing over the network unless that is the point of the tool, and says so if it does | the tool itself makes no network call; the judge command is the user's and the README says so in the run section |
| [x] | 7. No dependency that costs money, and no API key required to try it | imports: csv, json, math, os, re, subprocess, sys; the example runs on a simulated judge that is declared as such |
| [x] | 8. The claim in the README is exactly what the tool does, with no "coming soon" | every verdict, column, exit code and refusal in the README has a test; the simulated judge is named as not a model in three places; the Paper 2 paragraph restates method 6a's published result and nothing beyond it |

## Rules

- Not a CRM, marketing, revenue or integration deliverable: a measurement check
  for model-judged evaluations.
- Nothing negative about any company, product, project or person. The example
  answers are neutral filler sentences; no model or vendor is named.
- Free and local: no service, no GPU, no key. A judge that needs one is the
  user's choice and lives outside the tool.
- Research claims stay inside what the paper shows: the "Where it comes from"
  section restates the method 6a result in Paper 2 and claims no finding of
  its own.
- English in every file. No em-dashes.

## Publication

Passing the bar is not itself the decision to publish. That is made per tool,
separately, after the bar.
