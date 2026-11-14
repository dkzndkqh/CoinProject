import client from './client'

// 지표 판정 조회  GET /api/market/{coin}/indicators
export async function fetchIndicators(coin) {
    const res = await client.get(`/api/market/${coin}/indicators`)
    return res.data // Axios는 응답 본문(JSON)을 res.data 객체에 넣어준다.    
}
