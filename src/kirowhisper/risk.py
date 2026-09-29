"""Risk classification — the intelligence of Ambient Awareness.

Assigns each approval a risk level of LOW / HIGH / UNKNOWN, driving the
three-bucket filter (auto-approve / auto-block / surface).

Two layers:
  (a) Deterministic rules (this module's RuleClassifier) — fast, reliable, run
      first. Security tightens ONE WAY only: a rule can raise risk, never lower a
      HIGH to LOW.
  (b) Bedrock classification (bedrock.py) — nuanced, called only when the rules
      are inconclusive. On error/unsure it returns UNKNOWN (never LOW).

Safety invariant (NFR-1): when unsure, classify UNKNOWN so the engine surfaces it
to a human. Nothing destructive is ever silently downgraded.
"""

from __future__ import annotations

import re

from .models import Approval, RiskAssessment, RiskLevel

# Patterns that mark an operation as destructive / irreversible / dangerous.
# Case-insensitive. Kept conservative: matching means "at least HIGH".
_DESTRUCTIVE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\brm\s+-[a-z]*[rf]"), "recursive/forced file removal (rm -rf)"),
    (re.compile(r"(?i)\brmdir\b"), "directory removal"),
    (re.compile(r"(?i)\bgit\s+push\b.*(--force|-f)\b"), "git force push"),
    (re.compile(r"(?i)\bgit\s+reset\s+--hard\b"), "git hard reset"),
    (re.compile(r"(?i)\bgit\s+clean\b.*-[a-z]*f"), "git clean -f"),
    (re.compile(r"(?i)\bdrop\s+(table|database|schema)\b"), "SQL DROP"),
    (re.compile(r"(?i)\btruncate\s+table\b"), "SQL TRUNCATE"),
    (re.compile(r"(?i)\bdelete\s+from\b"), "SQL DELETE"),
    (re.compile(r"(?i)\b(sudo|chmod\s+777|chown)\b"), "privileged/permission change"),
    (re.compile(r"(?i)\b(mkfs|dd\s+if=|:\s*\(\)\s*\{)"), "disk/format/fork-bomb"),
    (re.compile(r"(?i)(force|--force|-f)\b.*(deploy|prod|production)"), "forced prod deploy"),
    (re.compile(r"(?i)\b(prod|production)\b.*(deploy|delete|drop|wipe)"), "production mutation"),
]

# Patterns that suggest a secret/credential is being exposed (e.g. written to a
# log or committed). Presence -> HIGH (R2.4).
_SECRET_EXPOSURE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\b(aws_secret_access_key|secret_key|private_key)\b"), "secret key reference"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
    (re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"), "secret-key token"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "GitHub token"),
    (re.compile(r"(?i)\.env\b"), ".env file"),
    (re.compile(r"(?i)\b(id_rsa|id_ed25519|\.pem)\b"), "private key material"),
]


# Catastrophic operations: never worth a human's time, always auto-blocked (the
# AUTO_BLOCK bucket). Deliberately narrow — wiping the root or home directory,
# piping a download into a shell, formatting or overwriting a raw disk, a fork
# bomb, or opening up the whole filesystem. Blocking means rejecting, which is the
# safe direction: the step simply does not run. Everything merely risky (e.g.
# `rm -rf /tmp/x`) is NOT here; it stays HIGH and is surfaced to the user.
_CATASTROPHIC_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(?i)\brm\s+(?:-{1,2}[a-z-]*\s+)*?-{1,2}[a-z-]*r[a-z-]*\s+(?:-{1,2}[a-z-]*\s+)*"
        r"(?:/\*?|~/?|\$HOME|\$\{HOME\})(?=$|[\s;&|])"
    ),
    re.compile(r"(?i)\b(?:curl|wget)\b[^|;\n]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b"),
    re.compile(r"(?i)\bmkfs(?:\.[a-z0-9]+)?\b"),
    re.compile(r"(?i)\bdd\b[^\n;]*\bof=/dev/(?!null\b)"),
    re.compile(r":\s*\(\s*\)\s*\{[^}]*:\s*\|\s*:"),
    re.compile(r"(?i)\bchmod\s+-R\s+0?777\s+/(?=$|\s)"),
]


def is_catastrophic(approval: Approval) -> bool:
    """True if the approval matches a bundled always-block rule.

    Used as the Ambient engine's explicit-deny check. Only the tool title and the
    tool input are inspected (not the free-text purpose), so a description that
    merely *mentions* a dangerous command does not trigger a block.
    """
    haystack = f"{approval.tool_title}\n{approval.diff}"
    return any(p.search(haystack) for p in _CATASTROPHIC_PATTERNS)


