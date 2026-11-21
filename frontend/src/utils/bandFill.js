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
        color: d.color,
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
      // 색이 같은 연속 구간(start~end)을 한 덩어리로 칠한다.
      // 색이 바뀌는 곳에서는 경계점까지 포함해서 구간 사이에 틈이 안 생기게 한다.
      // 볼린저처럼 color가 전부 undefined면 구간이 하나라서 예전과 똑같이 그려진다.
      let start = 0;
      for (let i = 1; i <= pts.length; i++) {
        if (i < pts.length && pts[i].color === pts[start].color) continue;
        const end = Math.min(i, pts.length - 1);
        if (end > start) {
          ctx.beginPath();
          ctx.moveTo(pts[start].x, pts[start].upper);
          for (let j = start + 1; j <= end; j++)
            ctx.lineTo(pts[j].x, pts[j].upper);
          for (let j = end; j >= start; j--) ctx.lineTo(pts[j].x, pts[j].lower);
          ctx.closePath();
          ctx.fillStyle = hexToRgba(
            pts[start].color ?? this._color,
            this._alpha,
          );
          ctx.fill();
        }
        start = i;
      }
    });
  }
}
