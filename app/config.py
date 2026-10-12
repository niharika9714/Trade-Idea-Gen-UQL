import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("INVESTMENT_CHATBOT_DATA_DIR", PROJECT_ROOT / "data"))
METADATA_DB_PATH = Path(os.getenv("INVESTMENT_CHATBOT_METADATA_DB", DATA_DIR / "metadata.db"))
MARKET_DB_PATH = Path(os.getenv("INVESTMENT_CHATBOT_MARKET_DB", DATA_DIR / "market_data" / "market.db"))
DOCUMENTS_DIR = Path(os.getenv("INVESTMENT_CHATBOT_DOCUMENTS_DIR", DATA_DIR / "documents"))
MODEL_NAME = os.getenv("INVESTMENT_CHATBOT_MODEL", "qwen3:8b")
