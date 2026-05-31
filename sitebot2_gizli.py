import logging
import random
import string
import os
import threading
import requests
import io
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
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;50&display=swap" rel="stylesheet">
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
      <div class="logo-text">Premium Residence</div>
      <div class="logo-sub">Yönetim Destek Sistemi</div>
    </div>
  </div>

  <div id="form-container">
    <h1>Şikayet Bildir</h1>
    <div class="subtitle">Lütfen aşağıdaki alanları eksiksiz doldurunuz. Talebiniz anında yönetime iletilecektir.</div>
    
    <div id="error-box" class="error-msg"></div>

    <form id="complaint-form">
      <div class="field">
        <label>Ad Soyad</label>
        <input type="text" id="ad_soyad" required placeholder="Örn. Ahmet Yılmaz">
      </div>
      
      <div class="row">
        <div class="field">
          <label>Daire No</label>
          <input type="text" id="daire_no" required placeholder="Örn. D:12">
        </div>
        <div class="field">
          <label>Kategori</label>
          <select id="kategori">
            <option value="Asansör">Asansör</option>
            <option value="Aydınlatma">Aydınlatma</option>
            <option value="Temizlik">Temizlik</option>
            <option value="Gürültü">Gürültü</option>
            <option value="Diğer">Diğer</option>
          </select>
        </div>
      </div>

      <div class="field">
        <label>Şikayet Detayı</label>
        <textarea id="detay" required placeholder="Lütfen şikayetinizi detaylıca açıklayınız..."></textarea>
      </div>

      <button type="submit" class="btn" id="submit-btn">Gönderiyi İlet</button>
    </form>
  </div>

  <div id="success-container" class="success-box">
    <div class="success-icon">✓</div>
    <h2>Başarıyla İletildi</h2>
    <p>Şikayetiniz sisteme kaydedildi ve yönetim bildirim paneline düştü.</p>
    <div class="kod-badge" id="takip-kodu">-</div>
    <p style="font-size: 12px;">Lütfen bu kodu takip işlemleriniz için saklayınız.</p>
  </div>
</div>

