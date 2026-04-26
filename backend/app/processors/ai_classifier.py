"""
AIClassifier — uses Claude Haiku to classify budget transactions.

Called by BudgetProcessor when no rule matches with sufficient confidence.
One API call returns: category_id, confidence, reasoning, and suggested_rule.

Environment variables:
  ANTHROPIC_API_KEY             — required
  BUDGET_AI_CONFIDENCE_THRESHOLD — default 0.70
"""
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

log = logging.getLogger(__name__)

AI_CONFIDENCE_THRESHOLD = float(os.getenv("BUDGET_AI_CONFIDENCE_THRESHOLD", "0.70"))
AI_MODEL = "claude-haiku-4-5-20251001"


@dataclass
class ClassifyResult:
    category_id: Optional[UUID]
    confidence: float
    reasoning: Optional[str]
    suggested_rule: Optional[Dict[str, Any]]  # conditions dict ready to store
    prompt_tokens: int = 0
    completion_tokens: int = 0


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
    ) -> ClassifyResult:
        """
        Classify a transaction using Claude Haiku.
        Single API call returns category + confidence + suggested rule.
        """
        category_list = "\n".join(
            f"- id: {c.id} | name: {c.name} | type: {c.category_type}"
            + (f" | english: {c.name_en}" if getattr(c, "name_en", None) else "")
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
7. For suggested_rule: only include if confidence > 0.85 and there is a reliable
   keyword. Otherwise set suggested_rule to null.

Response format (JSON only):
{{
  "category_id": "<uuid from the list>",
  "confidence": 0.0,
  "reasoning": "brief explanation in English",
  "suggested_rule": {{
    "operator": "AND",
    "rules": [
      {{"field": "description", "op": "contains", "value": "keyword"}}
    ]
  }}
}}

If no reliable rule exists, use: "suggested_rule": null"""

        try:
            response = await self._client.messages.create(
                model=AI_MODEL,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            text = text.strip()

            result = json.loads(text)
            category_id_str = result.get("category_id")
            confidence = float(result.get("confidence", 0.0))
            reasoning = result.get("reasoning")
            raw_rule = result.get("suggested_rule")

            if not category_id_str:
                return ClassifyResult(
                    category_id=None, confidence=0.0, reasoning=None,
                    suggested_rule=None,
                    prompt_tokens=response.usage.input_tokens,
                    completion_tokens=response.usage.output_tokens,
                )

            # Validate suggested_rule shape
            suggested_rule = None
            if isinstance(raw_rule, dict) and "operator" in raw_rule and "rules" in raw_rule:
                suggested_rule = raw_rule

            return ClassifyResult(
                category_id=UUID(category_id_str),
                confidence=confidence,
                reasoning=reasoning,
                suggested_rule=suggested_rule,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
            )

        except json.JSONDecodeError as e:
            log.warning("AI classifier returned invalid JSON: %s", e)
            return ClassifyResult(category_id=None, confidence=0.0, reasoning=None, suggested_rule=None)
        except Exception as e:
            log.error("AI classifier error: %s", e, exc_info=True)
            return ClassifyResult(category_id=None, confidence=0.0, reasoning=None, suggested_rule=None)
