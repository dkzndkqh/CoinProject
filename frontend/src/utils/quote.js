// 일봉 2개(오래된 순)로 시세를 계산한다. 헤더와 코인 목록이 같이 쓴다.
// rows: fetchCandles(coin, '1d', 2)의 결과. 마지막이 오늘(진행 중), 그 앞이 전일.
// 서버가 못 주거나 캔들이 1개뿐이면 null (화면에서는 가격을 비워 둔다).
export function makeQuote(rows) {
  if (!rows || rows.length < 2) return null;

  const price = rows[rows.length - 1].close; // 현재가 = 최신 캔들 종가 (최대 15분 지연)
  const prev = rows[rows.length - 2].close; // 전일 종가
  const diff = price - prev; // 전일 대비 변동 금액
  const pct = prev ? (diff / prev) * 100 : 0; // 전일 대비 변동률(%)

  return {
    // 색 규칙: 오르거나 같으면 up(빨강), 떨어지면 down(파랑)
    cls: diff >= 0 ? "up" : "down",
    price: won(price),
    // 퍼센트는 오르면 +를 붙이고, 내리면 -는 숫자가 이미 갖고 있다. 0이면 부호 없음.
    pct: (pct > 0 ? "+" : "") + pct.toFixed(2) + "%",
    // 금액은 업비트처럼 오르면 ▲ 금액, 내리면 ▼ -금액, 같으면 0
    amount: diff > 0 ? "▲ " + won(diff) : diff < 0 ? "▼ -" + won(-diff) : "0",
  };
}

// 1234567 -> "1,234,567". 원화라 소수점은 버린다(반올림).
function won(n) {
  return Math.round(n).toLocaleString("ko-KR");
}
