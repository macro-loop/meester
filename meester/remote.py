"""Deciding whether a posting is actually remote.

This is harder than it looks and it is the gate everything downstream depends on,
so it lives on its own with tests.

Each ATS exposes a different, partial signal:

  * Ashby  - an ``isRemote`` boolean, a ``workplaceType`` string, AND
             ``secondaryLocations``. A role is frequently listed primary "New York"
             with "Remote (US)" tucked into the secondaries. Reading only the
             primary location silently drops real remote roles.
  * Lever   - a ``workplaceType`` enum ("remote"/"hybrid"/"onsite") plus a free-text
             ``categories.location`` and ``allLocations``.
  * Greenhouse - nothing structured at all. Just free text such as
             "Remote, Canada; Remote, United States". Its ``metadata`` array is
             per-employer custom (GitLab publishes "Quota Coverage Type",
             Anthropic publishes "Location Type") so it cannot be relied on.

So the shared primitive is a text classifier, and each harvester layers whatever
structured signal it has on top.
"""

from __future__ import annotations

import re

from .models import Workplace

# --- country / region vocabulary -------------------------------------------------

# Order matters: longer, more specific phrases are matched first so that
# "United States" is not shadowed by "US".
_COUNTRY_PATTERNS: list[tuple[str, str]] = [
    # "U.S. Remote" is common and the naive `\bu\.s\.\b` never matches it: after a
    # trailing "." followed by a space there is no word boundary. Hence the
    # explicit lookaround instead of \b.
    ("US", r"united\s+states(?:\s+of\s+america)?|(?<![a-z])u\.\s?s\.?a?\.?(?![a-z])|\busa\b|\bus\b"),
    ("CA", r"\bcanada\b|\bcanadian\b|\bcan\b"),
    ("GB", r"united\s+kingdom|\bu\.?k\.?\b|\bengland\b|\bscotland\b|\bwales\b|\blondon\b"),
    ("IE", r"\bireland\b|\bdublin\b"),
    ("DE", r"\bgermany\b|\bdeutschland\b|\bberlin\b|\bmunich\b"),
    ("FR", r"\bfrance\b|\bparis\b"),
    ("NL", r"netherlands|\bholland\b|amsterdam"),
    ("ES", r"\bspain\b|\bmadrid\b|\bbarcelona\b"),
    ("PT", r"\bportugal\b|\blisbon\b"),
    ("PL", r"\bpoland\b|\bwarsaw\b|\bkrakow\b"),
    ("IN", r"\bindia\b|\bbangalore\b|\bbengaluru\b|\bhyderabad\b|\bpune\b|\bmumbai\b|\bdelhi\b|\bgurgaon\b|\bnoida\b|\bchennai\b"),
    ("AU", r"\baustralia\b|\bsydney\b|\bmelbourne\b"),
    ("NZ", r"new\s+zealand"),
    ("SG", r"\bsingapore\b"),
    ("JP", r"\bjapan\b|\btokyo\b"),
    ("BR", r"\bbrazil\b|\bbrasil\b|sao\s+paulo"),
    ("MX", r"\bmexico\b"),
    ("AR", r"\bargentina\b"),
    ("IL", r"\bisrael\b|tel\s+aviv"),
    ("ZA", r"south\s+africa"),
    ("AE", r"\bdubai\b|united\s+arab\s+emirates|\buae\b"),
    ("CH", r"switzerland|\bzurich\b"),
    ("SE", r"\bsweden\b|\bstockholm\b"),
    ("NO", r"\bnorway\b|\boslo\b"),
    ("DK", r"\bdenmark\b|copenhagen"),
    ("FI", r"\bfinland\b|\bhelsinki\b"),
    ("IT", r"\bitaly\b|\bmilan\b|\brome\b"),
    ("PH", r"philippines|\bmanila\b"),
    ("CN", r"\bchina\b|\bbeijing\b|\bshanghai\b|hong\s+kong"),
    ("KR", r"(?:south\s+)?\bkorea\b|\bseoul\b"),
    ("CO", r"\bcolombia\b|\bbogota\b"),
    ("CL", r"\bchile\b|\bsantiago\b"),
    ("PE", r"\bperu\b|\blima\b"),
    ("CR", r"costa\s+rica"),
    ("NG", r"\bnigeria\b|\blagos\b"),
    ("KE", r"\bkenya\b|\bnairobi\b"),
    ("EG", r"\begypt\b|\bcairo\b"),
    ("TR", r"\bturkey\b|\bturkiye\b|\bistanbul\b"),
    ("GR", r"\bgreece\b|\bathens\b"),
    ("RO", r"\bromania\b|\bbucharest\b"),
    ("CZ", r"\bczech(?:ia)?\b|\bprague\b"),
    ("HU", r"\bhungary\b|\bbudapest\b"),
    ("UA", r"\bukraine\b|\bkyiv\b|\bkiev\b"),
    ("VN", r"\bvietnam\b|\bhanoi\b"),
    ("TH", r"\bthailand\b|\bbangkok\b"),
    ("ID", r"\bindonesia\b|\bjakarta\b"),
    ("MY", r"\bmalaysia\b|kuala\s+lumpur"),
    ("TW", r"\btaiwan\b|\btaipei\b"),
    ("PK", r"\bpakistan\b|\blahore\b|\bkarachi\b"),
    ("BD", r"\bbangladesh\b|\bdhaka\b"),
    # Regions, kept distinct from countries because "EMEA remote" does not mean
    # US-eligible and quietly treating it as such wastes applications.
    ("EU", r"\beurope\b|european\s+union|\beu\b|\bemea\b"),
    ("APAC", r"\bapac\b|asia[\s-]*pacific"),
    ("LATAM", r"\blatam\b|latin\s+america|south\s+america"),
    ("AMERICAS", r"\bamericas\b|north\s+america|\bnamer\b"),
    ("ANYWHERE", r"\banywhere\b|world\s*wide|\bworldwide\b|\bglobal(?:ly)?\b|any\s+location|\bdistributed\b"),
]

