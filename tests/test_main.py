import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlsplit

from main import (
    PlaywrightError, Product, SearchResult, STORES, parse_price,
    parse_products, run, save_result, scrape_store, search_url,
)


HTML = '''
<div class="p-card-wrppr"><a href="/marka/klavye-p-123?campaign=1">
<span class="product-name">Türkçe Klavye</span>
<div class="price-section"><del>2.000 TL</del>
<span class="discounted-price">1.299,90 TL</span></div></a></div>
<div class="p-card-wrppr"><span class="product-name">Fiyatı yok</span></div>
<div class="p-card-wrppr"><span class="product-name">Fare</span>
<div class="price-section">300 TL</div></div>
'''


class ParsingTests(unittest.TestCase):
    def test_missing_price_does_not_shift_names(self):
        products = parse_products(HTML, STORES['trendyol'])
        self.assertEqual([p.price for p in products], ['1.299,90 TL', None, '300 TL'])
        self.assertEqual(products[0].price_value, '1299.90')
        self.assertEqual(products[0].url, 'https://www.trendyol.com/marka/klavye-p-123')
        self.assertEqual(products[2].name, 'Fare')

    def test_duplicate_and_nested_cards(self):
        html = '''<li><a href="/urun"><h2 class="title-module_titleRoot__new">
        Ürün</h2></a><div class="price-module_finalPrice__new">10 TL</div></li>'''
        products = parse_products(html * 2, STORES['hepsiburada'])
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].price_value, '10.00')

    def test_empty_and_unrelated_html(self):
        self.assertEqual(parse_products('<h2>Access denied</h2>', STORES['trendyol']), [])

    def test_external_link_rejected(self):
        html = HTML.replace('/marka/klavye-p-123?campaign=1', 'https://example.com/x')
        self.assertIsNone(parse_products(html, STORES['trendyol'])[0].url)

    def test_turkish_prices(self):
        for text, expected in [('1.234,56 TL', '1234.56'), ('₺ 99,9', '99.90'),
                               ('1.234', '1234.00'), ('0 TL', '0.00'),
                               ('1\u00a0299,90 TL', '1299.90')]:
            with self.subTest(text=text):
                self.assertEqual(parse_price(text), expected)

    def test_ambiguous_or_invalid_prices(self):
        for text in [None, '', '100 TL 200 TL', 'Sepette 100 TL', '-10 TL', '1,2,3', '10 USD']:
            with self.subTest(text=text):
                self.assertIsNone(parse_price(text))

    def test_query_encoding_and_pagination(self):
        for store in STORES.values():
            parameters = parse_qs(urlsplit(search_url(store, 'şarj & usb+c', 2)).query)
            self.assertEqual(parameters['q'], ['şarj & usb+c'])
            self.assertEqual(parameters[store.page_parameter], ['2'])


class SavingTests(unittest.TestCase):
    def test_json_alignment_and_unicode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'nested' / 'products.json'
            products = parse_products(HTML, STORES['trendyol'])
            save_result(path, 'Türkçe', SearchResult(products, 1, ['2. sayfa hatası']))
            data = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(data['query'], 'Türkçe')
            self.assertEqual(data['prices'][1], None)
            self.assertEqual(len(data['products']), len(data['names']))
            self.assertEqual(data['errors'], ['2. sayfa hatası'])
            self.assertEqual(list(path.parent.glob('*.tmp')), [])

    def test_failed_replace_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'products.json'
            path.write_text('existing', encoding='utf-8')
            with patch('main.os.replace', side_effect=OSError('disk error')):
                with self.assertRaises(OSError):
                    save_result(path, 'test', SearchResult())
            self.assertEqual(path.read_text(encoding='utf-8'), 'existing')
            self.assertEqual(list(path.parent.glob('*.tmp')), [])


