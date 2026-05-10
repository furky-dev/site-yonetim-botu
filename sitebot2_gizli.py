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
AD, DAIRE = range(2)

# --- 2. YARDIMCI FONKSİYONLAR ---
def takip_kodu_uret():
    return f"#SB-{''.join(random.choices(string.digits, k=4))}"

# ============================================================
# --- WEB FORMU (FLASK) ---
# ============================================================

flask_app = Flask(__name__)

HTML_FORM = """
<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Bina Şikayet Formu</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0f0f13;
    --surface: #17171e;
    --border: #2a2a38;
    --accent: #c8a96e;
    --accent2: #e8c98e;
    --text: #e8e8f0;
    --muted: #7a7a99;
    --success: #4caf82;
    --radius: 12px;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'DM Sans', sans-serif;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    background-image: radial-gradient(ellipse at 20% 50%, rgba(200,169,110,0.05) 0%, transparent 60%),
                      radial-gradient(ellipse at 80% 20%, rgba(200,169,110,0.03) 0%, transparent 50%);
  }

  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 48px 40px;
    width: 100%;
    max-width: 480px;
    box-shadow: 0 24px 64px rgba(0,0,0,0.4);
  }

  .logo {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 32px;
  }

  .logo-icon {
    width: 44px; height: 44px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 20px;
  }

  .logo-text {
    font-family: 'DM Serif Display', serif;
    font-size: 22px;
    color: var(--text);
    letter-spacing: -0.3px;
  }

  .logo-sub {
    font-size: 12px;
    color: var(--muted);
    font-weight: 300;
    margin-top: 1px;
  }

  h1 {
    font-family: 'DM Serif Display', serif;
    font-size: 28px;
    font-weight: 400;
    letter-spacing: -0.5px;
    margin-bottom: 8px;
    line-height: 1.2;
  }

  .subtitle {
    color: var(--muted);
    font-size: 14px;
    font-weight: 300;
    margin-bottom: 32px;
    line-height: 1.5;
  }

  .field {
    margin-bottom: 20px;
  }

  label {
    display: block;
    font-size: 12px;
    font-weight: 500;
    color: var(--muted);
    letter-spacing: 0.8px;
    text-transform: uppercase;
    margin-bottom: 8px;
  }

  input, textarea, select {
    width: 100%;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    color: var(--text);
    font-family: 'DM Sans', sans-serif;
    font-size: 15px;
    font-weight: 300;
    padding: 14px 16px;
    transition: border-color 0.2s, box-shadow 0.2s;
    outline: none;
    -webkit-appearance: none;
  }

  input::placeholder, textarea::placeholder { color: var(--muted); }

  input:focus, textarea:focus, select:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(200,169,110,0.1);
  }

  textarea { resize: vertical; min-height: 120px; line-height: 1.6; }

  select {
    cursor: pointer;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' fill='none'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%237a7a99' stroke-width='1.5' stroke-linecap='round'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 16px center;
    padding-right: 40px;
  }

  select option { background: var(--surface); }

  .row { display: flex; gap: 12px; }
  .row .field { flex: 1; }

  .btn {
    width: 100%;
    padding: 16px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border: none;
    border-radius: var(--radius);
    color: #0f0f13;
    font-family: 'DM Sans', sans-serif;
    font-size: 15px;
    font-weight: 500;
    cursor: pointer;
    transition: opacity 0.2s, transform 0.1s;
    margin-top: 8px;
    letter-spacing: 0.2px;
  }

  .btn:hover { opacity: 0.9; }
  .btn:active { transform: scale(0.98); }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }

  .success-box {
    display: none;
    text-align: center;
    padding: 32px 0 8px;
    animation: fadeIn 0.4s ease;
  }

  .success-icon {
    width: 64px; height: 64px;
    background: rgba(76,175,130,0.12);
    border: 1px solid rgba(76,175,130,0.3);
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 28px;
    margin: 0 auto 20px;
  }

  .success-box h2 {
    font-family: 'DM Serif Display', serif;
    font-size: 22px;
    font-weight: 400;
    margin-bottom: 8px;
  }

  .success-box p { color: var(--muted); font-size: 14px; line-height: 1.6; }

  .kod-badge {
    display: inline-block;
    background: rgba(200,169,110,0.1);
    border: 1px solid rgba(200,169,110,0.3);
    color: var(--accent2);
    font-family: monospace;
    font-size: 18px;
    padding: 8px 20px;
    border-radius: 8px;
    margin: 16px 0;
    letter-spacing: 1px;
  }

  .error-msg {
    display: none;
    background: rgba(229,72,72,0.1);
    border: 1px solid rgba(229,72,72,0.3);
    color: #e54848;
    border-radius: var(--radius);
    padding: 12px 16px;
    font-size: 13px;
    margin-bottom: 16px;
  }

  @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

  @media (max-width: 480px) {
    .card { padding: 32px 24px; }
    .row { flex-direction: column; gap: 0; }
  }
</style>
</head>
<body>
<div class="card">
  <div class="logo">
    <div class="logo-icon">🏢</div>
    <div>
      <div class="logo-text">SiteBot</div>
      <div class="logo-sub">Bina Yönetim Sistemi</div>
    </div>
  </div>

  <div id="formView">
    <h1>Şikayet Bildir</h1>
    <p class="subtitle">Formu doldurun, yöneticiye anında iletilsin.<br>Takip kodunuzu saklayın.</p>

    <div class="error-msg" id="errorMsg"></div>

    <div class="row">
      <div class="field">
        <label>Ad Soyad</label>
        <input type="text" id="ad_soyad" placeholder="Ahmet Yılmaz" required>
      </div>
      <div class="field">
        <label>Daire No</label>
        <input type="text" id="daire_no" placeholder="12" required>
      </div>
    </div>

    <div class="field">
      <label>Kategori</label>
      <select id="kategori">
        <option value="Asansör">🛗 Asansör</option>
        <option value="Aydınlatma">💡 Aydınlatma</option>
        <option value="Temizlik">🧹 Temizlik</option>
        <option value="Gürültü">🔊 Gürültü</option>
        <option value="Diğer">✨ Diğer</option>
      </select>
    </div>

    <div class="field">
      <label>Şikayet Detayı</label>
      <textarea id="aciklama" placeholder="Sorunu kısaca açıklayın..."></textarea>
    </div>

    <button class="btn" id="submitBtn" onclick="gonder()">Şikayeti İlet →</button>
  </div>

  <div class="success-box" id="successView">
    <div class="success-icon">✅</div>
    <h2>Şikayetiniz İletildi</h2>
    <div class="kod-badge" id="takipKodu"></div>
    <p>Takip kodunuzu not edin.<br>Yönetici en kısa sürede inceleyecektir.</p>
  </div>
</div>

<script>
async function gonder() {
  const ad = document.getElementById('ad_soyad').value.trim();
  const daire = document.getElementById('daire_no').value.trim();
  const kategori = document.getElementById('kategori').value;
  const aciklama = document.getElementById('aciklama').value.trim();
  const errEl = document.getElementById('errorMsg');
  const btn = document.getElementById('submitBtn');

  errEl.style.display = 'none';

  if (!ad || !daire || !aciklama) {
    errEl.textContent = 'Lütfen tüm alanları doldurun.';
    errEl.style.display = 'block';
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Gönderiliyor...';

  try {
    const res = await fetch('/sikayet', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ad_soyad: ad, daire_no: daire, kategori, aciklama})
    });
    const data = await res.json();

    if (data.success) {
      document.getElementById('formView').style.display = 'none';
      const sv = document.getElementById('successView');
      sv.style.display = 'block';
      document.getElementById('takipKodu').textContent = data.takip_kodu;
    } else {
      errEl.textContent = data.error || 'Bir hata oluştu, tekrar deneyin.';
      errEl.style.display = 'block';
      btn.disabled = false;
      btn.textContent = 'Şikayeti İlet →';
    }
  } catch(e) {
    errEl.textContent = 'Bağlantı hatası, lütfen tekrar deneyin.';
    errEl.style.display = 'block';
    btn.disabled = false;
    btn.textContent = 'Şikayeti İlet →';
  }
}
</script>
</body>
</html>
"""

