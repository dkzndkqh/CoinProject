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

// 일목균형표 기본 기간(표준값 9/26/52). tenkan=전환선, kijun=기준선(선행스팬 이동 칸 수도 이것), senkouB=선행스팬2
export const ICHI_DEFAULT = { tenkan: 9, kijun: 26, senkouB: 52 };

// 봉 하나의 길이(초). 마지막 캔들 뒤 "미래 구름"의 시각을 만들 때 쓴다.
export const TF_SEC = { "1h": 3600, "4h": 14400, "1d": 86400 };

// i번째 캔들까지 최근 n개의 (최고가 + 최저가) / 2. 데이터가 모자라면 null.
function midline(candles, i, n) {
  if (i < n - 1) return null;
  let hi = -Infinity;
  let lo = Infinity;
  for (let k = i - n + 1; k <= i; k++) {
    hi = Math.max(hi, candles[k].high);
    lo = Math.min(lo, candles[k].low);
  }
  return (hi + lo) / 2;
}

// 일목균형표 계산. candles: 오래된 순, p: { tenkan, kijun, senkouB }, stepSec: 봉 길이(초)
// 결과: 각 선 [{ time, value }]과 구름 [{ time, upper, lower, color }]
export function ichimoku(candles, p, stepSec) {
  const n = candles.length;
  const tenkan = [];
  const kijun = [];
  const spanA = [];
  const spanB = [];
  // j번째 칸의 시각. 마지막 캔들을 넘어가면 봉 길이를 더해서 미래 시각을 만든다.
  const timeAt = (j) =>
    j < n ? candles[j].time : candles[n - 1].time + (j - (n - 1)) * stepSec;

  for (let i = 0; i < n; i++) {
    const t = midline(candles, i, p.tenkan); // 전환선
    const k = midline(candles, i, p.kijun); // 기준선
    const b = midline(candles, i, p.senkouB); // 선행스팬2 원값
    if (t !== null) tenkan.push({ time: candles[i].time, value: t });
    if (k !== null) kijun.push({ time: candles[i].time, value: k });
    // 선행스팬은 계산한 값을 kijun칸 "앞" 시각에 찍는다 (이게 구름이 미래로 나가는 이유)
    const time = timeAt(i + p.kijun);
    if (t !== null && k !== null) spanA.push({ time, value: (t + k) / 2 });
    if (b !== null) spanB.push({ time, value: b });
  }

  // 두 스팬을 시각으로 짝지어 구름을 만든다. 빨강=1이 위(상승), 파랑=2가 위(하락).
  const bByTime = new Map(spanB.map((x) => [x.time, x.value]));
  const cloud = spanA
    .filter((a) => bByTime.has(a.time))
    .map((a) => ({
      time: a.time,
      upper: a.value,
      lower: bByTime.get(a.time),
      color: a.value >= bByTime.get(a.time) ? "#ef5350" : "#4285f4",
    }));

  return { tenkan, kijun, spanA, spanB, cloud };
}
