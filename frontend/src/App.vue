<script setup>
import { ref, computed, onMounted, onUnmounted } from "vue";
import CandleChart from "./components/CandleChart.vue";
import { connectTicker } from "./api/ticker";
import { makeQuote } from "./utils/quote";
import { useThemeStore } from "./stores/theme";
import { useIndicatorStore } from "./stores/indicators";
import IndicatorSettings from "./components/IndicatorSettings.vue";

const ind = useIndicatorStore();
const showSettings = ref(false); // 설정 창을 보일지 여부
const timeframe = ref("1d");
// 선택된 코인. 값은 백엔드 URL에 들어가는 소문자('btc'|'eth')
const coin = ref("btc");
// 코인 목록. name은 한글 이름, market은 업비트 식 표기, glyph·color는 동그란 아이콘용
const coins = [
  { value: "btc", name: "비트코인", market: "BTC/KRW", glyph: "₿", color: "#f7931a" },
  { value: "eth", name: "이더리움", market: "ETH/KRW", glyph: "Ξ", color: "#627eea" },
];
// 현재 선택된 코인 객체를 찾는다. coin이 바뀌면 자동으로 다시 계산된다.
// (자바로 치면 list.stream().filter(...).findFirst() 결과를 필드처럼 쓰는 것과 같다)
const currentCoin = computed(() => coins.find((c) => c.value === coin.value));

// ── 코인별 시세 (현재가, 전일 대비) ──
const quotes = ref({}); // { btc: {cls, price, pct, amount}, eth: {...} }
const showCoinMenu = ref(false); // 코인 목록이 펼쳐졌는지

// 웹소켓 연결 종료 함수. 화면이 사라질 때 호출한다.
let stopTicker = null;

onMounted(() => {
  // ticker 메시지가 올 때마다 해당 코인의 시세만 갈아 끼운다.
  // t.code는 "KRW-BTC" 모양이라 "KRW-"를 떼고 소문자로 바꾸면 coins의 value("btc")와 같다.
  stopTicker = connectTicker((t) => {
    const key = t.code.replace("KRW-", "").toLowerCase();
    quotes.value[key] = makeQuote(t);
  });
});

onUnmounted(() => {
  if (stopTicker) stopTicker();
});

// 시세는 웹소켓이 계속 갱신하므로 펼칠 때 다시 받을 필요가 없다.
function toggleCoinMenu() {
  showCoinMenu.value = !showCoinMenu.value;
}
function selectCoin(value) {
  coin.value = value;
  showCoinMenu.value = false;
}
const theme = useThemeStore(); // 공유 스토어를 꺼낸다. theme.theme, theme.toggle() 로 쓴다.

const timeframes = [
  { label: "1시간", value: "1h" },
  { label: "4시간", value: "4h" },
  { label: "일", value: "1d" },
];
</script>

