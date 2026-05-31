import logging
import random
import string
import os
import threading
from flask import Flask
from supabase import create_client, Client
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, 
    ContextTypes, CallbackQueryHandler, ConversationHandler
)

# --- 1. AYARLAR ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YONETICI_ID = os.getenv("YONETICI_ID")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Durumlar
AD, DAIRE, KAT_BLOK, SIKAYET_DETAY = range(4)

# --- 2. YARDIMCI FONKSİYONLAR ---
def takip_kodu_uret():
    return f"#SB-{''.join(random.choices(string.digits, k=4))}"

async def upload_photo_to_supabase(file_id, context):
    try:
        file = await context.bot.get_file(file_id)
        file_bytes = await file.download_as_bytearray()
        file_name = f"sikayet_{file_id}.jpg"
        
        # Supabase Storage'a yükle
        supabase.storage.from_("sikayet-fotograflari").upload(
            path=file_name, 
            file=bytes(file_bytes),
            file_options={"content-type": "image/jpeg"}
        )
        return supabase.storage.from_("sikayet-fotograflari").get_public_url(file_name)
    except Exception as e:
        print(f"Fotoğraf yükleme hatası: {e}")
        return None

# --- 3. BOT AKIŞI ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    res = supabase.table("sakinler").select("*").eq("telegram_id", str(chat_id)).execute()
    if res.data:
        await update.message.reply_text("Hoş geldiniz! Şikayet kategorinizi seçin:", reply_markup=kategori_klavyesi())
        return SIKAYET_DETAY
    await update.message.reply_text("Adınızı ve Soyadınızı girin:")
    return AD

async def get_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['ad_soyad'] = update.message.text
    await update.message.reply_text("Daire Numaranızı yazın:")
    return DAIRE

async def get_daire(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['daire_no'] = update.message.text
    await update.message.reply_text("Dairenizin bulunduğu Kat ve Blok bilgisini girin (Örn: 5. Kat, A Blok):")
    return KAT_BLOK

async def get_kat_blok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kat_blok = update.message.text
    chat_id = update.message.chat_id
    # Veritabanına tüm bilgileri birlikte kaydet
    supabase.table("sakinler").insert({
        "telegram_id": str(chat_id),
        "ad_soyad": context.user_data['ad_soyad'],
        "daire_no": context.user_data['daire_no'],
        "kat_blok": kat_blok
    }).execute()
    await update.message.reply_text("✅ Kaydınız tamamlandı! Kategori seçin:", reply_markup=kategori_klavyesi())
    return SIKAYET_DETAY

def kategori_klavyesi():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛗 Asansör", callback_data="Asansör"), InlineKeyboardButton("🧹 Temizlik", callback_data="Temizlik")],
        [InlineKeyboardButton("💡 Aydınlatma", callback_data="Aydınlatma"), InlineKeyboardButton("📦 Diğer", callback_data="Diğer")]
    ])

async def kategori_secimi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['kategori'] = query.data
    context.user_data['fotograf_url'] = None
    await query.edit_message_text(f"Seçilen: {query.data}. Lütfen bir fotoğraf gönderin veya şikayetinizi yazın.")
    return SIKAYET_DETAY

async def handle_sikayet_detay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        url = await upload_photo_to_supabase(update.message.photo[-1].file_id, context)
        context.user_data['fotograf_url'] = url
        await update.message.reply_text("Fotoğraf alındı! Şimdi şikayet detayınızı yazın.")
        return SIKAYET_DETAY
    
    # Şikayeti Kaydet
    aciklama = update.message.text
    kategori = context.user_data.get('kategori', 'Diğer')
    foto_url = context.user_data.get('fotograf_url')
    
    sakin_res = supabase.table("sakinler").select("*").eq("telegram_id", str(update.message.chat_id)).execute()
    sakin = sakin_res.data[0]
    kod = takip_kodu_uret()
    
    supabase.table("sikayetler").insert({
        "sakin_id": int(sakin['telegram_id']),
        "ad_soyad": sakin['ad_soyad'],
        "daire_no": sakin['daire_no'],
        "kategori": kategori,
        "aciklama": aciklama,
        "fotograf_url": foto_url,
        "takip_kodu": kod,
        "durum": "Beklemede"
    }).execute()
    
    await update.message.reply_text(f"Şikayetiniz alındı! Takip kodunuz: {kod}")
    
    # Yöneticiye Bildirim
    # Yöneticiye Bildirim (İkonlu Şık Versiyon)
    msg = (f"🔔 **YENİ ŞİKAYET KAYDI**\n\n"
           f"🆔 **Takip Kodu:** `{kod}`\n"
           f"👤 **Sakin:** {sakin['ad_soyad']}\n"
           f"🏠 **Daire:** {sakin['daire_no']}\n"
           f"📂 **Kategori:** {kategori}\n"
           f"📝 **Açıklama:** {aciklama}")
    if foto_url:
        await context.bot.send_photo(chat_id=YONETICI_ID, photo=foto_url, caption=msg)
    else:
        await context.bot.send_message(chat_id=YONETICI_ID, text=msg)
    return ConversationHandler.END

# --- 4. SERVİSLER ---
flask_app = Flask(__name__)
@flask_app.route('/')
def index(): return "Bot Aktif"

if __name__ == '__main__':
    threading.Thread(target=lambda: flask_app.run(host="0.0.0.0", port=8080), daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            AD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_ad)],
            DAIRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_daire)],
            SIKAYET_DETAY: [
                MessageHandler(filters.PHOTO, handle_sikayet_detay),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_sikayet_detay)
            ]
        },
        fallbacks=[CommandHandler('start', start)]
    )
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(kategori_secimi, pattern="^(Asansör|Aydınlatma|Temizlik|Gürültü|Diğer)$"))
    app.run_polling()
