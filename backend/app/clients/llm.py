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


def ask(system: str, user: str, max_tokens: int = 1024) -> dict:
    """Claude에게 질문 하나를 보내고 답을 돌려준다.

    system: 역할과 규칙을 적는 지시문 (예: "너는 암호화폐 분석가다")
    user: 사용자의 질문이나 입력 데이터
    max_tokens: 답의 최대 길이. 넘으면 답이 중간에 잘린다.
    돌려주는 값: {"text": 답 문장, "input_tokens": 보낸 토큰 수, "output_tokens": 받은 토큰 수}
    """

    if not settings.anthropic_api_key:
        # 키가 없는데 호출하면 SDK가 알아듣기 어려운 에러를 보냄
        raise RuntimeError("ANTHROPIC_API_KEY가 설정되어 있지 않습니다")

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