<template>
  <main class="page">
    <section class="panel">
      <header class="bar">
        <div>
          <div class="coin-wrap">
            <!-- 코인 선택 버튼. 눌러야 하는 버튼이라는 걸 테두리와 화살표 칸으로 알린다 -->
            <button
              class="coin-pick"
              :aria-expanded="showCoinMenu"
              @click="toggleCoinMenu"
            >
              <span class="coin-dot" :style="{ background: currentCoin.color }">{{
                currentCoin.glyph
              }}</span>
              <span class="coin-name">{{ currentCoin.name }}</span>
              <span class="coin-market">{{ currentCoin.market }}</span>
              <span class="coin-chev">▼</span>
            </button>

            <!-- 목록 밖을 누르면 닫히게 하는 투명 막. 메뉴(z-index 5)보다 아래(4)에 깐다 -->
            <div
              v-if="showCoinMenu"
              class="backdrop"
              @click="showCoinMenu = false"
            ></div>

            <div v-if="showCoinMenu" class="coin-menu">
              <div class="menu-head">코인 선택</div>
              <button
                v-for="c in coins"
                :key="c.value"
                class="menu-item"
                :class="{ on: coin === c.value }"
                @click="selectCoin(c.value)"
              >
                <span class="check">{{ coin === c.value ? "✓" : "" }}</span>
                <span class="coin-dot" :style="{ background: c.color }">{{
                  c.glyph
                }}</span>
                <span class="menu-name">
                  <b>{{ c.name }}</b>
                  <small>{{ c.market }}</small>
                </span>
                <!-- 시세가 있으면 코인마다 자기 색(cls)으로 칠한다 -->
                <span
                  v-if="quotes[c.value]"
                  class="menu-price"
                  :class="quotes[c.value].cls"
                >
                  <b>{{ quotes[c.value].price }}</b>
                  <span class="menu-chg">
                    <span>{{ quotes[c.value].pct }}</span>
                    <span>{{ quotes[c.value].amount }}</span>
                  </span>
                </span>
              </button>
            </div>
          </div>

          <!-- 업비트 방식 시세: 큰 현재가, 그 아래 '퍼센트 ▲ 금액'. 현재가도 같은 색 -->
          <div v-if="quotes[coin]" class="quote" :class="quotes[coin].cls">
            <div class="big">
              {{ quotes[coin].price }}<small>KRW</small>
            </div>
            <div class="chg">
              <span>{{ quotes[coin].pct }}</span>
              <span>{{ quotes[coin].amount }}</span>
            </div>
          </div>
        </div>

        <div class="right">
          <div class="tabs">
            <button
              v-for="tf in timeframes"
              :key="tf.value"
              :class="{ active: timeframe === tf.value }"
              @click="timeframe = tf.value"
            >
              {{ tf.label }}
            </button>
          </div>

          <!-- 테마 전환 버튼. 지금이 다크면 해(→화이트), 화이트면 달(→다크)을 보여 준다. -->
          <button
            class="theme-btn"
            @click="theme.toggle()"
            aria-label="테마 전환"
          >
            {{ theme.theme === "dark" ? "화이트 모드" : "다크 모드" }}
          </button>

          <!-- 지표 설정 창 열기 -->
          <button
            class="theme-btn icon-btn"
            @click="showSettings = true"
            aria-label="지표 설정"
            title="지표 설정"
          >
            <!-- 톱니바퀴 아이콘(SVG). 색은 글자색(currentColor)을 따라가서 테마가 바뀌어도 맞는다 -->
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <circle cx="12" cy="12" r="3" />
              <path
                d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"
              />
            </svg>
          </button>
        </div>
      </header>

      <!-- 이동평균선 켜기/끄기 칩. 켜진 건 .on 클래스로 강조, 앞의 작은 점은 선 색 -->
      <div class="chips">
        <button
          v-for="(m, i) in ind.ma"
          :key="i"
          :class="{ on: m.on }"
          @click="ind.toggleMa(i)"
        >
          <i :style="{ background: ind.maColor(i, theme.theme) }"></i>MA{{
            m.period
          }}
        </button>

        <button :class="{ on: ind.bb.on }" @click="ind.toggleBb()">
          <i :style="{ background: ind.bbColor(theme.theme) }"></i>볼린저 밴드
          {{ ind.bb.period }}/{{ ind.bb.mult }}
        </button>

        <button :class="{ on: ind.ichi.on }" @click="ind.toggleIchi()">
          <i style="background: #ef5350"></i>일목 구름
          {{ ind.ichi.tenkan }}/{{ ind.ichi.kijun }}/{{ ind.ichi.senkouB }}
        </button>
      </div>

      <CandleChart :coin="coin" :timeframe="timeframe" />

      <!-- v-if가 false면 DOM에서 사라진다. @close는 자식의 emit("close")를 받는다 -->
      <IndicatorSettings v-if="showSettings" @close="showSettings = false" />
    </section>
  </main>
</template>

<style>
/* 색을 CSS 변수로 뺐다. 기본값은 화이트이고, <html data-theme="dark">일 때 다크 값으로 덮어쓴다.
    자바로 치면 상수 테이블 두 벌을 두고 현재 모드에 따라 고르는 것과 같다. */
:root {
  --bg: #f4f6f9;
  --panel: #ffffff;
  --border: #e2e5ea;
  --text: #1c2330;
  --muted: #6b7482;
  --track: #eef0f4;
  --tab-active-bg: #2563eb; /* 선택된 탭: 두 모드 공통 파란색 */
  --tab-active-text: #ffffff;
  --up: #d24f45; /* 상승·보합 빨강. 화이트 모드는 흰 배경에서 읽히게 조금 진하게 */
  --down: #1261c4; /* 하락 파랑 */
}
:root[data-theme="dark"] {
  --bg: #0e1117;
  --panel: #151a23;
  --border: #232a36;
  --text: #e6e8ec;
  --muted: #8b93a1;
  --track: #0e1117;
  --up: #ef5350;
  --down: #4285f4;
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, "Segoe UI", "Noto Sans KR", sans-serif;
  display: block;
}

/* 버튼·입력칸은 기본으로 글꼴을 안 물려받아서(브라우저 기본 Arial) 본문 글꼴을 따르게 한다 */
button,
input,
select,
textarea {
  font-family: inherit;
}
</style>

