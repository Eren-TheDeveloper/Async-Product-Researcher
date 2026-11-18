"""Hepsiburada ve Trendyol ürünlerini eşzamanlı araştırır."""

import argparse
import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import logging
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from playwright.async_api import Error as PlaywrightError, async_playwright

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Store:
    name: str
    base_url: str
    search_path: str
    page_parameter: str
    cards: str
    titles: str
    prices: tuple[str, ...]


STORES = {
    "hepsiburada": Store(
        "Hepsiburada", "https://www.hepsiburada.com", "/ara", "sayfa",
        'li:has(h2[class*="title-module_titleRoot"]), '
        '[data-test-id="product-card"], '
        'a:has(h2[class*="title-module_titleRoot"])',
        'h2[class*="title-module_titleRoot"], [data-test-id="product-card-name"]',
        ('[class*="price-module_finalPrice"]', '[data-test-id="price-current-price"]'),
    ),
    "trendyol": Store(
        "Trendyol", "https://www.trendyol.com", "/sr", "pi",
        '.p-card-wrppr, .product-card, [data-testid="product-card"]',
        '.product-name, .prdct-desc-cntnr-name',
        ('.prc-dsc', '.discounted-price', '.price-section .price-current',
         '.price-section .sale-price', '.prc-box-dscntd', '.price-section', '.prc-box-sllng'),
    ),
}


@dataclass(frozen=True)
class Product:
    name: str
    price: str | None
    price_value: str | None
    url: str | None


@dataclass
class SearchResult:
    products: list[Product] = field(default_factory=list)
    pages_completed: int = 0
    errors: list[str] = field(default_factory=list)


def search_url(store: Store, query: str, page_number: int) -> str:
    parameters = urlencode({'q': query, store.page_parameter: page_number})
    return f"{store.base_url}{store.search_path}?{parameters}"


