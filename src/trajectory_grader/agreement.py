"""Agreement between the automated grader and the human gold labels.

This is the module the project's pitch actually rests on: a rubric that
reports violations is unremarkable, but a rubric with a *measured, honestly
reported* agreement rate against independent human judgement is the part
that says whether its output means anything.

Two numbers are reported per rule, deliberately:

- **raw agreement** — the fraction of labeled trajectories where automated
  and human verdicts match. Easy to read, and misleading on its own: if
  98% of trajectories genuinely have no violation of some rule, a rule that
  never fires at all scores 0.98.
- **Cohen's kappa** — the same agreement corrected for what chance alone
  would produce given each side's marginal rates. This is what catches the
  "never fires, looks great" failure above, which is precisely the failure
  mode a deterministic rubric is most prone to.

Both are reported because either alone is easy to misread, and the
project's honesty requirement means publishing the unflattering one too.

Kappa is **undefined**, not zero and not one, when expected agreement is
exactly 1.0 (both sides assigned every item to the same single category).
That is a real and common situation on a small gold set, so it is
represented as ``None`` and must be rendered as "undefined" rather than
silently coerced into a flattering number.
"""

from __future__ import annotations

from dataclasses import dataclass

from .grader import Report
from .labels import GoldLabel


@dataclass(frozen=True)
class RuleAgreement:
    """Agreement stats for one rule across the labeled trajectories."""

    rule: str
    n: int
    agreements: int
    #: (automated, human) verdict pairs that disagreed, with the task_id.
    disagreements: tuple[tuple[str, str, str], ...]
    kappa: float | None
    #: Why kappa is None, when it is. Empty string when kappa is a number.
    #: Carried explicitly because "undefined" has two distinct causes with
    #: different meanings for the reader, and collapsing them into a bare
    #: None loses the one a reviewer needs.
    kappa_undefined_because: str = ""

    @property
    def raw_agreement(self) -> float | None:
        """Fraction of scorable items where both sides matched.

        ``None`` when ``n == 0``: no labeled items means no measurement,
        which must not be reported as 0.0 agreement.
        """
        if self.n == 0:
            return None
        return self.agreements / self.n

    def describe(self) -> str:
        if self.n == 0:
            return f"{self.rule}: no labeled trajectories cover this rule — not measured"
        raw = self.raw_agreement
        assert raw is not None  # n > 0
        if self.kappa is None:
            kappa = f"not reportable ({self.kappa_undefined_because})"
        else:
            kappa = f"{self.kappa:.3f}"
        return (
            f"{self.rule}: raw agreement {raw:.3f} ({self.agreements}/{self.n}), "
            f"Cohen's kappa {kappa}"
        )


#: Below this many scorable items, kappa is suppressed regardless of whether
#: the formula yields a number.
#:
#: The formula is happy to produce a confident-looking value from almost no
#: evidence: at n=1 with a disagreement, pe = 0 and kappa = 0.000 exactly —
#: which a reader takes as "measured, agreement no better than chance" when
#: it is one item. The same reasoning that makes returning None for pe == 1
#: correct (never print a number the evidence cannot support) applies here,
#: so the floor is enforced rather than left to the prose around the number.
#:
#: 5 is a deliberately modest floor: it does not make kappa *reliable* — the
#: project targets 20-30 labels for that — it only rules out the sizes where
#: the value is arithmetic rather than evidence.
MIN_N_FOR_KAPPA = 5


def rule_agreement(
    rule: str,
    pairs: list[tuple[str, str, str]],
) -> RuleAgreement:
    """Compute agreement for one rule from ``(task_id, automated, human)`` triples.

    ``pairs`` must already have ``unclear`` human verdicts filtered out (see
    :meth:`GoldLabel.scorable`) — an undecided human label is not a
    disagreement and must not be counted as one.
    """
    n = len(pairs)
    agreements = sum(1 for _, auto, human in pairs if auto == human)
    disagreements = tuple((task, auto, human) for task, auto, human in pairs if auto != human)

    reason = ""
    if n == 0:
        kappa = None
        reason = "nothing labeled"
    elif n < MIN_N_FOR_KAPPA:
        kappa = None
        reason = f"n={n}, below the n>={MIN_N_FOR_KAPPA} floor"
    else:
        kappa = cohens_kappa([(a, h) for _, a, h in pairs])
        if kappa is None:
            reason = "both sides used a single category"

    return RuleAgreement(
        rule=rule,
        n=n,
        agreements=agreements,
        disagreements=disagreements,
        kappa=kappa,
        kappa_undefined_because=reason,
    )


def cohens_kappa(pairs: list[tuple[str, str]]) -> float | None:
    """Cohen's kappa for two raters over categorical verdicts.

    kappa = (po - pe) / (1 - pe), where ``po`` is observed agreement and
    ``pe`` is the agreement expected from the two raters' marginal
    distributions alone.

    Returns ``None`` when kappa is genuinely undefined — an empty input, or
    ``pe == 1.0`` (both raters used exactly one category, so chance already
    "explains" perfect agreement and the formula divides by zero). Callers
    must render that as undefined rather than substituting a number.
    """
    n = len(pairs)
    if n == 0:
        return None

    categories = {c for pair in pairs for c in pair}
    observed = sum(1 for a, b in pairs if a == b) / n

    expected = 0.0
    for category in categories:
        p_a = sum(1 for a, _ in pairs if a == category) / n
        p_b = sum(1 for _, b in pairs if b == category) / n
        expected += p_a * p_b

    if expected >= 1.0:
        return None
    return (observed - expected) / (1.0 - expected)


def automated_verdicts(report: Report, rules: list[str]) -> dict[str, str]:
    """The grader's own verdict per rule, in gold-label vocabulary.

    A rule that produced no violations for this trajectory is ``ok``; one
    that fired at least once is ``violation``. ``rules`` is passed in
    explicitly (rather than read off the report) because a rule that did
    not fire leaves no trace in the report, and "did not fire" is a real
    verdict that must be comparable against a human one.
    """
    fired = {v.rule for v in report.violations}
    return {rule: ("violation" if rule in fired else "ok") for rule in rules}


def compare(
    graded: dict[str, Report],
    gold: list[GoldLabel],
    rules: list[str],
) -> list[RuleAgreement]:
    """Compare automated reports against human gold labels, per rule.

    ``graded`` maps task_id -> the grader's :class:`Report` for it. Gold
    labels whose ``task_id`` has no corresponding report are skipped rather
    than guessed at; see :func:`missing_reports` to surface them instead of
    letting them vanish from the denominator unnoticed.
    """
    per_rule: dict[str, list[tuple[str, str, str]]] = {rule: [] for rule in rules}
    for label in gold:
        report = graded.get(label.task_id)
        if report is None:
            continue
        auto = automated_verdicts(report, rules)
        for rule, human in label.scorable().items():
            if rule in per_rule:
                per_rule[rule].append((label.task_id, auto[rule], human))
    return [rule_agreement(rule, pairs) for rule, pairs in per_rule.items()]


def missing_reports(graded: dict[str, Report], gold: list[GoldLabel]) -> list[str]:
    """task_ids that are labeled but have no graded trajectory.

    Reported separately so a shrinking denominator is visible: silently
    dropping labeled items is how an agreement number drifts away from the
    gold set it claims to describe.
    """
    return sorted(label.task_id for label in gold if label.task_id not in graded)