@flask_app.route("/")
def index():
    return render_template_string(HTML_FORM)

@flask_app.route("/sikayet", methods=["POST"])
def sikayet_al():
    try:
        data = request.get_json()
        ad_soyad = data.get("ad_soyad", "").strip()
        daire_no  = data.get("daire_no", "").strip()
        kategori  = data.get("kategori", "Diğer")
        aciklama  = data.get("aciklama", "").strip()

        if not all([ad_soyad, daire_no, aciklama]):
            return jsonify({"success": False, "error": "Eksik alan"}), 400

        kod = takip_kodu_uret()

        # Supabase'e kaydet (web kaynağını belirt)
        supabase.table("sikayetler").insert({
            "sakin_id": 0,  # Web formundan geldi, telegram_id yok
            "kategori": kategori,
            "aciklama": aciklama,
            "takip_kodu": kod,
            "durum": "beklemede",
            "kaynak": "web",
            "ad_soyad": ad_soyad,
            "daire_no": daire_no
        }).execute()

        # Telegram'a bildirim gönder
        msg = (
            f"🌐 *YENİ (Web Formu)*\n"
            f"👤 {ad_soyad} — Daire {daire_no}\n"
            f"📂 {kategori}\n"
            f"📝 {aciklama}\n"
            f"🔖 `{kod}`"
        )
        telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(telegram_url, json={
            "chat_id": YONETICI_ID,
            "text": msg,
            "parse_mode": "Markdown"
        }, timeout=5)

        return jsonify({"success": True, "takip_kodu": kod})

    except Exception as e:
        logging.error(f"Web form hatası: {e}")
        return jsonify({"success": False, "error": "Sunucu hatası"}), 500

