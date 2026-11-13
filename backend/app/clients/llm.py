import anthropic

from app.core.config import settings

# 모듈이 처음 불러와질 때 클라이언트를 한 번만 만들고 계속 재사용한다.
# 자바의 싱글톤 빈(@Bean)과 같다. 요청마다 새로 만들면 연결을 매번 새로 맺어서 느려진다.
# 키가 비어 있어도 여기서는 에러가 나지 않는다 (CI나 테스트처럼 키가 없는 환경에서도 앱이 켜지게).
# 키 검사는 실제로 부르는 ask() 안에서 한다.

_client = anthropic.Anthropic(
    api_key=settings.anthropic_api_key or None,
    # 응답이 60초 안에 안오면 포기.
    timeout=60.0,
    # 일시적 오류로 재시도
    max_retries=2,
)


class LLMError(Exception):
    """Claude API 호출이 SDK의 자동 재시도(2번) 후에도 실패했을 때. 예: 네트워크 끊김, 한도 초과, 서버 오류."""


def _check_key() -> None:
    """API 키가 없으면 알아보기 쉬운 에러를 낸다. ask()와 ask_with_tool()이 같이 쓴다."""
    if not settings.anthropic_api_key:
        # 키가 없는데 호출하면 SDK가 알아듣기 어려운 에러를 보냄
        raise RuntimeError("ANTHROPIC_API_KEY가 설정되어 있지 않습니다")


def ask(system: str, user: str, max_tokens: int = 1024) -> dict:
    """Claude에게 질문 하나를 보내고 답을 돌려준다.

    system: 역할과 규칙을 적는 지시문 (예: "너는 암호화폐 분석가다")
    user: 사용자의 질문이나 입력 데이터
    max_tokens: 답의 최대 길이. 넘으면 답이 중간에 잘린다.
    돌려주는 값: {"text": 답 문장, "input_tokens": 보낸 토큰 수, "output_tokens": 받은 토큰 수}
    """

    _check_key()

    response = _client.messages.create(
        model=settings.llm_model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )

    # response.content는 블록 목록이다. 글 블록(type == "text")만 모아서 이어 붙인다.
    text = "".join(b.text for b in response.content if b.type == "text")
    return {
        "text": text,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }


def ask_with_tool(system: str, user: str, tool: dict, max_tokens: int = 2048) -> dict:
    """Claude에게 도구 하나를 반드시 호출하게 해서, 그 도구의 입력값(= 우리가 정한 양식에 채운 값)을 받는다.

    tool: {"name": 도구 이름, "description": 설명, "input_schema": JSON 스키마(dict)}
        양식은 AnalysisResult.model_json_schema()로 만든 것을 넣는다.
    돌려주는 값: {"input": 양식에 채운 dict (못 받으면 None), "stop_reason": 멈춘 이유,
                "input_tokens": ..., "output_tokens": ...}

    tool_choice로 강제하는 이유: 자유 글로 답하지 않고 반드시 양식 칸을 채워서 답하게 하기 위해서다.
    값이 양식 규칙에 맞는지(허용 값, 길이 등)는 여기서 검사하지 않고 호출한 쪽(서비스)이 pydantic으로 검사한다.
    """
    _check_key()

    # anthropic.APIError: SDK가 던지는 모든 API 에러의 부모 클래스다 (자바의 IOException 계열 부모처럼).
    # 서비스가 anthropic을 몰라도 되게 우리 에러(LLMError)로 바꿔서 던진다.
    # raise ... from e: 원래 에러를 원인(cause)으로 붙인다. 자바의 new LLMError(msg, cause)와 같다.
    try:
        response = _client.messages.create(
            model=settings.llm_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            # 호출할 수 있는 도구 목록. 자바로 치면 "사용 가능한 함수 목록"을 알려주는 것이다.
            tools=[tool],
            # {"type": "tool", "name": ...}: 이 도구를 반드시 호출하라고 강제한다.
            # (기본값 auto는 도구를 쓸지 말지 Claude가 정한다)
            tool_choice={"type": "tool", "name": tool["name"]},
        )
    except anthropic.APIError as e:
        raise LLMError(str(e)) from e

    # 응답 블록 중 도구 호출 블록(type == "tool_use")을 찾는다. 강제했으니 보통 하나 있다.
    # next(제너레이터, 기본값): 조건에 맞는 첫 항목을 꺼낸다. 없으면 기본값(None)을 돌려준다.
    # (자바 스트림의 findFirst().orElse(null)과 같다)
    block = next((b for b in response.content if b.type == "tool_use"), None)
    return {
        "input": block.input if block else None,
        "stop_reason": response.stop_reason,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }


def ask_with_tools(
    system: str,
    messages: list,
    tools: list[dict],
    force_tool: str | None = None,
    max_tokens: int = 2048,
) -> dict:
    """도구 여러 개를 주고, 지금까지의 대화(messages)에 이어서 Claude를 한 번 부른다.
    도구 호출 반복문이 이 함수를 여러 번 부른다. 반복문 자체는 호출하는 쪽(서비스)이 만든다.

    messages: [{"role": "user"|"assistant", "content": ...}, ...] 지금까지의 전체 대화.
        Claude는 이전 호출을 기억하지 못해서 매번 전부 다시 보낸다.
    tools: 쓸 수 있는 도구 목록 (이름, 설명, 입력 스키마).
    force_tool: 도구 이름을 주면 그 도구를 반드시 호출하게 강제한다 (마지막 차례에 답안 제출을 강제할 때).
        None이면 Claude가 도구를 쓸지, 어떤 걸 쓸지 스스로 정한다 (auto).
    돌려주는 값:
        content: Claude 응답 블록 그대로. 다음 호출의 messages에 assistant 메시지로 붙여야 한다.
        tool_uses: Claude가 요청한 도구 호출 목록 [{"id", "name", "input"}]. 없으면 빈 목록.
        stop_reason, input_tokens, output_tokens
    """
    _check_key()

    # force_tool 이 있으면 그 도구를 강제, 없으면 자동 선택
    tool_choice = (
        {"type": "tool", "name": force_tool} if force_tool else {"type": "auto"}
    )

    try:
        response = _client.messages.create(
            model=settings.llm_model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
        )
    except anthropic.APIError as e:
        raise LLMError(str(e)) from e

    # 응답에서 도구 요청 블록만 뽑는다. Claude는 한 번에 도구를 여러 개 요청할 수도 있다.
    tool_uses = [
        {"id": b.id, "name": b.name, "input": b.input}
        for b in response.content
        if b.type == "tool_use"
    ]
    return {
        "content": response.content,
        "tool_uses": tool_uses,
        "stop_reason": response.stop_reason,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
