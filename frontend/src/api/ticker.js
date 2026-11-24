// 업비트 웹소켓에 연결해서 BTC·ETH 시세(ticker)를 실시간으로 받는다.
// 키가 필요 없고, 한 연결로 두 코인을 같이 구독한다.

const URL = "wss://api.upbit.com/websocket/v1";
const CODES = ["KRW-BTC", "KRW-ETH"];

export function connectTicker(onTick) {
  let ws = null; // 현재 연결
  let timer = null; // 재연결 예약 타이머
  let closed = false; // 사용자가 직접 끊었는지 (true면 재연결하지 않는다)

  function open() {
    ws = new WebSocket(URL);
    // 업비트는 JSON을 바이너리로 보내므로 ArrayBuffer로 받아서 직접 문자로 바꾼다.
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      // 구독 요청: [티켓(요청 식별자), 받을 데이터 종류와 코인, 응답 형식]
      ws.send(
        JSON.stringify([
          { ticket: crypto.randomUUID() },
          { type: "ticker", codes: CODES },
          { format: "DEFAULT" },
        ]),
      );
    };

    // 메시지가 올 때마다 JSON으로 바꿔서 콜백에 넘긴다.
    // t.code("KRW-BTC"), t.trade_price(현재가), t.signed_change_price, t.signed_change_rate 등
    ws.onmessage = (e) => {
      onTick(JSON.parse(new TextDecoder().decode(e.data)));
    };

    // 연결이 끊기면 3초 뒤 다시 연결한다. 직접 끊은 경우는 제외.
    ws.onclose = () => {
      if (!closed) timer = setTimeout(open, 3000);
    };
  }

  open();

  // 호출하면 연결을 끊고 재연결도 막는다 (화면이 사라질 때 호출).
  return () => {
    closed = true;
    clearTimeout(timer);
    if (ws) ws.close();
  };
}
