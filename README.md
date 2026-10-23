# Coin Agent

BTC·ETH 시장 데이터와 AI 예측을 근거로 분석 의견을 주는 AI 에이전트 웹앱입니다. (개발 중)

> 본 서비스의 분석과 예측은 참고용이며 투자 권유가 아닙니다.

## 기술 스택

- Backend: Python 3.12, FastAPI, SQLAlchemy, Alembic, APScheduler
- DB: PostgreSQL
- Infra: Docker Compose
- 패키지 관리: uv

## 로컬 실행

사전 준비: Python 3.12, uv, Docker Desktop

```bash
# 1. 환경변수 파일 준비 후 값 수정
cp backend/.env.example backend/.env

# 2. PostgreSQL 실행
docker compose up -d

# 3. 백엔드 의존성 설치
cd backend
uv sync
```