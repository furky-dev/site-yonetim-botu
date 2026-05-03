

import logging
import random
import string
from supabase import create_client, Client
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler

# --- 1. AYARLAR ---
SUPABASE_URL = "SUPABASE_URL"
SUPABASE_KEY = "SUPABASE_KEY"
TELEGRAM_TOKEN ="TELEGRAM_TOKEN"
YONETICI_ID = "YONETICI_ID"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Durum Sabitleri
AD, DAIRE = range(2)

# --- 2. YARDIMCI FONKSİYONLAR ---
def takip_kodu_uret():
    return f"#SB-{''.join(random.choices(string.digits, k=4))}"

# --- 3. YÖNETİCİ PANELİ ---
async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Eğer bir butondan geliyorsa mesajı düzenle, komuttan geliyorsa yeni mesaj at
    user_id = str(update.effective_user.id)
    if user_id != YONETICI_ID:
        await update.effective_message.reply_text("Yetkisiz erişim.")
        return

    keyboard = [
        [InlineKeyboardButton("🆕 Yeni Şikayetler", callback_data="liste_Beklemede")],
        [InlineKeyboardButton("⚙️ Devam Edenler", callback_data="liste_İnceleniyor")],
        [InlineKeyboardButton("✅ Çözülenler (Arşiv)", callback_data="liste_Çözüldü")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "📊 **Yönetici Kontrol Paneli**\nBakmak istediğiniz klasmanı seçin:"

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

# --- 4. SAKİN AKIŞI ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sakin = supabase.table("sakinler").select("*").eq("telegram_id", user_id).execute()
    
    if not sakin.data:
        await update.message.reply_text("🏢 SiteBot Kayıt Sistemi\nLütfen Adınızı ve Soyadınızı yazın:")
        return AD
    
    keyboard = [
        [InlineKeyboardButton("Asansör 🛗", callback_data='Asansör'), InlineKeyboardButton("Aydınlatma 💡", callback_data='Aydınlatma')],
        [InlineKeyboardButton("Temizlik 🧹", callback_data='Temizlik'), InlineKeyboardButton("Gürültü 🔊", callback_data='Gürültü')],
        [InlineKeyboardButton("Diğer ✨", callback_data='Diğer')]
    ]
    await update.message.reply_text(f"Hoş geldiniz {sakin.data[0]['ad_soyad']}!\nKategori seçiniz:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

async def get_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['ad'] = update.message.text
    await update.message.reply_text("Daire numaranız:")
    return DAIRE

async def get_daire(update: Update, context: ContextTypes.DEFAULT_TYPE):
    supabase.table("sakinler").insert({"telegram_id": update.effective_user.id, "ad_soyad": context.user_data['ad'], "daire_no": update.message.text}).execute()
    await update.message.reply_text("Kayıt tamam! /start yazarak şikayet iletebilirsiniz.")
    return ConversationHandler.END

async def kategori_secimi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Sadece kategori butonlarını yakala
    if query.data in ['Asansör', 'Aydınlatma', 'Temizlik', 'Gürültü', 'Diğer']:
        context.user_data['secilen_kategori'] = query.data
        context.user_data['bekliyor_mu'] = True # Metin girişini aktif et
        await query.edit_message_text(text=f"📂 Kategori: {query.data}\nŞikayetinizi yazın:")

async def sikayet_kaydet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Eğer kullanıcı bir kategori seçmediyse metni görmezden gel (Panel karışıklığını önler)
    if not context.user_data.get('bekliyor_mu'):
        return

    user_id = update.effective_user.id
    kod = takip_kodu_uret()
    
    res = supabase.table("sakinler").select("*").eq("telegram_id", user_id).execute()
    sakin = res.data[0]
    
    supabase.table("sikayetler").insert({
        "sakin_id": user_id, 
        "kategori": context.user_data.get('secilen_kategori', 'Diğer'),
        "aciklama": update.message.text, 
        "takip_kodu": kod, 
        "durum": "beklemede"
    }).execute()

    context.user_data['bekliyor_mu'] = False # İşlem bitti
    await update.message.reply_text(f"✅ Şikayet iletildi. Kod: {kod}")
    
    admin_m = f"📩 **YENİ!**\n{sakin['ad_soyad']} ({sakin['daire_no']})\n{kod}: {update.message.text}"
    kb = [[InlineKeyboardButton("⚙️ İnceleniyor", callback_data=f"durum_incele_{kod}"),
           InlineKeyboardButton("✅ Çözüldü", callback_data=f"durum_cozuldu_{kod}")]]
    await context.bot.send_message(chat_id=YONETICI_ID, text=admin_m, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# --- 5. BUTON İŞLEMLERİ ---
async def buton_islem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("liste_"):
        durum_tipi = data.split("_")[1]
        res = supabase.table("sikayetler").select("*").ilike("durum", f"{durum_tipi}").execute()

        if not res.data:
            await query.edit_message_text(f"📭 '{durum_tipi}' klasmanında kayıt bulunmuyor.\n\n/panel ile dönebilirsiniz.")
            return

        mesaj = f"📂 **Klasman: {durum_tipi}**\n\n"
        keyboard = []
        for s in res.data:
            kod = s['takip_kodu']
            mesaj += f"🔸 {kod} | {s['kategori']}\n"
            keyboard.append([InlineKeyboardButton(f"Detay Gör: {kod}", callback_data=f"yonet_{kod}")])
        
        keyboard.append([InlineKeyboardButton("⬅️ Panele Dön", callback_data="panele_don")])
        await query.edit_message_text(mesaj, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("yonet_"):
        kod = data.split("_")[1]
        res = supabase.table("sikayetler").select("*").eq("takip_kodu", kod).execute()
        
        if res.data:
            s = res.data[0]
            sakin_res = supabase.table("sakinler").select("ad_soyad, daire_no").eq("telegram_id", s['sakin_id']).execute()
            sakin_bilgi = sakin_res.data[0] if sakin_res.data else {"ad_soyad": "Bilinmiyor", "daire_no": "?"}

            detay_mesaj = f"🛠 **Şikayet: {kod}**\n👤: {sakin_bilgi['ad_soyad']} ({sakin_bilgi['daire_no']})\n📊: {s['durum']}\n📝: {s['aciklama']}"
            kb = [
                [InlineKeyboardButton("⚙️ İnceleniyor Yap", callback_data=f"durum_incele_{kod}"),
                 InlineKeyboardButton("✅ Çözüldü Yap", callback_data=f"durum_cozuldu_{kod}")],
                [InlineKeyboardButton("⬅️ Listeye Dön", callback_data=f"liste_{s['durum'].capitalize()}")]
            ]
            await query.edit_message_text(detay_mesaj, reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("durum_"):
        islem, kod = data.split("_")[1], data.split("_")[2]
        yeni_durum = "inceleniyor" if islem == "incele" else "çözüldü"
        res = supabase.table("sikayetler").update({"durum": yeni_durum}).eq("takip_kodu", kod).execute()
        
        if res.data:
            await query.edit_message_text(f"✅ {kod} durumu '{yeni_durum}' yapıldı.\n/panel komutunu kullanabilirsiniz.")
            try:
                await context.bot.send_message(chat_id=res.data[0]['sakin_id'], text=f"📢 {kod} kodlu şikayetiniz: **{yeni_durum.upper()}**", parse_mode="Markdown")
            except: pass

    elif data == "panele_don":
        await panel(update, context)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # HANDLER SIRALAMASI ÇOK ÖNEMLİ
    app.add_handler(CommandHandler('panel', panel))
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            AD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_ad)],
            DAIRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_daire)]
        },
        fallbacks=[]
    ))
    
    # Buton yakalayıcılar
    app.add_handler(CallbackQueryHandler(kategori_secimi, pattern="^(Asansör|Aydınlatma|Temizlik|Gürültü|Diğer)$"))
    app.add_handler(CallbackQueryHandler(buton_islem, pattern="^(liste_|yonet_|durum_|panele_don)"))
    
    # Şikayet metni yakalayıcı (Sadece kullanıcı kategori seçtikten sonra çalışır)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, sikayet_kaydet))

    app.run_polling()