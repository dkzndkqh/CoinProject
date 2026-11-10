from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class NewsArticle(Base):
    """뉴스 기사 한 건 = 테이블 한 행. 자바 JPA의 @Entity와 같은 역할이다.
    서버가 RSS에서 기사를 모아 저장하고(수집 시점엔 감성 점수가 비어 있다),
    내 PC(ai_inference)의 FinBERT가 나중에 감성 점수를 계산해서 올린다.
    """

    __tablename__ = "news_articles"

    # id: 자동으로 올라가는 번호. 자바의 @Id @GeneratedValue와 같다.
    # autoincrement=True: DB가 1, 2, 3...을 알아서 붙여 준다.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # url: 기사 주소. 같은 기사가 RSS에 계속 다시 나오므로 이 값으로 중복을 막는다.
    # unique=True: 같은 값이 두 번 들어가면 DB가 거부한다 (자바의 @Column(unique = true)).
    # 기사 주소는 길 수 있어서 넉넉히 잡는다.
    url: Mapped[str] = mapped_column(String(2000), unique=True)

    # title: 기사 제목
    title: Mapped[str] = mapped_column(String(500))

    # source: 출처 이름. 예: "coindesk", "cointelegraph", "decrypt"
    source: Mapped[str] = mapped_column(String(50))

    # published_at: 기사가 발행된 시각 (UTC)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # summary: RSS가 주는 요약. 없는 기사도 있어서 None(NULL)을 허용한다.
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- FinBERT 결과: 수집 직후에는 아직 없으므로 모두 NULL 허용 ---
    sentiment_label: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # fetched_at: 우리가 이 기사를 수집한 시각. 값을 안 넣으면 DB가 현재 시각을 채운다.
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