_COUNTRY_RE = [(code, re.compile(pat, re.I)) for code, pat in _COUNTRY_PATTERNS]

# US state abbreviations imply the US even with no country named ("Austin, TX").
_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
    "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}
_US_STATE_RE = re.compile(r",\s*([A-Z]{2})\b")

# Full state names, for strings like "Remote - Colorado" where there is no comma
# to anchor the abbreviation rule. Georgia is deliberately omitted: it is also a
# country, and mislabelling a Tbilisi role as US-eligible is worse than missing
# an Atlanta one.
_US_STATE_NAMES = re.compile(
    r"\b(alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware"
    r"|florida|hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|maine"
    r"|maryland|massachusetts|michigan|minnesota|mississippi|missouri|montana"
    r"|nebraska|nevada|new\s+hampshire|new\s+jersey|new\s+mexico|new\s+york"
    r"|north\s+carolina|north\s+dakota|ohio|oklahoma|oregon|pennsylvania"
    r"|rhode\s+island|south\s+carolina|south\s+dakota|tennessee|texas|utah|vermont"
    r"|virginia|washington|west\s+virginia|wisconsin|wyoming)\b",
    re.I,
)

_REMOTE_RE = re.compile(
    r"\bremote(?:ly)?\b|\bwork\s+from\s+home\b|\bwfh\b|\bdistributed\b|\banywhere\b|\bvirtual\b|\btelecommute\b",
    re.I,
)
_HYBRID_RE = re.compile(r"\bhybrid\b|\bflexible\s+onsite\b|\bpartially\s+remote\b", re.I)
# "Remote-first office in Berlin" and "no remote" mean the opposite of what the
# keyword suggests.
_NEGATED_REMOTE_RE = re.compile(r"\bno\s+remote\b|\bnot\s+remote\b|\bremote\s+not\b", re.I)

# Split multi-location strings. Greenhouse joins with "; ", others use "|" or " and ".
_PART_SPLIT = re.compile(r"\s*[;|]\s*|\s+\band\b\s+", re.I)

_PRECEDENCE = {
    Workplace.REMOTE: 3,
    Workplace.HYBRID: 2,
    Workplace.ONSITE: 1,
    Workplace.UNKNOWN: 0,
}


