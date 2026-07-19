import logging, random, string, os, threading, asyncio, uuid
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template_string
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.exceptions import HTTPException
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from supabase import create_client, Client
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, BotCommand, BotCommandScopeChat
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
AD, DAIRE, KAT_BLOK, SIKAYET_DETAY, KVKK_ONAY, FOTOGRAF_SOR = range(6)

YENI_SIKAYET_BUTONU = "📝 Yeni Şikayet Bildir"
SIKAYETLERIM_BUTONU = "📋 Şikayetlerim"

# --- YARDIMCI FONKSİYONLAR ---
def takip_kodu_uret(): return f"#SB-{''.join(random.choices(string.digits, k=4))}"

def kod_normallestir(ham):
    ham = ham.strip().upper()
    rakamlar = ''.join(ch for ch in ham if ch.isdigit())
    return f"#SB-{rakamlar}" if rakamlar else ham

def kategori_klavyesi():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛗 Asansör", callback_data="Asansör"), InlineKeyboardButton("🧹 Temizlik", callback_data="Temizlik")],
        [InlineKeyboardButton("💡 Aydınlatma", callback_data="Aydınlatma"), InlineKeyboardButton("📦 Diğer", callback_data="Diğer")]
    ])

def fotograf_sor_klavyesi():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📷 Evet, Fotoğraf Ekle", callback_data="foto_evet")],
        [InlineKeyboardButton("⏭️ Hayır, Fotoğrafsız Gönder", callback_data="foto_hayir")]
    ])

def ana_menu_klavyesi():
    return ReplyKeyboardMarkup(
        [[YENI_SIKAYET_BUTONU], [SIKAYETLERIM_BUTONU]],
        resize_keyboard=True
    )

async def upload_photo_to_supabase(file_id, context):
    try:
        file = await context.bot.get_file(file_id)
        file_bytes = await file.download_as_bytearray()
        file_name = f"sikayet_{file_id}.jpg"
        supabase.storage.from_("sikayet-fotograflari").upload(path=file_name, file=bytes(file_bytes), file_options={"content-type": "image/jpeg"})
        return supabase.storage.from_("sikayet-fotograflari").get_public_url(file_name)
    except: return None

def upload_web_photo_to_supabase(file_storage):
    try:
        file_bytes = file_storage.read()
        file_name = f"web_{uuid.uuid4().hex}.jpg"
        supabase.storage.from_("sikayet-fotograflari").upload(
            path=file_name, file=file_bytes,
            file_options={"content-type": file_storage.content_type or "image/jpeg"}
        )
        return supabase.storage.from_("sikayet-fotograflari").get_public_url(file_name)
    except Exception:
        return None

