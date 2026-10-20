"""Complete SOP identifier extraction for exact lexical matching."""

import re

_ID = r"[a-z0-9]+(?:[./-][a-z0-9]+)*"
_QUALIFIED = re.compile(r"\b(?:[a-z0-9]+[./-])+sop[-#]?\s*\d[a-z0-9]*(?:[./-][a-z0-9]+)*\b", re.I)
_LABELLED = re.compile(rf"\b(?:sop|policy)\s*(?:no\.?|number|[-#])?\s*({_ID})\b", re.I)


def policy_references(text: str, *, metadata: bool = False) -> set[str]:
    """Normalize prefix typography, retaining complete qualified identifiers.

    Qualified references never acquire a short trailing alias: AJTM/STORE/SOP-1
    must not falsely match AJTM/GATE/SOP-1. Plain metadata identifiers are
    accepted only when the entire value is an identifier containing a digit.
    """
    qualified = list(_QUALIFIED.finditer(text))
    refs = {re.sub(r"\s+", "", m.group()).casefold() for m in qualified}
    for match in _LABELLED.finditer(text):
        if any(q.start() <= match.start() < q.end() for q in qualified):
            continue
        identifier = match.group(1)
        if any(c.isdigit() for c in identifier):
            refs.add("sop-" + identifier.casefold())
    for match in re.finditer(r"\b[a-z]{2,8}(?:-[a-z]{2,8})*-\d+(?:[./-][a-z0-9]+)*\b", text, re.I):
        if not any(q.start() <= match.start() < q.end() for q in qualified):
            refs.add(match.group().casefold())
    raw = text.strip()
    if metadata and re.fullmatch(_ID, raw, re.I) and any(c.isdigit() for c in raw):
        if not refs:
            refs.add("sop-" + raw.casefold())
    return refs
