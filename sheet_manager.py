import os
import csv
import sys
from datetime import datetime
from dotenv import load_dotenv

# Antigravity kök dizinini bularak merkezi google_auth.py modülünü ekleyelim
_current_dir = os.path.dirname(os.path.abspath(__file__))
_antigravity_root = os.path.abspath(os.path.join(_current_dir, "..", ".."))
sys.path.insert(0, os.path.join(_antigravity_root, "_knowledge", "credentials", "oauth"))

try:
    from google_auth import get_sheets_service
except ImportError:
    get_sheets_service = None

# Sütun Başlıkları
HEADERS = [
    "Email", "Name", "Company", "Website", "Violation_Type", 
    "Violation_Detail", "Outreach_Status", "Outreach_Date", "Personalized_Message"
]

class SheetManager:
    def __init__(self, sheet_id=None, sheet_name="Sheet1", local_csv_name="leads.csv"):
        load_dotenv(os.path.join(_current_dir, ".env"))
        
        self.sheet_id = sheet_id or os.environ.get("GOOGLE_SHEET_ID")
        self.sheet_name = sheet_name or os.environ.get("GOOGLE_SHEET_NAME", "Sheet1")
        self.local_csv_path = os.path.join(_current_dir, local_csv_name)
        
        # Google Sheet ID boşlukları temizlenmiş olarak kontrol edilir
        if self.sheet_id and "<" in self.sheet_id:
            self.sheet_id = None
            
        self.use_sheets = False
        self.service = None
        
        if self.sheet_id and get_sheets_service:
            try:
                # GMAIL_OUTREACH_ACCOUNT değerini oku, varsayılan 'outreach'
                account = os.environ.get("GMAIL_OUTREACH_ACCOUNT", "outreach")
                self.service = get_sheets_service(account)
                self.use_sheets = True
                print(f"📊 Google Sheets API Entegrasyonu Aktif (Hesap: {account}, Sheet ID: {self.sheet_id})")
                self._initialize_sheets()
            except Exception as e:
                print(f"⚠️ Google Sheets bağlantı hatası: {e}. Yerel CSV moduna geçiliyor.")
                self.use_sheets = False
                
        if not self.use_sheets:
            print(f"📄 Yerel CSV Dosya Modu Aktif (Dosya: {self.local_csv_path})")
            self._initialize_local_csv()

    def _initialize_sheets(self):
        """Eğer sayfa boşsa başlıkları ekler."""
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range=f"{self.sheet_name}!A1:I1"
            ).execute()
            rows = result.get('values', [])
            if not rows:
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.sheet_id,
                    range=f"{self.sheet_name}!A1",
                    valueInputOption="USER_ENTERED",
                    body={"values": [HEADERS]}
                ).execute()
                print("✅ Google Sheets başlıkları oluşturuldu.")
        except Exception as e:
            print(f"⚠️ Sayfa başlıkları doğrulanırken hata oluştu: {e}")

    def _initialize_local_csv(self):
        """Yerel CSV yoksa başlıkları ekleyerek oluşturur."""
        if not os.path.exists(self.local_csv_path):
            with open(self.local_csv_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(HEADERS)
            print(f"✅ Yerel CSV dosyası oluşturuldu: {self.local_csv_path}")

    def read_leads(self):
        """Tüm lead'leri okur ve liste halinde döndürür."""
        if self.use_sheets:
            try:
                result = self.service.spreadsheets().values().get(
                    spreadsheetId=self.sheet_id,
                    range=f"{self.sheet_name}!A1:Z1000"
                ).execute()
                values = result.get('values', [])
                if len(values) <= 1:
                    return []
                
                headers = values[0]
                # Sütun isimlerini normalize et
                headers = [h.strip() for h in headers]
                
                leads = []
                # 1. satır başlık olduğu için 1-index tabanlı 2. satırdan (yani idx=1) başlarız
                for idx, row in enumerate(values[1:], start=1):
                    # Satırı başlık sayısına tamamla
                    while len(row) < len(headers):
                        row.append("")
                    lead = {headers[i]: row[i] for i in range(len(headers))}
                    # Google Sheets üzerinde güncelleme yapabilmek için row_idx değerini sakla
                    lead['row_idx'] = idx + 1 # 1-based index (Header = 1, ilk data = 2)
                    leads.append(lead)
                return leads
            except Exception as e:
                print(f"⚠️ Google Sheets okunurken hata oluştu: {e}. CSV'ye geçiliyor.")
                self.use_sheets = False
                self._initialize_local_csv()
                
        # CSV modunda oku
        leads = []
        with open(self.local_csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader):
                lead = dict(row)
                lead['row_idx'] = idx  # CSV için 0-based veri satırı indexi
                leads.append(lead)
        return leads

    def add_new_leads(self, leads_list):
        """Yeni lead listesini ekler. leads_list, dict listesidir."""
        if not leads_list:
            return
            
        new_rows = []
        for lead in leads_list:
            row = [lead.get(col, "") for col in HEADERS]
            new_rows.append(row)
            
        if self.use_sheets:
            try:
                self.service.spreadsheets().values().append(
                    spreadsheetId=self.sheet_id,
                    range=f"{self.sheet_name}!A:I",
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body={"values": new_rows}
                ).execute()
                print(f"✅ Google Sheets'e {len(leads_list)} yeni lead eklendi.")
                return
            except Exception as e:
                print(f"⚠️ Google Sheets'e ekleme hatası: {e}. CSV modu deneniyor.")
                
        # CSV'ye ekle
        with open(self.local_csv_path, 'a', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(new_rows)
        print(f"✅ Yerel CSV'ye {len(leads_list)} yeni lead eklendi.")

    def update_lead_status(self, row_idx, status, date_str, message_body):
        """E-posta gönderim durumunu satır numarasına göre günceller."""
        if self.use_sheets:
            try:
                # Durum (Outreach_Status): G sütunu (7. sütun, A=1, B=2, C=3, D=4, E=5, F=6, G=7, H=8, I=9)
                # Tarih (Outreach_Date): H sütunu (8. sütun)
                # Mesaj (Personalized_Message): I sütunu (9. sütun)
                range_to_update = f"{self.sheet_name}!G{row_idx}:I{row_idx}"
                body = {
                    "values": [[status, date_str, message_body]]
                }
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.sheet_id,
                    range=range_to_update,
                    valueInputOption="USER_ENTERED",
                    body=body
                ).execute()
                return
            except Exception as e:
                print(f"⚠️ Google Sheets güncelleme hatası: {e}. CSV fallback uygulanıyor.")

        # CSV Güncellemesi
        temp_csv = self.local_csv_path + ".tmp"
        with open(self.local_csv_path, 'r', encoding='utf-8') as f_read:
            reader = csv.DictReader(f_read)
            fieldnames = reader.fieldnames
            rows = list(reader)
            
        for idx, row in enumerate(rows):
            if idx == row_idx:
                row['Outreach_Status'] = status
                row['Outreach_Date'] = date_str
                row['Personalized_Message'] = message_body.replace('\n', '\\n')
                
        with open(temp_csv, 'w', encoding='utf-8', newline='') as f_write:
            writer = csv.DictWriter(f_write, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            
        os.replace(temp_csv, self.local_csv_path)

    def update_lead_reply(self, email, reply_status, reply_text):
        """E-posta adresine göre lead satırını bulur ve yanıt durumunu günceller."""
        leads = self.read_leads()
        found = False
        
        for lead in leads:
            if lead.get('Email', '').strip().lower() == email.strip().lower():
                row_idx = lead['row_idx']
                # Eğer Sheets modundaysak row_idx doğrudan satır nosudur
                # CSV modundaysak row_idx sıfır tabanlı liste indexidir
                self.update_lead_status(
                    row_idx, 
                    reply_status, 
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                    f"[GELEN YANIT]: {reply_text}"
                )
                print(f"📝 {email} için yanıt durumu güncellendi: {reply_status}")
                found = True
                break
        
        if not found:
            print(f"⚠️ Yanıt durum güncellemesi başarısız: {email} listemizde bulunamadı.")

if __name__ == "__main__":
    # Test kodları
    print("Testing SheetManager...")
    manager = SheetManager()
    leads = manager.read_leads()
    print(f"Okunan lead sayısı: {len(leads)}")