# --- WEB ŞİKAYET FORMU ---
HTML_FORM = """
<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Şikayet Formu</title>
<style>
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: #f2f4f7;
    color: #1a1a1a;
    font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
    font-size: 20px;
    line-height: 1.5;
    padding: 20px;
    overflow-x: hidden;
  }
  .card {
    background: #ffffff;
    max-width: 560px;
    margin: 0 auto;
    border-radius: 16px;
    padding: 28px 24px 36px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.08);
  }
  h1 {
    font-size: 30px;
    margin: 0 0 6px;
    color: #08326b;
  }
  .subtitle {
    font-size: 19px;
    color: #333;
    margin: 0 0 12px;
  }
  .sorgu-link {
    display: block;
    font-size: 17px;
    margin: 0 0 28px;
  }
  .sorgu-link a {
    color: #08519c;
    font-weight: 700;
  }
  label {
    display: block;
    font-size: 20px;
    font-weight: 700;
    margin-bottom: 8px;
    color: #111;
  }
  .field { margin-bottom: 24px; }
  .opsiyonel {
    font-weight: 400;
    font-size: 16px;
    color: #555;
  }
  input[type="text"], textarea {
    width: 100%;
    font-size: 20px;
    font-family: inherit;
    padding: 16px;
    border: 2px solid #999;
    border-radius: 10px;
    color: #111;
    background: #fff;
  }
  input[type="text"]:focus, textarea:focus {
    outline: 3px solid #08519c;
    border-color: #08519c;
  }
  textarea { min-height: 130px; resize: vertical; }
  .kategori-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: 12px;
  }
  .kategori-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    min-width: 0;
    min-height: 64px;
    font-size: 19px;
    font-weight: 700;
    border: 3px solid #999;
    border-radius: 12px;
    background: #fff;
    color: #111;
    cursor: pointer;
    padding: 8px;
    text-align: center;
  }
  .kategori-btn.secili {
    border-color: #08519c;
    background: #08519c;
    color: #fff;
  }
  .foto-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    width: 100%;
    min-height: 64px;
    font-size: 19px;
    font-weight: 700;
    border: 3px dashed #999;
    border-radius: 12px;
    background: #fafafa;
    color: #333;
    cursor: pointer;
  }
  .foto-durum { margin-top: 10px; font-size: 17px; color: #08326b; font-weight: 600; }
  .gonder-btn {
    width: 100%;
    min-height: 68px;
    font-size: 23px;
    font-weight: 700;
    border: none;
    border-radius: 12px;
    background: #08519c;
    color: #fff;
    cursor: pointer;
    margin-top: 8px;
  }
  .gonder-btn:disabled { background: #9bb6d3; cursor: not-allowed; }
  .hata {
    display: none;
    background: #fdecec;
    border: 2px solid #c81e1e;
    color: #8a1414;
    border-radius: 10px;
    padding: 14px 16px;
    font-size: 18px;
    font-weight: 600;
    margin-bottom: 22px;
  }
  .basarili { display: none; text-align: center; }
  .basarili .tik { font-size: 60px; margin-bottom: 10px; }
  .basarili h2 { font-size: 26px; color: #08326b; margin: 0 0 14px; }
  .kod-kutu {
    display: inline-block;
    font-size: 32px;
    font-weight: 700;
    letter-spacing: 1px;
    background: #eaf1fb;
    border: 3px solid #08519c;
    color: #08326b;
    border-radius: 12px;
    padding: 14px 26px;
    margin: 10px 0 20px;
  }
  .basarili p { font-size: 19px; color: #333; margin-bottom: 26px; }
  .yeni-btn {
    width: 100%;
    min-height: 60px;
    font-size: 19px;
    font-weight: 700;
    border: 2px solid #08519c;
    border-radius: 12px;
    background: #fff;
    color: #08519c;
    cursor: pointer;
  }
  .kvkk-bilgi {
    font-size: 16px;
    color: #444;
    margin: 4px 0 18px;
  }
  .kvkk-bilgi a {
    color: #08519c;
    font-weight: 700;
  }
  .kvkk-onay-kutusu {
    background: #f5f8fc;
    border: 2px solid #c7d7ea;
    border-radius: 12px;
    padding: 14px 16px;
  }
  .kvkk-onay-label {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    font-weight: 400;
    font-size: 17px;
    color: #222;
    cursor: pointer;
  }
  .kvkk-onay-label input[type="checkbox"] {
    width: 28px;
    height: 28px;
    flex-shrink: 0;
    margin-top: 2px;
  }
</style>
</head>
<body>
<div class="card">

  <div id="formGorunumu">
    <h1>🏢 Şikayet Bildir</h1>
    <p class="subtitle">Aşağıdaki alanları doldurup en alttaki büyük butona basın.</p>
    <p class="sorgu-link">Daha önce şikayet bildirdiyseniz: <a href="/sorgula">Şikayet Durumunu Sorgula</a></p>

    <div class="hata" id="hataMesaji"></div>

    <form id="sikayetForm">
      <div style="position:absolute;left:-9999px;top:-9999px" aria-hidden="true">
        <label for="web_sitesi">Web siteniz</label>
        <input type="text" id="web_sitesi" name="web_sitesi" tabindex="-1" autocomplete="off">
      </div>

      <div class="field">
        <label for="ad_soyad">Ad Soyad</label>
        <input type="text" id="ad_soyad" name="ad_soyad" required>
      </div>

      <div class="field">
        <label for="daire_no">Daire No</label>
        <input type="text" id="daire_no" name="daire_no" required>
      </div>

      <div class="field">
        <label for="kat_blok">Kat / Blok <span class="opsiyonel">(isteğe bağlı)</span></label>
        <input type="text" id="kat_blok" name="kat_blok">
      </div>

      <div class="field">
        <label>Konu</label>
        <input type="hidden" id="kategori" name="kategori">
        <div class="kategori-grid" id="kategoriGrid">
          <button type="button" class="kategori-btn" data-deger="Asansör">🛗 Asansör</button>
          <button type="button" class="kategori-btn" data-deger="Aydınlatma">💡 Aydınlatma</button>
          <button type="button" class="kategori-btn" data-deger="Temizlik">🧹 Temizlik</button>
          <button type="button" class="kategori-btn" data-deger="Diğer">📦 Diğer</button>
        </div>
      </div>

      <div class="field">
        <label for="aciklama">Şikayet Detayı</label>
        <textarea id="aciklama" name="aciklama" required></textarea>
      </div>

      <div class="field">
        <label>Fotoğraf <span class="opsiyonel">(isteğe bağlı)</span></label>
        <label class="foto-btn" for="fotograf">📷 Fotoğraf Ekle</label>
        <input type="file" id="fotograf" name="fotograf" accept="image/*" style="display:none">
        <div class="foto-durum" id="fotoDurum"></div>
      </div>

      <p class="kvkk-bilgi">Kişisel verileriniz KVKK kapsamında işlenmektedir. Detaylar için: <a href="/kvkk" target="_blank" rel="noopener">Aydınlatma Metnini Oku</a></p>

      <div class="field kvkk-onay-kutusu">
        <label class="kvkk-onay-label">
          <input type="checkbox" id="acik_riza" name="acik_riza">
          <span>Kişisel verilerimin yurt dışında bulunan sunucularda barındırılmasına <b>açık rıza veriyorum.</b></span>
        </label>
      </div>

      <button type="submit" class="gonder-btn" id="gonderBtn">ŞİKAYETİ GÖNDER</button>
    </form>
  </div>

  <div class="basarili" id="basariGorunumu">
    <div class="tik">✅</div>
    <h2>Şikayetiniz Alındı</h2>
    <div class="kod-kutu" id="takipKodu"></div>
    <p>Bu kodu not edin. Durumu <a href="/sorgula">Şikayet Durumunu Sorgula</a> sayfasından bu kodla sorgulayabilirsiniz.</p>
    <button type="button" class="yeni-btn" onclick="location.reload()">Yeni Şikayet Bildir</button>
  </div>

</div>

<script>
document.querySelectorAll('.kategori-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.kategori-btn').forEach(b => b.classList.remove('secili'));
    btn.classList.add('secili');
    document.getElementById('kategori').value = btn.dataset.deger;
  });
});

document.getElementById('fotograf').addEventListener('change', (e) => {
  const dosya = e.target.files[0];
  document.getElementById('fotoDurum').textContent = dosya ? ('Seçilen dosya: ' + dosya.name) : '';
});

document.getElementById('sikayetForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const hataEl = document.getElementById('hataMesaji');
  const btn = document.getElementById('gonderBtn');
  hataEl.style.display = 'none';

  const adSoyad = document.getElementById('ad_soyad').value.trim();
  const daireNo = document.getElementById('daire_no').value.trim();
  const kategori = document.getElementById('kategori').value;
  const aciklama = document.getElementById('aciklama').value.trim();
  const acikRiza = document.getElementById('acik_riza').checked;

  if (!adSoyad || !daireNo || !kategori || !aciklama) {
    hataEl.textContent = 'Lütfen Ad Soyad, Daire No, Konu ve Şikayet Detayı alanlarını doldurun.';
    hataEl.style.display = 'block';
    return;
  }

  if (!acikRiza) {
    hataEl.textContent = 'Devam etmek için KVKK açık rıza onay kutusunu işaretlemeniz gerekiyor.';
    hataEl.style.display = 'block';
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Gönderiliyor...';

  const veri = new FormData(document.getElementById('sikayetForm'));

  try {
    const res = await fetch('/sikayet', { method: 'POST', body: veri });
    const sonuc = await res.json();
    if (sonuc.success) {
      document.getElementById('formGorunumu').style.display = 'none';
      document.getElementById('takipKodu').textContent = sonuc.takip_kodu;
      document.getElementById('basariGorunumu').style.display = 'block';
    } else {
      hataEl.textContent = sonuc.error || 'Bir hata oluştu, lütfen tekrar deneyin.';
      hataEl.style.display = 'block';
      btn.disabled = false;
      btn.textContent = 'ŞİKAYETİ GÖNDER';
    }
  } catch (err) {
    hataEl.textContent = 'Bağlantı hatası. İnternetinizi kontrol edip tekrar deneyin.';
    hataEl.style.display = 'block';
    btn.disabled = false;
    btn.textContent = 'ŞİKAYETİ GÖNDER';
  }
});
</script>
</body>
</html>
"""

