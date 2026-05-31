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

# --- YARDIMCI FONKSİYONLAR ---
def takip_kodu_uret(): return f"#SB-{''.join(random.choices(string.digits, k=4))}"

def kategori_klavyesi():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛗 Asansör", callback_data="Asansör"), InlineKeyboardButton("🧹 Temizlik", callback_data="Temizlik")],
        [InlineKeyboardButton("💡 Aydınlatma", callback_data="Aydınlatma"), InlineKeyboardButton("📦 Diğer", callback_data="Diğer")]
    ])

async def upload_photo_to_supabase(file_id, context):
    try:
        file = await context.bot.get_file(file_id)
        file_bytes = await file.download_as_bytearray()
        file_name = f"sikayet_{file_id}.jpg"
        supabase.storage.from_("sikayet-fotograflari").upload(path=file_name, file=bytes(file_bytes), file_options={"content-type": "image/jpeg"})
        return supabase.storage.from_("sikayet-fotograflari").get_public_url(file_name)
    except: return None

# --- ANA MENÜ VE START ---
async def ana_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("📝 Şikayet Bildir", callback_data="sikayet_baslat")],
          [InlineKeyboardButton("📁 Şikayetlerim", callback_data="listem_sakin")]]
    reply_markup = InlineKeyboardMarkup(kb)
    if update.callback_query: await update.callback_query.edit_message_text("🏠 Ana Menü:", reply_markup=reply_markup)
    else: await update.message.reply_text("🏠 Premium Residence'a hoş geldiniz:", reply_markup=reply_markup)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    if str(chat_id) == str(YONETICI_ID):
        await update.message.reply_text("👮‍♂️ Yönetici panelindesiniz. /panel yazın.")
        return ConversationHandler.END
    res = supabase.table("sakinler").select("*").eq("telegram_id", str(chat_id)).execute()
    if res.data: return await ana_menu(update, context)
    await update.message.reply_text("🏠 Hoş geldiniz. Lütfen Adınızı ve Soyadınızı girin:")
    return AD

# --- CONVERSATION ---
async def get_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['ad_soyad'] = update.message.text
    await update.message.reply_text("🔢 Daire Numaranızı yazın:")
    return DAIRE

async def get_daire(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['daire_no'] = update.message.text
    await update.message.reply_text("🏢 Kat ve Blok bilginizi girin:")
    return KAT_BLOK

async def get_kat_blok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    supabase.table("sakinler").insert({"telegram_id": str(update.message.chat_id), "ad_soyad": context.user_data['ad_soyad'],
        "daire_no": context.user_data['daire_no'], "kat_blok": update.message.text}).execute()
    await update.message.reply_text("✅ Kayıt tamam!")
    return await ana_menu(update, context)

async def kategori_secimi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "sikayet_baslat":
        await query.edit_message_text("📝 Kategori seçin:", reply_markup=kategori_klavyesi())
        return SIKAYET_DETAY
    elif query.data == "listem_sakin":
        items = supabase.table("sikayetler").select("*").eq("sakin_id", update.callback_query.message.chat_id).execute().data
        txt = "📂 **Şikayetlerim:**\n\n" + "\n".join([f"{s['takip_kodu']} | {s['durum']}" for s in items]) if items else "Şikayetiniz bulunamadı."
        await query.edit_message_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Geri", callback_data="ana_menu")]]))
        return SIKAYET_DETAY
    elif query.data == "ana_menu": return await ana_menu(update, context)

async def handle_sikayet_detay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        context.user_data['fotograf_url'] = await upload_photo_to_supabase(update.message.photo[-1].file_id, context)
        await update.message.reply_text("📸 Fotoğraf alındı! Detay yazın:")
        return SIKAYET_DETAY
    aciklama, foto_url = update.message.text, context.user_data.get('fotograf_url')
    sakin = supabase.table("sakinler").select("*").eq("telegram_id", str(update.message.chat_id)).execute().data[0]
    kod = takip_kodu_uret()
    supabase.table("sikayetler").insert({"sakin_id": int(sakin['telegram_id']), "ad_soyad": sakin['ad_soyad'], "daire_no": sakin['daire_no'],
        "kat_blok": sakin.get('kat_blok', ''), "kategori": context.user_data.get('kategori', 'Diğer'), "aciklama": aciklama, 
        "fotograf_url": foto_url, "takip_kodu": kod, "durum": "Beklemede"}).execute()
    await update.message.reply_text(f"✅ Şikayet alındı! Takip kodu: `{kod}`", parse_mode="Markdown")
    return ConversationHandler.END

# --- YÖNETİCİ ---
async def yonetici_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    yeni = supabase.table("sikayetler").select("*", count='exact').eq("durum", "Beklemede").execute().count
    kb = [[InlineKeyboardButton(f"🆕 Yeni ({yeni})", callback_data="liste_yeni"), InlineKeyboardButton("⬅️ Kapat", callback_data="kapat")]]
    if update.callback_query: await update.callback_query.edit_message_text("⚙️ Yönetici:", reply_markup=InlineKeyboardMarkup(kb))
    else: await update.message.reply_text("⚙️ Yönetici:", reply_markup=InlineKeyboardMarkup(kb))

async def panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("liste_"):
        d = "Beklemede" if "yeni" in query.data else "İnceleniyor"
        items = supabase.table("sikayetler").select("*").eq("durum", d).execute().data
        kb = [[InlineKeyboardButton(f"{s['takip_kodu']}", callback_data=f"detay_{s['takip_kodu']}")] for s in items]
        await query.edit_message_text(f"📊 {d}:", reply_markup=InlineKeyboardMarkup(kb + [[InlineKeyboardButton("⬅️ Geri", callback_data="liste_menu")]]))
    elif query.data == "detay_menu": await yonetici_panel(update, context)
    # ... (Diğer detay ve durum işlemleri)

async def takip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: await update.message.reply_text("Kod girin: /takip #SB-XXXX")
    else:
        res = supabase.table("sikayetler").select("*").eq("takip_kodu", context.args[0]).execute()
        if res.data: await update.message.reply_text(f"🔎 {res.data[0]['durum']}")
        else: await update.message.reply_text("❌ Kod geçersiz.")

if __name__ == '__main__':
    threading.Thread(target=lambda: Flask(__name__).run(host="0.0.0.0", port=8080), daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    conv = ConversationHandler(entry_points=[CommandHandler('start', start)], 
        states={AD:[MessageHandler(filters.TEXT, get_ad)], DAIRE:[MessageHandler(filters.TEXT, get_daire)], 
                KAT_BLOK:[MessageHandler(filters.TEXT, get_kat_blok)], SIKAYET_DETAY:[MessageHandler(filters.PHOTO | filters.TEXT, handle_sikayet_detay)]},
        fallbacks=[CommandHandler('start', start)])
    app.add_handler(conv)
    app.add_handler(CommandHandler('panel', yonetici_panel))
    app.add_handler(CommandHandler('takip', takip))
    app.add_handler(CallbackQueryHandler(kategori_secimi))
    app.run_polling()
