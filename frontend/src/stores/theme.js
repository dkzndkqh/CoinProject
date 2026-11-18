import { defineStore } from "pinia";
import { ref, watch } from "vue";

// 첫 값 정하기: 저장된 선택 > OS 설정 > 다크
function initialTheme() {
  try {
    const saved = localStorage.getItem("theme");
    if (saved === "dark" || saved === "light") return saved;
  } catch (e) {}
  return window.matchMedia("(prefers-color-scheme: light)").matches
    ? "light"
    : "dark";
}

// defineStore(이름, 함수): 앱 전체에서 하나만 공유되는 상태 보관소.
// 자바의 싱글톤 빈(@Component)이라고 보면 된다. 어느 컴포넌트에서 꺼내 써도 같은 객체다
export const useThemeStore = defineStore("theme", () => {
  const theme = ref(initialTheme()); // 'dark | 'light

  watch(
    theme,
    (v) => {
      document.documentElement.dataset.theme = v;
      try {
        localStorage.setItem("theme", v);
      } catch (e) {}
    },
    { immediate: true },
  );

  function toggle() {
    theme.value = theme.value === "dark" ? "light" : "dark";
  }

  return { theme, toggle };
});