# --- KVKK AYDINLATMA METNİ SAYFASI ---
HTML_KVKK = """
<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>KVKK Aydınlatma Metni</title>
<style>
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: #f2f4f7;
    color: #1a1a1a;
    font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
    font-size: 19px;
    line-height: 1.6;
    padding: 20px;
  }
  .card {
    background: #ffffff;
    max-width: 700px;
    margin: 0 auto;
    border-radius: 16px;
    padding: 28px 24px 36px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.08);
  }
  h1 { font-size: 26px; color: #08326b; margin-top: 0; }
  h2 { font-size: 21px; color: #08326b; margin-top: 30px; }
  .geri-btn {
    display: inline-block;
    margin-top: 30px;
    padding: 14px 22px;
    font-size: 18px;
    font-weight: 700;
    background: #08519c;
    color: #fff;
    border-radius: 10px;
    text-decoration: none;
  }
</style>
</head>
<body>
<div class="card">
<h1>Kişisel Verilerin Korunması Kanunu Kapsamında Aydınlatma Metni</h1>

<p><b>Veri Sorumlusu:</b> Furkan Toptan</p>

<p>Bu Aydınlatma Metni, 6698 sayılı Kişisel Verilerin Korunması Kanunu ("KVKK") uyarınca, veri sorumlusu sıfatıyla Furkan Toptan tarafından, Telegram botu ve web formu üzerinden şikayet bildirim hizmeti kapsamında işlenen kişisel verileriniz hakkında sizi bilgilendirmek amacıyla hazırlanmıştır.</p>

<h2>1. İşlenen Kişisel Veriler</h2>
<p>Ad soyad, daire numarası, kat/blok bilgisi, şikayet konusu ve açıklaması, varsa eklediğiniz fotoğraf ve (Telegram kullanıyorsanız) Telegram kullanıcı kimliğiniz işlenmektedir. Web formu üzerinden gönderim yaparken, kötüye kullanımın/istenmeyen otomatik gönderimlerin (spam) önlenmesi amacıyla IP adresiniz kısa süreliğine (birkaç dakika) işlenir; kalıcı olarak saklanmaz veya şikayetinizle ilişkilendirilmez.</p>

<h2>2. İşlenme Amacı</h2>
<p>Verileriniz; bina/site içerisindeki şikayetlerin kayıt altına alınması, ilgili yöneticiye iletilmesi, takip kodu ile durumunun sorgulanabilmesi ve bu süreçle ilgili tarafınıza bilgi verilmesi amacıyla işlenmektedir. IP adresiniz ise yalnızca hizmetin güvenliğinin sağlanması ve kötüye kullanımının önlenmesi amacıyla işlenmektedir.</p>

<h2>3. Aktarılabileceği Taraflar</h2>
<p>Verileriniz; bina/site yöneticisi ile, hizmetin teknik altyapısını sağlayan Supabase Inc. (veriler Tokyo/Japonya bölgesinde barındırılmaktadır) ve Telegram ile sınırlı olarak paylaşılabilir.</p>
<p><b>Yurt dışı aktarım:</b> Verileriniz Türkiye dışında (Japonya) barındırıldığından, bu aktarım ancak açık rızanızın alınmasıyla mümkündür ve form/bot üzerinden ayrıca bu onayınız istenmektedir.</p>

<h2>4. Toplama Yöntemi ve Hukuki Sebebi</h2>
<p>Verileriniz Telegram botu veya web formu aracılığıyla doğrudan sizin tarafınızdan paylaşılması yoluyla toplanır; KVKK m.5'teki "veri sorumlusunun meşru menfaati" hukuki sebebine, yurt dışı aktarım özelinde ise açık rızanıza dayanılarak işlenir.</p>

<h2>5. Haklarınız (KVKK m. 11)</h2>
<p>Kişisel verinizin işlenip işlenmediğini öğrenme, bilgi talep etme, işlenme amacını öğrenme, aktarıldığı üçüncü kişileri bilme, düzeltilmesini/silinmesini isteme, itiraz etme ve zararın giderilmesini talep etme haklarına sahipsiniz. Bu haklarınızı kullanmak için <b>furkantoptang4+kvkk@gmail.com</b> adresinden bize ulaşabilirsiniz.</p>

<a class="geri-btn" href="/">⬅ Forma Dön</a>
</div>
</body>
</html>
"""

