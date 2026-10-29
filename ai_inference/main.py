import logging
import time

from backend_client import get_candles, post_forecast
from config import INPUTS, MARKETS
from forecaster import STEP, load_predictor, make_forecasts

# logging은 자바의 SLF4J/Logger와 같다. print보다 시각과 수준(INFO, ERROR)이 같이 찍혀서
# 오래 도는 프로그램의 기록을 나중에 읽기 좋다.
log = logging.getLogger("ai_inference")

CHECK_INTERVAL_SEC = 15 * 60  # 새 봉이 생겼는지 확인하는 주기 (15분)

# 기록 장부: '마지막으로 계산한 기준 시각'을 (코인, 입력 봉) 단위로 적어 둔다.
# 예: {("KRW-BTC", "4h"): 2026-10-30 04:00 UTC}
# 프로그램 안에만 있는 메모라서 껐다 켜면 사라진다. 그러면 한 번은 다시 계산하지만,
# 백엔드가 같은 예측을 무시해 주므로 DB에 중복이 쌓이지는 않는다.
last_done: dict[tuple[str, str], object] = {}


def process(predictor, market: str, timeframe: str) -> None:
    """코인 하나, 입력 봉 하나를 확인하고, 새 봉이 있을 때만 계산해서 올린다."""
    # ① 가볍게 확인: 마감된 최신 캔들 1개만 받아서 기준 시각을 계산한다 (GPU를 안 쓴다).
    latest = get_candles(market, timeframe, limit=1)
    base_time = latest["candle_time"].iloc[-1] + STEP[timeframe]

    # 장부의 기준 시각과 같으면 이미 계산한 것이다. 바로 끝낸다.
    if last_done.get((market, timeframe)) == base_time:
        return

    # ② 새 봉이다. 입력용 캔들 512개를 받아서 계산한다 (코인당 약 3분).
    log.info("새 봉 감지: %s %s 기준 %s, 계산 시작", market, timeframe, base_time)
    candles = get_candles(market, timeframe)
    forecasts = make_forecasts(predictor, market, timeframe, candles)

    # ③ 결과를 백엔드에 올린다. True면 새로 저장, False면 이미 있어서 건너뜀.
    saved = [post_forecast(f) for f in forecasts]
    log.info(
        "업로드 완료: %s %s 총 %d건 중 새로 저장 %d건",
        market,
        timeframe,
        len(saved),
        sum(saved),
    )

    # ④ 전부 성공했을 때만 장부에 적는다. 중간에 실패하면 장부가 그대로라서 다음 확인 때 다시 시도한다.
    last_done[(market, timeframe)] = candles["candle_time"].iloc[-1] + STEP[timeframe]


def run_once(predictor) -> None:
    """모든 코인, 모든 입력 봉을 한 번씩 확인한다."""
    for market in MARKETS:
        for timeframe in INPUTS:
            try:
                process(predictor, market, timeframe)
            except Exception:
                # 하나가 실패(서버 꺼짐, 캔들 없음 등)해도 프로그램이 죽지 않고 나머지를 계속한다.
                # log.exception은 에러 내용과 위치(스택 트레이스)를 같이 기록한다.
                log.exception("실패: %s %s (다음 확인 때 다시 시도)", market, timeframe)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    predictor = load_predictor()  # 모델은 시작할 때 한 번만 불러온다 (무거운 작업)
    log.info(
        "시작: %d개 코인, 입력 봉 %s, %d분마다 확인",
        len(MARKETS),
        list(INPUTS),
        CHECK_INTERVAL_SEC // 60,
    )
    while True:  # 끝나지 않는 반복. Ctrl+C로 멈춘다.
        run_once(predictor)
        time.sleep(CHECK_INTERVAL_SEC)  # 15분 쉰다


# 이 파일을 직접 실행했을 때만 main()을 부른다. (다른 파일이 import할 때는 실행되지 않음)
# 자바의 public static void main(String[] args)와 같은 시작점이다.
if __name__ == "__main__":
    main()
