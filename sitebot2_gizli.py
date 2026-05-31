import logging
import random
import string
import os
import threading
import io
from flask import Flask, request, jsonify, render_template_string
from supabase import create_client, Client
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler

# --- AYARLAR ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YONETICI_ID = os.getenv("YONETICI_ID")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

AD, DAIRE = range(2)

# --- WEB FORMU ---
flask_app = Flask(__name__)
@flask_app.route('/')
def index():
    return "Bot Servisi Aktif"

def flask_calistir():
    flask_app.run(host="0.0.0.0", port=5000)

# --- TELEGRAM BOT MANTIĞI ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    
    # 1. Veritabanından kontrol et (Sütun: sakin_id)
    try:
        res = supabase.table("sakinler").select("*").eq("sakin_id", str(chat_id)).execute()
        
        if res.data and len(res.data) > 0:
            sakin = res.data[0]
            await update.message.reply_text(
                f"Tekrar hoş geldiniz, {sakin.get('ad_soyad')}!\n"
                "Premium Residence Yönetim Sistemi'ne eriştiniz. Lütfen şikayet kategorinizi seçin:",
                reply_markup=kategori_klavyesi()
            )
            return ConversationHandler.END
        else:
            await update.message.reply_text("Premium Residence Botuna Hoş Geldiniz.\nKayıt için Adınızı ve Soyadınızı giriniz:")
            return AD
    except Exception as e:
        print(f"Hata: {e}")
        await update.message.reply_text("Sistemde bir hata oluştu, lütfen daha sonra deneyin.")
        return ConversationHandler.END

async def get_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['ad_soyad'] = update.message.text
    await update.message.reply_text("Teşekkürler. Şimdi lütfen Daire Numaranızı yazınız (Örn: D:14):")
    return DAIRE

async def get_daire(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    ad_soyad = context.user_data.get('ad_soyad')
    daire_no = update.message.text

    try:
        supabase.table("sakinler").insert({
            "sakin_id": str(chat_id),
            "ad_soyad": ad_soyad,
            "daire_no": daire_no
        }).execute()
        
        await update.message.reply_text("Kaydınız oluşturuldu! Şimdi şikayet kategorinizi seçebilirsiniz:", reply_markup=kategori_klavyesi())
    except Exception as e:
        await update.message.reply_text("Kayıt sırasında hata oluştu: " + str(e))
    
    return ConversationHandler.END

def kategori_klavyesi():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Asansör 🛗", callback_data="Asansör"), InlineKeyboardButton("Temizlik 🧹", callback_data="Temizlik")],
        [InlineKeyboardButton("Diğer 🛑", callback_data="Diğer")]
    ])

async def kategori_secimi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['secilen_kategori'] = query.data
    await query.edit_message_text(f"Seçilen: {query.data}. Lütfen detay yazın veya fotoğraf gönderin.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Fotoğraf mı metin mi diye bak
    if update.message.photo:
        await update.message.reply_text("Fotoğraf alındı, sisteme işleniyor...")
        # Fotoğraf işleme kodun buraya...
    else:
        # Metin işleme kodun buraya...
        await update.message.reply_text("Şikayetiniz kaydedildi.")

if __name__ == '__main__':
    threading.Thread(target=flask_calistir, daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={AD: [MessageHandler(filters.TEXT, get_ad)], DAIRE: [MessageHandler(filters.TEXT, get_daire)]},
        fallbacks=[]
    )
    
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(kategori_secimi))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))
    
    app.run_polling()
