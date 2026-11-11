import json
import logging
from typing import Any, Dict, List, Optional

from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI, RateLimitError
from tenacity import before_sleep_log, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from processor.mock import MOCK_RESPONSES
from processor.prompts import REQUIRED_KEYS

logger = logging.getLogger(__name__)

_TRANSIENT = (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)


class LLMOutputError(Exception):
    pass


def validate(task: str, data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise LLMOutputError(f"{task}: output is not a JSON object")
    for key, expected in REQUIRED_KEYS[task].items():
        if not isinstance(data.get(key), expected):
            raise LLMOutputError(f"{task}: missing or invalid key '{key}'")
    return data


class DeepSeekClient:
    def __init__(self, llm_cfg: Dict[str, Any], api_key: Optional[str], mock: bool = False) -> None:
        self.mock = mock
        self.model = str(llm_cfg.get("model", "deepseek-chat"))
        self.temperature = float(llm_cfg.get("temperature", 0.3))
        self.max_tokens = int(llm_cfg.get("max_tokens", 4000))
        self.thinking = str(llm_cfg.get("thinking", "disabled"))
        self.client: Optional[OpenAI] = None
        if not mock:
            if not api_key:
                raise RuntimeError("DEEPSEEK_API_KEY is not set")
            # SDK retries disabled so tenacity is the single retry layer
            self.client = OpenAI(api_key=api_key, base_url=llm_cfg["base_url"],
                                 timeout=float(llm_cfg.get("timeout_seconds", 90)), max_retries=0)

    @retry(
        retry=retry_if_exception_type(_TRANSIENT),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _call(self, messages: List[Dict[str, str]]) -> str:
        assert self.client is not None
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            response_format={"type": "json_object"},
            extra_body={"thinking": {"type": self.thinking}},
        )
        return resp.choices[0].message.content or ""

    def complete_json(self, task: str, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        if self.mock:
            return validate(task, json.loads(json.dumps(MOCK_RESPONSES[task])))
        last_error: Exception = LLMOutputError(f"{task}: no attempt made")
        # One extra attempt when the model returns malformed or incomplete JSON
        for attempt in range(2):
            content = self._call(messages)
            try:
                return validate(task, json.loads(content))
            except (json.JSONDecodeError, LLMOutputError) as exc:
                last_error = exc
                logger.warning("LLM task %s attempt %d returned invalid JSON: %s", task, attempt + 1, exc)
        raise LLMOutputError(str(last_error))
