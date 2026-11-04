import json
import logging
from pathlib import Path

from pydantic import ValidationError

from app.agent.schemas import ChatTurn, QuestionPlan
from app.clients import llm

logger = logging.getLogger(__name__)

# 분류 프롬프트 파일.
PROMPT_PATH = Path(__file__).parent / "prompts" / "planner.md"

# Claude가 분류 결과를 낼 때 채우는 스키마 도구. service.py의 SUBMIT_TOOL과 같은 방식으로,
# input_schema는 QuestionPlan에서 자동으로 만든다 (스키마가 바뀌면 QuestionPlan 한 곳만 고치면 된다).
PLAN_TOOL = {
    "name": "submit_plan",
    "description": "질문 분류 결과를 제출한다. 분류 결과는 반드시 이 도구로 낸다.",
    "input_schema": QuestionPlan.model_json_schema(),
}

# 분류 결과는 짧은 JSON 한 덩어리라 출력 상한을 작게 둔다 (분석 호출의 2048보다 훨씬 작다).
MAX_TOKENS = 256


def _build_user_message(question: str, history: list[ChatTurn]) -> str:
    """분류 호출에 보낼 사용자 메시지. 이력과 질문을 태그로 나눠서, 안에 든 지시가 섞이지 않게 한다.
    history는 ChatTurn 객체 리스트다. model_dump()로 dict로 바꿔야 json.dumps가 직렬화할 수 있다.
    (자바에서 DTO를 Jackson으로 JSON 문자열로 바꾸는 것과 같다)
    """
    turns = [turn.model_dump() for turn in history]
    return (
        f"<history>\n{json.dumps(turns, ensure_ascii=False)}\n</history>\n\n"
        f"<question>\n{question}\n</question>"
    )


def plan_question(question: str, history: list[ChatTurn]) -> QuestionPlan:
    """질문을 읽고 QuestionPlan(action, market, horizon)을 돌려준다.
    Claude 호출이 실패하거나 응답이 깨져도 예외를 내지 않고, 기본값 QuestionPlan(action="analyze")으로 돌아간다.
    (market, horizon이 None이면 이후 코드가 차트 힌트, BTC, 기본 1d로 채운다)
    분류가 실패했다고 사용자 요청 전체를 실패시키지 않기 위해서다.
    """
    fallback = QuestionPlan(action="analyze")

    system = PROMPT_PATH.read_text(encoding="utf-8")
    user = _build_user_message(question, history)

    try:
        raw = llm.ask_with_tool(system, user, PLAN_TOOL, max_tokens=MAX_TOKENS)
    except llm.LLMError as e:
        logger.warning("분류 호출 실패, 기본 값 사용 : %s", e)
        return fallback

    if raw["input"] is None:
        logger.warning(
            "분류가 양식도구를 호출하지 않음 (stop_reason=%s), 기본값 사용",
            raw["stop_reason"],
        )
        return fallback

    try:
        plan = QuestionPlan.model_validate(raw["input"])
    except ValidationError as e:
        logger.warning("분류 응답이 양식 규칙을 어김, 기본값 사용: %s", e)
        return fallback

    logger.info(
        "분류 action=%s market=%s horizon=%s tokens=%d/%d",
        plan.action,
        plan.market,
        plan.horizon,
        raw["input_tokens"],
        raw["output_tokens"],
    )
    return plan
