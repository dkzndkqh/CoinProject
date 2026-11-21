<script setup>
import { ref } from "vue";
import { useIndicatorStore } from "../stores/indicators";
import { useThemeStore } from "../stores/theme";
import { LINE_WIDTHS, LINE_STYLES } from "../utils/indicators";

const ind = useIndicatorStore();
const theme = useThemeStore();
const emit = defineEmits(["close"]);

const tab = ref("ma"); // 현재 탭: "ma" | "bb" | "ichi"
const openKey = ref(null); // 선 두께·모양 팝업이 열린 줄: 0~4(이동평균 슬롯) | "bb" | null

// 선 모양 숫자(0,1,2) -> CSS border 모양 이름. 인덱스가 곧 차트의 lineStyle 값이다.
const CSS_STYLE = ["solid", "dotted", "dashed"];

// 팝업 열기/닫기. 같은 줄을 다시 누르면 닫힌다.
function togglePop(key) {
  openKey.value = openKey.value === key ? null : key;
}

// 기간 검증: 정수 1~500. 통과한 값만 스토어에 넣고, 틀리면 입력창을 되돌린다.
function setPeriod(slot, e) {
  const n = Number(e.target.value);
  if (Number.isInteger(n) && n >= 1 && n <= 500) {
    slot.period = n;
  } else {
    e.target.value = slot.period;
  }
}

// 볼린저 배수 검증: 0.1~5
function setMult(e) {
  const n = Number(e.target.value);
  if (n >= 0.1 && n <= 5) {
    ind.bb.mult = n;
  } else {
    e.target.value = ind.bb.mult;
  }
}

// 일목 기간 검증: 정수 1~500. key는 "tenkan" | "kijun" | "senkouB".
// 통과한 값만 스토어에 넣고, 틀리면 입력창을 원래 값으로 되돌린다. (setPeriod와 같은 방식)
// ind.ichi[key]는 자바의 map.get(key)처럼 이름으로 필드를 고르는 문법이다.
function setIchi(key, e) {
  const n = Number(e.target.value);
  if (Number.isInteger(n) && n >= 1 && n <= 500) {
    ind.ichi[key] = n;
  } else {
    e.target.value = ind.ichi[key];
  }
}

// 현재 탭의 초기화 버튼. 탭마다 자기 설정만 되돌린다.
function resetCurrent() {
  openKey.value = null;
  if (tab.value === "ma") ind.resetMa();
  else if (tab.value === "bb") ind.resetBb();
  else ind.resetIchi();
}
</script>

