import asyncio
import logging
import sys
import time
from datetime import datetime
from typing import Optional, Tuple

import config
from scraper import ShopifyScraper, ProductScraper
from embedding import EmbeddingGenerator
from database import DatabaseManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)


class MenesScraper:
    def __init__(self):
        self.shopify_scraper = ShopifyScraper()
        self.product_scraper = ProductScraper()
        self.embedding_generator = EmbeddingGenerator()
        self.db = DatabaseManager()
        
        self.stats = {
            "new_added": 0,
            "updated": 0,
            "unchanged": 0,
            "deleted": 0,
            "failed_batch_products": []
        }

    async def run(self):
        logger.info("=" * 60)
        logger.info("Starting Menes Scraper - Smart Product Management")
        logger.info("=" * 60)

        start_time = time.time()

        logger.info("Step 1: Checking database connection...")
        if not self.db.check_connection():
            logger.error("Database connection failed. Exiting.")
            return

        logger.info("Step 2: Getting all product URLs...")
        product_urls = await self.shopify_scraper.get_all_product_urls()

        if not product_urls:
            logger.error("No products found. Exiting.")
            return

        logger.info(f"Found {len(product_urls)} total products")

        logger.info("Step 3: Fetching existing products from database...")
        existing_products = self.db.get_existing_products()
        logger.info(f"Already in database: {len(existing_products)} products")

        logger.info("Step 4: Scraping and processing products...")
        
        new_products_batch = []
        update_products_batch = []
        
        batch_size = 50
        all_new_products = []
        all_update_products = []

        for i, url in enumerate(product_urls):
            logger.info(f"Processing {i+1}/{len(product_urls)}: {url}")
            
            result = await self.scrape_and_process_product(url, existing_products.get(url))
            
            if result:
                if result[0] == "unchanged":
                    self.stats["unchanged"] += 1
                elif result[1]:
                    new_products_batch.append(result[0])
                    all_new_products.append(result[0])
                else:
                    all_update_products.append((result[0], result[2]))
            else:
                logger.warning(f"Failed to scrape: {url}")

            if (i + 1) % 10 == 0:
                logger.info(f"Progress: {i+1}/{len(product_urls)} products processed")

            await asyncio.sleep(0.5)

        logger.info(f"Processed all products. New: {len(all_new_products)}, Updates: {len(all_update_products)}")

        logger.info("Step 5: Batch inserting/updating products...")
        
        for i in range(0, len(new_products_batch), batch_size):
            batch = new_products_batch[i:i+batch_size]
            inserted, failed = self.db.insert_products_batch(batch)
            self.stats["new_added"] += inserted
            if failed:
                self.stats["failed_batch_products"].extend(failed)
            logger.info(f"Inserted batch {i//batch_size + 1}: {inserted} new products")
            await asyncio.sleep(1)

        for i in range(0, len(all_update_products), batch_size):
            batch_data = all_update_products[i:i+batch_size]
            products_to_update = [p for p, _ in batch_data]
            
            updated, failed = self.db.update_products_batch(products_to_update)
            self.stats["updated"] += updated
            if failed:
                self.stats["failed_batch_products"].extend(failed)
            logger.info(f"Updated batch {i//batch_size + 1}: {updated} products")
            await asyncio.sleep(1)

        logger.info("Step 6: Removing stale products...")
        deleted = self.db.delete_stale_products(product_urls)
        self.stats["deleted"] = deleted

        elapsed_time = time.time() - start_time

        self.print_summary(elapsed_time)
        self.log_failures()

    async def scrape_and_process_product(self, url: str, existing_product: dict = None) -> Optional[tuple]:
        try:
            html = await self.product_scraper.fetch_product_page(url)
            if not html:
                logger.error(f"Failed to fetch product page: {url}")
                return None

            product_data = await self.product_scraper.extract_product_data(html, url)
            if not product_data:
                logger.error(f"Failed to extract product data: {url}")
                return None

            is_new = existing_product is None
            
            if is_new:
                logger.info(f"  NEW: {product_data.get('title', 'N/A')}")
                
                if product_data.get("image_url"):
                    logger.info(f"  Generating image embedding...")
                    image_embedding = await self.embedding_generator.get_image_embedding_from_url(
                        product_data["image_url"]
                    )
                    product_data["image_embedding"] = image_embedding
                    await asyncio.sleep(0.5)
                else:
                    product_data["image_embedding"] = None

                logger.info(f"  Generating info embedding...")
                info_embedding = self.embedding_generator.get_info_embedding(product_data)
                product_data["info_embedding"] = info_embedding

                return (product_data, True, True)

            else:
                has_changed = self.db.check_if_changed(existing_product, product_data)
                
                if not has_changed:
                    logger.info(f"  UNCHANGED: {product_data.get('title', 'N/A')} (skipping)")
                    return ("unchanged", False, False)
                
                needs_embedding = self.db.needs_embedding_regeneration(existing_product, product_data)
                
                logger.info(f"  CHANGED: {product_data.get('title', 'N/A')} (updating)")
                
                if needs_embedding and product_data.get("image_url"):
                    logger.info(f"  Regenerating image embedding (URL changed)...")
                    image_embedding = await self.embedding_generator.get_image_embedding_from_url(
                        product_data["image_url"]
                    )
                    product_data["image_embedding"] = image_embedding
                    await asyncio.sleep(0.5)
                else:
                    product_data["image_embedding"] = existing_product.get("image_embedding")

                logger.info(f"  Regenerating info embedding...")
                info_embedding = self.embedding_generator.get_info_embedding(product_data)
                product_data["info_embedding"] = info_embedding

                return (product_data, False, needs_embedding)

        except Exception as e:
            logger.error(f"Error processing product {url}: {e}")
            return None

    def print_summary(self, elapsed_time: float):
        logger.info("=" * 60)
        logger.info("RUN SUMMARY")
        logger.info("=" * 60)
        logger.info(f"New products added:     {self.stats['new_added']}")
        logger.info(f"Products updated:      {self.stats['updated']}")
        logger.info(f"Products unchanged:    {self.stats['unchanged']}")
        logger.info(f"Stale products deleted: {self.stats['deleted']}")
        logger.info(f"Total in database:     {self.db.get_product_count()}")
        logger.info(f"Time elapsed:           {elapsed_time:.2f} seconds")
        logger.info("=" * 60)

    def log_failures(self):
        if self.stats['failed_batch_products']:
            log_file = f"failed_products_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            try:
                with open(log_file, 'w') as f:
                    f.write("Failed batch products:\n")
                    for url in self.stats['failed_batch_products']:
                        f.write(f"  - {url}\n")
                logger.warning(f"Logged {len(self.stats['failed_batch_products'])} failed products to {log_file}")
            except Exception as e:
                logger.error(f"Failed to write failure log: {e}")


async def main():
    scraper = MenesScraper()
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())