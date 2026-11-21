import { defineStore } from "pinia";
import { ref, watch } from "vue";
import {
  BB_DEFAULT,
  ICHI_DEFAULT,
  MA_DEFAULTS,
  LINE_WIDTHS,
  LINE_STYLES,
} from "../utils/indicators";

const KEY = "chartMaSettings";
const BB_KEY = "chartBbSettings";
const ICHI_KEY = "chartIchiSettings";

// 기본 설정 5슬롯을 만든다. 호출할 때마다 새 객체를 만들어서 기본값 원본이 수정되지 않게 한다.
// 슬롯 모양: { period: 기간, color: 사용자가 고른 색(없으면 null), on: 켜짐 여부 }
function makeDefaults() {
  return MA_DEFAULTS.map((m) => ({
    period: m.period,
    color: null, // null이면 모드별 기본색(MA_DEFAULTS의 dark/light)을 쓴다
    on: m.period === 20 || m.period === 60,
    width: 1, // 선 두께 (기본 1)
    style: 0, // 선 모양 (0=실선)
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
        LINE_WIDTHS.includes(x.width) &&
        LINE_STYLES.includes(x.style) &&
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

// 볼린저 기본 설정. 슬롯 하나라서 배열이 아니라 객체다.
function makeBbDefaults() {
  return {
    period: BB_DEFAULT.period,
    mult: BB_DEFAULT.mult,
    color: null,
    on: true,
    width: 1,
    style: 0,
    fill: true, // 백그라운드(위·아래 선 사이 색) 켜짐
    alpha: 12, // 백그라운드 투명도(%). 1~60, 클수록 진하다
  };
}
// 저장된 볼린저 값이 쓸 만한지 검사 (기간 정수 1~500, 배수 0.1~5)
function isBbValid(s) {
  return (
    s !== null &&
    typeof s === "object" &&
    Number.isInteger(s.period) &&
    s.period >= 1 &&
    s.period <= 500 &&
    typeof s.mult === "number" &&
    s.mult >= 0.1 &&
    s.mult <= 5 &&
    typeof s.on === "boolean" &&
    LINE_WIDTHS.includes(s.width) &&
    LINE_STYLES.includes(s.style) &&
    typeof s.fill === "boolean" &&
    Number.isInteger(s.alpha) &&
    s.alpha >= 1 &&
    s.alpha <= 60 &&
    (s.color === null || typeof s.color === "string")
  );
}

function loadBb() {
  try {
    const s = JSON.parse(localStorage.getItem(BB_KEY));
    if (isBbValid(s)) return s;
  } catch (e) {}
  return makeBbDefaults();
}

export const useIndicatorStore = defineStore("indicators", () => {
  const ma = ref(loadSaved()); // 5슬롯 배열. 순서가 곧 슬롯 번호(0~4)
  const bb = ref(loadBb()); // { period, mult, color, on }
  const ichi = ref(loadIchi()); // { on, tenkan, kijun, senkouB }
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

  watch(
    bb,
    (v) => {
      try {
        localStorage.setItem(BB_KEY, JSON.stringify(v));
      } catch (e) {}
    },
    { deep: true },
  );

  watch(
    ichi,
    (v) => {
      try {
        localStorage.setItem(ICHI_KEY, JSON.stringify(v));
      } catch (e) {}
    },
    { deep: true },
  );

  // 이미 켜져 있으면 빼고, 없으면 넣는다.
  function toggleMa(i) {
    ma.value[i].on = !ma.value[i].on;
  }

  function toggleBb() {
    bb.value.on = !bb.value.on;
  }

  // i번 슬롯의 현재 색. 사용자가 고른 색이 있으면 그것, 없으면 모드별 기본색.
  // ?? 는 "왼쪽이 null이면 오른쪽을 쓴다" (자바의 Optional.orElse와 비슷)
  function maColor(i, mode) {
    return ma.value[i].color ?? MA_DEFAULTS[i][mode];
  }

  // 볼린저의 현재 색 (사용자 색이 없으면 모드별 기본색)
  function bbColor(mode) {
    return bb.value.color ?? BB_DEFAULT[mode];
  }

  // 모든 슬롯을 기본값으로 되돌린다. (3단계 설정 창의 초기화 버튼이 쓴다)
  function resetMa() {
    ma.value = makeDefaults();
  }

  // 볼린저만 기본값으로 되돌린다. (MA 설정은 그대로)
  function resetBb() {
    bb.value = makeBbDefaults();
  }

  function toggleIchi() {
    ichi.value.on = !ichi.value.on;
  }

  function resetIchi() {
    ichi.value = makeIchiDefaults();
  }

  return {
    ma,
    toggleMa,
    maColor,
    resetMa,
    bb,
    toggleBb,
    bbColor,
    resetBb,
    ichi,
    toggleIchi,
    resetIchi,
  };
});

// 일목 기본 설정: 꺼짐 + 표준 기간. 색은 고정이라 저장하지 않는다.
function makeIchiDefaults() {
  return { on: false, ...ICHI_DEFAULT };
}

// 저장된 값 검사: on은 true/false, 세 기간은 정수 1~500
function isIchiValid(s) {
  return (
    s !== null &&
    typeof s === "object" &&
    typeof s.on === "boolean" &&
    [s.tenkan, s.kijun, s.senkouB].every(
      (v) => Number.isInteger(v) && v >= 1 && v <= 500,
    )
  );
}

function loadIchi() {
  try {
    const s = JSON.parse(localStorage.getItem(ICHI_KEY));
    if (isIchiValid(s)) return s;
  } catch (e) {}
  return makeIchiDefaults();
}
