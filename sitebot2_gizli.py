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
    try:
        file = await context.bot.get_file(file_id)
        # Bytes olarak indir
        file_bytes = await file.download_as_bytearray()
        file_name = f"sikayet_{file_id}.jpg"
        
        # Supabase'e yükle (file_options kısmını sadeleştirdik)
        # Bucket adının "sikayet-fotograflari" olduğundan %100 emin ol
        res = supabase.storage.from_("sikayet-fotograflari").upload(
            path=file_name, 
            file=bytes(file_bytes),
            file_options={"content-type": "image/jpeg"}
        )
        
        # URL al
        url_res = supabase.storage.from_("sikayet-fotograflari").get_public_url(file_name)
        return url_res
    except Exception as e:
        print(f"SUPABASE YÜKLEME HATASI: {e}")
        return None # Hata durumunda None dön ki kod patlamasın

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

# --- ŞİKAYET EKLEME FONKSİYONU ---
async def handle_sikayet_detay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Fotoğraf kontrolü
    if update.message.photo:
        url = await upload_photo_to_supabase(update.message.photo[-1].file_id, context)
        if url:
            context.user_data['fotograf_url'] = url
            await update.message.reply_text("Fotoğraf başarıyla yüklendi! Şimdi şikayet detayınızı yazın.")
        else:
            await update.message.reply_text("Fotoğraf yüklenemedi, yine de devam edebilirsiniz.")
        return SIKAYET_DETAY
    
    # Metin geldiğinde şikayeti bitir
    aciklama = update.message.text
    kategori = context.user_data.get('kategori', 'Diğer')
    foto_url = context.user_data.get('fotograf_url')
    
    # Kullanıcıyı bul
    res = supabase.table("sakinler").select("*").eq("telegram_id", str(update.message.chat_id)).execute()
    sakin = res.data[0]
    
    # VERİTABANI İNSERT (bigint hatasını engellemek için int dönüşümü!)
    supabase.table("sikayetler").insert({
        "sakin_id": int(sakin['telegram_id']),  # <--- Burası int olmalı
        "ad_soyad": sakin['ad_soyad'],
        "daire_no": sakin['daire_no'],
        "kat_blok": sakin.get('kat_blok', ''),
        "kategori": kategori,
        "aciklama": aciklama,
        "fotograf_url": foto_url,
        "takip_kodu": takip_kodu_uret(),
        "durum": "Beklemede"
    }).execute()
    
    await update.message.reply_text("Şikayetiniz oluşturuldu!")
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
