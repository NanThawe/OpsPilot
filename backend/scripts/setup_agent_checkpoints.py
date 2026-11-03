import os
from pathlib import Path

from dotenv import load_dotenv


# Locate the OpsPilot project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Load OpsPilot/.env before importing application modules
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(ENV_FILE)

if not os.getenv("DATABASE_URL"):
    raise RuntimeError(
        f"DATABASE_URL could not be loaded from {ENV_FILE}"
    )


from langgraph.checkpoint.postgres import PostgresSaver

from app.db.session import get_engine


# Reuse OpsPilot's existing database configuration
engine = get_engine()

database_url = (
    engine.url
    .set(drivername="postgresql")
    .render_as_string(hide_password=False)
)


with PostgresSaver.from_conn_string(database_url) as checkpointer:
    checkpointer.setup()

print("LangGraph checkpoint tables created successfully.")