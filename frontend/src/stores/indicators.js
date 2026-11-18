import { defineStore } from "pinia";
import { ref, watch } from "vue";
import { MA_DEFAULTS } from "../utils/indicators";

const KEY = "chartMaSettings";

// 기본 설정 5슬롯을 만든다. 호출할 때마다 새 객체를 만들어서 기본값 원본이 수정되지 않게 한다.
// 슬롯 모양: { period: 기간, color: 사용자가 고른 색(없으면 null), on: 켜짐 여부 }
function makeDefaults() {
  return MA_DEFAULTS.map((m) => ({
    period: m.period,
    color: null, // null이면 모드별 기본색(MA_DEFAULTS의 dark/light)을 쓴다
    on: m.period === 20 || m.period === 60,
  }));
}

// 저장된 값이 쓸만한 모양인지 검사,
function isValid(s) {
  return (
    Array.isArray(s) &&
    s.length === MA_DEFAULTS.length &&
    s.every(
      (x) =>
        Number.isInteger(x.period) &&
        x.period >= 1 &&
        x.period <= 500 &&
        typeof x.on === "boolean" &&
        (x.color === null || typeof x.color === "string"),
    )
  );
}

// 저장된 선택 불러오기. 없거나 깨졌으면 기본값(20, 60일선)
function loadSaved() {
  try {
    const s = JSON.parse(localStorage.getItem(KEY));
    if (isValid(s)) return s;
  } catch (e) {}
  return makeDefaults(); // 없거나 깨졌으면 기본값
}

export const useIndicatorStore = defineStore("indicators", () => {
  const ma = ref(loadSaved()); // 5슬롯 배열. 순서가 곧 슬롯 번호(0~4)

  // 바뀔 때마다 브라우저에 저장 (deep: 배열 안쪽 변화도 감지)
  watch(
    ma,
    (v) => {
      try {
        localStorage.setItem(KEY, JSON.stringify(v));
      } catch (e) {}
    },
    { deep: true },
  );

  // 이미 켜져 있으면 빼고, 없으면 넣는다.
  function toggleMa(i) {
    ma.value[i].on = !ma.value[i].on;
  }

  // i번 슬롯의 현재 색. 사용자가 고른 색이 있으면 그것, 없으면 모드별 기본색.
  // ?? 는 "왼쪽이 null이면 오른쪽을 쓴다" (자바의 Optional.orElse와 비슷)
  function maColor(i, mode) {
    return ma.value[i].color ?? MA_DEFAULTS[i][mode];
  }

  // 모든 슬롯을 기본값으로 되돌린다. (3단계 설정 창의 초기화 버튼이 쓴다)
  function resetMa() {
    ma.value = makeDefaults();
  }

  return { ma, toggleMa, maColor, resetMa };
});
