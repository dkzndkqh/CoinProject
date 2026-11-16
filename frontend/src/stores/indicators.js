import { defineStore } from "pinia";
import { ref, watch } from "vue";

const KEY = "chartIndicators";

// 저장된 선택 불러오기. 없거나 깨졌으면 기본값(20, 60일선)
function loadSaved() {
  try {
    const s = JSON.parse(localStorage.getItem(KEY));
    if (Array.isArray(s)) return s;
  } catch (e) {}
  return [20, 60];
}

export const useIndicatorStore = defineStore("indicators", () => {
  const maOn = ref(loadSaved()); // 켜진 이동평균 기간 배열, 예: [20, 60]

  // 바뀔 때마다 브라우저에 저장 (deep: 배열 안쪽 변화도 감지)
  watch(
    maOn,
    (v) => {
      try {
        localStorage.setItem(KEY, JSON.stringify(v));
      } catch (e) {}
    },
    { deep: true },
  );

  // 이미 켜져 있으면 빼고, 없으면 넣는다.
  function toggleMa(period) {
    maOn.value = maOn.value.includes(period)
      ? maOn.value.filter((p) => p !== period)
      : [...maOn.value, period];
  }

  return { maOn, toggleMa };
});