def flask_calistir():
    port = int(os.getenv("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port, debug=False)

# ============================================================
# --- TELEGRAM BOT (DEĞİŞMEDİ) ---
# ============================================================

async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    supabase.table("sakinler").insert({
        "telegram_id": update.effective_user.id,
        "ad_soyad": context.user_data['ad'],
        "daire_no": update.message.text
    }).execute()
    await update.message.reply_text("Kayıt tamam! /start yazarak şikayet iletebilirsiniz.")
    return ConversationHandler.END

async def kategori_secimi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data in ['Asansör', 'Aydınlatma', 'Temizlik', 'Gürültü', 'Diğer']:
        context.user_data['secilen_kategori'] = query.data
        context.user_data['bekliyor_mu'] = True
        await query.edit_message_text(text=f"📂 Kategori: {query.data}\nŞikayetinizi yazın:")

async def sikayet_kaydet(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        "durum": "beklemede",
        "kaynak": "telegram"
    }).execute()

    context.user_data['bekliyor_mu'] = False
    await update.message.reply_text(f"✅ Şikayet iletildi. Kod: {kod}")

    admin_m = f"📩 **YENİ!**\n{sakin['ad_soyad']} ({sakin['daire_no']})\n{kod}: {update.message.text}"
    kb = [[InlineKeyboardButton("⚙️ İnceleniyor", callback_data=f"durum_incele_{kod}"),
           InlineKeyboardButton("✅ Çözüldü", callback_data=f"durum_cozuldu_{kod}")]]
    await context.bot.send_message(chat_id=YONETICI_ID, text=admin_m, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

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
            # Web veya Telegram kaynağına göre sakin bilgisi al
            if s.get('kaynak') == 'web':
                ad_soyad = s.get('ad_soyad', 'Bilinmiyor')
                daire_no = s.get('daire_no', '?')
            else:
                sakin_res = supabase.table("sakinler").select("ad_soyad, daire_no").eq("telegram_id", s['sakin_id']).execute()
                sakin_bilgi = sakin_res.data[0] if sakin_res.data else {"ad_soyad": "Bilinmiyor", "daire_no": "?"}
                ad_soyad = sakin_bilgi['ad_soyad']
                daire_no = sakin_bilgi['daire_no']

            kaynak_emoji = "🌐" if s.get('kaynak') == 'web' else "✈️"
            detay_mesaj = (
                f"🛠 **Şikayet: {kod}** {kaynak_emoji}\n"
                f"👤: {ad_soyad} ({daire_no})\n"
                f"📊: {s['durum']}\n"
                f"📝: {s['aciklama']}"
            )
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
            # Sadece Telegram şikayetlerinde sakin'e bildirim gönder
            sakin_id = res.data[0].get('sakin_id')
            if sakin_id and sakin_id != 0:
                try:
                    await context.bot.send_message(
                        chat_id=sakin_id,
                        text=f"📢 {kod} kodlu şikayetiniz: **{yeni_durum.upper()}**",
                        parse_mode="Markdown"
                    )
                except:
                    pass

    elif data == "panele_don":
        await panel(update, context)


# ============================================================
# --- ANA BAŞLATICI ---
# ============================================================

if __name__ == '__main__':
    # Flask'ı ayrı thread'de başlat
    t = threading.Thread(target=flask_calistir, daemon=True)
    t.start()
    print("✅ Web formu başlatıldı.")

    # Telegram botunu ana thread'de çalıştır
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler('panel', panel))
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            AD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_ad)],
            DAIRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_daire)]
        },
        fallbacks=[]
    ))

    app.add_handler(CallbackQueryHandler(kategori_secimi, pattern="^(Asansör|Aydınlatma|Temizlik|Gürültü|Diğer)$"))
    app.add_handler(CallbackQueryHandler(buton_islem, pattern="^(liste_|yonet_|durum_|panele_don)"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, sikayet_kaydet))

    print("🤖 Telegram botu başlatıldı.")
    app.run_polling()
