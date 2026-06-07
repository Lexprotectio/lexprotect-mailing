import os
import sys
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
from sheet_manager import SheetManager

# Antigravity kök dizinini bularak merkezi google_auth.py modülünü ekleyelim
_current_dir = os.path.dirname(os.path.abspath(__file__))
_antigravity_root = os.path.abspath(os.path.join(_current_dir, "..", ".."))
sys.path.insert(0, os.path.join(_antigravity_root, "_knowledge", "credentials", "oauth"))

try:
    from google_auth import get_gmail_service
except ImportError:
    get_gmail_service = None

class InboxMonitor:
    def __init__(self, sheet_manager=None):
        load_dotenv(os.path.join(_current_dir, ".env"))
        self.openai_key = os.environ.get("OPENAI_API_KEY")
        self.notification_email = os.environ.get("NOTIFICATION_EMAIL")
        self.gmail_account = os.environ.get("GMAIL_OUTREACH_ACCOUNT", "outreach")
        self.sheet_manager = sheet_manager or SheetManager()
        
        # master.env'den API anahtarlarını çekme (eğer .env'de yoksa)
        master_env_path = os.path.join(_antigravity_root, "_knowledge", "credentials", "master.env")
        if os.path.exists(master_env_path):
            with open(master_env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if '=' in line and not line.startswith('#'):
                        k, v = line.split('=', 1)
                        k, v = k.strip(), v.strip()
                        if k == "OPENAI_API_KEY" and not self.openai_key:
                            self.openai_key = v
                        elif k == "NOTIFICATION_EMAIL" and not self.notification_email:
                            self.notification_email = v

        if self.openai_key and "<" in self.openai_key: self.openai_key = None
        if self.notification_email and "<" in self.notification_email: self.notification_email = None

    def check_gmail_replies(self):
        """
        Gmail API üzerinden gönderim yapılmış olan aktif e-postaların
        gelen kutusundaki yanıtlarını kontrol eder.
        """
        if not get_gmail_service:
            print("⚠️ Gmail API modülü bulunamadı. Yanıt kontrolü atlanıyor.")
            return
            
        try:
            service = get_gmail_service(self.gmail_account)
        except Exception as e:
            print(f"⚠️ Gmail Service yetkilendirme hatası: {e}. Yanıt kontrolü atlanıyor.")
            return

        print("🔍 Gönderilen e-postalara gelen yanıtlar taranıyor...")
        leads = self.sheet_manager.read_leads()
        
        # Sadece gönderilmiş durumdaki lead'leri filtreleyelim (Sent)
        active_leads = [l for l in leads if l.get("Outreach_Status") == "Sent" and l.get("Email")]
        
        if not active_leads:
            print("ℹ️ Yanıtı taranacak 'Sent' durumunda aktif lead bulunamadı.")
            return
            
        for lead in active_leads:
            email = lead["Email"].strip()
            print(f"   📧 {email} adresinden gelen yanıtlar taranıyor...")
            
            # Gmail API üzerinden bu email adresinden gelen mesajları sorgulayalım
            query = f"from:{email}"
            try:
                results = service.users().messages().list(userId='me', q=query).execute()
                messages = results.get('messages', [])
                
                if not messages:
                    continue
                    
                # En son gelen mesajın içeriğini okuyalım
                latest_msg_id = messages[0]['id']
                msg_detail = service.users().messages().get(userId='me', id=latest_msg_id, format='full').execute()
                
                # Mesajın gövde metnini çekelim
                payload = msg_detail.get('payload', {})
                body = self._extract_body(payload)
                
                if not body:
                    continue
                
                # Gelen mailin tarihini doğrula (Outreach tarihinden sonra mı?)
                internal_date = int(msg_detail.get('internalDate', 0)) / 1000.0
                msg_time = datetime.fromtimestamp(internal_date)
                
                outreach_date_str = lead.get("Outreach_Date", "")
                if outreach_date_str:
                    try:
                        outreach_time = datetime.strptime(outreach_date_str, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        outreach_time = datetime.min
                else:
                    outreach_time = datetime.min
                    
                if msg_time > outreach_time:
                    print(f"      📥 Yeni yanıt alındı! Tarih: {msg_time}")
                    self.process_reply(lead, body)
                    
            except Exception as e:
                print(f"      ⚠️ Gelen kutusu sorgulama hatası ({email}): {e}")

    def _extract_body(self, payload):
        """Gmail mesaj gövdesini recursive olarak ayıklar."""
        body = ""
        if 'parts' in payload:
            for part in payload['parts']:
                body += self._extract_body(part)
        else:
            mime_type = payload.get('mimeType', '')
            if mime_type in ['text/plain', 'text/html']:
                data = payload.get('body', {}).get('data', '')
                if data:
                    body += base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        return body

    def process_reply(self, lead, reply_text):
        """Gelen yanıtın niyetini analiz eder, tablolarda günceller ve gerekirse mail ile bildirir."""
        email = lead["Email"]
        company = lead["Company"]
        name = lead["Name"]
        
        # 1. OpenAI ile Niyet Analizi
        reply_status = "Replied (Neutral)"
        summary = reply_text[:300]
        
        if self.openai_key:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.openai_key}",
                "Content-Type": "application/json"
            }
            system_prompt = (
                "Sana cold outreach e-postamıza gelen bir yanıt metni vereceğim. "
                "Bu yanıtı 3 kategoriden birine ayır:\n"
                "1. 'positive': Karşı taraf ilgileniyor, fiyat soruyor, toplantı/demo istiyor, daha fazla detay talep ediyor veya olumlu konuşuyor.\n"
                "2. 'negative': Karşı taraf ilgilenmiyor, listeden çıkmak istiyor (opt-out), yasal işlem tehdidi savuruyor veya sert şekilde reddediyor.\n"
                "3. 'auto': Ofis dışı yanıtı (Out of Office) veya otomatik sistem cevabı.\n"
                "4. 'neutral': Diğer durumlar.\n"
                "Yanıt olarak sadece şu kelimelerden birini dön: 'positive', 'negative', 'auto', 'neutral'. Ekstra metin ekleme."
            )
            payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Yanıt Metni:\n{reply_text}"}
                ],
                "temperature": 0.0
            }
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=10)
                if response.status_code == 200:
                    intent = response.json()['choices'][0]['message']['content'].strip().lower()
                    if "positive" in intent:
                        reply_status = "Replied (Positive)"
                    elif "negative" in intent:
                        reply_status = "Replied (Negative)"
                    elif "auto" in intent:
                        reply_status = "Replied (Auto-Reply)"
            except Exception as e:
                print(f"      ⚠️ Yanıt analizi hatası: {e}")

        # 2. Durumu Google Sheets/CSV üzerinde güncelle
        self.sheet_manager.update_lead_reply(email, reply_status, reply_text)
        
        # 3. Eğer olumlu ise e-posta bildirimi gönder
        if reply_status == "Replied (Positive)":
            print(f"🔥 OLUMLU YANIT! E-posta bildirimi hazırlanıyor...")
            self.send_notification_email(name, company, email, summary)

    def send_notification_email(self, name, company, email, reply_summary):
        """Olumlu lead yanıtlarında kullanıcıya bildirim maili atar."""
        if not self.notification_email:
            print("⚠️ Bildirim e-posta adresi (NOTIFICATION_EMAIL) tanımlı değil. Bildirim gönderilemedi.")
            return

        subject = f"🔔 [LexProtect Outreach] Yeni İlgili Müşteri: {company}"
        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
                <h2 style="color: #2e7d32; border-bottom: 2px solid #2e7d32; padding-bottom: 10px;">🎉 Yeni Olumlu Dönüş Alındı!</h2>
                <p>LexProtect cold-outreach kampanyanızdan bir olumlu dönüş aldınız. Detaylar aşağıdadır:</p>
                <table style="width: 100%; border-collapse: collapse; margin: 15px 0;">
                    <tr>
                        <td style="padding: 8px; font-weight: bold; width: 120px; border-bottom: 1px solid #eee;">Şirket:</td>
                        <td style="padding: 8px; border-bottom: 1px solid #eee;">{company}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; font-weight: bold; border-bottom: 1px solid #eee;">Kişi:</td>
                        <td style="padding: 8px; border-bottom: 1px solid #eee;">{name}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; font-weight: bold; border-bottom: 1px solid #eee;">E-posta:</td>
                        <td style="padding: 8px; border-bottom: 1px solid #eee;"><a href="mailto:{email}">{email}</a></td>
                    </tr>
                </table>
                <div style="background-color: #f9f9f9; border-left: 4px solid #2e7d32; padding: 15px; margin: 15px 0; font-style: italic;">
                    <strong>Gelen Cevap Özeti:</strong><br>
                    "{reply_summary}"
                </div>
                <p>Müşteriyle doğrudan iletişime geçmek için e-postayı yanıtlayabilirsiniz.</p>
                <hr style="border: 0; border-top: 1px solid #eee; margin-top: 20px;">
                <p style="font-size: 0.8em; color: #777; text-align: center;">Bu e-posta LexProtect Otonom Satış Pipeline'ı tarafından otomatik gönderilmiştir.</p>
            </div>
        </body>
        </html>
        """
        
        # Gönderimi yapmak için OutreachManager kütüphanesini kullanalım
        try:
            from outreach_manager import OutreachManager
            sender = OutreachManager()
            success, _ = sender.send_email(self.notification_email, subject, body_html)
            if success:
                print(f"✅ Bildirim e-postası başarıyla gönderildi: {self.notification_email}")
            else:
                print("❌ Bildirim e-postası gönderilemedi.")
        except Exception as e:
            print(f"⚠️ Bildirim e-postası gönderme aşamasında hata: {e}")

if __name__ == "__main__":
    print("Testing InboxMonitor...")
    monitor = InboxMonitor()
    # Mock data testi
    # monitor.process_reply({"Email": "test@demo.com", "Company": "Test Ltd", "Name": "Test Yetkili"}, "Lexprotect yazılımınız çok ilginç görünüyor, fiyat teklifini ve demo detaylarını iletebilir misiniz?")
    monitor.check_gmail_replies()