<template>
  <!-- 배경을 누르면 닫힌다(.self: 배경 자신을 직접 누른 경우만) -->
  <div class="backdrop" @click.self="emit('close')">
    <!-- 모달 안 아무 곳이나 누르면 열려 있던 팝업이 닫힌다. 팝업과 그 버튼은 @click.stop으로 예외 -->
    <div class="modal" @click="openKey = null">
      <div class="top">
        <h2>지표 설정</h2>
        <button class="close" @click="emit('close')" aria-label="닫기">✕</button>
      </div>

      <div class="tabs">
        <button :class="{ active: tab === 'ma' }" @click="tab = 'ma'">
          이동평균선
        </button>
        <button :class="{ active: tab === 'bb' }" @click="tab = 'bb'">
          볼린저 밴드
        </button>
        <button :class="{ active: tab === 'ichi' }" @click="tab = 'ichi'">
          일목 구름
        </button>
      </div>

      <div class="sect">
        <p v-if="tab === 'ma'">
          차트에 그릴 이동평균선을 켜고, 길이와 모양을 정하세요.
        </p>
        <p v-else-if="tab === 'bb'">
          가격이 움직이는 범위를 보여 주는 위·중간·아래 3개 선입니다.
        </p>
        <p v-else>
          전환선·기준선과 구름으로 추세를 보는 지표입니다. 구름은 마지막 캔들
          앞쪽으로 나갑니다.
        </p>
        <button class="reset" @click.stop="resetCurrent">
          <span>↺</span>기본값으로 초기화
        </button>
      </div>

      <!-- 이동평균 탭 -->
      <div class="card" v-if="tab === 'ma'">
        <div class="grid th">
          <span>표시</span><span>선</span><span>길이</span><span>색상</span
          ><span>두께·모양</span>
        </div>

        <div class="grid tr" v-for="(m, i) in ind.ma" :key="i">
          <label class="sw">
            <input type="checkbox" v-model="m.on" />
            <i></i>
          </label>
          <div class="nm">
            <b>MA{{ m.period }}</b>
            <small>최근 {{ m.period }}봉 평균</small>
          </div>
          <div class="num">
            <input
              type="number"
              min="1"
              max="500"
              :value="m.period"
              @change="setPeriod(m, $event)"
            />
            <span>봉</span>
          </div>
          <input
            class="color"
            type="color"
            title="선 색상"
            :value="ind.maColor(i, theme.theme)"
            @input="m.color = $event.target.value"
          />
          <button
            class="linebtn"
            :class="{ open: openKey === i }"
            title="선 두께·모양"
            @click.stop="togglePop(i)"
          >
            <span
              class="ln"
              :style="{
                borderTopWidth: m.width + 'px',
                borderTopStyle: CSS_STYLE[m.style],
              }"
            ></span
            >▾
          </button>

          <!-- 두께·모양 팝업 -->
          <div class="pop" v-if="openKey === i" @click.stop>
            <p class="lbl">선 두께</p>
            <div class="pk">
              <button
                v-for="w in LINE_WIDTHS"
                :key="w"
                :class="{ sel: m.width === w }"
                @click="m.width = w"
              >
                <span class="ln" :style="{ borderTopWidth: w + 'px' }"></span>
              </button>
            </div>
            <p class="lbl">선 모양</p>
            <div class="pk">
              <button
                v-for="st in LINE_STYLES"
                :key="st"
                :class="{ sel: m.style === st }"
                @click="m.style = st"
              >
                <span
                  class="ln"
                  :style="{
                    borderTopWidth: '2px',
                    borderTopStyle: CSS_STYLE[st],
                  }"
                ></span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 볼린저 탭: 줄이 하나라서 세로 폼 -->
      <div class="card" v-else-if="tab === 'bb'">
        <div class="frow">
          <label>표시</label>
          <label class="sw">
            <input type="checkbox" v-model="ind.bb.on" />
            <i></i>
          </label>
        </div>
        <div class="frow">
          <label>길이<small>평균을 낼 봉 개수</small></label>
          <div class="num">
            <input
              type="number"
              min="1"
              max="500"
              :value="ind.bb.period"
              @change="setPeriod(ind.bb, $event)"
            />
            <span>봉</span>
          </div>
        </div>
        <div class="frow">
          <label>배수<small>표준편차의 몇 배</small></label>
          <div class="num">
            <input
              type="number"
              min="0.1"
              max="5"
              step="0.1"
              :value="ind.bb.mult"
              @change="setMult($event)"
            />
            <span>배</span>
          </div>
        </div>
        <div class="frow">
          <label>색상</label>
          <input
            class="color left"
            type="color"
            title="선 색상"
            :value="ind.bbColor(theme.theme)"
            @input="ind.bb.color = $event.target.value"
          />
        </div>
        <div class="frow">
          <label
            >두께·모양<small
              >위·아래 선만 적용<br />(중간선은 점선 고정)</small
            ></label
          >
          <div class="anchor">
            <button
              class="linebtn left"
              :class="{ open: openKey === 'bb' }"
              title="선 두께·모양"
              @click.stop="togglePop('bb')"
            >
              <span
                class="ln"
                :style="{
                  borderTopWidth: ind.bb.width + 'px',
                  borderTopStyle: CSS_STYLE[ind.bb.style],
                }"
              ></span
              >▾
            </button>
            <div class="pop" v-if="openKey === 'bb'" @click.stop>
              <p class="lbl">선 두께</p>
              <div class="pk">
                <button
                  v-for="w in LINE_WIDTHS"
                  :key="w"
                  :class="{ sel: ind.bb.width === w }"
                  @click="ind.bb.width = w"
                >
                  <span class="ln" :style="{ borderTopWidth: w + 'px' }"></span>
                </button>
              </div>
              <p class="lbl">선 모양</p>
              <div class="pk">
                <button
                  v-for="st in LINE_STYLES"
                  :key="st"
                  :class="{ sel: ind.bb.style === st }"
                  @click="ind.bb.style = st"
                >
                  <span
                    class="ln"
                    :style="{
                      borderTopWidth: '2px',
                      borderTopStyle: CSS_STYLE[st],
                    }"
                  ></span>
                </button>
              </div>
            </div>
          </div>
        </div>
        <div class="frow">
          <label>백그라운드<small>위·아래 선 사이 색</small></label>
          <label class="sw">
            <input type="checkbox" v-model="ind.bb.fill" />
            <i></i>
          </label>
        </div>
        <div class="frow">
          <label>투명도<small>클수록 진하게</small></label>
          <!-- 슬라이더는 브라우저가 min~max 안의 정수만 주므로 따로 검증하지 않는다.
               v-model.number: 입력 문자열을 숫자로 바꿔서 스토어에 넣는다 -->
          <div class="slider" :class="{ off: !ind.bb.fill }">
            <input
              type="range"
              min="1"
              max="60"
              :disabled="!ind.bb.fill"
              v-model.number="ind.bb.alpha"
            />
            <output>{{ ind.bb.alpha }}%</output>
          </div>
        </div>
      </div>

      <!-- 일목 탭: 켜기 + 기간 3개. 색은 고정이라 고르는 칸이 없다 -->
      <div class="card" v-else>
        <div class="frow">
          <label>표시</label>
          <label class="sw">
            <input type="checkbox" v-model="ind.ichi.on" />
            <i></i>
          </label>
        </div>
        <div class="frow">
          <label>전환선<small>짧은 추세선</small></label>
          <div class="num">
            <input
              type="number"
              min="1"
              max="500"
              :value="ind.ichi.tenkan"
              @change="setIchi('tenkan', $event)"
            />
            <span>봉</span>
          </div>
        </div>
        <div class="frow">
          <label>기준선<small>구름을 앞으로 미는 칸 수도 이 값</small></label>
          <div class="num">
            <input
              type="number"
              min="1"
              max="500"
              :value="ind.ichi.kijun"
              @change="setIchi('kijun', $event)"
            />
            <span>봉</span>
          </div>
        </div>
        <div class="frow">
          <label>선행스팬2<small>구름의 한쪽 끝</small></label>
          <div class="num">
            <input
              type="number"
              min="1"
              max="500"
              :value="ind.ichi.senkouB"
              @change="setIchi('senkouB', $event)"
            />
            <span>봉</span>
          </div>
        </div>
      </div>

      <p class="foot">
        여기서 바꾼 값은 차트 선에만 적용됩니다. 매수·매도 판정은 표준값(이동평균
        5/20/60/120/200, 볼린저 20/2, 일목 9/26/52) 기준입니다. 일목의 선 색은
        고정입니다.
      </p>
    </div>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  z-index: 10;
}
.modal {
  width: 100%;
  max-width: 420px;
  max-height: 100%;
  overflow-y: auto;
  background: var(--panel);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 18px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.35);
}
.top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}
.top h2 {
  margin: 0;
  font-size: 17px;
}
.close {
  width: 30px;
  height: 30px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: transparent;
  color: var(--muted);
  font-size: 14px;
  cursor: pointer;
}
.close:hover {
  color: var(--text);
  border-color: var(--muted);
}