def extract_countries(text: str) -> set[str]:
    """Pull country/region codes out of a location string."""
    found: set[str] = set()
    if not text:
        return found
    for code, rx in _COUNTRY_RE:
        if rx.search(text):
            found.add(code)
    for m in _US_STATE_RE.finditer(text):
        if m.group(1).upper() in _US_STATES:
            found.add("US")
    if _US_STATE_NAMES.search(text):
        found.add("US")
    # Bare two-letter abbreviations after a dash ("Remote - CA") are left alone on
    # purpose: roughly half the state codes collide with ISO country codes
    # (CA/Canada, IN/India, DE/Germany, IL/Israel), and a wrong country is more
    # expensive than an unscoped one, which the policy accepts anyway.
    return found


def _classify_part(part: str) -> tuple[Workplace, set[str]]:
    countries = extract_countries(part)
    if _NEGATED_REMOTE_RE.search(part):
        return Workplace.ONSITE, countries
    is_hybrid = bool(_HYBRID_RE.search(part))
    is_remote = bool(_REMOTE_RE.search(part))
    if is_hybrid:
        # Within a single location, "hybrid" wins over a co-occurring "remote":
        # "Hybrid Remote - NYC" is an office job. Being conservative here costs a
        # missed opportunity; being permissive costs a wasted application and a
        # confused recruiter.
        return Workplace.HYBRID, countries
    if is_remote:
        return Workplace.REMOTE, countries
    if not part.strip():
        return Workplace.UNKNOWN, countries
    return Workplace.ONSITE, countries


def classify_location_text(text: str) -> tuple[Workplace, set[str]]:
    """Classify a possibly multi-location free-text string.

    Across *separate* locations the most permissive wins: a role posted as
    "Remote, US; New York, NY" can genuinely be done remotely.

    >>> classify_location_text("Remote, Canada; Remote, United States")[0]
    <Workplace.REMOTE: 'remote'>
    """
    if not text or not text.strip():
        return Workplace.UNKNOWN, set()

    parts = [p for p in _PART_SPLIT.split(text) if p and p.strip()] or [text]
    best = Workplace.UNKNOWN
    remote_countries: set[str] = set()
    all_countries: set[str] = set()

    for part in parts:
        mode, countries = _classify_part(part)
        all_countries |= countries
        if mode == Workplace.REMOTE:
            remote_countries |= countries
        if _PRECEDENCE[mode] > _PRECEDENCE[best]:
            best = mode

    if best == Workplace.REMOTE:
        # "Remote" with no geography named is genuinely unscoped; fall back to any
        # country mentioned elsewhere in the string rather than claiming ANYWHERE.
        return best, (remote_countries or all_countries)
    return best, all_countries


def combine(
    *signals: tuple[Workplace, set[str]] | None,
) -> tuple[Workplace, set[str]]:
    """Merge several partial signals, most permissive workplace wins."""
    best = Workplace.UNKNOWN
    countries: set[str] = set()
    for sig in signals:
        if not sig:
            continue
        mode, cs = sig
        countries |= cs
        if _PRECEDENCE[mode] > _PRECEDENCE[best]:
            best = mode
    return best, countries


def workplace_from_enum(value: str | None) -> Workplace:
    """Normalise Lever's and Ashby's ``workplaceType`` strings."""
    if not value:
        return Workplace.UNKNOWN
    v = value.strip().lower().replace("-", "").replace("_", "").replace(" ", "")
    if v in {"remote", "fullyremote"}:
        return Workplace.REMOTE
    if v == "hybrid":
        return Workplace.HYBRID
    if v in {"onsite", "inoffice", "office"}:
        return Workplace.ONSITE
    return Workplace.UNKNOWN


def is_acceptable(
    workplace: Workplace,
    countries: set[str] | list[str],
    accept_countries: list[str],
    accept_hybrid: bool = False,
) -> bool:
    """Apply the configured remote policy.

    A remote role with no geography stated is accepted: boards very often write
    just "Remote", and rejecting those would throw away a large slice of the market.
    Geography then gets confirmed at the scoring stage from the description.
    """
    if workplace == Workplace.REMOTE:
        pass
    elif workplace == Workplace.HYBRID and accept_hybrid:
        pass
    else:
        return False

    accept = {c.upper() for c in accept_countries}
    if "ANY" in accept:
        return True

    cs = {c.upper() for c in countries}
    if not cs:
        return True  # unscoped "Remote" - let the scorer decide
    if cs & accept:
        return True
    # A globally-remote role satisfies any country requirement.
    return "ANYWHERE" in cs