# --- ŞİKAYET SORGULAMA SAYFASI ---
HTML_SORGULA = """
<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Şikayet Sorgula</title>
<style>
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: #f2f4f7;
    color: #1a1a1a;
    font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
    font-size: 20px;
    line-height: 1.5;
    padding: 20px;
  }
  .card {
    background: #ffffff;
    max-width: 560px;
    margin: 0 auto;
    border-radius: 16px;
    padding: 28px 24px 36px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.08);
  }
  h1 { font-size: 28px; color: #08326b; margin: 0 0 20px; }
  label { display: block; font-size: 19px; font-weight: 700; margin-bottom: 8px; }
  input[type="text"] {
    width: 100%;
    font-size: 20px;
    padding: 16px;
    border: 2px solid #999;
    border-radius: 10px;
    margin-bottom: 16px;
  }
  .sorgu-btn {
    width: 100%;
    min-height: 60px;
    font-size: 20px;
    font-weight: 700;
    border: none;
    border-radius: 12px;
    background: #08519c;
    color: #fff;
    cursor: pointer;
  }
  .hata-sorgu {
    background: #fdecec;
    border: 2px solid #c81e1e;
    color: #8a1414;
    border-radius: 10px;
    padding: 14px 16px;
    font-size: 18px;
    font-weight: 600;
    margin-bottom: 20px;
  }
  .sonuc-kutu {
    background: #eaf1fb;
    border: 2px solid #08519c;
    border-radius: 12px;
    padding: 18px 20px;
    margin-bottom: 22px;
    font-size: 18px;
  }
  .sonuc-kutu p { margin: 6px 0; }
  .geri-link { display: block; margin-top: 20px; font-size: 17px; text-align: center; }
  .geri-link a { color: #08519c; font-weight: 700; }
</style>
</head>
<body>
<div class="card">
  <h1>🔎 Şikayet Sorgula</h1>

  {% if hata %}
  <div class="hata-sorgu">{{ hata }}</div>
  {% endif %}

  {% if sonuc %}
  <div class="sonuc-kutu">
    <p><b>Kod:</b> {{ sonuc.takip_kodu }}</p>
    <p><b>Kategori:</b> {{ sonuc.kategori }}</p>
    <p><b>Durum:</b> {{ sonuc.durum }}</p>
    <p><b>Detay:</b> {{ sonuc.aciklama }}</p>
  </div>
  {% endif %}

  <form method="get" action="/sorgula">
    <label for="kod">Takip Kodunuz</label>
    <input type="text" id="kod" name="kod" placeholder="#SB-1234" value="{{ kod_ham or '' }}" required>
    <button type="submit" class="sorgu-btn">SORGULA</button>
  </form>

  <p class="geri-link"><a href="/">⬅ Şikayet Formuna Dön</a></p>
</div>
</body>
</html>
"""