/* 탭 */
.tabs {
  display: flex;
  gap: 2px;
  padding: 3px;
  margin-bottom: 14px;
  background: var(--track);
  border: 1px solid var(--border);
  border-radius: 10px;
}
.tabs button {
  flex: 1;
  padding: 8px 0;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--muted);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.tabs button.active {
  background: var(--tab-active-bg);
  color: var(--tab-active-text);
}

/* 설명 + 초기화 버튼 */
.sect {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.sect p {
  margin: 0;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.4;
}
.reset {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--track);
  color: var(--text);
  font-size: 12px;
  cursor: pointer;
}
.reset:hover {
  border-color: var(--muted);
}

/* 표 카드 */
.card {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--track);
}
.grid {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr) 76px 40px 72px;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  position: relative;
}
.grid.th {
  padding-top: 10px;
  padding-bottom: 8px;
  font-size: 11px;
  color: var(--muted);
  border-bottom: 1px solid var(--border);
}
.grid.th span:nth-child(n + 3) {
  text-align: center;
}
.grid.tr {
  border-bottom: 1px solid var(--border);
}
.grid.tr:last-child {
  border-bottom: none;
}
.grid.tr:hover {
  background: color-mix(in srgb, var(--text) 5%, transparent);
}
.nm b {
  display: block;
  font-size: 13px;
}
.nm small {
  color: var(--muted);
  font-size: 11px;
}

