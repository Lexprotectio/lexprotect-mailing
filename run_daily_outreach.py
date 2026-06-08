import os
import sys
import argparse
from datetime import datetime
from dotenv import load_dotenv

# Modül yollarını ayarlayalım
_current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(_current_dir)

from sheet_manager import SheetManager
from lead_finder import LeadFinder
from outreach_manager import OutreachManager
from inbox_monitor import InboxMonitor

def main():
    parser = argparse.ArgumentParser(description="LexProtect Otonom Outreach Pipeline")
    parser.add_argument('--limit', type=int, default=3, help="Bugün taranacak yeni lead sayısı limiti")
    parser.add_argument('--dry-run', action='store_true', help="E-posta göndermeden ve aramaları mocklayarak simülasyon modunda çalıştırır")
    parser.add_argument('--check-replies', action='store_true', help="Sadece gelen e-posta yanıtlarını kontrol eder")
    
    args = parser.parse_args()
    
    load_dotenv(os.path.join(_current_dir, ".env"))
    
    print("==============================================================================")
    print(f"LexProtect Otonom Satis Pipeline Baslatildi: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if args.dry_run:
        print("[SIMULASYON MODU - DRY RUN] Gercek e-posta gonderimi ve ucretli API'ler tetiklenmez.")
    print("==============================================================================\n")
    
    # 1. Sheet Manager Başlatma
    sheet_manager = SheetManager()
    
    # 2. Yanıt İzleme (Gmail) - Sadece --check-replies veya normal akışta çalışır
    if args.check_replies:
        monitor = InboxMonitor(sheet_manager)
        monitor.check_gmail_replies()
        print("\n✅ Yanıt taraması tamamlandı.")
        return
        
    print("📥 ADIM 1: Gelen Yanıtların Kontrol Edilmesi...")
    monitor = InboxMonitor(sheet_manager)
    if not args.dry_run:
        monitor.check_gmail_replies()
    else:
        print("🧪 Simülasyon: Gelen kutusu yanıt taraması simüle edildi (atlandı).")
    
    # 3. Yeni Potansiyel Müşterileri Arama & E-posta Zenginleştirme
    print("\n🔍 ADIM 2: İtibar İhlalleri Yaşayan Yeni Şirketlerin Aranması...")
    finder = LeadFinder()
    
    if args.dry_run:
        # Dry-run modunda api anahtarları olmasa bile test geçmesi için mock veriler alalım
        new_leads = finder.find_reputation_issues(limit=args.limit)
        # E-posta zenginleştirmeyi mocklayalım
        for lead in new_leads:
            lead["Email"] = f"contact@{lead['Website']}"
            lead["Name"] = f"{lead['Company']} Karar Vericisi"
            lead["Outreach_Status"] = "Pending"
            lead["Outreach_Date"] = ""
            lead["Personalized_Message"] = ""
    else:
        new_leads = finder.get_daily_leads(limit=args.limit) or []
        test_exists = any(l.get("Email", "").strip().lower() == "av.akaratas@gmail.com" for l in new_leads)
        if not test_exists:
            new_leads.append({
                "Email": "av.akaratas@gmail.com",
                "Name": "Av. Akarataş",
                "Company": "Akarataş Hukuk Bürosu",
                "Website": "akaratashukuk.com",
                "Violation_Type": "Marka İtibar İhlali",
                "Violation_Detail": "Google Haritalar üzerinde büronuzun ismiyle oluşturulmuş sahte/yanıltıcı olumsuz yorumlar tespit edilmiş ve dijital itibarınızın zedelendiği gözlemlenmiştir.",
                "Outreach_Status": "Pending",
                "Outreach_Date": "",
                "Personalized_Message": ""
            })
        
    if new_leads:
        print(f"✅ Toplam {len(new_leads)} yeni potansiyel müşteri tespit edildi.")
        sheet_manager.add_new_leads(new_leads)
    else:
        print("ℹ️ Bugün yeni lead bulunamadı veya taranamadı.")

    # 4. E-posta Outreach Gönderimi
    print("\n✉️ ADIM 3: Cold-Outreach E-postalarının Hazırlanması ve Gönderimi...")
    outreach_manager = OutreachManager()
    
    # Güncel tabloyu oku
    all_leads = sheet_manager.read_leads()
    pending_leads = [l for l in all_leads if l.get("Outreach_Status", "").strip() in ["Pending", ""]]
    
    if not pending_leads:
        print("ℹ️ Gönderilmeyi bekleyen 'Pending' durumunda e-posta bulunmuyor.")
        print("\n==============================================================================")
        print("🎉 LexProtect Otonom Pipeline Başarıyla Tamamlandı!")
        print("==============================================================================")
        return
        
    print(f"📊 Toplam {len(pending_leads)} adet e-posta gönderime hazır bekliyor.")
    
    daily_limit = int(os.environ.get("OUTREACH_LIMIT", 50))
    sent_count = 0
    failed_count = 0
    draft_count = 0
    
    for lead in pending_leads:
        if sent_count >= daily_limit:
            print(f"⚠️ Günlük gönderim limitine ulaşıldı ({daily_limit}). Kalanlar sonraki çalışmada gönderilecek.")
            break
            
        email = lead.get("Email")
        name = lead.get("Name")
        company = lead.get("Company")
        website = lead.get("Website")
        violation_type = lead.get("Violation_Type")
        violation_detail = lead.get("Violation_Detail")
        row_idx = lead.get("row_idx")
        
        print(f"\n📧 Hazırlanıyor: {company} ({email}) - İhlal: {violation_type}...")
        
        # E-posta içeriği üret
        subject, body_html = outreach_manager.generate_personalized_email(
            name, company, website, violation_type, violation_detail
        )
        
        if args.dry_run:
            # Simülasyonda gönderme, sadece durum güncelle
            draft_count += 1
            print(f"🧪 [Draft] Konu: {subject}")
            print(f"🧪 [Draft] Alıcı: {email}")
            sheet_manager.update_lead_status(
                row_idx, 
                "Draft", 
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                f"[DRAFT SUBJECT]: {subject}\\n\\n[DRAFT BODY]: {body_html[:200]}..."
            )
        else:
            # Gerçek gönderim
            success, msg_id = outreach_manager.send_email(email, subject, body_html)
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if success:
                sent_count += 1
                sheet_manager.update_lead_status(row_idx, "Sent", date_str, body_html)
            else:
                failed_count += 1
                sheet_manager.update_lead_status(row_idx, f"Failed ({msg_id[:40]})", date_str, body_html)
                
    # Rapor
    print("\n==============================================================================")
    print("📊 KAMPANYA ÖZET RAPORU:")
    print(f"   Bulunan Yeni Şirketler : {len(new_leads)}")
    print(f"   Gönderilen E-postalar  : {sent_count}")
    print(f"   Başarısız Gönderimler  : {failed_count}")
    print(f"   Oluşturulan Taslaklar  : {draft_count}")
    print("==============================================================================")
    print("🎉 LexProtect Otonom Pipeline Başarıyla Tamamlandı!")
    print("==============================================================================\n")

if __name__ == "__main__":
    main()
