<script setup>
// <script setup>: 이 파일 안에서 선언한 변수·함수를 템플릿이 바로 쓰게 해 주는 Vue 3 문법.
import { ref, onMounted } from 'vue'
import { fetchIndicators } from './api/market'

// ref: 값이 바뀌면 화면이 자동으로 다시 그려지는 "반응형 변수". 값은 .value 로 읽고 쓴다.
const data = ref(null)
const error = ref('')

// onMounted: 컴포넌트가 화면에 붙은 직후 한 번 실행 (자바의 @PostConstruct와 비슷)
onMounted(async () => {
  try {
    data.value = await fetchIndicators('BTC')
  } catch (e) {
    error.value = e.message
  }
})
</script>

<template>
  <!-- v-if: 조건이 참일 때만 그린다. pre는 JSON을 들여쓰기 그대로 보여 준다. -->
  <p v-if="error">에러: {{ error }}</p>
  <pre v-else-if="data">{{ JSON.stringify(data, null, 2) }}</pre>
  <p v-else>불러오는 중...</p>
</template>