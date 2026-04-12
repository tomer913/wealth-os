"""
AIClassifier — uses Claude Haiku to classify budget transactions.

Called by BudgetProcessor when no rule matches with sufficient confidence.
Generates classification + optionally a rule for similar future transactions.

Environment variables:
  ANTHROPIC_API_KEY             — required
  BUDGET_AI_CONFIDENCE_THRESHOLD — default 0.70
"""
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

log = logging.getLogger(__name__)

AI_CONFIDENCE_THRESHOLD = float(os.getenv("BUDGET_AI_CONFIDENCE_THRESHOLD", "0.70"))
AI_MODEL = "claude-haiku-4-5-20251001"


class AIClassifier:

    def __init__(self):
        import anthropic
        self._client = anthropic.AsyncAnthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY"),
        )

    async def classify(
        self,
        transaction: Dict[str, Any],
        categories: list,
        db=None,
    ) -> Tuple[Optional[UUID], float, Optional[str]]:
        """
        Classify a transaction using Claude Haiku.
        Returns (category_id, confidence, reasoning).
        """
        category_list = "\n".join(
            f"- id: {c.id} | name: {c.name} | type: {c.category_type}"
            + (f" | english: {c.name_en}" if c.name_en else "")
            for c in categories
            if c.is_active
        )

        prompt = f"""You are a budget classification assistant for an Israeli family's personal budget.

Transaction to classify:
- Date: {transaction.get('date', 'unknown')}
- Description: {transaction.get('description', '')}
- Amount: {transaction.get('amount', 0)} {transaction.get('currency', 'ILS')}
- Source: {transaction.get('source', '')}

Available budget categories:
{category_list}

Rules:
1. Return ONLY valid JSON, no other text.
2. Choose the most appropriate category_id from the list above.
3. Consider Hebrew merchant names and Israeli context.
4. For salary/income: use the matching income category.
5. For mortgages/loans: match exact name if possible.
6. If genuinely uncertain, set confidence below 0.7.

Response format:
{{"category_id": "<uuid>", "confidence": 0.0-1.0, "reasoning": "<brief explanation in English>"}}"""

        try:
            response = await self._client.messages.create(
                model=AI_MODEL,
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text.strip()
            # Strip markdown code blocks if present
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            text = text.strip()

            result = json.loads(text)
            category_id_str = result.get("category_id")
            confidence = float(result.get("confidence", 0.0))
            reasoning = result.get("reasoning")

            if not category_id_str:
                return None, 0.0, None

            prompt_tokens = response.usage.input_tokens
            completion_tokens = response.usage.output_tokens

            # Store token counts on result for caller to log
            self._last_prompt_tokens = prompt_tokens
            self._last_completion_tokens = completion_tokens

            return UUID(category_id_str), confidence, reasoning

        except json.JSONDecodeError as e:
            log.warning("AI classifier returned invalid JSON: %s", e)
            return None, 0.0, None
        except Exception as e:
            log.error("AI classifier error: %s", e)
            return None, 0.0, None

    async def generate_rule(
        self,
        transaction: Dict[str, Any],
        category_id: UUID,
        category_name: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Ask Claude to generate a rule that would catch similar transactions.
        Returns conditions JSONB dict or None.
        Only generates a rule if it can be confident (conservative approach).
        """
        prompt = f"""You are a rule generator for a budget classification system.

This transaction was categorized as: {category_name}
- Description: {transaction.get('description', '')}
- Amount: {transaction.get('amount', 0)} {transaction.get('currency', 'ILS')}
- Source: {transaction.get('source', '')}

Generate a JSON rule that would reliably catch SIMILAR transactions.
Be conservative — only generate a rule if confidence > 0.85.
If no reliable rule is possible, return null.

Available fields: description, amount, source, economic_type, domain, currency
Available ops: contains, not_contains, eq, neq, gt, lt, between, starts_with, regex
(string ops are case-insensitive)

Rule format:
{{
  "operator": "AND",
  "rules": [
    {{"field": "description", "op": "contains", "value": "some text"}},
    ...
  ]
}}

Return ONLY the rule JSON or null. No other text."""

        try:
            response = await self._client.messages.create(
                model=AI_MODEL,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text.strip()
            if text.lower() in ("null", "none", ""):
                return None

            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            text = text.strip()

            conditions = json.loads(text)
            if not isinstance(conditions, dict):
                return None
            if "operator" not in conditions or "rules" not in conditions:
                return None

            return conditions

        except Exception as e:
            log.warning("Rule generation failed: %s", e)
            return None
