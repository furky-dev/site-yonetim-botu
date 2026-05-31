import logging, random, string, os, threading
from flask import Flask
from supabase import create_client, Client
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, 
    ContextTypes, CallbackQueryHandler, ConversationHandler
)

# --- AYARLAR ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YONETICI_ID = os.getenv("YONETICI_ID")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
AD, DAIRE, KAT_BLOK, SIKAYET_DETAY = range(4)

# --- FONKSİYONLAR (Hata bu kısım aşağıda tanımlı olduğu için oluyordu) ---
def takip_kodu_uret(): return f"#SB-{''.join(random.choices(string.digits, k=4))}"

async def upload_photo_to_supabase(file_id, context):
    try:
        file = await context.bot.get_file(file_id)
        file_bytes = await file.download_as_bytearray()
        file_name = f"sikayet_{file_id}.jpg"
        supabase.storage.from_("sikayet-fotograflari").upload(path=file_name, file=bytes(file_bytes), file_options={"content-type": "image/jpeg"})
        return supabase.storage.from_("sikayet-fotograflari").get_public_url(file_name)
    except: return None

async def handle_sikayet_detay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        context.user_data['fotograf_url'] = await upload_photo_to_supabase(update.message.photo[-1].file_id, context)
        await update.message.reply_text("📸 Fotoğraf alındı! Şikayet detayını yazın:")
        return SIKAYET_DETAY
    
    aciklama, foto_url = update.message.text, context.user_data.get('fotograf_url')
    sakin = supabase.table("sakinler").select("*").eq("telegram_id", str(update.message.chat_id)).execute().data[0]
    kod = takip_kodu_uret()
    
    supabase.table("sikayetler").insert({
        "sakin_id": int(sakin['telegram_id']), "ad_soyad": sakin['ad_soyad'], "daire_no": sakin['daire_no'],
        "kat_blok": sakin.get('kat_blok', ''), "kategori": context.user_data['kategori'],
        "aciklama": aciklama, "fotograf_url": foto_url, "takip_kodu": kod, "durum": "Beklemede"
    }).execute()
    
    await update.message.reply_text(f"✅ Şikayetiniz alındı! Takip kodu: `{kod}`", parse_mode="Markdown")
    msg = f"🔔 **Yeni Şikayet**\nKod: `{kod}`\nSakin: {sakin['ad_soyad']}\nDetay: {aciklama}"
    if foto_url: await context.bot.send_photo(chat_id=YONETICI_ID, photo=foto_url, caption=msg, parse_mode="Markdown")
    else: await context.bot.send_message(chat_id=YONETICI_ID, text=msg, parse_mode="Markdown")
    return ConversationHandler.END

# (DİĞER FONKSİYONLAR: start, get_ad, get_daire, get_kat_blok, yonetici_panel, panel_callback, takip, kategori_secimi vs buraya gelecek)
# NOT: Hata vermemesi için bu fonksiyonların tamamını buraya eklemelisin.

if __name__ == '__main__':
    threading.Thread(target=lambda: Flask(__name__).run(host="0.0.0.0", port=8080), daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # ConversationHandler buraya gelmeli
    conv = ConversationHandler(entry_points=[CommandHandler('start', start)], 
        states={
            AD:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_ad)], 
            DAIRE:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_daire)], 
            KAT_BLOK:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_kat_blok)], 
            SIKAYET_DETAY:[MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, handle_sikayet_detay)]
        },
        fallbacks=[CommandHandler('start', start)])
    
    app.add_handler(conv)
    app.add_handler(CommandHandler('panel', yonetici_panel))
    app.add_handler(CommandHandler('takip', takip))
    app.add_handler(CallbackQueryHandler(kategori_secimi, pattern="^(Asansör|Aydınlatma|Temizlik|Diğer)$"))
    app.add_handler(CallbackQueryHandler(panel_callback))
    app.run_polling(drop_pending_updates=True)
