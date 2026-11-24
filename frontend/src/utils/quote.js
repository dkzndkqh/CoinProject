// 업비트 웹소켓 ticker 메시지 하나로 화면에 보여 줄 시세를 만든다.
// 헤더와 코인 목록이 같이 쓴다. 전일 대비 값은 업비트가 계산해서 주므로 우리가 계산하지 않는다.
// t.trade_price: 현재가 / t.signed_change_price: 전일 대비 금액(부호 포함)
// t.signed_change_rate: 전일 대비 비율(부호 포함, 0.0125 = 1.25%)
export function makeQuote(t) {
  const diff = t.signed_change_price;
  const pct = t.signed_change_rate * 100;

  return {
    // 색 규칙: 오르거나 같으면 up(빨강), 떨어지면 down(파랑)
    cls: diff >= 0 ? "up" : "down",
    price: won(t.trade_price),
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
