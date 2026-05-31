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

# --- AYARLAR ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
YONETICI_ID = os.getenv("YONETICI_ID")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
AD, DAIRE, KAT_BLOK, SIKAYET_DETAY = range(4)

# --- YARDIMCI ---
def takip_kodu_uret(): return f"#SB-{''.join(random.choices(string.digits, k=4))}"

# --- BOT AKIŞI ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    # Yönetici ise panele yönlendir
    if str(chat_id) == str(YONETICI_ID):
        return await yonetici_panel(update, context)
    
    res = supabase.table("sakinler").select("*").eq("telegram_id", str(chat_id)).execute()
    if res.data:
        await update.message.reply_text("👋 Tekrar hoş geldiniz! Şikayet kategorinizi seçin:", reply_markup=kategori_klavyesi())
        return SIKAYET_DETAY
    await update.message.reply_text("🏠 Premium Residence'a hoş geldiniz.\nLütfen Adınızı ve Soyadınızı girin:")
    return AD

async def get_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['ad_soyad'] = update.message.text
    await update.message.reply_text("🔢 Daire Numaranızı yazın:")
    return DAIRE

async def get_daire(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['daire_no'] = update.message.text
    await update.message.reply_text("🏢 Kat ve Blok bilginizi girin (Örn: 5. Kat, A Blok):")
    return KAT_BLOK

async def get_kat_blok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kat_blok = update.message.text
    supabase.table("sakinler").insert({
        "telegram_id": str(update.message.chat_id),
        "ad_soyad": context.user_data['ad_soyad'],
        "daire_no": context.user_data['daire_no'],
        "kat_blok": kat_blok
    }).execute()
    await update.message.reply_text("✅ Kaydınız tamamlandı! Kategori seçin:", reply_markup=kategori_klavyesi())
    return SIKAYET_DETAY

# --- YÖNETİCİ PANELİ ---
async def yonetici_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    yeni = supabase.table("sikayetler").select("*", count='exact').eq("durum", "Beklemede").execute().count
    inceleme = supabase.table("sikayetler").select("*", count='exact').eq("durum", "İnceleniyor").execute().count
    
    keyboard = [
        [InlineKeyboardButton(f"🆕 Yeni Gelenler ({yeni})", callback_data="liste_yeni")],
        [InlineKeyboardButton(f"⏳ İnceleniyor ({inceleme})", callback_data="liste_inceleme")],
        [InlineKeyboardButton("✅ Çözülenler", callback_data="liste_cozuldu")]
    ]
    if update.callback_query:
        await update.callback_query.edit_message_text("⚙️ **Yönetici Paneli**\nDurumu görüntülemek için seçin:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.message.reply_text("⚙️ **Yönetici Paneli**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("liste_"):
        durum_map = {"liste_yeni": "Beklemede", "liste_inceleme": "İnceleniyor", "liste_cozuldu": "Çözüldü"}
        durum = durum_map.get(query.data)
        sikayetler = supabase.table("sikayetler").select("*").eq("durum", durum).execute().data
        
        if not sikayetler:
            await query.edit_message_text("📭 Bu kategoride şikayet yok.")
            return
        
        text = f"📊 **{durum} Şikayetler:**\n\n"
        for s in sikayetler:
            text += f"🔹 {s['takip_kodu']} | {s['ad_soyad']} ({s['daire_no']})\n"
        await query.edit_message_text(text, parse_mode="Markdown")

# --- KATEGORİ & ŞİKAYET ---
def kategori_klavyesi():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛗 Asansör", callback_data="Asansör"), InlineKeyboardButton("🧹 Temizlik", callback_data="Temizlik")],
        [InlineKeyboardButton("💡 Aydınlatma", callback_data="Aydınlatma"), InlineKeyboardButton("📦 Diğer", callback_data="Diğer")]
    ])

async def kategori_secimi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['kategori'] = query.data
    await query.edit_message_text(f"📝 Seçilen: {query.data}. Lütfen detay yazın veya fotoğraf gönderin.")
    return SIKAYET_DETAY

async def handle_sikayet_detay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        # Fotoğrafı yükle (daha önce yazdığımız fonksiyonu buraya çağır)
        # ...
        await update.message.reply_text("📸 Fotoğraf alındı, şikayet detayını yazın:")
        return SIKAYET_DETAY
    
    # ... (Buraya daha önce yazdığımız veritabanı kayıt bloğunu ekle)
    
    await update.message.reply_text("✅ Şikayetiniz başarıyla alındı!")
    return ConversationHandler.END

# --- BAŞLATICI ---
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    # Handler'ları buraya ekle (conv_handler, callback_handler vs.)
    app.run_polling()
