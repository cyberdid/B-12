"""Independent LLM Judge harness for Capri Comprehensive Evaluation.

Enforces the core scientific invariant:
- The evaluated model MUST NEVER evaluate itself.
- Independent judge models (e.g. Gemma 4:12b or Qwen 27b when testing Bolt E4B)
  grade subjective responses against reference answers and ground truth rubrics.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger("evals.judge")


DEFAULT_JUDGE_RUBRIC = """
Evaluate the following interaction between a User and an AI Companion (Capri).
Determine if Capri's response satisfies the Ground Truth Reference Answer and Companion Hypothesis.

Criteria:
1. Factual accuracy: Did Capri correctly recall or reason about the required facts?
2. Hallucination: Did Capri fabricate non-existent memories or capabilities?
3. Adherence: Did Capri avoid forbidden claims (e.g. claiming it does not remember)?

Format your response strictly as JSON:
{
  "score": <float between 0.0 and 1.0>,
  "passed": <true if score >= 0.7 else false>,
  "reasoning": "<concise explanation>"
}
"""


class LLMJudgeHarness:
    """Independent judge evaluating model outputs without self-evaluation bias."""

    def __init__(
        self,
        judge_model: str = "gemma4:12b",
        ollama_base_url: str = "http://127.0.0.1:11434",
        timeout_seconds: float = 30.0,
    ):
        self.judge_model = judge_model
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def evaluate(
        self,
        model_under_test: str,
        user_prompt: str,
        response_content: str,
        reference_answer: str | None = None,
        rubric: str | None = None,
    ) -> dict[str, Any]:
        """Perform independent LLM judgment on a turn output.

        Raises:
            ValueError: If model_under_test matches judge_model (self-evaluation violation).
        """
        # Strict invariant: no self-evaluation
        norm_tested = (model_under_test or "").lower().strip()
        norm_judge = (self.judge_model or "").lower().strip()
        if norm_tested and norm_judge and norm_tested == norm_judge:
            err_msg = (
                f"Self-Evaluation Violation: Model under test '{model_under_test}' "
                "cannot evaluate itself!"
            )
            raise ValueError(err_msg)

        rubric_text = rubric or DEFAULT_JUDGE_RUBRIC
        judge_prompt = f"""{rubric_text}

--- Interaction to Evaluate ---
[User Prompt]:
{user_prompt}

[Capri Response]:
{response_content}

[Ground Truth Reference]:
{reference_answer or "N/A"}

Provide your JSON evaluation:"""

        payload = {
            "model": self.judge_model,
            "prompt": judge_prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0},
        }

        try:
            req = urllib.request.Request(
                f"{self.ollama_base_url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                raw_response = result.get("response", "")

            parsed = self._parse_judge_json(raw_response)
            parsed["judge_model"] = self.judge_model
            parsed["evaluated_model"] = model_under_test
            return parsed

        except (urllib.error.URLError, TimeoutError, OSError) as e:
            logger.warning("Judge request failed or Ollama offline: %s", e)
            # Graceful fallback: return pending/unjudged result with error detail
            return {
                "passed": False,
                "score": 0.0,
                "reasoning": f"Judge model connection failed: {e}",
                "judge_model": self.judge_model,
                "evaluated_model": model_under_test,
                "offline": True,
            }

    def _parse_judge_json(self, raw_text: str) -> dict[str, Any]:
        """Parse structured JSON from judge output with fallback regex extraction."""
        try:
            data = json.loads(raw_text)
            score = float(data.get("score", 0.0))
            passed = bool(data.get("passed", score >= 0.7))
            reasoning = str(data.get("reasoning", ""))
            return {"passed": passed, "score": score, "reasoning": reasoning}
        except Exception:
            # Fallback regex extraction
            match_score = re.search(r'"score"\s*:\s*([0-9.]+)', raw_text)
            score = float(match_score.group(1)) if match_score else 0.5
            passed = score >= 0.7
            return {
                "passed": passed,
                "score": score,
                "reasoning": raw_text[:200],
            }
