# 🚀 LexProtect Otonom B2B Müşteri Kazanım & Satış Pipeline'ı

Bu proje, **LexProtect.io**'nun 360° dijital itibar koruma, TÜBİTAK/eIDAS zaman damgalı delillendirme ve otomatik içerik kaldırma (takedown) yeteneklerini satabilmek için geliştirilmiş otonom bir B2B soğuk e-posta (cold outreach) satış otomasyonudur.

Sistem, internet genelindeki marka ihlali yaşayan potansiyel müşterileri otomatik bulur, yetkililerin e-postalarını zenginleştirir, kişiselleştirilmiş cold email'ler gönderir, gelen yanıtları izleyerek niyet analizi yapar ve olumlu geri dönüşleri size doğrudan bildirim e-postasıyla iletir. Tüm süreç **Google Sheets** veya yerel **CSV** üzerinden canlı olarak takip edilebilir.

---

## 🛠️ Teknoloji Yığını (Stack)

- **Dil:** Python 3.x
- **Veri Deposu:** Google Sheets API & Yerel CSV (`leads.csv`)
- **Yapay Zeka:** OpenAI API (`gpt-4o` & `gpt-4o-mini` modelleri)
- **Arama Motoru:** Perplexity API (Gerçek zamanlı itibar ihlali tespiti)
- **E-posta Zenginleştirme:** Apollo.io API / Hunter.io API
- **E-posta Gönderim Sağlayıcıları:** Gmail API (Merkezi OAuth Sistemi) veya Resend API

---

## 📂 Dosya Yapısı

```
Projeler/LexProtect_Mailing/
├── README.md                 ← Bu kullanım rehberi
├── .env.example              ← Ortam değişkenleri şablonu
├── sheet_manager.py          ← Google Sheets & CSV veri senkronizasyonu
├── lead_finder.py            ← Otonom itibar ihlali tarayıcı ve e-posta bulucu
├── outreach_manager.py       ← OpenAI ile kişiselleştirilmiş mail üretici ve gönderici
├── inbox_monitor.py          ← Gelen yanıtların izlenmesi, LLM analizi ve mail bildirimi
└── run_daily_outreach.py     ← Günlük ana orkestratör script
```

---

## ⚙️ Kurulum & Çalıştırma

### 1. Şifreleri ve Ortam Değişkenlerini Tanımlama

Projeyi yerelinizde veya Railway üzerinde çalıştırabilmek için öncelikle `.env` dosyasını yapılandırın:

- Dizin içerisindeki `.env.example` dosyasını kopyalayarak `.env` oluşturun.
- Gerekli API anahtarlarını girin (OpenAI, Apollo, Resend veya Gmail API Client ID).
- Eğer merkezi şifre yönetim sistemini kullanıyorsanız, `/sifre-bagla` komutuyla veya `sifre-yonetici` skill'i üzerinden `master.env` şifrelerini bu projeye bağlayabilirsiniz:
  ```powershell
  python ../../_skills/sifre-yonetici/scripts/env_manager.py generate Projeler/LexProtect_Mailing
  ```

### 2. Google Sheets Entegrasyonu (Opsiyonel)

Erişimi tarayıcınız üzerinden canlı izleyebilmek için:
- Bir Google Sheet oluşturun ve tarayıcı linkindeki Sayfa ID'sini (URL'de `/d/SAYFA_IDSI/edit` kısmını) `.env` içindeki `GOOGLE_SHEET_ID` kısmına yazın.
- Tablonun ilk satırını başlıklarla otomatik doldurmak için projeyi bir kez çalıştırmanız yeterlidir.
- *Eğer Google Sheet ID girilmezse, sistem otomatik olarak yerel `leads.csv` dosyasını veritabanı olarak kullanır ve hatasız çalışır.*

### 3. Çalıştırma Komutları

#### 🧪 A. Simülasyon / Test Modu (Dry-Run - Önerilen!)
Gerçek e-posta göndermeden ve ücretli API'lerinizi harcamadan tüm akışı mock verilerle test etmek, OpenAI'ın ürettiği e-posta taslaklarını incelemek için:
```powershell
python Projeler/LexProtect_Mailing/run_daily_outreach.py --dry-run
```
Bu modda üretilen tüm e-postalar `leads.csv` veya Google Sheet'e `Draft` statüsünde kaydedilir.

#### 🚀 B. Uçtan Uca Gerçek Gönderim Modu
Sistemi gerçek zamanlı çalıştırıp e-postaları göndermek için:
```powershell
python Projeler/LexProtect_Mailing/run_daily_outreach.py --limit 3
```
*Not: `--limit` değeri her gün taranacak maksimum yeni şirket sayısını belirtir.*

#### 📥 C. Sadece Gelen Yanıtları Tarama Modu
Mailing kampanyasından gelen yanıtları sorgulamak ve niyet analizi yapıp olumlu dönüşleri bildirmek için:
```powershell
python Projeler/LexProtect_Mailing/run_daily_outreach.py --check-replies
```

---

## 📊 Süreç ve Durum Takibi

Veritabanında (`leads.csv` / Google Sheet) bulunan `Outreach_Status` sütunundaki statüler sistem tarafından otomatik yönetilir:

- `Pending` veya Boş: Yeni bulunan veya henüz e-posta atılmamış lead'ler.
- `Sent`: E-postanın başarıyla gönderildiği anlamına gelir.
- `Failed (Hata Nedeni)`: Gönderim sırasında hata oluştuğunu gösterir.
- `Draft`: Dry-run (simülasyon) modunda oluşturulan e-posta kopyası.
- `Replied (Positive)`: **[KRİTİK]** Müşterinin e-postaya olumlu/ilgili cevap verdiğini belirtir. Bu durumda tarafınıza anlık bilgilendirme e-postası atılır.
- `Replied (Negative)`: Müşterinin e-postaya olumsuz yanıt verdiğini belirtir.
- `Replied (Auto-Reply)`: Ofis dışı/otomatik yanıt alan e-postaları gösterir.