# --- KVKK ONAY YARDIMCI FONKSİYONU ---
def kvkk_onay_klavyesi():
    kb = [[InlineKeyboardButton("✅ Kabul Ediyorum, Devam Et", callback_data="kvkk_kabul")]]
    dis_url = os.getenv("RENDER_EXTERNAL_URL")
    if dis_url:
        kb.append([InlineKeyboardButton("📄 Aydınlatma Metnini Oku", url=f"{dis_url}/kvkk")])
    return InlineKeyboardMarkup(kb)

KVKK_MESAJI = (
    "🔒 *Kişisel Verilerinizin Korunması Hakkında*\n\n"
    "Şikayetinizi işleyebilmemiz için ad soyad, daire bilginiz ve şikayet "
    "içeriğiniz kaydedilecektir. Bu veriler yurt dışında bulunan "
    "sunucularda barındırılmaktadır.\n\n"
    "Devam etmek için aşağıdaki butona basarak bu duruma açık rıza vermeniz "
    "gerekmektedir."
)

# --- CONVERSATION FONKSİYONLARI ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    if str(chat_id) == str(YONETICI_ID):
        await update.message.reply_text("👮‍♂️ Yönetici paneline hoş geldiniz. /panel yazın.")
        return ConversationHandler.END
    res = supabase.table("sakinler").select("*").eq("telegram_id", str(chat_id)).execute()
    if res.data:
        sakin = res.data[0]
        if sakin.get("kvkk_onay"):
            await update.message.reply_text("👋 Tekrar hoş geldiniz!", reply_markup=ana_menu_klavyesi())
            await update.message.reply_text("Kategori seçin:", reply_markup=kategori_klavyesi())
            return SIKAYET_DETAY
        context.user_data['kvkk_yeni_kayit'] = False
        await update.message.reply_text(KVKK_MESAJI, reply_markup=kvkk_onay_klavyesi(), parse_mode="Markdown")
        return KVKK_ONAY
    context.user_data['kvkk_yeni_kayit'] = True
    await update.message.reply_text(KVKK_MESAJI, reply_markup=kvkk_onay_klavyesi(), parse_mode="Markdown")
    return KVKK_ONAY

async def kvkk_onay_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if context.user_data.get('kvkk_yeni_kayit'):
        await query.edit_message_text("✅ Teşekkürler. Şimdi Adınızı ve Soyadınızı girin:")
        return AD
    supabase.table("sakinler").update({
        "kvkk_onay": True,
        "kvkk_onay_tarihi": datetime.now(timezone.utc).isoformat()
    }).eq("telegram_id", str(query.message.chat_id)).execute()
    await query.edit_message_text("✅ Teşekkürler.")
    await context.bot.send_message(query.message.chat_id, "Ana menü:", reply_markup=ana_menu_klavyesi())
    await context.bot.send_message(query.message.chat_id, "📋 Kategori seçin:", reply_markup=kategori_klavyesi())
    return SIKAYET_DETAY

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
        "daire_no": context.user_data['daire_no'], "kat_blok": update.message.text,
        "kvkk_onay": True, "kvkk_onay_tarihi": datetime.now(timezone.utc).isoformat()
    }).execute()
    await update.message.reply_text("✅ Kayıt tamam!", reply_markup=ana_menu_klavyesi())
    await update.message.reply_text("Kategori seçin:", reply_markup=kategori_klavyesi())
    return SIKAYET_DETAY