# Crew titles for tools that only look at things ("Reading x.py:1", "Listing src",
# "Searching for foo"). Crew does not reliably set is_read_only on these, so we
# recognize them ourselves. Only reached after the shell, destructive and secret
# rules have all passed, so "Reading .env" is still HIGH.
_READ_ONLY_TITLE = re.compile(r"^(?:Reading|Listing|Searching|Viewing|Grepping|Finding)\b")


class RuleClassifier:
    """Deterministic, testable rule layer. No network, no model calls."""

    def classify(self, approval: Approval) -> RiskAssessment | None:
        """Return a decisive assessment, or None if the rules are inconclusive.

        None means "defer to the Bedrock layer". A returned HIGH/LOW is final for
        the rule layer (the composed classifier only ever tightens it).
        """
        haystack = f"{approval.tool_title}\n{approval.purpose}\n{approval.diff}"

        # 1) Shell commands are inherently higher-risk (R2.3). Check before LOW so
        #    a read-only flag can never downgrade a shell command.
        if approval.is_shell:
            reason = "shell command"
            hit = self._first_match(haystack, _DESTRUCTIVE_PATTERNS)
            if hit:
                reason = f"shell command: {hit}"
            return RiskAssessment(RiskLevel.HIGH, reason, deterministic=True)

        # 2) Destructive/irreversible content anywhere -> HIGH (R2.3).
        hit = self._first_match(haystack, _DESTRUCTIVE_PATTERNS)
        if hit:
            return RiskAssessment(RiskLevel.HIGH, hit, deterministic=True)

        # 3) Secret exposure -> HIGH (R2.4).
        hit = self._first_match(haystack, _SECRET_EXPOSURE_PATTERNS)
        if hit:
            return RiskAssessment(
                RiskLevel.HIGH, f"possible secret exposure: {hit}", deterministic=True
            )

        # 4) Read-only / clearly reversible -> LOW (R2.2). Only reached when none
        #    of the danger rules fired above. deterministic=True: this is the only
        #    LOW that session trust may auto-approve.
        if approval.is_read_only:
            return RiskAssessment(RiskLevel.LOW, "read-only operation", deterministic=True)
        if _READ_ONLY_TITLE.match(approval.tool_title.strip()):
            return RiskAssessment(
                RiskLevel.LOW, "read-only operation (recognized tool)", deterministic=True
            )

        # 5) Inconclusive -> defer to the model layer.
        return None

    @staticmethod
    def _first_match(text: str, patterns: list[tuple[re.Pattern[str], str]]) -> str | None:
        for pat, label in patterns:
            if pat.search(text):
                return label
        return None


class RiskClassifier:
    """Composed classifier: rules first, model second, safe by default.

    The model layer is injected (a callable taking an Approval and returning a
    RiskAssessment) so this stays testable without network access. When no model
    is provided and the rules are inconclusive, the result is UNKNOWN (fail-safe).
    """

    def __init__(self, model_classify=None) -> None:
        self._rules = RuleClassifier()
        self._model_classify = model_classify

    def classify(self, approval: Approval) -> RiskAssessment:
        rule_result = self._rules.classify(approval)
        if rule_result is not None and rule_result.level == RiskLevel.HIGH:
            # Rules already found danger; never downgrade. Final.
            return rule_result

        if rule_result is not None and rule_result.level == RiskLevel.LOW:
            # Rules say clearly-safe. Trust the deterministic layer for read-only.
            return rule_result

        # Inconclusive -> ask the model layer, if available.
        if self._model_classify is not None:
            try:
                model_result = self._model_classify(approval)
            except Exception as exc:  # noqa: BLE001 - any model failure is fail-safe
                return RiskAssessment(
                    RiskLevel.UNKNOWN, f"model error, defaulting to UNKNOWN: {exc!r}"[:200]
                )
            if model_result is None:
                return RiskAssessment(RiskLevel.UNKNOWN, "model returned no result")
            # Tighten only: if the model says LOW but we have any doubt signal,
            # we still respect the model here since rules were inconclusive — but
            # a model UNKNOWN stays UNKNOWN.
            return model_result

        # No model available and rules inconclusive -> safe default.
        return RiskAssessment(RiskLevel.UNKNOWN, "inconclusive rules, no model layer")
