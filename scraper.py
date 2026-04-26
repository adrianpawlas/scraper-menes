import httpx
import asyncio
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential
from typing import List, Dict, Optional
import config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ShopifyScraper:
    def __init__(self):
        self.base_url = config.BASE_URL
        self.collections_url = config.COLLECTIONS_URL
        self.session = None

    async def get_client(self) -> httpx.AsyncClient:
        if self.session is None:
            self.session = httpx.AsyncClient(
                timeout=config.REQUEST_TIMEOUT,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                },
                follow_redirects=True,
            )
        return self.session

    @retry(stop=stop_after_attempt(config.MAX_RETRIES), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_page(self, url: str) -> Optional[str]:
        client = await self.get_client()
        try:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch {url}: {e}")
            raise

    def parse_product_links(self, html: str) -> List[str]:
        soup = BeautifulSoup(html, "lxml")
        product_links = []

        for a_tag in soup.select("a[href*='/products/']"):
            href = a_tag.get("href", "")
            if href and "/products/" in href:
                full_url = href if href.startswith("http") else f"{self.base_url}{href}"
                if full_url not in product_links:
                    product_links.append(full_url)

        return product_links

    def has_products(self, html: str) -> bool:
        soup = BeautifulSoup(html, "lxml")
        product_links = self.parse_product_links(html)
        return len(product_links) > 0

    async def get_all_product_urls(self) -> List[str]:
        logger.info(f"Starting to scrape all product URLs from {self.collections_url}")

        all_products = []
        page = 1
        max_pages = 100

        while page <= max_pages:
            if page == 1:
                url = self.collections_url
            else:
                url = f"{self.collections_url}?page={page}"

            logger.info(f"Scraping page {page}: {url}")

            html = await self.fetch_page(url)

            if not html or not self.has_products(html):
                logger.info(f"No products found on page {page}. Stopping pagination.")
                break

            products = self.parse_product_links(html)
            logger.info(f"Found {len(products)} products on page {page}")

            all_products.extend(products)
            page += 1

        unique_products = list(set(all_products))
        logger.info(f"Total unique products found: {len(unique_products)}")
        return unique_products


class ProductScraper:
    def __init__(self):
        self.base_url = config.BASE_URL
        self.session = None

    async def get_client(self) -> httpx.AsyncClient:
        if self.session is None:
            self.session = httpx.AsyncClient(
                timeout=config.REQUEST_TIMEOUT,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                },
                follow_redirects=True,
            )
        return self.session

    @retry(stop=stop_after_attempt(config.MAX_RETRIES), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def fetch_product_page(self, url: str) -> Optional[str]:
        client = await self.get_client()
        try:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch product {url}: {e}")
            raise

    def extract_product_data(self, html: str, url: str) -> Optional[Dict]:
        soup = BeautifulSoup(html, "lxml")

        title = soup.find("h1")
        title = title.text.strip() if title else None

        if not title:
            return None

        product_id = self.extract_product_id(html, url)

        price, sale = self.extract_prices(soup, html)

        description = self.extract_description(soup)

        images = self.extract_images(soup, html)
        image_url = images[0] if images else None
        additional_images = ", ".join(images[1:]) if len(images) > 1 else None

        category = self.extract_category(soup, html)

        gender = self.extract_gender(soup, html)

        sizes = self.extract_sizes(soup, html)

        metadata = self.build_metadata(title, description, price, sale, category, gender, sizes, images)

        return {
            "id": product_id,
            "source": config.SOURCE,
            "product_url": url,
            "image_url": image_url,
            "additional_images": additional_images,
            "brand": config.BRAND,
            "title": title,
            "description": description,
            "category": category,
            "gender": gender,
            "price": price,
            "sale": sale,
            "metadata": metadata,
            "second_hand": False,
            "country": "JP",
        }

    def extract_product_id(self, html: str, url: str) -> str:
        if "/products/" in url:
            handle = url.split("/products/")[-1].split("?")[0]
            return handle
        import hashlib
        return hashlib.md5(url.encode()).hexdigest()

    def extract_prices(self, soup: BeautifulSoup, html: str) -> tuple:
        price = None
        sale = None

        import re
        import json

        meta_match = re.search(r'var meta = (\{.*?\});', html, re.DOTALL)
        if meta_match:
            try:
                meta = json.loads(meta_match.group(1))
                product = meta.get("product", {})
                if "variants" in product and product["variants"]:
                    price_czk = product["variants"][0].get("price", 0)
                    if price_czk:
                        price = f"{price_czk / 100:.2f}CZK"

                    for variant in product["variants"]:
                        compare_at = variant.get("compare_at_price")
                        if compare_at and compare_at > price_czk:
                            sale = f"{price_czk / 100:.2f}CZK"
                            price = f"{compare_at / 100:.2f}CZK"
                            break
            except Exception as e:
                logger.debug(f"Failed to parse meta JSON: {e}")

        if not price:
            price_elem = soup.select_one('.price .money, [data-product-price]')
            if price_elem:
                price = price_elem.text.strip()

        return price, sale

    def extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        desc_elem = soup.select_one('[data-testid="product-description"], .product-description, #product-description, .product-detail__description')
        if desc_elem:
            return desc_elem.text.strip()

        tabs = soup.select(".product-detail__tab-content, .product-tabs__content")
        for tab in tabs:
            if tab.text.strip():
                return tab.text.strip()

        return None

    def extract_images(self, soup: BeautifulSoup, html: str) -> List[str]:
        images = []

        for img in soup.select(".product-media img, [data-product-media] img"):
            src = img.get("src") or img.get("data-src")
            if not src:
                srcset = img.get("data-srcset") or img.get("srcset")
                if srcset:
                    src = srcset.split()[0] if srcset.split() else None
            if src:
                if src.startswith("//"):
                    src = "https:" + src
                elif src.startswith("/"):
                    src = f"{config.BASE_URL}{src}"
                if ("cdn.shop" in src or "/cdn/" in src) and src not in images:
                    images.append(src)

        if not images:
            for img in soup.select(".product-gallery__image img, .product-image img"):
                src = img.get("src") or img.get("data-src")
                if src:
                    if src.startswith("//"):
                        src = "https:" + src
                    elif src.startswith("/"):
                        src = f"{config.BASE_URL}{src}"
                    if ("cdn.shop" in src or "/cdn/" in src) and src not in images:
                        images.append(src)

        return images[:10]

    def extract_category(self, soup: BeautifulSoup, html: str) -> Optional[str]:
        breadcrumbs = soup.select(".breadcrumb a, .breadcrumbs a, .breadcrumb__item a")
        categories = []
        for crumb in breadcrumbs:
            text = crumb.text.strip()
            if text and text.lower() not in ["home", "menes", "all", "collections"]:
                categories.append(text)

        nav_link = soup.select_one(".product-detail__category, .product-category")
        if nav_link and nav_link.text.strip():
            cat_text = nav_link.text.strip()
            if cat_text not in categories:
                categories.append(cat_text)

        if not categories:
            meta_category = soup.select_one('meta[property="product:product_category"]')
            if meta_category:
                cat = meta_category.get("content")
                if cat:
                    categories = [c.strip() for c in cat.split(">")]

        return ", ".join(categories) if categories else None

    def extract_gender(self, soup: BeautifulSoup, html: str) -> Optional[str]:
        title_lower = soup.find("h1").text.lower() if soup.find("h1") else ""
        category = self.extract_category(soup, html) or ""

        if any(w in title_lower + category for w in ["men", "man", "male", "boys"]):
            return "male"
        elif any(w in title_lower + category for w in ["women", "woman", "female", "girls"]):
            return "female"
        elif any(w in title_lower + category for w in ["unisex", "neutral"]):
            return "unisex"

        return None

    def extract_sizes(self, soup: BeautifulSoup, html: str) -> List[str]:
        sizes = []

        variant_options = soup.select(".product-form__option-select option, .variant-picker option")
        for option in variant_options:
            text = option.text.strip()
            if text and text not in ["Select", "Choose", "Size"]:
                sizes.append(text)

        size_buttons = soup.select(".size-selector button, .product-size button, [data-variant-option] button")
        for btn in size_buttons:
            text = btn.text.strip()
            if text and text not in sizes:
                sizes.append(text)

        return sizes

    def build_metadata(self, title: str, description: Optional[str], price: Optional[str],
                      sale: Optional[str], category: Optional[str], gender: Optional[str],
                      sizes: List[str], images: List[str]) -> str:
        parts = []
        if title:
            parts.append(f"Title: {title}")
        if price:
            parts.append(f"Price: {price}")
        if sale:
            parts.append(f"Sale: {sale}")
        if category:
            parts.append(f"Category: {category}")
        if gender:
            parts.append(f"Gender: {gender}")
        if sizes:
            parts.append(f"Sizes: {', '.join(sizes)}")
        if description:
            parts.append(f"Description: {description[:500]}")
        if images:
            parts.append(f"Images: {len(images)} images")

        return " | ".join(parts)