/* 스위치: 진짜 체크박스는 투명하게 위에 겹쳐 두고 i가 모양을 그린다 */
.sw {
  position: relative;
  display: block;
  width: 38px;
  height: 22px;
}
.sw input {
  position: absolute;
  width: 100%;
  height: 100%;
  margin: 0;
  opacity: 0;
  cursor: pointer;
  z-index: 1;
}
.sw i {
  position: absolute;
  inset: 0;
  border-radius: 999px;
  background: color-mix(in srgb, var(--muted) 45%, var(--panel));
  transition: 0.15s;
}
.sw i::after {
  content: "";
  position: absolute;
  top: 3px;
  left: 3px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #fff;
  transition: 0.15s;
}
.sw input:checked + i {
  background: var(--tab-active-bg);
}
.sw input:checked + i::after {
  transform: translateX(16px);
}

/* 숫자 입력 + 단위 */
.num {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--muted);
}
.num input {
  width: 100%;
  min-width: 0;
  padding: 6px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
  color: var(--text);
  font-size: 13px;
  text-align: center;
}
.num input:focus {
  outline: none;
  border-color: var(--tab-active-bg);
}

/* 색상 네모 */
.color {
  justify-self: center;
  width: 30px;
  height: 30px;
  padding: 2px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
  cursor: pointer;
}
.color:hover {
  border-color: var(--muted);
}
.left {
  justify-self: start;
}

/* 선 두께·모양 버튼 */
.linebtn {
  justify-self: center;
  width: 72px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
  color: var(--muted);
  font-size: 10px;
  cursor: pointer;
}
.linebtn:hover,
.linebtn.open {
  border-color: var(--tab-active-bg);
}
.ln {
  width: 28px;
  height: 0;
  border-top: solid var(--text);
}

/* 팝업 */
.pop {
  position: absolute;
  right: 10px;
  top: 46px;
  z-index: 5;
  width: 240px;
  padding: 12px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
}
.pop .lbl {
  margin: 0 0 6px;
  font-size: 12px;
  font-weight: 600;
}
.pk {
  display: flex;
  gap: 6px;
  margin-bottom: 12px;
}
.pk:last-child {
  margin-bottom: 0;
}
.pk button {
  flex: 1;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--track);
  cursor: pointer;
}
.pk button:hover {
  border-color: var(--muted);
}
.pk button.sel {
  border-color: var(--tab-active-bg);
}
.pk .ln {
  width: 24px;
}

/* 볼린저 폼 */
.frow {
  display: grid;
  grid-template-columns: 96px 1fr;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
}
.frow:last-child {
  border-bottom: none;
}
.frow label {
  font-size: 13px;
}
.frow label small {
  display: block;
  font-size: 11px;
  color: var(--muted);
}
.frow .num {
  max-width: 140px;
}
.anchor {
  position: relative;
}

/* 투명도 슬라이더 */
.slider {
  display: flex;
  align-items: center;
  gap: 10px;
}
.slider input[type="range"] {
  flex: 1;
  min-width: 0;
  accent-color: var(--tab-active-bg);
}
.slider output {
  width: 40px;
  text-align: right;
  font-size: 13px;
}
.slider.off {
  opacity: 0.4;
}
.anchor .pop {
  right: auto;
  left: 0;
  top: 38px;
}

.foot {
  margin: 14px 0 0;
  font-size: 11px;
  color: var(--muted);
  line-height: 1.5;
}
</style>
