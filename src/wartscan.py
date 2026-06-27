"""wartscan.py -- mechanical mergeability gate for generated tests, run at persist time.

Restores the semantic wart checks that left with the deleted reward.py oracle: the patterns that
got real upstream PRs rejected (reflection-into-internals, test-spam, junk scratch files, trivial
accessor tests, piecemeal partial-asserts). Attribute to the AGENT'S ADDED LINES when a diff is
available (never blame the file for pre-existing upstream warts); fall back to whole-file otherwise.

scan(path, added_text=None) -> list[str] of wart tags (empty = clean). The persist step DROPS a
`junk` file outright and records the rest into meta.json so PR-prep ships only clean material.
Thresholds calibrated on the live store: catches URIBuilder(270t), PropertyHelper(167t),
AwsProxyHttpServletRequest(157t/1866L), watsonx(207t) while sparing NamingConfigurer(96t) and
AuthenticationFilter(43t/1221L).
"""
import re

_TEST = re.compile(r"@(Test|ParameterizedTest|RepeatedTest)\b")
_REFLECT = re.compile(r"getDeclaredField|getDeclaredMethod|setAccessible|\.getMethod\(")
_MAIN = re.compile(r"\bstatic\s+void\s+main\s*\(")
_TRIVIAL = re.compile(r"void\s+test(Get|Set)[A-Z]\w*\s*\(|void\s+\w*(?:[Ee]quals|[Hh]ashCode|[Tt]oString)\w*\s*\(")
_PARTIAL = re.compile(r"assert(?:True|That)\s*\([^;]*\.contains\s*\(")

SPAM_TESTS = 120     # @Test count above this = spam (legit thorough tops out ~96)
SPAM_LINES = 1800    # file lines above this = spam (legit big files ~1200-1400)
TRIVIAL_MIN = 5      # this many accessor/equals/hashCode/toString tests = accessor-theater
PARTIAL_MIN = 4      # this many piecemeal contains()-asserts = should be one assertEquals


def scan(path, added_text=None):
    """Return a list of wart tags. `added_text` (the agent's '+' lines) scopes the diff-attributable
    checks (reflection/trivial/partial); whole-file properties (junk/spam) always use the full file."""
    try:
        src = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return []
    diff = added_text if added_text is not None else src
    warts = []
    ntest = len(_TEST.findall(src))
    nlines = src.count("\n")

    # whole-file: junk scratch file, test-count / size spam
    if ntest == 0 and _MAIN.search(src):
        warts.append("junk:no-test-with-main")
    if ntest > SPAM_TESTS:
        warts.append(f"spam:tests={ntest}")
    if nlines > SPAM_LINES:
        warts.append(f"spam:lines={nlines}")

    # diff-attributed: do not penalise pre-existing upstream code
    nrefl = len(_REFLECT.findall(diff))
    if nrefl:
        warts.append(f"reflection:{nrefl}")
    ntriv = len(_TRIVIAL.findall(diff))
    if ntriv >= TRIVIAL_MIN:
        warts.append(f"trivial-accessor:{ntriv}")
    npart = len(_PARTIAL.findall(diff))
    if npart >= PARTIAL_MIN:
        warts.append(f"partial-assert:{npart}")
    return warts


def is_junk(warts):
    return any(w.startswith("junk") for w in warts)


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        print(p, "->", scan(p) or "CLEAN")