async def yeni_sikayet_giris(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📋 Kategori seçin:", reply_markup=kategori_klavyesi())
    return SIKAYET_DETAY

async def sikayetlerim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    res = supabase.table("sikayetler").select("*").eq("sakin_id", int(chat_id)).order("id", desc=True).limit(10).execute()
    if not res.data:
        await update.message.reply_text("Henüz bir şikayetiniz bulunmuyor.", reply_markup=ana_menu_klavyesi())
        return
    satirlar = []
    for s in res.data:
        emoji = "🟢" if s['durum'] == "Çözüldü" else "⏳" if s['durum'] == "İnceleniyor" else "🆕"
        satirlar.append(f"{emoji} `{s['takip_kodu']}` — {s['kategori']}\nDurum: {s['durum']}\nDetay: {s['aciklama']}")
    await update.message.reply_text("📋 *Şikayetleriniz:*\n\n" + "\n\n".join(satirlar), parse_mode="Markdown", reply_markup=ana_menu_klavyesi())

async def kategori_secimi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['kategori'] = query.data
    await query.edit_message_text(f"📝 Seçilen: {query.data}.\n\nŞikayetinizi detaylı yazın:")
    return SIKAYET_DETAY

async def get_sikayet_detay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['aciklama'] = update.message.text
    await update.message.reply_text("📷 Fotoğraf eklemek ister misiniz?", reply_markup=fotograf_sor_klavyesi())
    return FOTOGRAF_SOR

async def sikayeti_kaydet_ve_bildir(chat_id, context: ContextTypes.DEFAULT_TYPE, foto_url):
    sakin = supabase.table("sakinler").select("*").eq("telegram_id", str(chat_id)).execute().data[0]
    aciklama = context.user_data['aciklama']
    kod = takip_kodu_uret()
    supabase.table("sikayetler").insert({
        "sakin_id": int(sakin['telegram_id']), "ad_soyad": sakin['ad_soyad'], "daire_no": sakin['daire_no'],
        "kat_blok": sakin.get('kat_blok', ''), "kategori": context.user_data['kategori'],
        "aciklama": aciklama, "fotograf_url": foto_url, "takip_kodu": kod, "durum": "Beklemede",
        "kvkk_onay": sakin.get('kvkk_onay', True), "kvkk_onay_tarihi": sakin.get('kvkk_onay_tarihi')
    }).execute()
    await context.bot.send_message(
        chat_id, f"✅ Şikayetiniz alındı! Takip kodu: `{kod}`",
        parse_mode="Markdown", reply_markup=ana_menu_klavyesi()
    )
    msg = f"🔔 **Yeni Şikayet**\nKod: `{kod}`\nSakin: {sakin['ad_soyad']}\nDetay: {aciklama}"
    if foto_url:
        await context.bot.send_photo(chat_id=YONETICI_ID, photo=foto_url, caption=msg, parse_mode="Markdown")
    else:
        await context.bot.send_message(chat_id=YONETICI_ID, text=msg, parse_mode="Markdown")

async def foto_sor_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "foto_hayir":
        await query.edit_message_text("Şikayetiniz kaydediliyor...")
        await sikayeti_kaydet_ve_bildir(query.message.chat_id, context, None)
        return ConversationHandler.END
    await query.edit_message_text("📷 Lütfen fotoğrafı gönderin (galeri veya kameradan seçebilirsiniz):")
    return FOTOGRAF_SOR

async def get_sikayet_fotografi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    foto_url = await upload_photo_to_supabase(update.message.photo[-1].file_id, context)
    await sikayeti_kaydet_ve_bildir(update.message.chat_id, context, foto_url)
    return ConversationHandler.END

# --- YÖNETİCİ PANELİ ---
async def yonetici_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    yeni = supabase.table("sikayetler").select("*", count='exact').eq("durum", "Beklemede").execute().count
    inceleme = supabase.table("sikayetler").select("*", count='exact').eq("durum", "İnceleniyor").execute().count
    kb = [[InlineKeyboardButton(f"🆕 Yeni ({yeni})", callback_data="liste_yeni"), InlineKeyboardButton(f"⏳ İnceleme ({inceleme})", callback_data="liste_inceleme")]]
    if update.callback_query: await update.callback_query.edit_message_text("⚙️ Yönetici Paneli:", reply_markup=InlineKeyboardMarkup(kb))
    else: await update.message.reply_text("⚙️ Yönetici Paneli:", reply_markup=InlineKeyboardMarkup(kb))

async def panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "liste_yeni" or query.data == "liste_inceleme":
        d_map = {"liste_yeni": "Beklemede", "liste_inceleme": "İnceleniyor"}
        durum = d_map[query.data]
        items = supabase.table("sikayetler").select("*").eq("durum", durum).execute().data
        kb = [[InlineKeyboardButton(f"{s['takip_kodu']} | {s['ad_soyad']}", callback_data=f"detay_{s['takip_kodu']}")] for s in items]
        kb.append([InlineKeyboardButton("⬅️ Ana Menü", callback_data="liste_menu")])
        await query.edit_message_text(f"📊 {durum} Şikayetler:", reply_markup=InlineKeyboardMarkup(kb))
    elif query.data == "liste_menu": await yonetici_panel(update, context)
    elif query.data.startswith("detay_"):
        kod = query.data.split("_")[1]
        s = supabase.table("sikayetler").select("*").eq("takip_kodu", kod).execute().data[0]
        # Hangi listeden geldiğini anlamak için mevcut durumu yakalıyoruz
        donulecek_liste = "liste_inceleme" if s['durum'] == "İnceleniyor" else "liste_yeni"

        txt = f"📋 **{kod}**\n👤 {s['ad_soyad']}\n🏠 {s['daire_no']}\n📝 {s['aciklama']}\n🟢 {s['durum']}"
        kb = [
            [InlineKeyboardButton("⏳ İncelemeye Al", callback_data=f"durum_inceleme_{kod}"),
             InlineKeyboardButton("✅ Çözüldü", callback_data=f"durum_cozuldu_{kod}")],
            [InlineKeyboardButton("⬅️ Listeye Dön", callback_data=donulecek_liste)] # Dinamik dönüş
        ]
        try: await query.message.delete()
        except: pass
        if s.get('fotograf_url'): await context.bot.send_photo(query.message.chat_id, s['fotograf_url'], caption=txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        else: await context.bot.send_message(query.message.chat_id, txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif query.data.startswith("durum_"):
        _, yeni, kod = query.data.split("_")
        d = "İnceleniyor" if yeni == "inceleme" else "Çözüldü"
        supabase.table("sikayetler").update({"durum": d}).eq("takip_kodu", kod).execute()
        s = supabase.table("sikayetler").select("sakin_id").eq("takip_kodu", kod).execute().data[0]
        await context.bot.send_message(int(s['sakin_id']), f"🔔 Şikayet ({kod}) durumu: {d} oldu.")
        await yonetici_panel(update, context)

async def bot_hata_yakalayici(update, context):
    # Bot handler'larından biri (conv, panel_callback vb.) beklenmedik bir
    # hata fırlatırsa buraya düşer — normalde sessizce loglara gömülüp
    # kaybolurdu, artık yöneticiye anında Telegram mesajı olarak da gider.
    logging.error("Bot içinde beklenmeyen hata", exc_info=context.error)
    if YONETICI_ID:
        try:
            await context.bot.send_message(
                chat_id=YONETICI_ID,
                text=f"⚠️ Bot içinde beklenmeyen bir hata oluştu:\n{type(context.error).__name__}: {context.error}"
            )
        except Exception:
            logging.error("Hata bildirimi gönderilemedi", exc_info=True)

# --- BAŞLATICI ---
flask_app = Flask(__name__)
# Render bir proxy arkasında çalıştığı için gerçek istemci IP'sini
# X-Forwarded-For'dan almak üzere ProxyFix şart — yoksa rate-limit
# herkesi tek IP (Render'ın proxy'si) sanıp ilk kullanıcıda dolar.
flask_app.wsgi_app = ProxyFix(flask_app.wsgi_app, x_for=1)

limiter = Limiter(
    get_remote_address,
    app=flask_app,
    default_limits=[],
    storage_uri="memory://"
)

application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

conv = ConversationHandler(entry_points=[
        CommandHandler('start', start),
        MessageHandler(filters.Text([YENI_SIKAYET_BUTONU]), yeni_sikayet_giris)
    ],
    states={KVKK_ONAY:[CallbackQueryHandler(kvkk_onay_callback, pattern="^kvkk_kabul$")],
            AD:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_ad)], DAIRE:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_daire)],
            KAT_BLOK:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_kat_blok)],
            SIKAYET_DETAY:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_sikayet_detay)],
            FOTOGRAF_SOR:[CallbackQueryHandler(foto_sor_callback, pattern="^foto_(evet|hayir)$"), MessageHandler(filters.PHOTO, get_sikayet_fotografi)]},
    fallbacks=[CommandHandler('start', start)])

