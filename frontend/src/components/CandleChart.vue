<script setup>
import { ref, onMounted, onUnmounted, watch } from "vue";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries, // 이동평균선용
  LineStyle, // 중간선을 점선으로 그릴 때 쓴다
  CrosshairMode, // 십자선 모드(자석/일반)
} from "lightweight-charts";
import { fetchCandles } from "../api/market";
import { useThemeStore } from "../stores/theme";
import { useIndicatorStore } from "../stores/indicators";
import {
  MA_DEFAULTS,
  sma,
  bollinger,
  ichimoku,
  rsi,
  TF_SEC,
} from "../utils/indicators";
import { BandFill } from "../utils/bandFill";

const props = defineProps({
  coin: { type: String, default: "btc" },
  timeframe: { type: String, default: "1d" },
  tick: { type: Object, default: null }, // 이 코인의 최신 ticker 메시지(실시간 갱신용)
});

const theme = useThemeStore();
const ind = useIndicatorStore();

// 모드별 차트 색. 차트는 CSS 변수를 못 읽어서(JS 옵션으로 받는다) 여기에 따로 둔다.
const palettes = {
  dark: { bg: "#151a23", text: "#8b93a1", grid: "#1e2531", border: "#232a36" },
  light: { bg: "#ffffff", text: "#6b7482", grid: "#eef0f3", border: "#e2e5ea" },
};

// 모드 이름을 받아 차트 옵션 조각을 만든다.
function chartColors(mode) {
  const p = palettes[mode];
  return {
    layout: {
      background: { color: p.bg },
      textColor: p.text,
      // 차트 축 글자도 가격·본문과 같은 글꼴로 맞춘다(라이브러리 기본은 Trebuchet MS)
      fontFamily: '-apple-system, "Segoe UI", "Noto Sans KR", sans-serif',
    },
    grid: { vertLines: { color: p.grid }, horzLines: { color: p.grid } },
    rightPriceScale: { borderColor: p.border },
    timeScale: { borderColor: p.border },
  };
}

const container = ref(null);
const error = ref("");

let chart = null;
let candleSeries = null;
let volumeSeries = null;
const maSeries = []; // 슬롯 번호(0~4)로 찾는 선 시리즈 배열
let lastCandles = []; // 가장 최근 캔들. 기간이 바뀌면 이걸로 선을 다시 계산한다.
let bbSeries = null;
let bbFill = null; // 볼린저 위·아래 선 사이를 칠하는 플러그인
let ichiSeries = null; // { tenkan, kijun, spanA, spanB } 선 4개
let ichiFill = null; // 구름을 칠하는 플러그인
let rsiSeries = null; // RSI 선. 켜져 있을 때만 있고, 차트 아래 둘째 칸(pane)에 그린다
let rsiFill = null; // 70~30 사이 연한 배경을 칠하는 플러그인
let rsiLines = []; // 70·30 기준선(점선) 2개

// ── 과거 이어받기용 상태 ──
let allRows = []; // 지금까지 받은 원본 행 전체(오래된 순). 자바의 List<Row> 필드와 같다.
let loadingMore = false; // 이어받는 중이면 true. 같은 요청이 겹쳐 나가는 걸 막는 잠금
let noMore = false; // 서버에 더 옛날 캔들이 없으면 true. 더 요청하지 않는다
let seq = 0; // load()를 부를 때마다 1씩 올리는 번호. 코인·봉이 바뀐 뒤 늦게 도착한 옛 응답을 버리는 데 쓴다

// ── 실시간 갱신용 상태 ──
let liveReady = false; // load()가 끝나 처음 그림이 완성된 뒤에만 true. 그 전의 ticker는 무시한다
let volBase = 0; // 마지막 봉이 웹소켓 누적을 시작하기 전에 이미 가지고 있던 거래량
let accBase = null; // 그 시점의 당일 누적 거래량(acc_trade_volume). 이후 늘어난 만큼을 더한다

function toSec(iso) {
  const s = /Z|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + "Z";
  return Math.floor(Date.parse(s) / 1000);
}

