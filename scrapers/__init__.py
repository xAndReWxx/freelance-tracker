"""
Scraper registry — maps platform names to scraper classes.
To add a new platform: create a scraper module, then add it here.
"""
from scrapers.mostaql import MostaqlScraper
from scrapers.nafezly import NafezlyScraper
from scrapers.freelanceyard import FreelanceYardScraper
from scrapers.kafiil import KafiilScraper
from scrapers.khamsat import KhamsatScraper

SCRAPER_REGISTRY = {
    "Mostaql": MostaqlScraper,
    "Nafezly": NafezlyScraper,
    "FreelanceYard": FreelanceYardScraper,
    "Kafiil": KafiilScraper,
    "Khamsat": KhamsatScraper,
}