application.add_handler(conv)
application.add_handler(CommandHandler('panel', yonetici_panel))
application.add_handler(MessageHandler(filters.Text([SIKAYETLERIM_BUTONU]), sikayetlerim))
application.add_handler(CallbackQueryHandler(kategori_secimi, pattern="^(Asansör|Aydınlatma|Temizlik|Diğer)$"))
application.add_handler(CallbackQueryHandler(panel_callback))
application.add_error_handler(bot_hata_yakalayici)

bot_loop = asyncio.new_event_loop()
flask_app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # foto yüklemede 5MB üst sınır

async def _web_sikayet_bildir(kod, ad_soyad, daire_no, aciklama, foto_url):
    msg = f"🔔 **Yeni Şikayet (Web)**\nKod: `{kod}`\nSakin: {ad_soyad}\nDaire: {daire_no}\nDetay: {aciklama}"
    if foto_url:
        await application.bot.send_photo(chat_id=YONETICI_ID, photo=foto_url, caption=msg, parse_mode="Markdown")
    else:
        await application.bot.send_message(chat_id=YONETICI_ID, text=msg, parse_mode="Markdown")

@flask_app.route("/")
def index():
    return render_template_string(HTML_FORM)

@flask_app.route("/kvkk")
def kvkk_metni():
    return render_template_string(HTML_KVKK)

@flask_app.route("/sorgula")
def sorgula():
    kod_ham = request.args.get("kod", "").strip()
    sonuc = None
    hata = None
    if kod_ham:
        kod = kod_normallestir(kod_ham)
        res = supabase.table("sikayetler").select("*").eq("takip_kodu", kod).execute()
        if res.data:
            sonuc = res.data[0]
        else:
            hata = "Bu koda ait bir şikayet bulunamadı. Kodu kontrol edip tekrar deneyin."
    return render_template_string(HTML_SORGULA, sonuc=sonuc, hata=hata, kod_ham=kod_ham)