def parse_price(text: str | None) -> str | None:
    """Tek bir Türk lirası tutarını, kayıpsız ondalık metne dönüştürür."""
    if not text:
        return None
    amount = re.sub(r"^₺\s*|\s*(?:TL|₺)$", "", text.strip())
    compact = re.sub(r"\s+", "", amount)
    if not re.fullmatch(r"(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?", compact):
        return None  # Birden fazla fiyatı veya kampanya metnini tutar olarak yorumlama.
    try:
        value = Decimal(compact.replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None
    return format(value, ".2f") if value >= 0 else None


def parse_products(html: str, store: Store) -> list[Product]:
    soup = BeautifulSoup(html, "html.parser")
    products = []
    seen = set()
    cards = soup.select(store.cards)
    card_ids = {id(card) for card in cards}
    for card in cards:
        if any(id(parent) in card_ids for parent in card.parents):
            continue
        title = card.select_one(store.titles)
        if title is None:
            continue
        name = title.get_text(" ", strip=True)
        if not name:
            continue
        price = None
        for selector in store.prices:
            node = card.select_one(selector)
            if node is not None and node.get_text(strip=True):
                price = node.get_text(" ", strip=True)
                break
        link = card if card.name == "a" else card.select_one("a[href]")
        url = None
        if link is not None and link.get("href"):
            parts = urlsplit(urljoin(store.base_url, link["href"]))
            if parts.scheme in {"http", "https"} and parts.netloc == urlsplit(store.base_url).netloc:
                url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        product = Product(name, price, parse_price(price), url)
        key = (url, name, price)
        if key not in seen:
            seen.add(key)
            products.append(product)
    return products


async def scrape_store(browser, store: Store, query: str, pages: int,
                       timeout: int, retries: int) -> SearchResult:
    result = SearchResult()
    seen = set()
    context = await browser.new_context(locale="tr-TR")
    try:
        page = await context.new_page()
        for page_number in range(1, pages + 1):
            for attempt in range(retries + 1):
                try:
                    LOGGER.info("%s: %s/%s. sayfa", store.name, page_number, pages)
                    response = await page.goto(search_url(store, query, page_number),
                                               wait_until="domcontentloaded", timeout=timeout)
                    if response is not None and response.status >= 400:
                        raise PlaywrightError(f"HTTP {response.status}")
                    await page.locator(store.cards).first.wait_for(state="attached", timeout=timeout)
                    # Kartın kabuğunun gelmesi yeterli değil; fiyatların da yüklenmesini bekle.
                    await page.locator(", ".join(store.prices)).first.wait_for(
                        state="attached", timeout=timeout)
                    products = parse_products(await page.content(), store)
                    if not products:
                        raise PlaywrightError("Ürün ayrıştırılamadı; sayfa yapısı değişmiş olabilir.")
                    result.pages_completed += 1
                    for product in products:
                        key = (product.url, product.name, product.price)
                        if key not in seen:
                            seen.add(key)
                            result.products.append(product)
                    break
                except PlaywrightError as exc:
                    if attempt < retries:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        message = f"{page_number}. sayfa alınamadı: {exc}"
                        result.errors.append(message)
                        LOGGER.warning("%s: %s", store.name, message)
    finally:
        await context.close()
    return result


def save_result(path: Path, query: str, result: SearchResult) -> None:
    """Geçici dosyayı atomik değiştirerek mevcut sonucu korur."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "query": query,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "currency": "TRY",
        "pages_completed": result.pages_completed,
        "errors": result.errors,
        "products": [asdict(product) for product in result.products],
        # Eski okuyucular için iki liste aynı ürün sırasını korur.
        "names": [product.name for product in result.products],
        "prices": [product.price for product in result.products],
    }
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


async def run(args: argparse.Namespace) -> int:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=not args.show_browser)
        try:
            keys = list(STORES) if args.store == "all" else [args.store]
            results = await asyncio.gather(*(
                scrape_store(browser, STORES[key], args.query, args.pages, args.timeout, args.retries)
                for key in keys
            ), return_exceptions=True)
        finally:
            await browser.close()
    failed = False
    for key, result in zip(keys, results):
        if isinstance(result, BaseException):
            LOGGER.error("%s: %s", STORES[key].name, result)
            failed = True
            continue
        failed = failed or bool(result.errors) or not result.products
        if not result.products:
            LOGGER.error("%s: Ürün alınamadı; mevcut çıktı dosyası korundu.", STORES[key].name)
            continue
        output = args.output_dir / f"{key}_products.json"
        try:
            save_result(output, args.query, result)
        except OSError as exc:
            LOGGER.error("%s: Sonuç kaydedilemedi: %s", STORES[key].name, exc)
            failed = True
            continue
        print(f"{STORES[key].name}: {len(result.products)} ürün -> {output}")
        priced = [product for product in result.products if product.price_value is not None]
        if priced:
            cheapest = min(priced, key=lambda product: Decimal(product.price_value))
            print(f"  Bu mağazadaki en düşük fiyat: {cheapest.name} — {cheapest.price}")
    return int(failed)


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("Değer en az 1 olmalıdır.")
    return number


def nonnegative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("Değer negatif olamaz.")
    return number


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", help="Aranacak ürün")
    parser.add_argument("--pages", type=positive_int, default=5, help="Mağaza başına sayfa sayısı")
    parser.add_argument("--store", choices=["all", *STORES], default="all")
    parser.add_argument("--timeout", type=positive_int, default=30000, help="İşlem zaman aşımı (ms)")
    parser.add_argument("--retries", type=nonnegative_int, default=2, help="Başarısız sayfa için tekrar sayısı")
    parser.add_argument("--output-dir", type=Path, default=Path("."))
    parser.add_argument("--show-browser", action="store_true", help="Tarayıcı penceresini göster")
    args = parser.parse_args()
    if args.query is None:
        try:
            args.query = input("Aramak istediğiniz ürünü yazınız: ")
        except EOFError:
            parser.error("Aranacak ürünü belirtin.")
    args.query = args.query.strip()
    if not args.query:
        parser.error("Ürün adı boş olamaz.")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        LOGGER.info("İşlem kullanıcı tarafından durduruldu.")
        return 130
    except (PlaywrightError, OSError) as exc:
        LOGGER.error("İşlem tamamlanamadı: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
