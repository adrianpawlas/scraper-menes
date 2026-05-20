import asyncio
import logging
import sys

import config
from scraper import ProductScraper
from embedding import EmbeddingGenerator
from database import DatabaseManager
from supabase import create_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def update_missing_info_embeddings():
    client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    
    response = client.table('products').select('id, product_url').eq('source', 'scraper-menes').is_('info_embedding', 'null').execute()
    
    if not response.data:
        logger.info("All products already have info embeddings!")
        return
    
    logger.info(f"Found {len(response.data)} products with missing info embeddings")
    
    scraper = ProductScraper()
    generator = EmbeddingGenerator()
    
    for product in response.data:
        url = product['product_url']
        product_id = product['id']
        
        logger.info(f"Processing: {product_id}")
        
        try:
            html = await scraper.fetch_product_page(url)
            product_data = await scraper.extract_product_data(html, url)
            
            if product_data:
                info_emb = generator.get_info_embedding(product_data)
                if info_emb:
                    client.table('products').update({'info_embedding': info_emb}).eq('id', product_id).execute()
                    logger.info(f"  Updated info embedding for {product_id}")
                else:
                    logger.warning(f"  Failed to generate info embedding")
            else:
                logger.warning(f"  Failed to extract product data")
        except Exception as e:
            logger.error(f"  Error: {e}")
        
        await asyncio.sleep(0.5)
    
    logger.info("Done updating info embeddings!")

if __name__ == "__main__":
    asyncio.run(update_missing_info_embeddings())