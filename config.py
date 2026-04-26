import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://yqawmzggcgpeyaaynrjk.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlxYXdtemdnY2dwZXlhYXlucmprIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NTAxMDkyNiwiZXhwIjoyMDcwNTg2OTI2fQ.XtLpxausFriraFJeX27ZzsdQsFv3uQKXBBggoz6P4D4")

BASE_URL = "https://menestokyo.com"
COLLECTIONS_URL = "https://menestokyo.com/en/collections/all"

SOURCE = "scraper-menes"
BRAND = "Menes"

EMBEDDING_MODEL = "google/siglip-base-patch16-384"
EMBEDDING_DIMENSION = 768

CONCURRENCY_LIMIT = 5
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

DATABASE_TABLE = "products"