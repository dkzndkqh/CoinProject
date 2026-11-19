// 볼린저 밴드의 위·아래 선 사이를 칠하는 차트 플러그인(시리즈 프리미티브).
// Lightweight Charts에는 두 선 사이를 채우는 기능이 없어서, 차트가 그림을 그릴 때마다
// 불리는 renderer.draw()에서 직접 캔버스에 다각형을 칠한다.
// 자바로 치면 라이브러리가 정한 인터페이스(attached/detached/paneViews...)를 구현한 클래스다.

// "#rrggbb" + 투명도(0~1) -> "rgba(r,g,b,a)". 색 선택기는 항상 #rrggbb 형식만 준다.
function hexToRgba(hex, alpha) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

export class BandFill {
  constructor() {
    this._data = []; // [{ time, upper, lower }] 오래된 순
    this._color = "#26c6da";
    this._alpha = 0.12;
    this._visible = true;
    this._points = []; // 화면 좌표로 바꾼 값 [{ x, upper, lower }]. updateAllViews가 채운다.
    this._chart = null;
    this._series = null;
    this._requestUpdate = null;

    // 차트가 칠할 때 부르는 객체. 화살표 함수라 this가 BandFill을 가리킨다.
    this._view = {
      zOrder: () => "bottom", // 캔들과 선보다 아래에 그려서 캔들을 가리지 않게 한다
      renderer: () => ({
        draw: (target) => this._draw(target),
      }),
    };
  }

  // 차트가 이 플러그인을 시리즈에 붙일 때 불러 준다.
  attached({ chart, series, requestUpdate }) {
    this._chart = chart;
    this._series = series;
    this._requestUpdate = requestUpdate;
  }

  detached() {
    this._chart = null;
    this._series = null;
    this._requestUpdate = null;
  }

  // 값(데이터)이 바뀌었을 때 호출한다.
  setData(data) {
    this._data = data;
    this._requestUpdate?.(); // 차트에 "다시 그려 달라"고 요청
  }

  // 색·투명도·보임 여부가 바뀌었을 때 호출한다.
  setStyle({ color, alpha, visible }) {
    this._color = color;
    this._alpha = alpha;
    this._visible = visible;
    this._requestUpdate?.();
  }

  // 차트가 그리기 직전에 부른다. 시간/가격 값을 화면 좌표로 바꿔 둔다.
  updateAllViews() {
    if (!this._chart || !this._series) return;
    const ts = this._chart.timeScale();
    this._points = this._data
      .map((d) => ({
        x: ts.timeToCoordinate(d.time),
        upper: this._series.priceToCoordinate(d.upper),
        lower: this._series.priceToCoordinate(d.lower),
      }))
      // 화면 밖이라 좌표가 null인 점은 뺀다
      .filter((p) => p.x !== null && p.upper !== null && p.lower !== null);
  }

  paneViews() {
    return [this._view];
  }

  _draw(target) {
    if (!this._visible || this._points.length < 2) return;
    // media 좌표계: 화면 배율(dpr)에 상관없이 CSS 픽셀 단위로 그린다
    target.useMediaCoordinateSpace(({ context: ctx }) => {
      const pts = this._points;
      ctx.beginPath();
      // 위 선을 왼쪽에서 오른쪽으로, 아래 선을 오른쪽에서 왼쪽으로 이어서 닫힌 띠 모양을 만든다
      ctx.moveTo(pts[0].x, pts[0].upper);
      for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].upper);
      for (let i = pts.length - 1; i >= 0; i--)
        ctx.lineTo(pts[i].x, pts[i].lower);
      ctx.closePath();
      ctx.fillStyle = hexToRgba(this._color, this._alpha);
      ctx.fill();
    });
  }
}
