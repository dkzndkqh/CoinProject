from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 애플리케이션 설정 .env 파일 에서 값을 읽어 타입 검증 및 필수 값이 없으면 서버 시작 시점에서 에러 발생
    # .env 파일 위치와 인코딩 지정, 정의되지 않은 변수는 무시함

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf8", extra="ignore"
    )

    # DB 접속 주소 기본값이 없으므로 .env에 반드시 있어야함
    database_url: str

    # /api/internal/* 인증용 비밀 키. 내 PC(ai_inference)가 헤더로 보낸다.
    # 기본값이 없으므로 .env에 없으면 서버가 시작할 때 에러가 난다 (키 없이 열려 버리는 사고 방지).
    internal_api_key: str

    # Claude API 키. .env의 ANTHROPIC_API_KEY 값을 읽는다 (변수 이름을 소문자로 바꾼 필드와 자동으로 연결된다).
    # 기본값을 빈 문자열로 둔 이유: 키가 없는 환경(CI, 테스트)에서도 앱이 시작되어야 해서다.
    # 키가 없는데 실제로 Claude를 부르면 clients/llm.py가 분명한 에러를 낸다.
    anthropic_api_key: str = ""

    # 에이전트가 쓸 모델 이름. 코드에 박지 않고 .env(LLM_MODEL)로 바꿀 수 있게 한다.
    llm_model: str = "claude-haiku-4-5"


# 앱 전체에서 이 인스턴스 하나를 import
settings = Settings()