@flask_app.route("/sikayet", methods=["POST"])
@limiter.limit("3 per 5 minutes")
def sikayet_al():
    # Honeypot: gerçek kullanıcılar bu görünmez alanı hiç görmez/doldurmaz.
    # Doluysa muhtemelen bot — fark ettirmeden sahte bir başarı dönüyoruz.
    if request.form.get("web_sitesi", "").strip():
        return jsonify({"success": True, "takip_kodu": takip_kodu_uret()})

    ad_soyad = request.form.get("ad_soyad", "").strip()
    daire_no = request.form.get("daire_no", "").strip()
    kat_blok = request.form.get("kat_blok", "").strip()
    kategori = request.form.get("kategori", "").strip()
    aciklama = request.form.get("aciklama", "").strip()
    acik_riza = request.form.get("acik_riza") == "on"
    foto = request.files.get("fotograf")

    if not ad_soyad or not daire_no or not kategori or not aciklama:
        return jsonify({"success": False, "error": "Lütfen zorunlu alanları doldurun."}), 400

    if not acik_riza:
        return jsonify({"success": False, "error": "Devam etmek için KVKK açık rıza onay kutusunu işaretlemeniz gerekiyor."}), 400

    foto_url = None
    if foto and foto.filename:
        foto_url = upload_web_photo_to_supabase(foto)

    kod = takip_kodu_uret()
    supabase.table("sikayetler").insert({
        "ad_soyad": ad_soyad, "daire_no": daire_no, "kat_blok": kat_blok,
        "kategori": kategori, "aciklama": aciklama, "fotograf_url": foto_url,
        "takip_kodu": kod, "durum": "Beklemede",
        "kvkk_onay": True, "kvkk_onay_tarihi": datetime.now(timezone.utc).isoformat()
    }).execute()

    asyncio.run_coroutine_threadsafe(
        _web_sikayet_bildir(kod, ad_soyad, daire_no, aciklama, foto_url), bot_loop
    )

    return jsonify({"success": True, "takip_kodu": kod})

@flask_app.errorhandler(429)
def rate_limit_asildi(e):
    return jsonify({"success": False, "error": "Çok fazla deneme yapıldı. Lütfen birkaç dakika sonra tekrar deneyin."}), 429

@flask_app.errorhandler(Exception)
def beklenmeyen_web_hatasi(e):
    # 404, 429 gibi normal HTTP durumları (HTTPException) kendi
    # handler'larına veya varsayılan davranışına bırakılır — burada
    # sadece gerçekten beklenmedik (500'e sebep olan) hatalar yakalanır.
    if isinstance(e, HTTPException):
        return e
    logging.error("Web tarafında beklenmeyen hata", exc_info=True)
    if YONETICI_ID:
        try:
            asyncio.run_coroutine_threadsafe(
                application.bot.send_message(
                    chat_id=YONETICI_ID,
                    text=f"⚠️ Web formunda beklenmeyen bir hata oluştu:\n{type(e).__name__}: {e}"
                ),
                bot_loop
            )
        except Exception:
            logging.error("Hata bildirimi gönderilemedi", exc_info=True)
    return jsonify({"success": False, "error": "Beklenmeyen bir hata oluştu, lütfen daha sonra tekrar deneyin."}), 500

def bot_motoru_baslat():
    asyncio.set_event_loop(bot_loop)
    bot_loop.run_until_complete(application.initialize())

    varsayilan_komutlar = [BotCommand("start", "Botu Başlat / Ana Menü")]
    bot_loop.run_until_complete(application.bot.set_my_commands(varsayilan_komutlar))

    if YONETICI_ID:
        yonetici_komutlari = [
            BotCommand("start", "Botu Başlat / Ana Menü"),
            BotCommand("panel", "Yönetici Paneli")
        ]
        bot_loop.run_until_complete(
            application.bot.set_my_commands(
                yonetici_komutlari,
                scope=BotCommandScopeChat(chat_id=int(YONETICI_ID))
            )
        )

    dis_url = os.getenv("RENDER_EXTERNAL_URL")
    if dis_url:
        webhook_url = f"{dis_url}/webhook"
        bot_loop.run_until_complete(application.bot.set_webhook(url=webhook_url))
        print(f"✅ Webhook ayarlandı: {webhook_url}")
    else:
        print("⚠️ RENDER_EXTERNAL_URL bulunamadı — webhook otomatik ayarlanamadı.")

    bot_loop.run_forever()

@flask_app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    asyncio.run_coroutine_threadsafe(application.process_update(update), bot_loop)
    return "OK", 200

if __name__ == '__main__':
    t = threading.Thread(target=bot_motoru_baslat, daemon=True)
    t.start()
    print("🤖 Telegram bot motoru (webhook modu) başlatıldı.")

    port = int(os.getenv("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)
