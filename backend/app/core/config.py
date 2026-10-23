from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 애플리케이션 설정 .env 파일 에서 값을 읽어 타입 검증 및 필수 값이 없으면 서버 시작 시점에서 에러 발생
    # .env 파일 위치와 인코딩 지정, 정의되지 않은 변수는 무시함

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf8", extra="ignore"
    )

    # DB 접속 주소 기본값이 없으므로 .env에 반드시 있어야함
    database_url: str


# 앱 전체에서 이 인스턴스 하나를 import
settings = Settings()