class ScrapingTests(unittest.IsolatedAsyncioTestCase):
    def make_browser(self):
        page = MagicMock()
        page.goto = AsyncMock(return_value=MagicMock(status=200))
        page.content = AsyncMock(return_value=HTML)
        page.locator.return_value.first.wait_for = AsyncMock()
        context = MagicMock()
        context.new_page = AsyncMock(return_value=page)
        context.close = AsyncMock()
        browser = MagicMock()
        browser.new_context = AsyncMock(return_value=context)
        return browser, context, page

    async def test_retry_and_deduplication_across_pages(self):
        browser, context, page = self.make_browser()
        page.goto.side_effect = [PlaywrightError('timeout'), MagicMock(status=200), MagicMock(status=200)]
        with patch('main.asyncio.sleep', new_callable=AsyncMock):
            result = await scrape_store(browser, STORES['trendyol'], 'x', 2, 100, 1)
        self.assertEqual(result.pages_completed, 2)
        self.assertEqual(result.errors, [])
        self.assertEqual(len(result.products), 3)
        self.assertEqual(page.goto.await_count, 3)
        context.close.assert_awaited_once()

    async def test_http_failure_keeps_later_success(self):
        browser, context, page = self.make_browser()
        page.goto.side_effect = [MagicMock(status=403), MagicMock(status=200)]
        with self.assertLogs('main', level='WARNING'):
            result = await scrape_store(browser, STORES['trendyol'], 'x', 2, 100, 0)
        self.assertEqual(result.pages_completed, 1)
        self.assertEqual(len(result.errors), 1)
        self.assertTrue(result.products)
        context.close.assert_awaited_once()

    async def test_context_closed_on_unexpected_error(self):
        browser, context, page = self.make_browser()
        page.content.side_effect = ValueError('unexpected')
        with self.assertRaises(ValueError):
            await scrape_store(browser, STORES['trendyol'], 'x', 1, 100, 0)
        context.close.assert_awaited_once()

    async def test_store_failure_does_not_lose_other_result(self):
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(store='all', query='x', pages=1, timeout=100,
                                      retries=0, output_dir=Path(directory), show_browser=False)
            browser = MagicMock(close=AsyncMock())
            playwright = MagicMock()
            playwright.chromium.launch = AsyncMock(return_value=browser)
            manager = MagicMock()
            manager.__aenter__ = AsyncMock(return_value=playwright)
            manager.__aexit__ = AsyncMock(return_value=False)
            result = SearchResult([Product('Ürün', '10 TL', '10.00', None)], 1)
            with patch('main.async_playwright', return_value=manager), \
                 patch('main.scrape_store', new_callable=AsyncMock, side_effect=[RuntimeError('failure'), result]), \
                 patch('builtins.print'), self.assertLogs('main', level='ERROR'):
                self.assertEqual(await run(args), 1)
            self.assertTrue((Path(directory) / 'trendyol_products.json').exists())
            browser.close.assert_awaited_once()

    async def test_no_products_preserves_previous_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'trendyol_products.json'
            path.write_text('previous', encoding='utf-8')
            args = argparse.Namespace(store='trendyol', query='x', pages=1, timeout=100,
                                      retries=0, output_dir=Path(directory), show_browser=False)
            playwright = MagicMock()
            playwright.chromium.launch = AsyncMock(return_value=MagicMock(close=AsyncMock()))
            manager = MagicMock()
            manager.__aenter__ = AsyncMock(return_value=playwright)
            manager.__aexit__ = AsyncMock(return_value=False)
            with patch('main.async_playwright', return_value=manager), \
                 patch('main.scrape_store', new_callable=AsyncMock, return_value=SearchResult()), \
                 self.assertLogs('main', level='ERROR'):
                self.assertEqual(await run(args), 1)
            self.assertEqual(path.read_text(encoding='utf-8'), 'previous')

    async def test_save_failure_does_not_skip_other_store(self):
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(store='all', query='x', pages=1, timeout=100,
                                      retries=0, output_dir=Path(directory), show_browser=False)
            playwright = MagicMock()
            playwright.chromium.launch = AsyncMock(return_value=MagicMock(close=AsyncMock()))
            manager = MagicMock()
            manager.__aenter__ = AsyncMock(return_value=playwright)
            manager.__aexit__ = AsyncMock(return_value=False)
            result = SearchResult([Product('Ürün', '10 TL', '10.00', None)], 1)
            saved = []

            def save(path, query, data):
                if path.name.startswith('hepsiburada'):
                    raise OSError('write failure')
                saved.append(path.name)

            with patch('main.async_playwright', return_value=manager), \
                 patch('main.scrape_store', new_callable=AsyncMock, return_value=result), \
                 patch('main.save_result', side_effect=save), patch('builtins.print'), \
                 self.assertLogs('main', level='ERROR'):
                self.assertEqual(await run(args), 1)
            self.assertEqual(saved, ['trendyol_products.json'])


if __name__ == '__main__':
    unittest.main()