// 스토어의 MA 설정(기간·색·켜짐)을 차트에 반영한다.
// 로드 직후, 설정이 바뀔 때, 테마가 바뀔 때 모두 이 함수 하나를 부른다.
function applyMa() {
  ind.ma.forEach((m, i) => {
    maSeries[i].setData(sma(lastCandles, m.period)); // 기간이 바뀌었을 수 있어서 다시 계산
    maSeries[i].applyOptions({
      visible: m.on,
      color: ind.maColor(i, theme.theme),
      lineWidth: m.width,
      lineStyle: m.style,
    });
  });
}

// 볼린저 설정(기간·배수·색·켜짐)을 차트에 반영한다. applyMa와 같은 역할
function applyBb() {
  const b = ind.bb;
  const data = bollinger(lastCandles, b.period, b.mult);
  const opt = { visible: b.on, color: ind.bbColor(theme.theme) };
  bbSeries.upper.setData(data.upper);
  bbSeries.middle.setData(data.middle);
  bbSeries.lower.setData(data.lower);
  // 백그라운드(위·아래 선 사이 색): 위/아래 값을 시간별로 짝지어 넘기고, 색은 선 색을 따른다
  bbFill.setData(
    data.upper.map((u, i) => ({
      time: u.time,
      upper: u.value,
      lower: data.lower[i].value,
    })),
  );
  bbFill.setStyle({
    color: ind.bbColor(theme.theme),
    alpha: b.alpha / 100, // 설정은 1~60(%)라 0~1로 바꾼다
    visible: b.on && b.fill,
  });
  // 위·아래 선은 사용자가 고른 두께·모양, 중간선은 색과 켜짐만 따른다(점선 고정)
  const edge = { ...opt, lineWidth: b.width, lineStyle: b.style };
  bbSeries.upper.applyOptions(edge);
  bbSeries.lower.applyOptions(edge);
  bbSeries.middle.applyOptions(opt);
}

function applyIchi() {
  const s = ind.ichi;
  const d = ichimoku(lastCandles, s, TF_SEC[props.timeframe]);
  ichiSeries.tenkan.setData(d.tenkan);
    ichiSeries.kijun.setData(d.kijun);
    ichiSeries.spanA.setData(d.spanA);
    ichiSeries.spanB.setData(d.spanB);
    ichiFill.setData(d.cloud);
    // 구름 색은 점마다 들어 있어서(color) 여기 color는 예비값이다
    ichiFill.setStyle({ color: "#ef5350", alpha: 0.15, visible: s.on });
    for (const line of Object.values(ichiSeries)) {
      line.applyOptions({ visible: s.on })
    }
}

// RSI 칸을 반영한다. 켜져 있을 때만 시리즈를 만들고, 꺼지면 시리즈를 지워서 칸 자체가 사라지게 한다.
function applyRsi() {
  const r = ind.rsi;
  if (!r.on) {
    if (rsiSeries) {
      chart.removeSeries(rsiSeries); // 칸 안의 마지막 시리즈라 칸도 같이 없어진다
      rsiSeries = null;
      rsiFill = null;
      rsiLines = [];
    }
    return;
  }

  if (!rsiSeries) {
    // 세 번째 값 1이 "둘째 칸"이다 (0이 캔들 칸).
    rsiSeries = chart.addSeries(
      LineSeries,
      {
        lineWidth: 1,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
        priceFormat: { type: "price", precision: 2, minMove: 0.01 },
        // 눈금을 0~100으로 고정한다. 안 하면 값 범위에 따라 눈금이 흔들린다.
        autoscaleInfoProvider: () => ({
          priceRange: { minValue: 0, maxValue: 100 },
        }),
      },
      1,
    );
    rsiFill = new BandFill();
    rsiSeries.attachPrimitive(rsiFill);
    // 과열(70)·침체(30) 기준선
    rsiLines = [70, 30].map((price) =>
      rsiSeries.createPriceLine({
        price,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: "",
      }),
    );
    // 캔들 칸 : RSI 칸 = 4 : 1 비율
    const panes = chart.panes();
    panes[0].setStretchFactor(4);
    panes[1].setStretchFactor(1);
  }

  const data = rsi(lastCandles, r.period);
  const color = ind.rsiColor(theme.theme);
  rsiSeries.setData(data);
  rsiSeries.applyOptions({ color, lineWidth: r.width, lineStyle: r.style });
  // 70~30 사이 연한 배경. 색은 RSI 선 색을 따른다.
  rsiFill.setData(data.map((d) => ({ time: d.time, upper: 70, lower: 30 })));
  rsiFill.setStyle({ color, alpha: 0.08, visible: true });
  // 기준선 색은 차트 글자색(모드별)을 쓴다
  const lineColor = palettes[theme.theme].text;
  rsiLines.forEach((l) => l.applyOptions({ color: lineColor }));
}