<style scoped>
.page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 16px;
}
.panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px;
}
.bar {
  display: flex;
  align-items: flex-start; /* 왼쪽(코인+시세)이 두 줄이라 오른쪽 버튼들을 위에 맞춘다 */
  justify-content: space-between;
  flex-wrap: wrap; /* 좁은 화면에서 제목과 버튼들이 줄바꿈되게 */
  gap: 8px;
  margin-bottom: 12px;
}
/* ── 코인 선택 버튼과 목록 ── */
.coin-wrap {
  position: relative; /* 목록을 버튼 바로 아래에 띄우는 기준 */
}
.coin-pick {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px 5px 6px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel);
  color: var(--text);
  font: inherit;
  cursor: pointer;
}
.coin-dot {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  color: #fff;
  flex: 0 0 auto;
}
.coin-name {
  font-size: 17px;
  font-weight: 700;
}
.coin-market {
  font-size: 12px;
  color: var(--muted);
}
.coin-chev {
  width: 26px;
  height: 26px;
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  background: var(--track);
  color: var(--muted);
  transition: transform 0.15s;
}
/* 마우스를 올리거나 펼쳤을 때: 테두리가 진해지고 화살표 칸이 반전된다 */
.coin-pick:hover,
.coin-pick[aria-expanded="true"] {
  border-color: var(--text);
}
.coin-pick:hover .coin-chev,
.coin-pick[aria-expanded="true"] .coin-chev {
  background: var(--text);
  color: var(--panel);
}
.coin-pick[aria-expanded="true"] .coin-chev {
  transform: rotate(180deg);
}

.backdrop {
  position: fixed;
  inset: 0;
  z-index: 4;
}
.coin-menu {
  position: absolute;
  z-index: 5;
  left: 0;
  top: calc(100% + 6px);
  width: 340px;
  max-width: calc(100vw - 32px);
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
  overflow: hidden;
}
.menu-head {
  padding: 7px 12px;
  font-size: 11px;
  color: var(--muted);
  border-bottom: 1px solid var(--border);
}
.menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  border: none;
  background: transparent;
  color: var(--text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.menu-item + .menu-item {
  border-top: 1px solid var(--border);
}
.menu-item:hover,
.menu-item.on {
  background: var(--track);
}
.check {
  width: 14px;
  font-weight: 700;
}
.menu-name {
  display: flex;
  flex-direction: column;
}
.menu-name small {
  font-size: 11px;
  color: var(--muted);
}
.menu-price {
  margin-left: auto;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.menu-chg {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
  font-size: 12px;
}

/* ── 업비트 방식 시세 ── */
.quote {
  margin-top: 8px;
}
.big {
  font-size: 30px;
  font-weight: 700;
  line-height: 1.15;
  font-variant-numeric: tabular-nums;
}
.big small {
  margin-left: 4px;
  font-size: 12px;
  font-weight: 400;
}
.chg {
  display: flex;
  gap: 8px;
  align-items: baseline;
  font-size: 14px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
/* 시세 영역과 목록이 같이 쓰는 색 규칙: 상승·보합 빨강, 하락 파랑 */
.up {
  color: var(--up);
}
.down {
  color: var(--down);
}
.right {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.tabs {
  display: flex;
  gap: 2px;
  padding: 3px;
  background: var(--track);
  border-radius: 8px;
}
.tabs button {
  padding: 6px 14px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--muted);
  font-size: 13px;
  cursor: pointer;
  transition:
    background 0.15s,
    color 0.15s;
}
.tabs button:hover {
  color: var(--text);
}
.tabs button.active {
  background: var(--tab-active-bg);
  color: var(--tab-active-text);
}

.chips {
  display: flex;
  flex-wrap: wrap; /* 모바일에서 줄바꿈 */
  gap: 6px;
  margin-bottom: 8px;
}
.chips button {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: transparent;
  color: var(--muted);
  font-size: 12px;
  cursor: pointer;
}
.chips button.on {
  color: var(--text);
  border-color: var(--text);
}
.chips i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.theme-btn {
  height: 34px;
  padding: 0 12px; /* 글자 폭에 맞게 늘어나도록 width 고정을 뺐다 */
  border: none;
  border-radius: 8px;
  background: var(--track);
  color: var(--text);
  font-size: 13px;
  cursor: pointer;
}
/* 아이콘 버튼. .theme-btn보다 뒤에 둬야 padding·height가 덮어써진다(같은 우선순위는 나중 규칙이 이긴다) */
.icon-btn {
  width: 38px;
  height: 38px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
.icon-btn:hover {
  color: var(--tab-active-bg);
}
</style>
