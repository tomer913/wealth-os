"""
AIClassifier — uses Claude Haiku to classify budget transactions.

Called by BudgetProcessor when no rule matches with sufficient confidence.
classify_batch() sends up to 20 transactions in one API call and returns
one ClassifyResult per transaction in the same order.

Environment variables:
  ANTHROPIC_API_KEY              — required
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

    async def classify_batch(
        self,
        transactions: List[Dict[str, Any]],
        categories: list,
    ) -> List[ClassifyResult]:
        """
        Classify a batch of transactions in a single API call.
        Returns one ClassifyResult per transaction in the same order.
        Any unparseable or missing result falls back to confidence=0, category=None.
        """
        if not transactions:
            return []

        category_list = "\n".join(
            f"- id: {c.id} | name: {c.name} | type: {c.category_type}"
            + (f" | english: {c.name_en}" if getattr(c, "name_en", None) else "")
            for c in categories
            if c.is_active
        )

        transactions_text = "\n".join(
            f"{i + 1}. Description: {t.get('description', '')} | "
            f"Amount: {t.get('amount', 0)} {t.get('currency', 'ILS')} | "
            f"Date: {t.get('date', 'unknown')} | Source: {t.get('source', '')}"
            for i, t in enumerate(transactions)
        )

        n = len(transactions)
        prompt = f"""You are a budget classification assistant for an Israeli family's personal budget.

Available budget categories:
{category_list}

Classify ALL {n} transactions below.
Return a JSON array with exactly {n} objects, one per transaction, in order.

Transactions:
{transactions_text}

Rules:
1. Return ONLY a valid JSON array — no other text, no markdown fences.
2. Each object must have exactly: index (1-based int), category_id (uuid string or null), confidence (0.0-1.0), reasoning (brief English string), suggested_rule (object or null).
3. Consider Hebrew merchant names and Israeli context.
4. Set confidence < 0.7 if uncertain. Set category_id to null if confidence < 0.5.
5. suggested_rule: only include when confidence > 0.85 and a reliable keyword exists.
   Format: {{"operator": "AND", "rules": [{{"field": "description", "op": "contains", "value": "keyword"}}]}}
   Otherwise: "suggested_rule": null

Response (JSON array only):
[
  {{
    "index": 1,
    "category_id": "<uuid or null>",
    "confidence": 0.85,
    "reasoning": "brief explanation",
    "suggested_rule": null
  }}
]"""

        # ~150 output tokens per result + buffer
        max_tokens = min(4096, n * 150 + 256)

        try:
            response = await self._client.messages.create(
                model=AI_MODEL,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            text = text.strip()

            raw_list = json.loads(text)
            if not isinstance(raw_list, list):
                raise ValueError(f"Expected JSON array, got {type(raw_list).__name__}")

            total_in = response.usage.input_tokens
            total_out = response.usage.output_tokens
            log.info(
                "AI batch: %d transactions → %d tokens in / %d tokens out",
                n, total_in, total_out,
            )

            # Build 1-based index → parsed result map
            by_index: Dict[int, dict] = {
                item["index"]: item
                for item in raw_list
                if isinstance(item, dict) and "index" in item
            }

            results: List[ClassifyResult] = []
            per_in = total_in // n
            per_out = total_out // n

            for i in range(n):
                item = by_index.get(i + 1)
                if item is None:
                    log.warning("AI batch: missing result for transaction index %d", i + 1)
                    results.append(ClassifyResult(
                        category_id=None, confidence=0.0,
                        reasoning=None, suggested_rule=None,
                    ))
                    continue

                cat_str = item.get("category_id")
                confidence = float(item.get("confidence", 0.0))
                reasoning = item.get("reasoning")
                raw_rule = item.get("suggested_rule")

                category_id: Optional[UUID] = None
                if cat_str:
                    try:
                        category_id = UUID(str(cat_str))
                    except (ValueError, AttributeError):
                        pass

                suggested_rule = None
                if (
                    isinstance(raw_rule, dict)
                    and "operator" in raw_rule
                    and "rules" in raw_rule
                ):
                    suggested_rule = raw_rule

                results.append(ClassifyResult(
                    category_id=category_id,
                    confidence=confidence,
                    reasoning=reasoning,
                    suggested_rule=suggested_rule,
                    prompt_tokens=per_in,
                    completion_tokens=per_out,
                ))

            return results

        except json.JSONDecodeError as e:
            log.warning("AI batch returned invalid JSON: %s", e)
        except Exception as e:
            log.error("AI batch error: %s", e, exc_info=True)

        # On any failure return neutral results for the whole batch
        return [
            ClassifyResult(category_id=None, confidence=0.0, reasoning=None, suggested_rule=None)
            for _ in transactions
        ]
