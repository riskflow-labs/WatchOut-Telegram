from __future__ import annotations

import re
from dataclasses import dataclass

from app.models import MonitorRule, TelegramMessage
from app.services.json_utils import loads_list


@dataclass(frozen=True)
class RuleMatch:
    rule: MonitorRule
    matched_patterns: list[str]


def evaluate_rules(message: TelegramMessage, rules: list[MonitorRule]) -> list[RuleMatch]:
    text = " ".join(
        [
            message.source or "",
            message.sender_id or "",
            message.sender_username or "",
            message.sender_name or "",
            message.content or "",
        ]
    )
    matches: list[RuleMatch] = []
    for rule in sorted(rules, key=lambda item: item.priority):
        if not rule.enabled:
            continue
        if not _filter_matches(message.source, rule.target_filter_json):
            continue
        sender_blob = " ".join([message.sender_id or "", message.sender_username or "", message.sender_name or ""])
        if not _filter_matches(sender_blob, rule.sender_filter_json):
            continue
        if _excluded(text, loads_list(rule.exclude_patterns_json)):
            continue
        patterns = _matched_patterns(text, rule.match_type, loads_list(rule.patterns_json))
        if patterns:
            matches.append(RuleMatch(rule=rule, matched_patterns=patterns))
    return matches


def _filter_matches(value: str, raw_filter: str) -> bool:
    filters = [str(item).lower() for item in loads_list(raw_filter) if str(item).strip()]
    if not filters:
        return True
    lowered = value.lower()
    return any(item in lowered for item in filters)


def _excluded(text: str, patterns: list[object]) -> bool:
    lowered = text.lower()
    return any(str(pattern).lower() in lowered for pattern in patterns)


def _matched_patterns(text: str, match_type: str, patterns: list[object]) -> list[str]:
    lowered = text.lower()
    matched: list[str] = []
    for item in patterns:
        pattern = str(item)
        if not pattern:
            continue
        if match_type == "regex":
            if re.search(pattern, text, flags=re.IGNORECASE):
                matched.append(pattern)
        elif match_type == "keyword":
            token = pattern.lower()
            if re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", lowered):
                matched.append(pattern)
        elif match_type == "exact":
            if lowered.strip() == pattern.lower().strip():
                matched.append(pattern)
        else:
            if pattern.lower() in lowered:
                matched.append(pattern)
    return matched