// 받아 둔 행(rows)을 차트와 지표선에 반영한다. load와 loadMore가 같이 쓴다.
function draw(rows) {
  // 차트 형식으로 변환한다(Java의 stream().map()과 같다)
  const candles = rows.map((r) => ({
    time: toSec(r.candle_time),
    open: r.open,
    high: r.high,
    low: r.low,
    close: r.close,
  }));
  candleSeries.setData(candles);

  lastCandles = candles;
  applyMa(); // 이동평균선 5개 계산 + 켜짐·색 적용
  applyBb();
  applyIchi();
  applyRsi();

  volumeSeries.setData(
    rows.map((r) => ({
      time: toSec(r.candle_time),
      value: r.volume,
      color: r.close >= r.open ? "rgba(239,83,80,0.5)" : "rgba(66,133,244,0.5)",
    })),
  );
}

// 처음 로딩(코인·봉이 바뀔 때도 호출). 최근 300개로 처음부터 다시 시작한다.
async function load() {
  error.value = "";
  liveReady = false; // 새로 받는 동안은 실시간 갱신을 멈춘다 (옛 코인·봉에 섞이는 것 방지)
  const mySeq = ++seq; // 이 호출의 번호표
  noMore = false;
  loadingMore = false;
  try {
    const rows = await fetchCandles(props.coin, props.timeframe, 300);
    if (mySeq !== seq) return; // 기다리는 사이 코인·봉이 또 바뀌었으면 이 응답은 버린다
    allRows = rows;
    draw(allRows);
    chart.timeScale().fitContent();
    // 실시간 거래량의 기준: 방금 받은 마지막 봉의 거래량
    volBase = rows.length ? rows[rows.length - 1].volume : 0;
    accBase = null; // 첫 ticker가 오면 그때 누적값으로 정한다
    liveReady = true;
  } catch (e) {
    error.value = "차트 데이터를 불러오지 못했습니다.";
  }
}

// 왼쪽 끝에 가까워졌을 때 더 옛날 캔들 300개를 받아 앞에 붙인다.
async function loadMore() {
  if (loadingMore || noMore || allRows.length === 0) return; // 받는 중이거나 더 없으면 무시
  loadingMore = true;
  const mySeq = seq;
  try {
    const oldestIso = allRows[0].candle_time; // 지금 가진 가장 오래된 캔들의 시각
    // end_time은 "이하"라서 응답 맨 끝에 oldest 캔들이 한 번 더 온다
    const rows = await fetchCandles(props.coin, props.timeframe, 300, oldestIso);
    if (mySeq !== seq) return;

    // 겹치는 캔들 거르기: oldest보다 "확실히 옛날"인 것만 남긴다
    const oldestSec = toSec(oldestIso);
    const older = rows.filter((r) => toSec(r.candle_time) < oldestSec);
    if (older.length === 0) {
      noMore = true; // 더 받을 게 없다 = 가장 오래된 데이터까지 왔다
      return;
    }

    // 붙이기 전에 지금 보고 있는 구간을 기억해 둔다
    const range = chart.timeScale().getVisibleLogicalRange();
    allRows = [...older, ...allRows]; // 앞에 이어 붙인다(Java의 addAll(0, list)와 같다)
    draw(allRows);
    // 차트 구간은 "몇 번째 캔들"이라는 번호라서, 앞에 older.length개가 들어오면 밀린다.
    // 같은 만큼 밀어 줘야 화면이 튀지 않는다.
    if (range) {
      chart.timeScale().setVisibleLogicalRange({
        from: range.from + older.length,
        to: range.to + older.length,
      });
    }
  } catch (e) {
    error.value = "과거 캔들을 불러오지 못했습니다.";
  } finally {
    if (mySeq === seq) loadingMore = false; // 잠금 해제(Java의 finally와 같다)
  }
}

