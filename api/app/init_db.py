from .db import engine, Base
from app.migrations import migrate_sqlite
from . import models  # noqa
Base.metadata.create_all(bind=engine)
migrate_sqlite(engine)
