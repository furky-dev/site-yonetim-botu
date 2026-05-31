import logging
import random
import string
import os
import threading
import requests
from flask import Flask, request, jsonify, render_template_string
from supabase import create_client, Client
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler

# --- 1. AYARLAR ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YONETICI_ID = os.getenv("YONETICI_ID")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Durum Sabitleri
AD, DAIRE, SIKAYET_DETAY = range(3)

# --- 2. YARDIMCI FONKSİYONLAR ---
def takip_kodu_uret():
    return f"#SB-{''.join(random.choices(string.digits, k=4))}"

async def upload_photo_to_supabase(file_id, context):
    file = await context.bot.get_file(file_id)
    file_bytes = await file.download_as_bytearray()
    file_name = f"sikayet_{file_id}.jpg"
    
    # Supabase'e yükle
    supabase.storage.from_("sikayet-fotograflari").upload(
        path=file_name, file=bytes(file_bytes), file_options={"content-type": "image/jpeg"}
    )
    # Public URL al
    url_res = supabase.storage.from_("sikayet-fotograflari").get_public_url(file_name)
    return url_res

# --- 3. BOT FONKSİYONLARI ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    res = supabase.table("sakinler").select("*").eq("telegram_id", str(chat_id)).execute()
    
    if res.data:
        await update.message.reply_text("Hoş geldiniz! Şikayet kategorinizi seçin:", reply_markup=kategori_klavyesi())
        return SIKAYET_DETAY
    else:
        await update.message.reply_text("Premium Residence'a hoş geldiniz. Adınızı ve Soyadınızı girin:")
        return AD

async def get_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['ad_soyad'] = update.message.text
    await update.message.reply_text("Daire Numaranızı yazın (Örn: D:14):")
    return DAIRE

async def get_daire(update: Update, context: ContextTypes.DEFAULT_TYPE):
    daire = update.message.text
    chat_id = update.message.chat_id
    
    supabase.table("sakinler").insert({
        "telegram_id": str(chat_id),
        "ad_soyad": context.user_data['ad_soyad'],
        "daire_no": daire
    }).execute()
    
    await update.message.reply_text("Kaydınız tamamlandı! Kategori seçin:", reply_markup=kategori_klavyesi())
    return SIKAYET_DETAY

def kategori_klavyesi():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Asansör", callback_data="Asansör"), InlineKeyboardButton("Temizlik", callback_data="Temizlik")],
        [InlineKeyboardButton("Aydınlatma", callback_data="Aydınlatma"), InlineKeyboardButton("Diğer", callback_data="Diğer")]
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
    
    # Şikayeti tamamlama
    aciklama = update.message.text
    kategori = context.user_data.get('kategori')
    foto_url = context.user_data.get('fotograf_url')
    sakin = supabase.table("sakinler").select("*").eq("telegram_id", str(update.message.chat_id)).execute().data[0]
    
    kod = takip_kodu_uret()
    supabase.table("sikayetler").insert({
        "sakin_id": sakin['id'],
        "ad_soyad": sakin['ad_soyad'],
        "daire_no": sakin['daire_no'],
        "kategori": kategori,
        "aciklama": aciklama,
        "fotograf_url": foto_url,
        "takip_kodu": kod
    }).execute()
    
    await update.message.reply_text(f"Şikayetiniz alındı! Takip kodunuz: {kod}")
    
    # Yöneticiye Bildirim
    msg = f"🔔 Yeni Şikayet!\nKod: {kod}\nSakin: {sakin['ad_soyad']}\nKategori: {kategori}\nDetay: {aciklama}"
    if foto_url:
        await context.bot.send_photo(chat_id=YONETICI_ID, photo=foto_url, caption=msg)
    else:
        await context.bot.send_message(chat_id=YONETICI_ID, text=msg)
    return ConversationHandler.END

# --- WEB FORMU ---
flask_app = Flask(__name__)
@flask_app.route('/')
def index(): return "Bot Servisi Aktif"

def flask_calistir(): flask_app.run(host="0.0.0.0", port=8080)

if __name__ == '__main__':
    threading.Thread(target=flask_calistir, daemon=True).start()
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
        fallbacks=[]
    )
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(kategori_secimi, pattern="^(Asansör|Aydınlatma|Temizlik|Gürültü|Diğer)$"))
    
    print("🚀 Telegram botu aktif!")
    app.run_polling(drop_pending_updates=True)