onMounted(() => {
  chart = createChart(container.value, {
    autoSize: true,
    timeScale: { timeVisible: true, secondsVisible: false },
    crosshair: { mode: CrosshairMode.Normal }, // 가로선이 마우스를 자유롭게 따라간다
  });
  // applyOptions는 기존 옵션과 합쳐서(덮어쓰기 아님) 적용하므로 timeVisible은 유지된다.
  chart.applyOptions(chartColors(theme.theme));

  candleSeries = chart.addSeries(CandlestickSeries, {
    upColor: "#ef5350",
    downColor: "#4285f4",
    borderVisible: false,
    wickUpColor: "#ef5350",
    wickDownColor: "#4285f4",
  });
  // 캔들이 아래 거래량 영역(아래 20%)과 겹치지 않게, 캔들 쪽 아래 여백을 25%로 늘린다.
  candleSeries.priceScale().applyOptions({
    scaleMargins: { top: 0.1, bottom: 0.25 },
  });

  volumeSeries = chart.addSeries(HistogramSeries, {
    priceFormat: { type: "volume" },
    priceScaleId: "",
  });
  volumeSeries
    .priceScale()
    .applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

  // 이동평균선 시리즈 5개를 만든다. 기간·색·켜짐은 applyMa()가 채운다.
  for (let i = 0; i < MA_DEFAULTS.length; i++) {
    maSeries[i] = chart.addSeries(LineSeries, {
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
  }

  const bbBase = {
    lineWidth: 1,
    priceLineVisible: false,
    lastValueVisible: false,
    crosshairMarkerVisible: false,
  };
  bbSeries = {
    upper: chart.addSeries(LineSeries, bbBase),
    middle: chart.addSeries(LineSeries, {
      ...bbBase,
      lineStyle: LineStyle.Dashed,
    }),
    lower: chart.addSeries(LineSeries, bbBase),
  };
  // 플러그인을 위 선 시리즈에 붙인다. 이후 차트가 그릴 때마다 알아서 칠해 준다.
  bbFill = new BandFill();
  bbSeries.upper.attachPrimitive(bbFill);

  // 일목 선 4개. 색은 고정(전환선 주황, 기준선 갈색, 스팬1 빨강, 스팬2 파랑)
  const ichiBase = {
    lineWidth: 1,
    priceLineVisible: false,
    lastValueVisible: false,
    crosshairMarkerVisible: false,
  };
  ichiSeries = {
    tenkan: chart.addSeries(LineSeries, { ...ichiBase, color: "#f57c00" }),
    kijun: chart.addSeries(LineSeries, { ...ichiBase, color: "#8d6e63" }),
    spanA: chart.addSeries(LineSeries, {
      ...ichiBase,
      color: "rgba(239,83,80,0.6)",
    }),
    spanB: chart.addSeries(LineSeries, {
      ...ichiBase,
      color: "rgba(66,133,244,0.6)",
    }),
  };
  ichiFill = new BandFill();
  ichiSeries.spanA.attachPrimitive(ichiFill); // 구름은 스팬1 시리즈에 붙인다

  // 보이는 구간이 바뀔 때마다 호출된다. from은 화면 왼쪽 끝의 캔들 번호이고,
  // 0이면 가진 데이터의 맨 처음이다. 20개 이내로 다가오면 미리 더 받는다.
  chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
    if (range && range.from < 20) loadMore();
  });

  load(); // 선 시리즈를 다 만든 뒤에 데이터를 넣는다
});

