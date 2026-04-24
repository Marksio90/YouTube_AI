"""
Rule-based compliance checks — synchronous, zero LLM cost.

Each check function returns a list of RawFlag dataclasses.
All patterns are compile-time constants; no DB access.

Rule IDs follow: {category}:{subcategory}:{code}
  e.g.  ad_safety:profanity:f001
        copyright_risk:brand_mention:c002
        factual_risk:medical_advice:fa003
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

from app.db.models.compliance import RiskCategory, RiskSeverity, FlagSource


# ── Raw flag (pre-persist) ────────────────────────────────────────────────────

@dataclass
class RawFlag:
    category:   RiskCategory
    severity:   RiskSeverity
    source:     FlagSource
    rule_id:    str
    title:      str
    detail:     str
    evidence:   str | None = None
    suggestion: str | None = None
    text_start: int | None = None
    text_end:   int | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_all(pattern: re.Pattern, text: str) -> list[re.Match]:
    return list(pattern.finditer(text))


def _first_match_evidence(m: re.Match, ctx: int = 80) -> tuple[str, int, int]:
    start = max(0, m.start() - ctx)
    end   = min(len(m.string), m.end() + ctx)
    return m.string[start:end], m.start(), m.end()


# ════════════════════════════════════════════════════════════════════════════
#  AD SAFETY  (weight 0.35 — highest, directly affects monetization)
# ════════════════════════════════════════════════════════════════════════════

_PROFANITY_CRITICAL = re.compile(
    r"\b(f+u+c+k+|s+h+i+t+|c+u+n+t+|n+i+g+g+e+r+|f+a+g+g+o+t+)\b",
    re.IGNORECASE,
)
_PROFANITY_HIGH = re.compile(
    r"\b(ass+h+o+l+e+|b+i+t+c+h+|b+a+s+t+a+r+d+|d+a+m+n+|c+r+a+p+)\b",
    re.IGNORECASE,
)
_VIOLENCE = re.compile(
    r"\b(murder|kill|stab|shoot|bomb|terrorist|massacre|genocide|rape|torture|behead)\b",
    re.IGNORECASE,
)
_WEAPONS = re.compile(
    r"\b(gun|rifle|pistol|ak-?47|ar-?15|explosive|grenade|ammunition|ammo)\b",
    re.IGNORECASE,
)
_DRUGS = re.compile(
    r"\b(cocaine|heroin|meth|methamphetamine|crack|fentanyl|ecstasy|mdma|lsd|marijuana|weed|cannabis)\b",
    re.IGNORECASE,
)
_ADULT = re.compile(
    r"\b(porn|pornography|sex tape|nude|naked|erotic|hentai|xxx|onlyfans)\b",
    re.IGNORECASE,
)
_CONTROVERSIAL_POLITICS = re.compile(
    r"\b(nazi|fascist|white supremac|kkk|antifa|jihad|isis|al-?qaeda|hamas|hezbollah)\b",
    re.IGNORECASE,
)
_GAMBLING = re.compile(
    r"\b(casino|gambling|bet|wager|poker|sports bet|crypto bet)\b",
    re.IGNORECASE,
)
_CLICKBAIT_TITLE = re.compile(
    r"([!?]{3,}|\b(YOU WON'T BELIEVE|SHOCKING|GONE WRONG|GONE SEXUAL|GONE WILD)\b)",
    re.IGNORECASE,
)


def check_ad_safety(title: str, body: str) -> list[RawFlag]:
    flags: list[RawFlag] = []
    full_text = f"{title}\n{body}"

    for m in _find_all(_PROFANITY_CRITICAL, full_text):
        ev, s, e = _first_match_evidence(m)
        flags.append(RawFlag(
            category=RiskCategory.ad_safety,
            severity=RiskSeverity.critical,
            source=FlagSource.rule,
            rule_id="ad_safety:profanity:f001",
            title="Severe profanity detected",
            detail="Strong profanity makes video ineligible for monetization and may result in demonetization.",
            evidence=ev, text_start=s, text_end=e,
            suggestion="Remove or replace with euphemism or bleep.",
        ))

    for m in _find_all(_PROFANITY_HIGH, full_text):
        ev, s, e = _first_match_evidence(m)
        flags.append(RawFlag(
            category=RiskCategory.ad_safety,
            severity=RiskSeverity.high,
            source=FlagSource.rule,
            rule_id="ad_safety:profanity:f002",
            title="Mild profanity detected",
            detail="Mild profanity limits ad tier to restricted inventory (lower CPM).",
            evidence=ev, text_start=s, text_end=e,
            suggestion="Replace for maximum monetization or add age restriction.",
        ))

    for m in _find_all(_VIOLENCE, full_text):
        ev, s, e = _first_match_evidence(m)
        flags.append(RawFlag(
            category=RiskCategory.ad_safety,
            severity=RiskSeverity.high,
            source=FlagSource.rule,
            rule_id="ad_safety:violence:f003",
            title="Violent content reference",
            detail="Violence references restrict ad eligibility. News/educational context may be exempt.",
            evidence=ev, text_start=s, text_end=e,
            suggestion="Add educational framing or apply for content exception.",
        ))

    for m in _find_all(_WEAPONS, full_text):
        ev, s, e = _first_match_evidence(m)
        flags.append(RawFlag(
            category=RiskCategory.ad_safety,
            severity=RiskSeverity.medium,
            source=FlagSource.rule,
            rule_id="ad_safety:weapons:f004",
            title="Weapons reference",
            detail="Weapon mentions may limit ad serving unless clearly educational.",
            evidence=ev, text_start=s, text_end=e,
            suggestion="Frame as educational/historical or avoid specific weapon names.",
        ))

    for m in _find_all(_DRUGS, full_text):
        ev, s, e = _first_match_evidence(m)
        flags.append(RawFlag(
            category=RiskCategory.ad_safety,
            severity=RiskSeverity.high,
            source=FlagSource.rule,
            rule_id="ad_safety:drugs:f005",
            title="Controlled substance reference",
            detail="Drug content is heavily restricted. Medical context may be exempt.",
            evidence=ev, text_start=s, text_end=e,
            suggestion="Add medical disclaimer or consult YT content policy.",
        ))

    for m in _find_all(_ADULT, full_text):
        ev, s, e = _first_match_evidence(m)
        flags.append(RawFlag(
            category=RiskCategory.ad_safety,
            severity=RiskSeverity.critical,
            source=FlagSource.rule,
            rule_id="ad_safety:adult:f006",
            title="Adult content reference",
            detail="Adult content is prohibited on YouTube without age restriction and demonetizes completely.",
            evidence=ev, text_start=s, text_end=e,
            suggestion="Remove adult references entirely.",
        ))

    for m in _find_all(_CONTROVERSIAL_POLITICS, full_text):
        ev, s, e = _first_match_evidence(m)
        flags.append(RawFlag(
            category=RiskCategory.ad_safety,
            severity=RiskSeverity.high,
            source=FlagSource.rule,
            rule_id="ad_safety:extremism:f007",
            title="Extremist/terrorist reference",
            detail="References to extremist groups trigger automatic demonetization and may result in strike.",
            evidence=ev, text_start=s, text_end=e,
            suggestion="Frame historically/educationally with clear condemnation context.",
        ))

    for m in _find_all(_GAMBLING, full_text):
        ev, s, e = _first_match_evidence(m)
        flags.append(RawFlag(
            category=RiskCategory.ad_safety,
            severity=RiskSeverity.medium,
            source=FlagSource.rule,
            rule_id="ad_safety:gambling:f008",
            title="Gambling content reference",
            detail="Gambling content restricts advertiser pool significantly.",
            evidence=ev, text_start=s, text_end=e,
            suggestion="Avoid promotional framing of gambling activities.",
        ))

    for m in _find_all(_CLICKBAIT_TITLE, title):
        flags.append(RawFlag(
            category=RiskCategory.ad_safety,
            severity=RiskSeverity.low,
            source=FlagSource.rule,
            rule_id="ad_safety:clickbait:f009",
            title="Clickbait title pattern",
            detail="Extreme clickbait may trigger YT reduced distribution and reduce CPM.",
            evidence=title,
            suggestion="Use curiosity gap without misleading or sensational phrasing.",
        ))

    return flags


# ════════════════════════════════════════════════════════════════════════════
#  COPYRIGHT RISK  (weight 0.30)
# ════════════════════════════════════════════════════════════════════════════

_MUSIC_CLAIM = re.compile(
    r"\b(playing|background music|song by|track by|music by|ft\.|feat\.|featuring)\b.*?\b([A-Z][a-z]+\s[A-Z][a-z]+)\b",
    re.IGNORECASE,
)
_MOVIE_CLIPS = re.compile(
    r"\b(clip from|footage from|scene from|excerpt from|using clips|using footage)\b",
    re.IGNORECASE,
)
_BRAND_NAMES_SENSITIVE = re.compile(
    r"\b(coca[-\s]cola|mcdonald'?s|nike|apple|google|microsoft|disney|netflix|amazon|meta|facebook)\b",
    re.IGNORECASE,
)
_FAIR_USE_CLAIM = re.compile(
    r"\bfair use\b",
    re.IGNORECASE,
)
_COPYRIGHTED_MUSIC = re.compile(
    r"\b(spotify|apple music|tidal|soundcloud|licensed track|copyrighted music)\b",
    re.IGNORECASE,
)
_REPOST_LANGUAGE = re.compile(
    r"\b(credit to|credits to|original by|not my (video|content|footage)|found on (reddit|twitter|tiktok|instagram))\b",
    re.IGNORECASE,
)


def check_copyright_risk(title: str, body: str) -> list[RawFlag]:
    flags: list[RawFlag] = []
    full_text = f"{title}\n{body}"

    for m in _find_all(_MUSIC_CLAIM, full_text):
        ev, s, e = _first_match_evidence(m)
        flags.append(RawFlag(
            category=RiskCategory.copyright_risk,
            severity=RiskSeverity.high,
            source=FlagSource.rule,
            rule_id="copyright_risk:music:c001",
            title="Music attribution suggests unlicensed use",
            detail="Mentioning playing a song/track without license confirmation is high copyright risk.",
            evidence=ev, text_start=s, text_end=e,
            suggestion="Use royalty-free music (YT Audio Library, Epidemic Sound) or obtain license.",
        ))

    for m in _find_all(_COPYRIGHTED_MUSIC, full_text):
        ev, s, e = _first_match_evidence(m)
        flags.append(RawFlag(
            category=RiskCategory.copyright_risk,
            severity=RiskSeverity.high,
            source=FlagSource.rule,
            rule_id="copyright_risk:music:c002",
            title="Copyrighted music platform reference",
            detail="Referencing tracks from streaming platforms implies potential copyright use.",
            evidence=ev, text_start=s, text_end=e,
            suggestion="Confirm music is royalty-free or licensed for YouTube.",
        ))

    for m in _find_all(_MOVIE_CLIPS, full_text):
        ev, s, e = _first_match_evidence(m)
        flags.append(RawFlag(
            category=RiskCategory.copyright_risk,
            severity=RiskSeverity.high,
            source=FlagSource.rule,
            rule_id="copyright_risk:footage:c003",
            title="Third-party footage use indicated",
            detail="Using clips from movies/shows without license is copyright infringement.",
            evidence=ev, text_start=s, text_end=e,
            suggestion="Use only footage you own, license, or falls clearly under fair use.",
        ))

    for m in _find_all(_FAIR_USE_CLAIM, full_text):
        ev, s, e = _first_match_evidence(m)
        flags.append(RawFlag(
            category=RiskCategory.copyright_risk,
            severity=RiskSeverity.medium,
            source=FlagSource.rule,
            rule_id="copyright_risk:fair_use:c004",
            title="Fair use claim detected",
            detail="Self-proclaimed fair use does not guarantee protection. YT still processes Content ID claims.",
            evidence=ev, text_start=s, text_end=e,
            suggestion="Ensure content is transformative, commentary, or parody. Document fair use basis.",
        ))

    for m in _find_all(_BRAND_NAMES_SENSITIVE, full_text):
        ev, s, e = _first_match_evidence(m)
        flags.append(RawFlag(
            category=RiskCategory.copyright_risk,
            severity=RiskSeverity.low,
            source=FlagSource.rule,
            rule_id="copyright_risk:trademark:c005",
            title="Trademarked brand name used",
            detail="Brand names in titles may trigger trademark claims. Descriptive use is generally safe.",
            evidence=ev, text_start=s, text_end=e,
            suggestion="Avoid brand names in thumbnail text. Descriptive use in script is usually fine.",
        ))

    for m in _find_all(_REPOST_LANGUAGE, full_text):
        ev, s, e = _first_match_evidence(m)
        flags.append(RawFlag(
            category=RiskCategory.copyright_risk,
            severity=RiskSeverity.critical,
            source=FlagSource.rule,
            rule_id="copyright_risk:repost:c006",
            title="Third-party content repost indicated",
            detail="Reposting or republishing others' content without license is copyright violation.",
            evidence=ev, text_start=s, text_end=e,
            suggestion="Create original content or obtain explicit written permission from content owner.",
        ))

    return flags


# ════════════════════════════════════════════════════════════════════════════
#  FACTUAL RISK  (weight 0.20)
# ════════════════════════════════════════════════════════════════════════════

_MEDICAL_ADVICE = re.compile(
    r"\b(cure[sd]?|treat[s]?|heals?|prevents?|diagnos[ei]s|you should take|take this supplement|dose of|mg of|medically proven)\b",
    re.IGNORECASE,
)
_FINANCIAL_ADVICE = re.compile(
    r"\b(guaranteed (return|profit|income)|100% (profit|return|safe)|will definitely (go up|make money)|buy (stock|crypto|bitcoin) now|financial advice)\b",
    re.IGNORECASE,
)
_LEGAL_ADVICE = re.compile(
    r"\b(this is not legal advice|you should (sue|file|claim)|legally you can|your rights include|according to the law you)\b",
    re.IGNORECASE,
)
_ABSOLUTE_CLAIMS = re.compile(
    r"\b(always|never|100%|guaranteed|scientifically proven|doctors hate|they don't want you to know|secret (they|the government|big pharma) (hide|hid))\b",
    re.IGNORECASE,
)
_CONSPIRACY = re.compile(
    r"\b(deep state|new world order|chemtrails|5g (causes|spreads|kills)|vaccines? (cause|autism|chips?|kill)|election (stolen|rigged|fraud))\b",
    re.IGNORECASE,
)
_STAT_WITHOUT_SOURCE = re.compile(
    r"\b(\d+%\s+of\s+(people|americans?|users?|viewers?))\b",
    re.IGNORECASE,
)


def check_factual_risk(title: str, body: str) -> list[RawFlag]:
    flags: list[RawFlag] = []
    full_text = f"{title}\n{body}"

    for m in _find_all(_MEDICAL_ADVICE, full_text):
        ev, s, e = _first_match_evidence(m)
        flags.append(RawFlag(
            category=RiskCategory.factual_risk,
            severity=RiskSeverity.high,
            source=FlagSource.rule,
            rule_id="factual_risk:medical:fa001",
            title="Medical advice or health claim detected",
            detail="Unqualified medical claims violate YT health policy and may cause real-world harm.",
            evidence=ev, text_start=s, text_end=e,
            suggestion='Add "consult your doctor" disclaimer. Avoid prescriptive medical language.',
        ))

    for m in _find_all(_FINANCIAL_ADVICE, full_text):
        ev, s, e = _first_match_evidence(m)
        flags.append(RawFlag(
            category=RiskCategory.factual_risk,
            severity=RiskSeverity.high,
            source=FlagSource.rule,
            rule_id="factual_risk:financial:fa002",
            title="Unqualified financial guarantee",
            detail="Guaranteed return claims are legally problematic and violate YT financial content policy.",
            evidence=ev, text_start=s, text_end=e,
            suggestion='Add "not financial advice" disclaimer. Remove guaranteed return language.',
        ))

    for m in _find_all(_ABSOLUTE_CLAIMS, full_text):
        ev, s, e = _first_match_evidence(m)
        flags.append(RawFlag(
            category=RiskCategory.factual_risk,
            severity=RiskSeverity.medium,
            source=FlagSource.rule,
            rule_id="factual_risk:absolute:fa003",
            title="Absolute or unverifiable claim",
            detail="Absolute claims without evidence may be flagged as misinformation.",
            evidence=ev, text_start=s, text_end=e,
            suggestion="Qualify with sources, add context, or soften language.",
        ))

    for m in _find_all(_CONSPIRACY, full_text):
        ev, s, e = _first_match_evidence(m)
        flags.append(RawFlag(
            category=RiskCategory.factual_risk,
            severity=RiskSeverity.critical,
            source=FlagSource.rule,
            rule_id="factual_risk:conspiracy:fa004",
            title="Conspiracy theory language detected",
            detail="Conspiracy content triggers YT misinformation policy — potential removal and channel strike.",
            evidence=ev, text_start=s, text_end=e,
            suggestion="Remove conspiracy framing. If debunking, clearly frame as debunking.",
        ))

    for m in _find_all(_STAT_WITHOUT_SOURCE, full_text):
        ev, s, e = _first_match_evidence(m)
        flags.append(RawFlag(
            category=RiskCategory.factual_risk,
            severity=RiskSeverity.low,
            source=FlagSource.rule,
            rule_id="factual_risk:stat:fa005",
            title="Statistic without visible source",
            detail="Unsourced statistics reduce credibility and may be flagged by YT fact-check systems.",
            evidence=ev, text_start=s, text_end=e,
            suggestion="Add source in description or on-screen text.",
        ))

    return flags


# ════════════════════════════════════════════════════════════════════════════
#  REUSED CONTENT  (weight 0.10)
# ════════════════════════════════════════════════════════════════════════════

_MIN_WORDS = 150  # below this threshold = suspiciously short


def check_reused_content(
    title: str,
    body: str,
    *,
    existing_titles: list[str] | None = None,
) -> list[RawFlag]:
    flags: list[RawFlag] = []
    word_count = len(body.split())

    if word_count < _MIN_WORDS:
        flags.append(RawFlag(
            category=RiskCategory.reused_content,
            severity=RiskSeverity.medium,
            source=FlagSource.rule,
            rule_id="reused_content:length:r001",
            title=f"Script too short ({word_count} words)",
            detail="Very short scripts suggest recycled or thin content. YT penalizes low-effort content.",
            suggestion=f"Expand to at least {_MIN_WORDS} words with original insight.",
        ))

    # Simple title similarity check against existing scripts
    if existing_titles:
        title_lower = title.lower()
        for existing in existing_titles:
            if existing and _title_similarity(title_lower, existing.lower()) > 0.75:
                flags.append(RawFlag(
                    category=RiskCategory.reused_content,
                    severity=RiskSeverity.high,
                    source=FlagSource.rule,
                    rule_id="reused_content:duplicate_title:r002",
                    title="Very similar title to existing content",
                    detail=f"Title is >75% similar to: '{existing}'. Duplicate content risks demotion.",
                    evidence=existing,
                    suggestion="Differentiate title angle or consolidate into updated version of original.",
                ))
            break  # flag once per most-similar match only

    return flags


def _title_similarity(a: str, b: str) -> float:
    """Jaccard similarity on word sets."""
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


# ════════════════════════════════════════════════════════════════════════════
#  AI DISCLOSURE  (weight 0.05)
# ════════════════════════════════════════════════════════════════════════════

_AI_GENERATED_DISCLAIMER = re.compile(
    r"\b(ai[-\s]?generated|made (with|by|using) ai|created (with|by|using) ai|ai[-\s]?written|ai[-\s]?produced)\b",
    re.IGNORECASE,
)
_AI_VOICE_DISCLAIMER = re.compile(
    r"\b(ai voice|voice clone|synthetic voice|text[-\s]to[-\s]speech|tts voice|ai narrat)\b",
    re.IGNORECASE,
)


def check_ai_disclosure(
    title: str,
    body: str,
    *,
    script_was_ai_generated: bool = False,
    voice_is_ai: bool = False,
) -> list[RawFlag]:
    flags: list[RawFlag] = []
    full_text = f"{title}\n{body}"

    has_disclaimer = bool(_AI_GENERATED_DISCLAIMER.search(full_text))
    has_voice_disclaimer = bool(_AI_VOICE_DISCLAIMER.search(full_text))

    if script_was_ai_generated and not has_disclaimer:
        flags.append(RawFlag(
            category=RiskCategory.ai_disclosure,
            severity=RiskSeverity.high,
            source=FlagSource.rule,
            rule_id="ai_disclosure:script:ai001",
            title="AI-generated script — no disclosure",
            detail=(
                "YouTube requires disclosure of AI-generated content. "
                "From 2024, undisclosed AI content in realistic scenarios may result in penalties."
            ),
            suggestion=(
                'Add "AI-generated script" to description. '
                'For realistic/news content, enable YT\'s AI disclosure toggle in Studio.'
            ),
        ))

    if voice_is_ai and not has_voice_disclaimer:
        flags.append(RawFlag(
            category=RiskCategory.ai_disclosure,
            severity=RiskSeverity.medium,
            source=FlagSource.rule,
            rule_id="ai_disclosure:voice:ai002",
            title="AI voice — no disclosure",
            detail="AI-synthesized voice narration should be disclosed per emerging platform policy.",
            suggestion='Add "AI voice narration" to description.',
        ))

    if has_disclaimer:
        # Positive info flag — disclosure found
        flags.append(RawFlag(
            category=RiskCategory.ai_disclosure,
            severity=RiskSeverity.info,
            source=FlagSource.rule,
            rule_id="ai_disclosure:present:ai000",
            title="AI disclosure present",
            detail="Script contains AI disclosure language — compliant.",
        ))

    return flags


# ════════════════════════════════════════════════════════════════════════════
#  ORCHESTRATOR
# ════════════════════════════════════════════════════════════════════════════

def run_rule_checks(
    *,
    title: str,
    body: str,
    script_was_ai_generated: bool = False,
    voice_is_ai: bool = False,
    existing_titles: list[str] | None = None,
) -> list[RawFlag]:
    """Run all rule-based checks. Returns combined flag list."""
    flags: list[RawFlag] = []
    flags.extend(check_ad_safety(title, body))
    flags.extend(check_copyright_risk(title, body))
    flags.extend(check_factual_risk(title, body))
    flags.extend(check_reused_content(title, body, existing_titles=existing_titles))
    flags.extend(check_ai_disclosure(
        title, body,
        script_was_ai_generated=script_was_ai_generated,
        voice_is_ai=voice_is_ai,
    ))
    return flags