<script>
document.getElementById('complaint-form').addEventListener('submit', async function(e) {
  e.preventDefault();
  
  const btn = document.getElementById('submit-btn');
  const errorBox = document.getElementById('error-box');
  
  btn.disabled = true;
  btn.innerText = 'Gönderiliyor...';
  errorBox.style.display = 'none';

  const data = {
    ad_soyad: document.getElementById('ad_soyad').value,
    daire_no: document.getElementById('daire_no').value,
    kategori: document.getElementById('kategori').value,
    detay: document.getElementById('detay').value
  };

  try {
    const response = await fetch('/sikayet-ekle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });

    const result = await response.json();

    if (response.ok) {
      document.getElementById('takip-kodu').innerText = result.kod;
      document.getElementById('form-container').style.display = 'none';
      document.getElementById('success-container').style.display = 'block';
    } else {
      throw new Error(result.error || 'Bir hata oluştu.');
    }
  } catch (err) {
    errorBox.innerText = err.message;
    errorBox.style.display = 'block';
    btn.disabled = false;
    btn.innerText = 'Gönderiyi İlet';
  }
});
</script>
</body>
</html>
"""

@flask_app.route('/')
def index():
    return render_template_string(HTML_FORM)

@flask_app.route('/sikayet-ekle', methods=['POST'])
def sikayet_ekle():
    data = request.json
    kod = takip_kodu_uret()
    
    try:
        res = supabase.table("sikayetler").insert({
            "kod": kod,
            "ad_soyad": data.get("ad_soyad"),
            "daire_no": data.get("daire_no"),
            "kategori": data.get("kategori"),
            "detay": data.get("detay"),
            "durum": "Beklemede",
            "kaynak": "Web Formu"
        }).execute()
        
        if YONETICI_ID:
            msg = (
                f"🌐 *Web Formundan Yeni Şikayet!*\n\n"
                f"🔑 *Kod:* `{kod}`\n"
                f"👤 *Sakin:* {data.get('ad_soyad')} ({data.get('daire_no')})\n"
                f"📂 *Kategori:* {data.get('kategori')}\n"
                f"📝 *Detay:* {data.get('detay')}"
            )
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": YONETICI_ID, "text": msg, "parse_mode": "Markdown"})

        return jsonify({"status": "success", "kod": kod}), 200
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

def flask_calistir():
    flask_app.run(host="0.0.0.0", port=5000)


# ============================================================
# --- TELEGRAM BOT ---
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    
    res = supabase.table("sakinler").select("*").eq("sakin_id", chat_id).execute()
    
    if res.data:
        sakin = res.data[0]
        await update.message.reply_text(
            f"Merhaba {sakin['ad_soyad']} ({sakin['daire_no']}), Premium Residence botuna tekrar hoş geldiniz!\n"
            "Lütfen bildirmek istediğiniz şikayet kategorisini seçin:",
            reply_markup=kategori_klavyesi()
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text("Premium Residence Yönetim Botuna Hoş Geldiniz!\nSizi tanıyabilmemiz için lütfen önce Adınızı ve Soyadınızı yazınız:")
        return AD

async def get_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['ad_soyad'] = update.message.text
    await update.message.reply_text("Teşekkürler. Şimdi lütfen Daire Numaranızı yazınız (Örn: D:14 veya Blok B D:2):")
    return DAIRE

async def get_daire(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    ad_soyad = context.user_data['ad_soyad']
    daire_no = update.message.text

    supabase.table("sakinler").insert({
        "sakin_id": chat_id,
        "ad_soyad": ad_soyad,
        "daire_no": daire_no
    }).execute()

    await update.message.reply_text(
        f"Kayıt işleminiz başarıyla tamamlandı, {ad_soyad}!\n"
        "Şimdi apartmanımız ile ilgili şikayetinizi kategorisini seçerek iletebilirsiniz:",
        reply_markup=kategori_klavyesi()
    )
    return ConversationHandler.END

def kategori_klavyesi():
    keyboard = [
        [InlineKeyboardButton("Asansör 🛗", callback_data="Asansör"), InlineKeyboardButton("Aydınlatma 💡", callback_data="Aydınlatma")],
        [InlineKeyboardButton("Temizlik 🧹", callback_data="Temizlik"), InlineKeyboardButton("Gürültü 🤫", callback_data="Gürültü")],
        [InlineKeyboardButton("Diğer 🛑", callback_data="Diğer")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def kategori_secimi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    kategori = query.data
    context.user_data['secilen_kategori'] = kategori

    await query.edit_message_text(
        text=f"📂 Seçilen Kategori: *{kategori}*\n\n"
             "Lütfen şikayetinizi detaylıca açıklayan bir *mesaj yazın* veya arızanın durumunu gösteren bir *fotoğraf gönderin* 📸:",
        parse_mode="Markdown"
    )

async def handle_photo_complaint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_data = context.user_data

    if 'secilen_kategori' not in user_data:
        await update.message.reply_text("Lütfen önce /start komutu ile bir şikayet kategorisi seçiniz.")
        return

    # Supabase'den sakini sorgula
    res_sakin = supabase.table("sakinler").select("*").eq("sakin_id", chat_id).execute()
    if not res_sakin.data:
        await update.message.reply_text("Lütfen önce /start yazarak kayıt işlemlerinizi tamamlayınız.")
        return
        
    sakin = res_sakin.data[0]
    kategori = user_data['secilen_kategori']
    kod = takip_kodu_uret()

    await update.message.reply_text("🔄 Fotoğrafınız alınıyor ve şikayet kaydınız oluşturuluyor, lütfen bekleyin...")

    try:
        # Fotoğrafı Telegram'dan indir
        photo_file = await update.message.photo[-1].get_file()
        
        photo_bytes = io.BytesIO()
        await photo_file.download_to_memory(out=photo_bytes)
        photo_bytes.seek(0)
        
        file_name = f"{chat_id}_{update.message.message_id}.jpg"
        bucket_name = "sikayet-fotograflari"
        
        # 1. Fotoğrafı Supabase Storage'a yükle
        supabase.storage.from_(bucket_name).upload(
            path=file_name,
            file=photo_bytes.getvalue(),
            file_options={"content-type": "image/jpeg"}
        )
        
        # 2. Fotoğrafın herkese açık URL'sini al
        photo_url = supabase.storage.from_(bucket_name).get_public_url(file_name)
        
        # 3. Veritabanına kaydet (Sütun isimleri tam olarak senin Supabase yapınla eşitlendi)
        supabase.table("sikayetler").insert({
            "kod": kod,
            "sakin_id": chat_id,
            "ad_soyad": sakin.get('ad_soyad'),
            "daire_no": sakin.get('daire_no'),
            "kategori": kategori,
            "detay": "Fotoğraflı şikayet bildirim şablonu (Ekli görseli inceleyiniz).",
            "durum": "Beklemede",
            "kaynak": "Telegram (Fotoğraf)",
            "fotograf_url": photo_url
        }).execute()
        
        # 4. Yöneticiye fotoğraflı bildirim gönder
        if YONETICI_ID:
            bildirim_metni = (
                f"🚨 *Telegram'dan Yeni Fotoğraflı Şikayet!*\n\n"
                f"🔑 *Kod:* `{kod}`\n"
                f"👤 *Sakin:* {sakin.get('ad_soyad')} ({sakin.get('daire_no')})\n"
                f"📂 *Kategori:* {kategori}\n"
                f"📝 *Durum:* Görsel ekte yer almaktadır."
            )
            try:
                await context.bot.send_photo(
                    chat_id=int(YONETICI_ID),
                    photo=photo_url,
                    caption=bildirim_metni,
                    parse_mode="Markdown"
                )
            except Exception as admin_err:
                print(f"Yöneticiye fotoğraf gönderilemedi: {admin_err}")

        # Başarılı çıkış ve temizlik
        if 'secilen_kategori' in user_data:
            del user_data['secilen_kategori']
            
        await update.message.reply_text(
            f"✅ Şikayetiniz fotoğraflı olarak başarıyla alınmış ve yöneticiye iletilmiştir!\n\n"
            f"🔑 Takip Kodunuz: *{kod}*",
            parse_mode="Markdown"
        )

    except Exception as e:
        print(f"Fotoğraf Yükleme Hatası: {e}")
        # Hatanın tam nedenini loglara basıyoruz ki Railway'de görebilelim
        logging.error(f"Kritik Hata Detayı: {str(e)}")
        await update.message.reply_text("❌ Şikayetiniz kaydedilirken veya fotoğraf yüklenirken teknik bir sorun oluştu.")

async def handle_complaint_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_data = context.user_data

    if 'secilen_kategori' not in user_data:
        return

    res_sakin = supabase.table("sakinler").select("*").eq("sakin_id", chat_id).execute()
    if not res_sakin.data:
        await update.message.reply_text("Lütfen önce /start yazarak kayıt olun.")
        return

    sakin = res_sakin.data[0]
    kategori = user_data['secilen_kategori']
    detay = update.message.text
    kod = takip_kodu_uret()

    try:
        supabase.table("sikayetler").insert({
            "kod": kod,
            "sakin_id": chat_id,
            "ad_soyad": sakin['ad_soyad'],
            "daire_no": sakin['daire_no'],
            "kategori": kategori,
            "detay": detay,
            "durum": "Beklemede",
            "kaynak": "Telegram"
        }).execute()

        if YONETICI_ID:
            msg = (
                f"🚨 *Telegram'dan Yeni Şikayet!*\n\n"
                f"🔑 *Kod:* `{kod}`\n"
                f"👤 *Sakin:* {sakin['ad_soyad']} ({sakin['daire_no']})\n"
                f"📂 *Kategori:* {kategori}\n"
                f"📝 *Detay:* {detay}"
            )
            await context.bot.send_message(chat_id=YONETICI_ID, text=msg, parse_mode="Markdown")

        del user_data['secilen_kategori']
        await update.message.reply_text(f"✅ Şikayetiniz başarıyla yöneticiye iletildi!\n🔑 Takip Kodunuz: *{kod}*", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Hata oluştu: {str(e)}")


# ============================================================
# --- YÖNETİCİ PANELİ (TELEGRAM) ---
# ============================================================

async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id) if update.message else str(update.callback_query.message.chat_id)
    
    if chat_id != str(YONETICI_ID):
        text = "Bu komut sadece yönetici yetkisine sahip kişilere özeldir."
        if update.message: await update.message.reply_text(text)
        else: await update.callback_query.message.reply_text(text)
        return

    keyboard = [
        [InlineKeyboardButton("Bekleyen Şikayetler ⏳", callback_data="liste_beklemede")],
        [InlineKeyboardButton("İşlemdeki Şikayetler ⚙️", callback_data="liste_islemde")],
        [InlineKeyboardButton("Çözülen Şikayetler ✅", callback_data="liste_cozuldu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "🏢 *Premium Residence Yönetim Paneli*\nLütfen listelemek istediğiniz şikayet durumunu seçin:"
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.callback_query.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def buton_islem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("liste_"):
        durum = data.split("_")[1]
        durum_tr = {"beklemede": "Beklemede", "islemde": "İşlemde", "cozuldu": "Çözüldü"}[durum]
        
        res = supabase.table("sikayetler").select("*").eq("durum", durum_tr).execute()
        
        if not res.data:
            keyboard = [[InlineKeyboardButton("« Panele Dön", callback_data="panele_don")]]
            await query.edit_message_text(f"📂 *{durum_tr}* durumunda şikayet bulunamadı.", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return

        text = f"📂 *{durum_tr} Şikayetler Listesi*:\n\n"
        keyboard = []
        for s in res.data[:5]:
            text += f"🔑 *{s['kod']}* - {s['ad_soyad']} ({s['daire_no']})\n📌 {s['kategori']}: {s['detay'][:40]}...\n\n"
            keyboard.append([InlineKeyboardButton(f"Yönet: {s['kod']}", callback_data=f"yonet_{s['kod']}")])
        
        keyboard.append([InlineKeyboardButton("« Panele Dön", callback_data="panele_don")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("yonet_"):
        kod = data.split("_")[1]
        res = supabase.table("sikayetler").select("*").eq("kod", kod).execute()
        if res.data:
            s = res.data[0]
            text = (
                f"🔍 *Şikayet Detayı* ({s['kod']})\n"
                f"👤 *Sakin:* {s['ad_soyad']} ({s['daire_no']})\n"
                f"📂 *Kategori:* {s['kategori']}\n"
                f"📝 *Detay:* {s['detay']}\n"
                f"⚙️ *Mevcut Durum:* {s['durum']}\n"
                f"🔗 *Kaynak:* {s['kaynak']}"
            )
            
            if s.get('fotograf_url'):
                text += f"\n📸 *Şikayet Fotoğrafı:* [Tıkla ve Gör]({s['fotograf_url']})"

            keyboard = [
                [InlineKeyboardButton("İşleme Al ⚙️", callback_data=f"durum_{kod}_İşlemde")],
                [InlineKeyboardButton("Çözüldü Olarak İşaretle ✅", callback_data=f"durum_{kod}_Çözüldü")],
                [InlineKeyboardButton("« Panele Dön", callback_data="panele_don")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown", disable_web_page_preview=False)

    elif data.startswith("durum_"):
        _, kod, yeni_durum = data.split("_")
        
        eski_res = supabase.table("sikayetler").select("sakin_id").eq("kod", kod).execute()
        supabase.table("sikayetler").update({"durum": yeni_durum}).eq("kod", kod).execute()
        
        keyboard = [[InlineKeyboardButton("« Panele Dön", callback_data="panele_don")]]
        await query.edit_message_text(f"✅ *{kod}* kodlu şikayetin durumu *{yeni_durum}* olarak güncellendi.", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

        if eski_res.data and eski_res.data[0].get("sakin_id"):
            sakin_id = eski_res.data[0]["sakin_id"]
            if sakin_id:
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
    t = threading.Thread(target=flask_calistir, daemon=True)
    t.start()
    print("✅ Web formu başlatıldı.")

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
    
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_complaint))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_complaint_text))

    print("🚀 Telegram botu aktif!")
    app.run_polling()