// 코인이나 봉이 바뀌면 다시 받아서 그린다.
watch(() => [props.coin, props.timeframe], load);

// ticker 메시지 하나로 마지막 봉(가격·거래량)을 갱신한다.
// allRows의 마지막 행을 고친 뒤 draw()로 다시 그리면 캔들·거래량·지표선이 항상 같은 데이터를 쓴다.
function applyTick(t) {
  if (!t || !liveReady || allRows.length === 0) return;
  // 다른 코인의 메시지는 무시한다 (코인을 바꾼 직후에 올 수 있다)
  if (t.code !== "KRW-" + props.coin.toUpperCase()) return;

  const step = TF_SEC[props.timeframe]; // 봉 길이(초)
  const price = t.trade_price;
  // 체결 시각이 속한 봉의 시작 시각. 업비트 봉은 UTC 0시부터 봉 길이 단위로 정렬돼 있다.
  const bucket = Math.floor(t.trade_timestamp / 1000 / step) * step;
  const lastSec = toSec(allRows[allRows.length - 1].candle_time);
  if (bucket < lastSec) return; // 늦게 도착한 옛 메시지

  if (bucket > lastSec) {
    // 새 봉이 시작됐다: 현재가로 시가·고가·저가·종가를 채워 새로 붙인다
    allRows.push({
      candle_time: new Date(bucket * 1000).toISOString(),
      open: price,
      high: price,
      low: price,
      close: price,
      volume: 0,
    });
    volBase = 0;
    accBase = t.acc_trade_volume;
  }

  const bar = allRows[allRows.length - 1];
  bar.high = Math.max(bar.high, price);
  bar.low = Math.min(bar.low, price);
  bar.close = price;

  // 거래량: 일봉은 당일 누적값이 곧 봉의 거래량. 1h·4h는 처음 받은 값 + 그 뒤 늘어난 누적량
  if (accBase === null) accBase = t.acc_trade_volume;
  bar.volume =
    props.timeframe === "1d"
      ? t.acc_trade_volume
      : volBase + (t.acc_trade_volume - accBase);

  draw(allRows);
}

// 부모가 새 ticker를 넘길 때마다(체결마다) 실행된다
watch(() => props.tick, applyTick);

// 테마가 바뀌면 차트 색과 선 색만 바꾼다. 캔들을 다시 받을 필요는 없다.
watch(
  () => theme.theme,
  (mode) => {
    chart?.applyOptions(chartColors(mode));
    if (maSeries.length) applyMa();
    if (bbSeries) applyBb();
    if (chart) applyRsi();
  },
);

// 이동평균 설정(기간·색·켜짐)이 바뀌면 선을 다시 반영한다.
watch(
  () => ind.ma,
  () => {
    if (maSeries.length) applyMa();
  },
  { deep: true },
);

// 볼린저 설정이 바뀌면 다시 반영한다.
watch(
  () => ind.bb,
  () => {
    if (bbSeries) applyBb();
  },
  { deep: true },
);

// 일목 설정이 바뀌면 다시 반영한다.
watch(
  () => ind.ichi,
  () => {
    if (ichiSeries) applyIchi();
  },
  { deep: true },
);

// RSI 설정(켜짐·길이·색·두께·모양)이 바뀌면 다시 반영한다.
watch(
  () => ind.rsi,
  () => {
    if (chart) applyRsi();
  },
  { deep: true },
);

onUnmounted(() => {
  chart?.remove();
  chart = null;
});
</script>

<template>
  <!-- 부모(.panel) 안에서 남는 높이를 차지하는 래퍼 -->
  <div style="flex: 1; min-height: 0; display: flex; flex-direction: column">
    <p v-if="error">{{ error }}</p>
    <!-- 차트가 그려질 자리. 높이 고정 대신 flex: 1, 모바일에서 너무 작아지지 않게 min-height만 둔다.
         autoSize: true라 이 칸 크기가 바뀌면 차트가 알아서 다시 맞춘다. -->
    <div ref="container" style="flex: 1; min-height: 320px; width: 100%"></div>
  </div>
</template>
