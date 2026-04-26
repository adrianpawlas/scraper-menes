import torch
import numpy as np
from PIL import Image
import httpx
import io
from typing import Optional, List
import logging
from transformers import AutoModel, AutoProcessor
import config

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    def __init__(self):
        self.model_name = config.EMBEDDING_MODEL
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Initializing embedding generator with model: {self.model_name}")
        logger.info(f"Using device: {self.device}")

        self.model = None
        self.processor = None

    def load_model(self):
        if self.model is None:
            logger.info(f"Loading model {self.model_name}...")
            self.processor = AutoProcessor.from_pretrained(self.model_name)
            self.model = AutoModel.from_pretrained(self.model_name)
            self.model.to(self.device)
            self.model.eval()
            logger.info("Model loaded successfully")

    def get_text_embedding(self, text: str) -> Optional[List[float]]:
        if not text:
            return None

        try:
            self.load_model()

            inputs = self.processor(text=text, return_tensors="pt", padding=True)
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self.model.get_text_features(**inputs)

            if hasattr(outputs, 'pooler_output'):
                embedding = outputs.pooler_output.squeeze().cpu().numpy()
            elif hasattr(outputs, 'last_hidden_state'):
                embedding = outputs.last_hidden_state[:, 0, :].squeeze().cpu().numpy()
            else:
                embedding = outputs.squeeze().cpu().numpy()
            return embedding.tolist()

        except Exception as e:
            logger.error(f"Failed to generate text embedding: {e}")
            return None

    async def get_image_embedding_from_url(self, url: str) -> Optional[List[float]]:
        if not url:
            return None

        try:
            self.load_model()

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url)
                response.raise_for_status()

            image = Image.open(io.BytesIO(response.content)).convert("RGB")

            inputs = self.processor(images=image, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self.model.get_image_features(**inputs)

            if hasattr(outputs, 'pooler_output'):
                embedding = outputs.pooler_output.squeeze().cpu().numpy()
            elif hasattr(outputs, 'last_hidden_state'):
                embedding = outputs.last_hidden_state[:, 0, :].squeeze().cpu().numpy()
            else:
                embedding = outputs.squeeze().cpu().numpy()
            return embedding.tolist()

        except Exception as e:
            logger.error(f"Failed to generate image embedding for {url}: {e}")
            return None

    def get_image_embedding_from_path(self, image_path: str) -> Optional[List[float]]:
        if not image_path:
            return None

        try:
            self.load_model()

            image = Image.open(image_path).convert("RGB")

            inputs = self.processor(images=image, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self.model.get_image_features(**inputs)

            if hasattr(outputs, 'pooler_output'):
                embedding = outputs.pooler_output.squeeze().cpu().numpy()
            elif hasattr(outputs, 'last_hidden_state'):
                embedding = outputs.last_hidden_state[:, 0, :].squeeze().cpu().numpy()
            else:
                embedding = outputs.squeeze().cpu().numpy()
            return embedding.tolist()

        except Exception as e:
            logger.error(f"Failed to generate image embedding from {image_path}: {e}")
            return None

    def get_info_embedding(self, product_data: dict) -> Optional[List[float]]:
        text_parts = []

        if product_data.get("title"):
            text = product_data['title'][:40]
            text_parts.append(text)
        if product_data.get("price"):
            text_parts.append(product_data['price'])
        if product_data.get("gender"):
            text_parts.append(product_data['gender'])
        if product_data.get("category"):
            cat = product_data['category'].split(',')[0][:30]
            text_parts.append(cat)

        combined_text = " ".join(text_parts)

        return self.get_text_embedding(combined_text)

    def batch_get_text_embeddings(self, texts: List[str]) -> List[Optional[List[float]]]:
        embeddings = []
        for text in texts:
            emb = self.get_text_embedding(text)
            embeddings.append(emb)
        return embeddings