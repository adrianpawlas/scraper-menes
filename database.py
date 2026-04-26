import supabase
from typing import List, Dict, Optional
import logging
import config

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self):
        self.client = supabase.create_client(
            config.SUPABASE_URL,
            config.SUPABASE_KEY
        )
        self.table_name = config.DATABASE_TABLE

    def check_connection(self) -> bool:
        try:
            response = self.client.table(self.table_name).select("id").limit(1).execute()
            logger.info("Database connection successful")
            return True
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return False

    def insert_product(self, product_data: dict) -> bool:
        try:
            product_data["created_at"] = "now()"

            response = self.client.table(self.table_name).upsert(
                product_data,
                on_conflict="source,product_url"
            ).execute()

            if response.data:
                logger.info(f"Inserted/updated product: {product_data.get('title', 'Unknown')}")
                return True
            return False

        except Exception as e:
            logger.error(f"Failed to insert product: {e}")
            logger.error(f"Product data: {product_data}")
            return False

    def insert_products_batch(self, products: List[dict]) -> int:
        success_count = 0
        for product in products:
            if self.insert_product(product):
                success_count += 1
        return success_count

    def get_existing_products(self, source: str = config.SOURCE) -> List[Dict]:
        try:
            response = self.client.table(self.table_name).select(
                "id, source, product_url, title"
            ).eq("source", source).execute()
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Failed to get existing products: {e}")
            return []

    def product_exists(self, source: str, product_url: str) -> bool:
        try:
            response = self.client.table(self.table_name).select(
                "id", count="exact"
            ).eq("source", source).eq("product_url", product_url).execute()
            return (response.count or 0) > 0
        except Exception as e:
            logger.error(f"Failed to check product existence: {e}")
            return False

    def delete_product(self, product_id: str) -> bool:
        try:
            self.client.table(self.table_name).delete().eq("id", product_id).execute()
            logger.info(f"Deleted product: {product_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete product: {e}")
            return False

    def get_product_count(self) -> int:
        try:
            response = self.client.table(self.table_name).select(
                "id", count="exact"
            ).eq("source", config.SOURCE).execute()
            return response.count or 0
        except Exception as e:
            logger.error(f"Failed to get product count: {e}")
            return 0

    def update_product_embedding(self, product_id: str, embedding: List[float]) -> bool:
        try:
            self.client.table(self.table_name).update(
                {"image_embedding": embedding}
            ).eq("id", product_id).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to update product embedding: {e}")
            return False

    def update_product_info_embedding(self, product_id: str, embedding: List[float]) -> bool:
        try:
            self.client.table(self.table_name).update(
                {"info_embedding": embedding}
            ).eq("id", product_id).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to update product info embedding: {e}")
            return False