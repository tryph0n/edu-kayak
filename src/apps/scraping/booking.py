import scrapy
from scrapy_playwright.page import PageMethod
import json


class BookingPlaywrightSpider(scrapy.Spider):
    name = "booking_playwright"

    cities = []
    max_hotels = 4

    custom_settings = {
        "DOWNLOAD_HANDLERS": {
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        },
        "PLAYWRIGHT_BROWSER_TYPE": "chromium",
        "PLAYWRIGHT_LAUNCH_OPTIONS": {
            "headless": False,
        },
        "CONCURRENT_REQUESTS": 1,
        "DOWNLOAD_DELAY": 3,
    }

    def start_requests(self):
        for city in self.cities:
            url = f"https://www.booking.com/searchresults.html?ss={city}&dest_type=city"

            yield scrapy.Request(
                url,
                errback=self.errback_retry,
                meta={
                    "playwright": True,
                    "playwright_page_methods": [
                        PageMethod("wait_for_load_state", "networkidle"),
                        PageMethod("wait_for_timeout", 3000),
                        PageMethod(
                            "wait_for_selector",
                            '[data-testid="property-card"]',
                            timeout=30000,
                        ),
                    ],
                    "city_name": city,
                },
            )

    def parse(self, response):
        city_name = response.meta.get("city_name")
        all_cards = response.css('[data-testid="property-card"]')
        hotels = [c for c in all_cards if c.css('[data-testid="review-score"]')]
        hotels = sorted(hotels, key=self._extract_card_score, reverse=True)[: self.max_hotels]
        self.logger.info(f"Found {len(hotels)} hotels for {city_name}")

        for hotel in hotels:
            hotel_link = hotel.css('a[data-testid="title-link"]::attr(href)').get()
            if hotel_link:
                yield scrapy.Request(
                    response.urljoin(hotel_link),
                    callback=self.parse_hotel,
                    errback=self.errback_retry,
                    meta={
                        "playwright": True,
                        "playwright_page_methods": [
                            PageMethod("wait_for_load_state", "networkidle"),
                            PageMethod("wait_for_timeout", 2000),
                        ],
                        "city_name": city_name,
                    },
                )

    def parse_hotel(self, response):
        city_name = response.meta.get("city_name")

        json_ld_script = response.xpath(
            '//script[@type="application/ld+json"]/text()'
        ).get()

        hotel_name = None
        address = None
        score = None
        description = None

        if json_ld_script:
            try:
                data = json.loads(json_ld_script)

                hotel_name = data.get("name")

                address_data = data.get("address", {})
                if isinstance(address_data, dict):
                    address = address_data.get("streetAddress")
                elif isinstance(address_data, str):
                    address = address_data

                rating_data = data.get("aggregateRating", {})
                if isinstance(rating_data, dict):
                    score = rating_data.get("ratingValue")

                description = data.get("description")

            except json.JSONDecodeError as e:
                self.logger.error(f"JSON-LD parsing error: {e}")

        if not hotel_name:
            hotel_name = response.css("h2.pp-header__title::text").get()
            if not hotel_name:
                hotel_name = response.css('[data-testid="title"]::text').get()

        if not address:
            address = response.css("span.hp_address_subtitle::text").get()
            if not address:
                address = response.css(
                    '[data-node_tt_id="location_score_tooltip"]::text'
                ).get()

        if not score:
            score_text = response.css(".b5cd09854e.d10a6220b4::text").get()
            if score_text:
                score = score_text.strip()

        if not description:
            description = response.css(
                '[data-testid="property-description"] ::text'
            ).getall()
            if description:
                description = " ".join(d.strip() for d in description if d.strip())

        yield {
            "city_name": city_name,
            "hotel_name": hotel_name,
            "url": response.url,
            "score": str(score) if score else None,
            "address": address,
            "description": description,
        }

    @staticmethod
    def _extract_card_score(card):
        text = card.css('[data-testid="review-score"] ::text').re_first(r"\d+[.,]\d+")
        return float(text.replace(",", ".")) if text else 0.0

    def errback_retry(self, failure):
        request = failure.request
        retry_count = request.meta.get("playwright_retry_count", 0)
        if retry_count < 2:
            self.logger.warning(
                f"retrying {request.url} ({retry_count + 1}/2) after {failure.value!r}"
            )
            new_meta = {**request.meta, "playwright_retry_count": retry_count + 1}
            return request.replace(meta=new_meta, dont_filter=True)
        self.logger.error(f"giving up on {request.url} after 2 retries")
