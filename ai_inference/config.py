from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """ai_inference 설정. .env에서 읽고, 필수 값이 없으면 시작 때 바로 에러가 난다.
    자바 Spring의 @ConfigurationProperties 클래스와 같은 역할이다.
    .env는 '실행한 위치(현재 폴더)' 기준이라 반드시 ai_inference 폴더에서 실행한다.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf8", extra="ignore"
    )

    # 백엔드 주소와 인증 키  
    backend_url: str
    internal_api_key: str

    # 모델 이름은 코드에 박지 않고 설정으로 둔다 (small로 바꾸거나 비교 실험할 때 .env만 고치면 된다).
    kronos_model: str = "NeoQuasar/Kronos-base"
    kronos_tokenizer: str = "NeoQuasar/Kronos-Tokenizer-base"

    # 같은 입력으로 몇번 시뮬레이션 할지 
    sample_count: int = 300

# 예측 기간별 (입력 봉, 예측 칸 수). 4h는 1h봉 4칸, 1d는 4h봉 6칸, 7d는 1d봉 7칸을 예측한다.
# 기간 목록은 코드에 하드코딩하지 말라는 방침이라, 나중에 30d를 넣을 때 여기만 고친다.
# 설정이 아니라 모듈 상수로 둔 이유: 환경마다 달라지는 값이 아니라 설계 값이기 때문이다.
HORIZONS = {
    "4h": {"input_timeframe": "1h", "pred_len": 4},
    "1d": {"input_timeframe": "4h", "pred_len": 6},
    "7d": {"input_timeframe": "1d", "pred_len": 7},
}

MARKETS = ["KRW-BTC", "KRW-ETH"]

settings = Settings()