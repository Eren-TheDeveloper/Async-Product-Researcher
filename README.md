<div align="center">

# ⚡ Async Price Research

### Tek arama. İki pazaryeri. Düzenli fiyat verisi.

Hepsiburada ve Trendyol ürünlerini eşzamanlı araştıran,<br>
sonuçları ürün bağlantıları ve fiyatlarıyla JSON'a kaydeden Python aracı.

![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Playwright](https://img.shields.io/badge/Browser-Playwright-2EAD33?style=for-the-badge)
![Asyncio](https://img.shields.io/badge/Async-asyncio-7C3AED?style=for-the-badge)
![JSON](https://img.shields.io/badge/Output-JSON-F59E0B?style=for-the-badge)

[Özellikler](#ozellikler) · [Kurulum](#kurulum) · [Kullanım](#kullanim) · [Örnek çıktı](#ornek-cikti) · [Testler](#testler)

</div>

---

Bir ürün adı yazın; araç iki mağazanın arama sayfalarını ayrı tarayıcı bağlamlarında toplasın. Ürün adları ve fiyatlar aynı karttan eşleştirilir, tekrar eden kayıtlar ayıklanır ve her mağaza için ayrı bir sonuç dosyası hazırlanır.

> **Mevcut durum:** Son canlı denemede iki mağaza da HTTP 403 döndürdü. Hata yönetimi doğrulandı; güncel mağaza sayfalarından başarılı veri toplama bu ortamda doğrulanamadı. Birim testleri gerçek sitelere bağlanmadan çalışır.

<a id="ozellikler"></a>

## ✨ Neler sunuyor?

| Özellik | Nasıl yardımcı olur? |
| --- | --- |
| ⚡ Eşzamanlı arama | Hepsiburada ve Trendyol işlemleri `asyncio` ile birlikte yürütülür. |
| 🎯 Kart bazında eşleştirme | Eksik fiyat, sonraki ürünün fiyatıyla eşleşmez; `null` olarak saklanır. |
| 🔁 Yeniden deneme | Başarısız sayfalar, ayarlanabilir tekrar sayısı ve bekleme aralığıyla yeniden istenir. |
| 🧩 Bağımsız mağaza sonuçları | Bir mağazanın hatası, diğerinden alınan sonuçların kaydedilmesini engellemez. |
| 🧹 Tekilleştirme | Aynı bağlantı, ürün adı ve fiyata sahip kayıtlar bir kez tutulur. |
| 💾 Güvenli dosya kaydı | Geçici dosya tamamlandıktan sonra sonuç dosyası atomik olarak değiştirilir. |
| 💰 Sayısal fiyat alanı | `1.299,90 TL` gibi tutarlar, hesaplamaya uygun `"1299.90"` metnine dönüştürülür. |
| 🛠️ Esnek komut satırı | Mağaza, sayfa sayısı, zaman aşımı ve çıktı klasörü seçilebilir. |

<a id="kurulum"></a>

## 🚀 Kurulum

**Gereksinimler:** Python 3.10 veya üzeri, internet bağlantısı ve Playwright Chromium tarayıcısı.

Proje klasöründe aşağıdaki komutları çalıştırın. Örnekler Windows PowerShell içindir; ortamı etkinleştirmek gerekmez.

```powershell
# 1. Sanal ortamı oluşturun
python -m venv .venv

# 2. Python bağımlılıklarını yükleyin
.\.venv\Scripts\python -m pip install -r requirements.txt

# 3. Chromium tarayıcısını yükleyin
.\.venv\Scripts\python -m playwright install chromium

# 4. İlk aramanızı başlatın
.\.venv\Scripts\python main.py "mekanik klavye" --pages 3
```

<details>
<summary><strong>macOS / Linux kurulumu</strong></summary>

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m playwright install chromium
./.venv/bin/python main.py "mekanik klavye" --pages 3
```

Chromium sistem kütüphaneleri eksik olan Linux ortamlarında Playwright'ın `install --with-deps chromium` komutu gerekebilir.

</details>

<a id="kullanim"></a>

## 🔎 Kullanım

Aşağıdaki örneklerde `python`, bağımlılıkları kurduğunuz ortamın yorumlayıcısını temsil eder. Yukarıdaki Windows kurulumuyla devam ediyorsanız yerine `.\.venv\Scripts\python` yazın.

```powershell
# Her iki mağazada arama yapın
python main.py "kablosuz kulaklık"

# Yalnızca Trendyol'da 2 sayfa tarayın
python main.py "usb & type-c" --store trendyol --pages 2

# Sonuçları ayrı bir klasöre kaydedin
python main.py "oyuncu monitörü" --output-dir results

# Tarayıcıyı görünür açın ve bekleme sınırını değiştirin
python main.py "klavye" --show-browser --timeout 15000 --retries 1

# Ürün adını etkileşimli olarak girin
python main.py

# Tüm seçenekleri görüntüleyin
python main.py --help
```

### Komut satırı seçenekleri

| Seçenek | Varsayılan | Açıklama |
| --- | --- | --- |
| `query` | Etkileşimli giriş | Aranacak ürün adı; boş bırakılamaz. |
| `--store` | `all` | `all`, `hepsiburada` veya `trendyol`. |
| `--pages` | `5` | Her mağaza için istenecek sayfa sayısı; en az `1`. |
| `--timeout` | `30000` | Her gezinme/bekleme işleminin zaman aşımı, milisaniye cinsinden. |
| `--retries` | `2` | İlk denemeden sonraki tekrar sayısı; `0` tekrarları kapatır. |
| `--output-dir` | `.` | Sonuçların yazılacağı klasör. |
| `--show-browser` | Kapalı | Tarayıcı penceresini görünür açar. |

<a id="ornek-cikti"></a>

## 📦 Çıktı nasıl görünür?

Her mağaza için ayrı dosya oluşturulur:

```text
results/
├── hepsiburada_products.json
└── trendyol_products.json
```

Aşağıdaki JSON, çıktı biçimini gösteren **temsili bir örnektir**; canlı fiyat verisi içermez.

```json
{
  "query": "mekanik klavye",
  "fetched_at": "2026-11-18T12:00:00+00:00",
  "currency": "TRY",
  "pages_completed": 1,
  "errors": [],
  "products": [
    {
      "name": "Örnek Mekanik Klavye",
      "price": "1.299,90 TL",
      "price_value": "1299.90",
      "url": null
    }
  ],
  "names": ["Örnek Mekanik Klavye"],
  "prices": ["1.299,90 TL"]
}
```

- **`products`**: Ürün adı, görünen fiyat, sayısal fiyat metni ve bulunabilen ürün bağlantısı.
- **`price_value`**: Ondalık hassasiyetini koruyan metin. Eksik veya belirsiz fiyatlar için `null`.
- **`fetched_at`**: Kaydın oluşturulduğu UTC zamanı.
- **`pages_completed` / `errors`**: Başarılı sayfa sayısı ve alınamayan sayfalara ilişkin hata bilgisi.
- **`names` / `prices`**: Eski okuyucularla uyumluluk için aynı sırada tutulan listeler. Eksik fiyat `null` olur.

Konsolda her mağazadan toplanan ürünler arasındaki en düşük ayrıştırılabilir fiyat da gösterilir.

### Hata olduğunda

Başarısız sayfalar sonrasında diğer sayfalar denenmeye devam edilir. Kısmi sonuçlar hata bilgileriyle birlikte kaydedilir. Bir mağazadan hiç ürün alınamazsa o mağazanın mevcut çıktı dosyası korunur. Başarılı veya kısmi kayıt aynı adlı eski dosyanın yerini alır.

| Çıkış kodu | Anlamı |
| --- | --- |
| `0` | Seçilen mağazaların sonuçları hatasız kaydedildi. |
| `1` | Hata oluştu, kısmi sonuç alındı veya ürün bulunamadı. |
| `130` | İşlem kullanıcı tarafından durduruldu. |

<a id="testler"></a>

## 🧪 Testler

```powershell
python -m unittest discover -s tests -v
```

Testler; ürün–fiyat eşleşmesini, Türkçe fiyat ayrıştırmayı, URL kodlamayı, tekilleştirmeyi, yeniden denemeyi, tarayıcı bağlamlarının kapatılmasını ve dosya hatalarında sonuçların korunmasını kapsar. Ek bir test paketi gerektirmez; uygulama bağımlılıklarının kurulu olması yeterlidir.

## 🗂️ Proje yapısı

```text
async_price_research/
├── main.py                     # Tarama, ayrıştırma ve komut satırı arayüzü
├── requirements.txt            # Python bağımlılıkları
├── tests/
│   └── test_main.py             # Ağ bağlantısı gerektirmeyen birim testleri
├── hepsiburada_products.json    # Önceden oluşturulmuş sonuç dosyası
├── trendyol_products.json       # Önceden oluşturulmuş sonuç dosyası
├── .gitignore
└── README.md
```

## 📌 Kullanım notları

- Mağazaların HTML yapıları değişebilir. Ürün seçicileri `main.py` içindeki `STORES` tanımından güncellenebilir.
- HTTP 403, CAPTCHA veya erişim engeli veri toplanmasını önleyebilir. `--show-browser` sayfadaki durumu incelemeye yardımcı olur; erişim engelini kaldırmaz.
- Gösterilen en düşük fiyat, yalnızca alınabilen sayfalardaki ürünler arasındadır. Aynı model eşleştirmesi veya kargo dahil toplam maliyet hesabı yapılmaz.
- Birden fazla tutar veya kampanya metni içeren fiyatlar güvenilir bir tek tutar olarak ayrıştırılamazsa `price_value` alanı `null` kalır.
- Depodaki mevcut JSON dosyaları eski biçimdedir; yeni şema ilk başarılı kayıtta yazılır. Eski Trendyol örneğinde ad ve fiyat sayıları farklı olduğundan bu listeler güvenilir biçimde eşleştirilemez.
