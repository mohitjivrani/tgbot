import logging
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

from flipkart_scraper import FlipkartScraper
from vivo_scraper import VivoScraper

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

SCRAPER_TIMEOUT = int(os.getenv("SCRAPER_TIMEOUT", "30"))

app = FastAPI(title="Scraper Service", version="1.0.0")

_scrapers = {
    "flipkart": FlipkartScraper(timeout=SCRAPER_TIMEOUT),
    "vivo": VivoScraper(timeout=SCRAPER_TIMEOUT),
}


class ScrapeRequest(BaseModel):
    url: str
    platform: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/scrape")
def scrape(payload: ScrapeRequest):
    platform = payload.platform.lower()
    scraper = _scrapers.get(platform)
    if scraper is None:
        raise HTTPException(status_code=400, detail=f"Unsupported platform: {platform}")

    logger.info("Scraping %s url=%s", platform, payload.url)
    result = scraper.scrape(payload.url)
    return result
