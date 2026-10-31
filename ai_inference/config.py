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


# 입력 종류별 설정. {입력 봉: {예측 칸 수, 저장할 기간}}
# 입력 봉마다 '몇 칸을 예측할지'와 '그중 어떤 칸을 어떤 이름으로 저장할지'가 다르다.
# 4h봉: 42칸 = 7일. 1번째 칸 = 4시간 뒤, 6번째 칸 = 24시간(1일) 뒤, 42번째 칸 = 7일 뒤.
# 1d봉 입력: 일봉 512개를 보고 7칸(7일)을 예측한다. 칸 하나가 하루라서 칸 번호가 곧 며칠 뒤다.
# 하루에 한 번, 일봉이 마감될 때(00:00 UTC = 09:00 KST)만 계산한다. 4h보다 칸이 적어 더 빨리 끝난다.
# 4h 입력도 1d~7d를 저장하는데, 모델 이름표(…|4h42 / …|1d7)가 달라서 DB에서 서로 덮어쓰지 않는다.
INPUTS = {
    "4h": {
        "pred_len": 42,
        "save_steps": {
            "4h": 1,
            "8h": 2,
            "12h": 3,
            "1d": 6,
            "2d": 12,
            "3d": 18,
            "4d": 24,
            "5d": 30,
            "6d": 36,
            "7d": 42,
        },
    },
    "1d": {
        "pred_len": 7,
        "save_steps": {
            "1d": 1,
            "2d": 2,
            "3d": 3,
            "4d": 4,
            "5d": 5,
            "6d": 6,
            "7d": 7,
        },
    },
    # 1d봉 입력은 3번 단계에서 여기에 추가한다. (7칸, 1d~7d)
}

MARKETS = ["KRW-BTC", "KRW-ETH"]

settings = Settings()
