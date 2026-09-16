from app.db.database import Base, engine
from app.db.models import Company, Job


def init_database() -> None:
    # Importing the models above registers them with SQLAlchemy.
    Base.metadata.create_all(bind=engine)

    print("Database initialized successfully.")


if __name__ == "__main__":
    init_database()