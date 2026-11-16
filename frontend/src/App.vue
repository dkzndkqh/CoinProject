<script setup>
import { ref } from "vue";
import CandleChart from "./components/CandleChart.vue";
import { useThemeStore } from "./stores/theme";
import { useIndicatorStore } from "./stores/indicators";
import { MA_LIST } from "./utils/indicators";

const ind = useIndicatorStore();
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
        </div>
      </header>

      <!-- 이동평균선 켜기/끄기 칩. 켜진 건 .on 클래스로 강조, 앞의 작은 점은 선 색 -->
      <div class="chips">
        <button
          v-for="m in MA_LIST"
          :key="m.period"
          :class="{ on: ind.maOn.includes(m.period) }"
          @click="ind.toggleMa(m.period)"
        >
          <i :style="{ background: m[theme.theme] }"></i>MA{{ m.period }}
        </button>
      </div>

      <CandleChart coin="btc" :timeframe="timeframe" />
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
</style>
