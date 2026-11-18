import client from './client'

// 지표 판정 조회  GET /api/market/{coin}/indicators
export async function fetchIndicators(coin) {
    const res = await client.get(`/api/market/${coin}/indicators`)
    return res.data // Axios는 응답 본문(JSON)을 res.data 객체에 넣어준다.    
}

// 차트용 캔들 조회  GET /api/market/{coin}/candles
// coin: 'btc' | 'eth' (소문자, 그 외는 백엔드가 404)
// timeframe: '1h' | '4h' | '1d'
// limit: 받을 개수 (백엔드 기본 300, 최대 1000)
// endTime: 이 시각 "이하"까지의 캔들만 받는다. 처음 로딩 때는 생략(undefined)하고,
//          과거를 이어받을 때만 ISO 문자열로 넘긴다.
export async function fetchCandles(coin, timeframe, limit = 300, endTime) {
    const res = await client.get(`/api/market/${coin}/candles`, {
        // params 객체는 Axios가 ?timeframe=1h&limit=300 으로 바꿔 붙인다.
        // 값이 undefined인 키(endTime)는 쿼리에서 자동으로 빠진다.
        params: { timeframe, limit, end_time: endTime },
    })
    return res.data // 오래된 순 배열 
}