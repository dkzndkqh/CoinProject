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
    if (i >= period - 1) out.push({ time: candles[i].time, value: sum / period });
  }
  return out;
}

