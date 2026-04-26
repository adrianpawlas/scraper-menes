import asyncio
import logging
import sys
import time
from datetime import datetime

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

    async def run(self):
        logger.info("=" * 60)
        logger.info("Starting Menes Scraper")
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

        existing_products = self.db.get_existing_products()
        existing_urls = {p["product_url"] for p in existing_products}
        new_urls = [url for url in product_urls if url not in existing_urls]

        logger.info(f"Already in database: {len(existing_products)}")
        logger.info(f"New products to scrape: {len(new_urls)}")

        if not new_urls:
            logger.info("No new products to scrape. Exiting.")
            return

        logger.info("Step 3: Scraping product details...")
        scraped_products = []
        batch_size = 10

        for i in range(0, len(new_urls), batch_size):
            batch = new_urls[i:i + batch_size]
            logger.info(f"Processing batch {i // batch_size + 1}/{(len(new_urls) + batch_size - 1) // batch_size} ({len(batch)} products)")

            tasks = []
            for url in batch:
                tasks.append(self.scrape_and_process_product(url))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, dict) and result:
                    scraped_products.append(result)

            await asyncio.sleep(1)

        logger.info(f"Successfully scraped {len(scraped_products)} products")

        logger.info("Step 4: Inserting products into database...")
        inserted = self.db.insert_products_batch(scraped_products)

        elapsed_time = time.time() - start_time

        logger.info("=" * 60)
        logger.info(f"Scraping completed in {elapsed_time:.2f} seconds")
        logger.info(f"Total products in database: {self.db.get_product_count()}")
        logger.info(f"New products inserted: {inserted}")
        logger.info("=" * 60)

    async def scrape_and_process_product(self, url: str) -> Optional[dict]:
        try:
            logger.info(f"Scraping: {url}")

            html = await self.product_scraper.fetch_product_page(url)
            if not html:
                logger.error(f"Failed to fetch product page: {url}")
                return None

            product_data = self.product_scraper.extract_product_data(html, url)
            if not product_data:
                logger.error(f"Failed to extract product data: {url}")
                return None

            logger.info(f"  Title: {product_data.get('title', 'N/A')}")

            if product_data.get("image_url"):
                logger.info(f"  Generating image embedding...")
                image_embedding = await self.embedding_generator.get_image_embedding_from_url(
                    product_data["image_url"]
                )
                product_data["image_embedding"] = image_embedding
            else:
                product_data["image_embedding"] = None

            logger.info(f"  Generating info embedding...")
            info_embedding = self.embedding_generator.get_info_embedding(product_data)
            product_data["info_embedding"] = info_embedding

            return product_data

        except Exception as e:
            logger.error(f"Error processing product {url}: {e}")
            return None


async def main():
    scraper = MenesScraper()
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())