"""Builds the test-manager seed prompt for the openhands-orch leg, from the baseline survivors that
panel.run_agent already computed. Groups by (method, signature) so overloads are delegated separately;
the reward count uses len(survivors) (SURVIVOR-status mutants only), never PIT's `survived` arithmetic
which can include un-killable RUN_ERROR/NON_VIABLE mutants."""
import collections

MANAGER_PROMPT = """You are the TEST-MANAGER for Java class `{cls}` (test class `{tests}`, JDK {jdk}).

You are an ORCHESTRATOR ONLY. You have NO terminal and NO file editor -- you cannot read files, run
commands, or write tests yourself. Your only actions are:
  - `task` with subagent_type="mutation-tester": delegate ONE method to a test-writer sub-agent.
  - `think`, `finish`.

YOUR REWARD = 0.9 ^ (total mutants still surviving across all methods). It is 1.0 only when every
mutant is killed; each surviving mutant costs a factor of 0.9. Right now {n} mutants survive, so your
reward is {r:.4f}. Drive it to 1.0.

Baseline surviving mutants, grouped by method:
{methods}

Each `mutation-tester` sub-agent runs PIT ITSELF: it scopes PIT to its one method (that is its
`SURVIVORS_BEFORE`), appends tests, and re-runs the scoped PIT (that is its `SURVIVORS_AFTER`). It hands
you back only those two numbers -- never any PIT or build output. That is the whole point: all the heavy
PIT reports and file edits stay inside each sub-agent's own throwaway context, so YOUR context holds only a
short before/after count per method and stays flat no matter how many rounds you run.

Do this:
1. For EACH method above, delegate one `mutation-tester` (the `task` tool). In the task prompt give it,
   verbatim: the method name, that method's surviving-mutant lines (copied from above), the source file
   for `{cls}`, and the test file `{tests}` to APPEND to. Tell it to: run its own scoped PIT first to
   confirm the method's surviving count (`SURVIVORS_BEFORE`), append @Test methods that kill those specific
   mutants, keep the suite green, re-run the scoped PIT (`SURVIVORS_AFTER`), and END its report with
   exactly two lines:
       `SURVIVORS_BEFORE: <b>`
       `SURVIVORS_AFTER: <a>`
   -- the method's surviving-mutant count from its FIRST scoped PIT run and from its LAST one (`0` if it
   killed them all). Tell it to distill everything else and NEVER paste raw PIT/build output back to you.
   Delegate the methods one at a time.
2. Read each sub-agent's `SURVIVORS_AFTER: <a>` and TALLY the `<a>` across all methods; your reward =
   0.9 ^ (that sum). The `SURVIVORS_BEFORE - SURVIVORS_AFTER` delta tells you how many mutants that
   sub-agent actually killed.
3. For any method whose sub-agent reported `SURVIVORS_AFTER` greater than 0 AND still below its
   `SURVIVORS_BEFORE` (it made progress but did not finish), delegate a FRESH `mutation-tester` to that
   method with the still-surviving mutants, and re-tally. Repeat until every method reports
   `SURVIVORS_AFTER: 0`, or until a method's `SURVIVORS_AFTER` stops dropping between attempts.
4. Then `finish` with a one-line summary: total remaining survivors (the tallied `SURVIVORS_AFTER`) and
   your reward.

Never attempt to read or edit files yourself -- you have no such tools. Delegate everything; get the
survivor counts from the sub-agents' `SURVIVORS_BEFORE` / `SURVIVORS_AFTER` lines.
"""


def build(cls, tests, jdk, survivors):
    by = collections.OrderedDict()
    for s in survivors:
        by.setdefault((s["mutatedMethod"], s.get("methodDescription", "")), []).append(s)
    blocks = []
    for (m, _sig), ss in by.items():
        rows = "\n".join(
            "        - line %d %s (%s)" % (s["lineNumber"], s["mutator"], (s.get("description", "") or "")[:70])
            for s in ss)
        blocks.append("  method `%s` -- %d surviving mutant(s):\n%s" % (m, len(ss), rows))
    n = len(survivors)
    return MANAGER_PROMPT.format(cls=cls, tests=tests, jdk=jdk, n=n, r=0.9 ** n,
                                 methods="\n".join(blocks))
