"""Match an answer string to one of a field's options (radio / select / checkbox)."""
import difflib
import re

from .. import config
from .store import norm

OPTION_MATCH_CUTOFF = config.get_float("OPTION_MATCH_CUTOFF")


def _range_contains(option, number):
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)", option)
    if m:
        return float(m.group(1)) <= number <= float(m.group(2))
    m = re.search(r"(\d+(?:\.\d+)?)\s*\+", option)
    if m:
        return number >= float(m.group(1))
    return False


def match_option(answer, options):
    """Return the index of the option best matching `answer`, or -1."""
    a = norm(answer)
    opts = [norm(o) for o in options]
    for i, o in enumerate(opts):
        if o == a:
            return i
    if a in ("yes", "y", "true"):
        for i, o in enumerate(opts):
            if o.startswith("yes"):
                return i
    if a in ("no", "n", "false"):
        for i, o in enumerate(opts):
            if o.startswith("no"):
                return i
    if re.fullmatch(r"\d+(\.\d+)?", a):
        for i, o in enumerate(opts):
            if _range_contains(o, float(a)):
                return i
    for i, o in enumerate(opts):
        if o and (a in o or o in a):
            return i
    best = difflib.get_close_matches(a, opts, n=1, cutoff=OPTION_MATCH_CUTOFF)
    return opts.index(best[0]) if best else -1
