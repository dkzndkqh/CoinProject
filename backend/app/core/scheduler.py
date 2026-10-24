from apscheduler.schedulers.background import BackgroundScheduler

# 앱 전체에서 쓰는 스케줄러 하나. 어떤 작업을 등록할지는 main.py에서 정한다
# (core가 market 같은 도메인을 직접 알지 않게 하기 위해서다).
# BackgroundScheduler는 별도 스레드에서 돌면서 정해진 시각에 작업을 실행한다.

scheduler = BackgroundScheduler(timezone="UTC")
