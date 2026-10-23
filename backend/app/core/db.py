from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

# 엔진: DB와의 연결 풀을 관리하는 객체 (자바의 HikariCP DataSource와 비슷)
# create_engine은 이 시점에 접속하지 않고, 처음 쿼리를 날릴 때 연결한다.
# pool_pre_ping=True: 연결을 꺼내 쓰기 전에 살아 있는지 확인해서,
# DB 재시작 등으로 끊어진 연결 때문에 에러가 나는 것을 막는다.
engine = create_engine(settings.database_url, pool_pre_ping=True)

# 세션 팩토리: 요청마다 DB 세션(JPA의 EntityManager)을 만들어 내는 공장
# autoflush=False: 쿼리 전에 변경 내용을 자동 반영하지 않는다 (동작을 예측하기 쉽다)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    """모든 테이블 모델(models.py)이 상속하는 부모 클래스.
    자바 JPA에서 @Entity 클래스들이 공통으로 쓰는 기반이라고 보면 된다.
    Alembic이 이 Base에 등록된 모델을 보고 테이블 생성 스크립트를 만든다.
    """


def get_db():
    """FastAPI 요청 하나당 DB 세션을 열고, 끝나면 반드시 닫는 함수.
    yield는 '여기서 값을 넘겨주고 일시정지했다가, 요청이 끝나면 아래 코드를 이어서 실행'한다는 뜻이다.
    자바의 try-with-resources(자동 close)와 같은 효과다.
    라우터에서 Depends(get_db)로 주입받아 쓴다 (Spring의 @Autowired와 비슷).
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
