<script setup>
import { ref } from "vue";
import CandleChart from "./components/CandleChart.vue";
import { useThemeStore } from "./stores/theme";
import { useIndicatorStore } from "./stores/indicators";
import IndicatorSettings from "./components/IndicatorSettings.vue";

const ind = useIndicatorStore();
const showSettings = ref(false); // 설정 창을 보일지 여부
const timeframe = ref("1d");
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
        <h1 class="title">BTC <span>비트코인</span></h1>

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

      <CandleChart coin="btc" :timeframe="timeframe" />

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
}
:root[data-theme="dark"] {
  --bg: #0e1117;
  --panel: #151a23;
  --border: #232a36;
  --text: #e6e8ec;
  --muted: #8b93a1;
  --track: #0e1117;
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, "Segoe UI", "Noto Sans KR", sans-serif;
  display: block;
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
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
}
.title span {
  margin-left: 6px;
  font-size: 13px;
  font-weight: 400;
  color: var(--muted);
}
.right {
  display: flex;
  align-items: center;
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
