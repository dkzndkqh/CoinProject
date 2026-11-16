<script setup>
import { ref, onMounted, onUnmounted, watch } from "vue";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
} from "lightweight-charts";
import { fetchCandles } from "../api/market";
import { useThemeStore } from "../stores/theme";

const props = defineProps({
  coin: { type: String, default: "btc" },
  timeframe: { type: String, default: "1d" },
});

const theme = useThemeStore();

// 모드별 차트 색. 차트는 CSS 변수를 못 읽어서(JS 옵션으로 받는다) 여기에 따로 둔다.
const palettes = {
  dark: { bg: "#151a23", text: "#8b93a1", grid: "#1e2531", border: "#232a36" },
  light: { bg: "#ffffff", text: "#6b7482", grid: "#eef0f3", border: "#e2e5ea" },
};

// 모드 이름을 받아 차트 옵션 조각을 만든다.
function chartColors(mode) {
  const p = palettes[mode];
  return {
    layout: { background: { color: p.bg }, textColor: p.text },
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

function toSec(iso) {
  const s = /Z|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + "Z";
  return Math.floor(Date.parse(s) / 1000);
}

async function load() {
  error.value = "";
  try {
    const rows = await fetchCandles(props.coin, props.timeframe, 300);

    candleSeries.setData(
      rows.map((r) => ({
        time: toSec(r.candle_time),
        open: r.open,
        high: r.high,
        low: r.low,
        close: r.close,
      })),
    );
    volumeSeries.setData(
      rows.map((r) => ({
        time: toSec(r.candle_time),
        value: r.volume,
        color:
          r.close >= r.open ? "rgba(239,83,80,0.5)" : "rgba(66,133,244,0.5)",
      })),
    );
    chart.timeScale().fitContent();
  } catch (e) {
    error.value = "차트 데이터를 불러오지 못했습니다.";
  }
}

onMounted(() => {
  chart = createChart(container.value, {
    autoSize: true,
    timeScale: { timeVisible: true, secondsVisible: false },
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

  volumeSeries = chart.addSeries(HistogramSeries, {
    priceFormat: { type: "volume" },
    priceScaleId: "",
  });
  volumeSeries
    .priceScale()
    .applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

  load();
});

watch(() => [props.coin, props.timeframe], load);

// 테마가 바뀌면 차트 색만 바꾼다. 캔들을 다시 받을 필요는 없다.
watch(
  () => theme.theme,
  (mode) => chart?.applyOptions(chartColors(mode)),
);

onUnmounted(() => {
  chart?.remove();
  chart = null;
});
</script>

<template>
  <div>
    <p v-if="error">{{ error }}</p>
    <!-- 차트가 그려질 자리. 높이를 안 주면 0이라 아무것도 안 보인다. -->
    <div ref="container" style="width: 100%; height: 500px"></div>
  </div>
</template>
