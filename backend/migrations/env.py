# 우리 앱의 설정(.env의 DATABASE_URL)과 모델 기반 클래스를 가져온다.
from app.core.config import settings
from app.core.db import Base

# 중요: 모델 파일을 임포트해야 Alembic이 그 안의 테이블을 인식한다.
# 임포트하지 않은 models.py의 클래스는 Base에 등록되지 않아서 테이블이 생성되지 않는다.
# 새 도메인의 models.py를 만들 때마다 여기에 한 줄씩 추가해야 한다.
# noqa: F401 = "쓰이지 않는 임포트라는 린트 경고를 무시"한다는 뜻이다.
from app.market import models  # noqa: F401

from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata

# Alembic이 "원하는 최종 모양"으로 비교할 기준이다.
# Base에 등록된 모든 모델의 테이블 정보가 여기에 들어 있다.
target_metadata = Base.metadata

# DB 주소를 alembic.ini에 하드코딩하지 않고 .env(settings)에서 가져온다.
# 비밀번호가 담긴 주소를 Git에 올라가는 ini 파일에 쓰지 않기 위해서다.
config.set_main_option("sqlalchemy.url", settings.database_url)

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
