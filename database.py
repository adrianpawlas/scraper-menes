import supabase
from typing import List, Dict, Optional
import logging
import config
import time
import asyncio

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

    def get_existing_products(self, source: str = config.SOURCE) -> Dict[str, dict]:
        try:
            response = self.client.table(self.table_name).select(
                "id, source, product_url, title, price, image_url, additional_images, description, category, gender, metadata"
            ).eq("source", source).execute()
            
            if response.data:
                return {p['product_url']: p for p in response.data}
            return {}
        except Exception as e:
            logger.warning(f"Failed to get existing products: {e}")
            try:
                response = self.client.table(self.table_name).select(
                    "id, source, product_url, title, price, image_url"
                ).eq("source", source).execute()
                if response.data:
                    return {p['product_url']: p for p in response.data}
            except:
                pass
            return {}

    def get_all_product_urls(self, source: str = config.SOURCE) -> List[str]:
        try:
            response = self.client.table(self.table_name).select("product_url").eq("source", source).execute()
            return [p['product_url'] for p in response.data] if response.data else []
        except Exception as e:
            logger.error(f"Failed to get all product URLs: {e}")
            return []

    def insert_products_batch(self, products: List[dict], retry_count: int = 3) -> tuple:
        if not products:
            return 0, []

        failed_products = []
        
        for attempt in range(retry_count):
            try:
                products_to_insert = []
                for p in products:
                    p_copy = {k: v for k, v in p.items() if v is not None}
                    products_to_insert.append(p_copy)

                response = self.client.table(self.table_name).upsert(
                    products_to_insert,
                    on_conflict="source,product_url"
                ).execute()

                if response.data:
                    return len(products_to_insert), []
                else:
                    if attempt < retry_count - 1:
                        time.sleep(1 * (attempt + 1))
                        continue

            except Exception as e:
                logger.warning(f"Batch insert attempt {attempt + 1} failed: {e}")
                if attempt < retry_count - 1:
                    time.sleep(1 * (attempt + 1))
                    continue

        failed_products = [p.get('product_url', 'unknown') for p in products]
        logger.error(f"Batch insert failed after {retry_count} attempts. Failed products: {len(failed_products)}")
        return 0, failed_products

    def update_products_batch(self, products: List[dict], retry_count: int = 3) -> tuple:
        if not products:
            return 0, []

        failed_products = []

        for attempt in range(retry_count):
            try:
                products_to_update = []
                for p in products:
                    p_copy = {k: v for k, v in p.items() if v is not None}
                    products_to_update.append(p_copy)

                response = self.client.table(self.table_name).upsert(
                    products_to_update,
                    on_conflict="source,product_url"
                ).execute()

                if response.data:
                    return len(products_to_update), []
                else:
                    if attempt < retry_count - 1:
                        time.sleep(1 * (attempt + 1))
                        continue

            except Exception as e:
                logger.warning(f"Batch update attempt {attempt + 1} failed: {e}")
                if attempt < retry_count - 1:
                    time.sleep(1 * (attempt + 1))
                    continue

        failed_products = [p.get('product_url', 'unknown') for p in products]
        logger.error(f"Batch update failed after {retry_count} attempts. Failed products: {len(failed_products)}")
        return 0, failed_products

    def check_if_changed(self, existing: dict, new_data: dict) -> bool:
        fields_to_check = ['title', 'price', 'image_url', 'additional_images', 'description', 'category', 'gender', 'metadata']
        
        for field in fields_to_check:
            existing_val = existing.get(field)
            new_val = new_data.get(field)
            
            if str(existing_val) != str(new_val):
                return True
        
        return False

    def needs_embedding_regeneration(self, existing: dict, new_data: dict) -> bool:
        existing_image = existing.get('image_url', '')
        new_image = new_data.get('image_url', '')
        
        return existing_image != new_image

    def delete_stale_products(self, urls_to_keep: List[str], source: str = config.SOURCE) -> int:
        try:
            all_urls = self.get_all_product_urls(source)
            urls_to_delete = [url for url in all_urls if url not in urls_to_keep]
            
            deleted_count = 0
            for url in urls_to_delete:
                response = self.client.table(self.table_name).select("id").eq("product_url", url).execute()
                if response.data:
                    self.client.table(self.table_name).delete().eq("id", response.data[0]['id']).execute()
                    logger.info(f"Deleted stale product: {url}")
                    deleted_count += 1
            
            return deleted_count
        except Exception as e:
            logger.error(f"Failed to delete stale products: {e}")
            return 0

    def get_product_count(self) -> int:
        try:
            response = self.client.table(self.table_name).select(
                "id", count="exact"
            ).eq("source", config.SOURCE).execute()
            return response.count or 0
        except Exception as e:
            logger.error(f"Failed to get product count: {e}")
            return 0