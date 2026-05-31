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

async def upload_photo_to_supabase(file_id, context):
    try:
        file = await context.bot.get_file(file_id)
        file_bytes = await file.download_as_bytearray()
        file_name = f"sikayet_{file_id}.jpg"
        supabase.storage.from_("sikayet-fotograflari").upload(path=file_name, file=bytes(file_bytes), file_options={"content-type": "image/jpeg"})
        return supabase.storage.from_("sikayet-fotograflari").get_public_url(file_name)
    except: return None

def kategori_klavyesi():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛗 Asansör", callback_data="Asansör"), InlineKeyboardButton("🧹 Temizlik", callback_data="Temizlik")],
        [InlineKeyboardButton("💡 Aydınlatma", callback_data="Aydınlatma"), InlineKeyboardButton("📦 Diğer", callback_data="Diğer")]
    ])

# --- BOT AKIŞI (CONVERSATION) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    if str(chat_id) == str(YONETICI_ID):
        await update.message.reply_text("👮‍♂️ Yönetici paneline hoş geldiniz. /panel yazın.")
        return ConversationHandler.END
    res = supabase.table("sakinler").select("*").eq("telegram_id", str(chat_id)).execute()
    if res.data:
        await update.message.reply_text("👋 Hoş geldiniz! Kategori seçin:", reply_markup=kategori_klavyesi())
        return SIKAYET_DETAY
    await update.message.reply_text("🏠 Premium Residence'a hoş geldiniz. Adınızı ve Soyadınızı girin:")
    return AD

async def get_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['ad_soyad'] = update.message.text
    await update.message.reply_text("🔢 Daire Numaranızı yazın:")
    return DAIRE

async def get_daire(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['daire_no'] = update.message.text
    await update.message.reply_text("🏢 Kat ve Blok bilginizi girin:")
    return KAT_BLOK

async def get_kat_blok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    supabase.table("sakinler").insert({
        "telegram_id": str(update.message.chat_id), "ad_soyad": context.user_data['ad_soyad'],
        "daire_no": context.user_data['daire_no'], "kat_blok": update.message.text
    }).execute()
    await update.message.reply_text("✅ Kayıt tamam! Kategori seçin:", reply_markup=kategori_klavyesi())
    return SIKAYET_DETAY

async def kategori_secimi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['kategori'] = query.data
    await query.edit_message_text(f"📝 Seçilen: {query.data}. Detay yazın veya fotoğraf gönderin.")
    return SIKAYET_DETAY

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

# --- YÖNETİCİ PANELİ ---
async def panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # 1. BUTON: LİSTEYE DÖN (Düzeltildi)
    if query.data == "liste_yeni":
        # Manuel olarak listeyi tekrar tetikliyoruz
        # Liste fonksiyonunu doğrudan çağırmak yerine callback verisini simüle ediyoruz
        # Ancak en garantisi fonksiyonun kendisini çağırmak:
        return await yonetici_panel(update, context)

    # 2. LİSTELERİ GÖRÜNTÜLEME
    if query.data.startswith("liste_"):
        if query.data == "liste_menu": return await yonetici_panel(update, context)
        
        d_map = {"liste_yeni": "Beklemede", "liste_inceleme": "İnceleniyor"}
        durum = d_map.get(query.data)
        items = supabase.table("sikayetler").select("*").eq("durum", durum).execute().data
        
        kb = [[InlineKeyboardButton(f"{s['takip_kodu']} | {s['ad_soyad']}", callback_data=f"detay_{s['takip_kodu']}")] for s in items]
        kb.append([InlineKeyboardButton("⬅️ Ana Menü", callback_data="liste_menu")])
        
        await query.edit_message_text(f"📊 {durum} Şikayetler:", reply_markup=InlineKeyboardMarkup(kb))

    # 3. DETAYLAR
    elif query.data.startswith("detay_"):
        kod = query.data.split("_")[1]
        s = supabase.table("sikayetler").select("*").eq("takip_kodu", kod).execute().data[0]
        txt = f"📋 **{kod}**\n👤 {s['ad_soyad']}\n🏠 {s['daire_no']}\n📝 {s['aciklama']}\n🟢 {s['durum']}"
        # BURADAKİ BUTONDA 'liste_yeni' VERİSİ GİDİYOR
        kb = [[InlineKeyboardButton("⏳ İncelemeye Al", callback_data=f"durum_inceleme_{kod}"), 
               InlineKeyboardButton("✅ Çözüldü", callback_data=f"durum_cozuldu_{kod}")], 
              [InlineKeyboardButton("⬅️ Listeye Dön", callback_data="liste_yeni")]]
        
        try: await query.message.delete()
        except: pass
        
        if s.get('fotograf_url'): 
            await context.bot.send_photo(query.message.chat_id, s['fotograf_url'], caption=txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        else: 
            await context.bot.send_message(query.message.chat_id, txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    # 4. DURUM GÜNCELLEME
    elif query.data.startswith("durum_"):
        _, yeni, kod = query.data.split("_")
        d = "İnceleniyor" if yeni == "inceleme" else "Çözüldü"
        supabase.table("sikayetler").update({"durum": d}).eq("takip_kodu", kod).execute()
        s_id = supabase.table("sikayetler").select("sakin_id").eq("takip_kodu", kod).execute().data[0]['sakin_id']
        await context.bot.send_message(int(s_id), f"🔔 Şikayetiniz ({kod}) durumu: {d} oldu.")
        await yonetici_panel(update, context)

async def takip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: await update.message.reply_text("Kod girin: /takip #SB-XXXX")
    else:
        res = supabase.table("sikayetler").select("*").eq("takip_kodu", context.args[0]).execute()
        if res.data: await update.message.reply_text(f"🔎 Durum: {res.data[0]['durum']}")
        else: await update.message.reply_text("❌ Kod geçersiz.")

# --- BAŞLATICI ---
if __name__ == '__main__':
    threading.Thread(target=lambda: Flask(__name__).run(host="0.0.0.0", port=8080), daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    conv = ConversationHandler(entry_points=[CommandHandler('start', start)], 
        states={AD:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_ad)], DAIRE:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_daire)], 
                KAT_BLOK:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_kat_blok)], SIKAYET_DETAY:[MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, handle_sikayet_detay)]},
        fallbacks=[CommandHandler('start', start)])
    app.add_handler(conv)
    app.add_handler(CommandHandler('panel', yonetici_panel))
    app.add_handler(CommandHandler('takip', takip))
    app.add_handler(CallbackQueryHandler(kategori_secimi, pattern="^(Asansör|Aydınlatma|Temizlik|Diğer)$"))
    app.add_handler(CallbackQueryHandler(panel_callback))
    app.run_polling(drop_pending_updates=True)
