// 이동평균선 목록: 기간과 모드별 선 색. 기간은 백엔드 지표 판정과 같은 표준값(5/20/60/120/200).
// dark는 어두운 배경용(밝고 선명), light는 흰 배경용(진하고 선명).
// MA200은 파란 캔들(하락)과 안 헷갈리게 흰색/검정 계열로 둔다.
export const MA_DEFAULTS = [
  { period: 5, dark: "#ffd60a", light: "#ff9800" },
  { period: 20, dark: "#ff4d9d", light: "#e6007a" },
  { period: 60, dark: "#00e676", light: "#00a152" },
  { period: 120, dark: "#c77dff", light: "#7c3aed" },
  { period: 200, dark: "#ffffff", light: "#111827" },
];

// 단순 이동평균(SMA): 최근 period개 종가의 평균.
// candles: [{ time, close, ... }] 오래된 순. 결과: [{ time, value }]
// 앞쪽 period-1개는 평균을 낼 데이터가 부족하므로 결과에서 뺀다.
export function sma(candles, period) {
  const out = [];
  let sum = 0;
  for (let i = 0; i < candles.length; i++) {
    sum += candles[i].close;
    // 윈도우 밖으로 나간 값을 뺀다 (매번 다시 더하지 않는 슬라이딩 합)
    if (i >= period) sum -= candles[i - period].close;
    if (i >= period - 1)
      out.push({ time: candles[i].time, value: sum / period });
  }
  return out;
}

// 선 설정에서 고를 수 있는 값. 차트 라이브러리가 받는 값 그대로다.
// 두께(lineWidth): 1~4 / 모양(lineStyle): 0=실선, 1=점선, 2=파선
export const LINE_WIDTHS = [1, 2, 3, 4];
export const LINE_STYLES = [0, 1, 2];

// 볼린저밴드 기본값. 업계 표준 20일, 표준편차 2배. 색은 모드별 기본색.
// 파란 캔들(하락)·MA 색과 안 헷갈리게 청록 계열을 쓴다.
export const BB_DEFAULT = {
  period: 20,
  mult: 2,
  dark: "#26c6da",
  light: "#00838f",
};

// 볼린저밴드 계산: 중간선 = period개 종가의 평균, 위/아래선 = 중간선 ± mult × 표준편차.
// candles: 오래된 순. 결과: { upper, middle, lower } 각각 [{ time, value }]
// 앞쪽 period-1개는 데이터가 부족해서 결과에서 뺀다 (sma와 같은 규칙).
export function bollinger(candles, period, mult) {
  const upper = [];
  const middle = [];
  const lower = [];
  for (let i = period - 1; i < candles.length; i++) {
    // 이 시점까지의 최근 period개 종가만 잘라 낸다 (자바의 subList와 비슷)
    const w = candles.slice(i - period + 1, i + 1).map((c) => c.close);
    const mean = w.reduce((a, b) => a + b, 0) / period;
    // 표준편차: (값-평균)² 의 평균에 루트. period로 나누는 방식(모집단)이다.
    const sd = Math.sqrt(w.reduce((a, b) => a + (b - mean) ** 2, 0) / period);
    const time = candles[i].time;
    upper.push({ time, value: mean + mult * sd });
    middle.push({ time, value: mean });
    lower.push({ time, value: mean - mult * sd });
  }
  return { upper, middle, lower };
}
