import os
import sys
import json
import base64
import requests
from email.mime.text import MIMEText
from datetime import datetime
from dotenv import load_dotenv

# Antigravity kök dizinini bularak merkezi google_auth.py modülünü ekleyelim
_current_dir = os.path.dirname(os.path.abspath(__file__))
_antigravity_root = os.path.abspath(os.path.join(_current_dir, "..", ".."))
sys.path.insert(0, os.path.join(_antigravity_root, "_knowledge", "credentials", "oauth"))

try:
    from google_auth import get_gmail_service
except ImportError:
    get_gmail_service = None

class OutreachManager:
    def __init__(self):
        load_dotenv(os.path.join(_current_dir, ".env"))
        self.openai_key = os.environ.get("OPENAI_API_KEY")
        self.provider = os.environ.get("EMAIL_PROVIDER", "resend").lower()
        
        # Resend ayarları
        self.resend_key = os.environ.get("RESEND_API_KEY")
        self.resend_from = os.environ.get("RESEND_FROM_EMAIL", "LexProtect Outreach <outreach@yourdomain.com>")
        
        # Gmail ayarları
        self.gmail_account = os.environ.get("GMAIL_OUTREACH_ACCOUNT", "outreach")
        
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
                        elif k == "RESEND_API_KEY" and not self.resend_key:
                            self.resend_key = v
                        elif k == "RESEND_FROM_EMAIL" and not self.resend_from:
                            self.resend_from = v

        # Check for placeholders
        if self.openai_key and "<" in self.openai_key: self.openai_key = None
        if self.resend_key and "<" in self.resend_key: self.resend_key = None
        if self.resend_from and "<" in self.resend_from: self.resend_from = "LexProtect Outreach <outreach@yourdomain.com>"

    def generate_personalized_email(self, name, company, website, violation_type, violation_detail):
        """
        OpenAI Chat Completions API'sini kullanarak LexProtect.io'nun gercek urun metniyle
        kisisellestirilmis cold email uretir.
        """
        if not self.openai_key:
            subject = f"{company} — Dijital Itibarinizi Koruma Hakkinda"
            body = f"""<html><body style="font-family: Arial, sans-serif; color: #222; max-width: 600px; margin: 0 auto;">
<p>Sayın {name},</p>
<p>Markanız hakkında internette söylenen her şeyi tek bir panelden görebilseydiniz? Peki ya itibarınıza zarar veren içerikleri tespit edip, yönetip ve kaldırma süreçlerini tek bir platform üzerinden yürütebilseydiniz?</p>
<p><strong>LexProtect.io</strong>, dijital itibarınızı ölçmenizi, riskleri erkenden tespit etmenizi ve marka itibarınızı tek bir platform üzerinden yönetmenizi sağlayan yapay zeka destekli <strong>360° Dijital İtibar Koruma Platformu</strong>dur.</p>
<p>Yaptığımız ön analizde <strong>{company}</strong> hakkında <strong>{violation_type}</strong> kapsamında bazı dikkat gerektiren bulgular tespit ettik: <em>{violation_detail}</em></p>
<p>LexProtect ile;</p>
<ul>
<li>✓ Haber siteleri, sosyal medya, forum ve şikayet platformlarını otomatik tarayın</li>
<li>✓ TÜBİTAK/eIDAS onaylı zaman damgasıyla hukuki delil oluşturun</li>
<li>✓ İçerik kaldırma bildirimlerini tek platform üzerinden yönetin</li>
</ul>
<p>💡 Siz uyurken markanızı izler. Siz büyümeye odaklanırken tehditleri analiz eder.</p>
<p><strong>#LEXPROTECT</strong> kodu ile ücretsiz itibar analizinizden yararlanın → <a href="https://www.lexprotect.io">www.lexprotect.io</a></p>
<p>Saygılarımızla,<br><strong>LexProtect.io Ekibi</strong></p>
</body></html>"""
            return subject, body

        # OpenAI ile kisisellestirilmis e-posta uretimi
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openai_key}",
            "Content-Type": "application/json"
        }

        LEXPROTECT_BRAND = (
            "LexProtect.io — Yapay Zeka Destekli 360 Derece Dijital Itibar Koruma Platformu\n\n"
            "Deger Onerisi: 'Markaniz hakkinda internette soylenen her seyi tek bir panelden "
            "gorebilseydiniz? Peki ya itibariniza zarar veren icerikleri tespit edip, yonetip "
            "ve kaldirma sureclerini tek bir platform uzerinden yurutebilseydiniz?'\n\n"
            "Temel ozellikler:\n"
            "- Haber siteleri, sosyal medya, forum ve sikayet platformlarini 7/24 otomatik tarama\n"
            "- Yapay zeka destekli risk analizi ve onceliklendirme\n"
            "- TUBITAK/eIDAS onayli yasal zaman damgasiyla delil olusturma (mahkemede gecerli)\n"
            "- Icerik kaldirma bildirimlerini ve hukuki surecleri platform uzerinden yonetme\n"
            "- Gercek zamanli uyari sistemi\n\n"
            "Slogan: 'Siz uyurken markanizi izler. Siz buyumeye odaklanirken tehditleri analiz eder.'\n"
            "CTA: #LEXPROTECT kodu ile ucretsiz itibar analizi — www.lexprotect.io"
        )

        system_instruction = (
            "Sen LexProtect.io'nun kıdemli B2B satış danışmanısın. "
            "Görevin: dijital itibar sorunu yaşayan bir KOBİ yöneticisine, "
            "profesyonel, samimi, yapay zeka kokmayan ve KISA (max 180 kelime) bir cold email yazmak. "
            "Şirketin yaşadığı sorunu empatiyle kabul et, LexProtect'in bu sorunu nasıl çözdüğünü net anlat. "
            "Abartma ve uydurma istatistik kullanma. Sonda #LEXPROTECT ile ücretsiz analiz CTA'sı bırak. "
            "E-postayı Türkçe yaz, HTML formatında döndür.\n\n"
            f"Ürün Bilgisi:\n{LEXPROTECT_BRAND}\n\n"
            "Yanıtı JSON formatında döndür. Alanlar: 'subject' (e-posta başlığı), 'body' (HTML gövde)."
        )

        user_prompt = (
            f"Alıcı:\n"
            f"- Kişi: {name}\n"
            f"- Şirket: {company}\n"
            f"- Website: {website}\n"
            f"- Sorun Türü: {violation_type}\n"
            f"- Sorun Detayı: {violation_detail}\n\n"
            f"Bu şirketin yaşadığı sorunu merkeze alarak LexProtect'i çözüm olarak sunan kişiselleştirilmiş bir e-posta yaz."
        )

        payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.4
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=25)
            if response.status_code == 200:
                result = response.json()
                content = json.loads(result['choices'][0]['message']['content'])
                return content.get('subject'), content.get('body')
        except Exception as e:
            print(f"  OpenAI e-posta hatasi: {e}")

        # Hata durumunda default sablon

        return f"{company} Dijital İtibar ve Marka Güvenliği Hkk.", f"Sayın {name}, markanızla ilgili tespit ettiğimiz {violation_type} ihlalleri ({violation_detail}) ve LexProtect.io çözümleri hakkında detaylı bilgi almak için lütfen yanıt veriniz."

    def send_email(self, to_email, subject, body_html):
        """EMAIL_PROVIDER seçimine göre e-postayı gönderir."""
        if self.provider == "gmail" and get_gmail_service:
            return self._send_via_gmail(to_email, subject, body_html)
        else:
            return self._send_via_resend(to_email, subject, body_html)

    def _send_via_gmail(self, to_email, subject, body_html):
        """Gmail API (merkezi oauth yetkilisi) üzerinden mail gönderir."""
        try:
            service = get_gmail_service(self.gmail_account)
            message = MIMEText(body_html, 'html')
            message['to'] = to_email
            message['subject'] = subject
            # Base64 urlsafe encoding
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            sent_message = service.users().messages().send(
                userId='me',
                body={'raw': raw}
            ).execute()
            print(f"  ✉️ Gmail ile e-posta gönderildi. Mesaj ID: {sent_message['id']}")
            return True, sent_message['id']
        except Exception as e:
            print(f"  ❌ Gmail gönderim hatası: {e}")
            return False, str(e)

    def _send_via_resend(self, to_email, subject, body_html):
        """Resend Email API üzerinden mail gönderir."""
        if not self.resend_key:
            return False, "Resend API anahtarı (.env veya master.env içinde) eksik."
            
        url = "https://api.resend.com/emails"
        headers = {
            "Authorization": f"Bearer {self.resend_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "from": self.resend_from,
            "to": [to_email],
            "subject": subject,
            "html": body_html
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            if response.status_code in [200, 201]:
                res_data = response.json()
                print(f"  ✉️ Resend ile e-posta gönderildi. Mesaj ID: {res_data.get('id')}")
                return True, res_data.get('id')
            else:
                err_msg = response.text
                print(f"  ❌ Resend gönderim hatası (HTTP {response.status_code}): {err_msg}")
                return False, err_msg
        except Exception as e:
            print(f"  ❌ Resend gönderim hatası: {e}")
            return False, str(e)

if __name__ == "__main__":
    print("Testing OutreachManager...")
    manager = OutreachManager()
    subject, body = manager.generate_personalized_email(
        "Ahmet Bey", "Hedef A.Ş.", "hedefas.com", 
        "Sahte Ürün Satışı", "Trendyol üzerinde yetkisiz kişiler firmanızın adıyla replika parfüm satıyor."
    )
    print(f"Subject: {subject}")
    print(f"Body snippet: {body[:300]}...")
