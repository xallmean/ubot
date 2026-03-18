import time
import asyncpg
from datetime import datetime
from telethon import events
from AyiinXd import CMD_HANDLER as cmd
from AyiinXd import CMD_HELP, DB_URI, bot
from AyiinXd.ayiin import ayiin_cmd
import asyncio

GROUP_ID_TUJUAN = -1002412201139  # ganti dengan grup log kamu

def konversi_ke_detik(durasi: str) -> int:
    if durasi == "lifetime":
        return -1
    jumlah = ''.join(filter(str.isdigit, durasi))
    satuan = ''.join(filter(str.isalpha, durasi))
    if not jumlah or not satuan:
        return 0
    jumlah = int(jumlah)
    konversi = {
        "menit": 60,
        "jam": 3600,
        "hari": 86400,
        "minggu": 7 * 86400,
        "bulan": 30 * 86400,
        "tahun": 365 * 86400,
    }
    return jumlah * konversi.get(satuan, 0)

# ==================== CEK DURASI MANUAL ====================
@ayiin_cmd(pattern="cekdurasi$")
async def _(event):
    try:
        conn = await asyncpg.connect(DB_URI)
        # bikin tabel & kolom notif_habis kalau belom ada
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_info (
                id INTEGER PRIMARY KEY,
                start_time BIGINT,
                jenis TEXT
            );
        """)
        await conn.execute("""
            ALTER TABLE bot_info
            ADD COLUMN IF NOT EXISTS notif_habis BOOLEAN DEFAULT FALSE;
        """)

        row = await conn.fetchrow("SELECT start_time, jenis FROM bot_info WHERE id=1")
        now = int(time.time())

        if not row:
            await event.edit("**Durasi belum disetel. Silakan hubungi admin.**")
            await conn.close()
            return

        teks = await buat_teks_durasi(row['jenis'], row['start_time'], now)
        await event.edit(teks)
        await conn.close()
    except Exception as e:
        await event.edit(f"**Terjadi kesalahan:** `{e}`")

# ==================== BANTUAN MEMBUAT TEKS DURASI ====================
async def buat_teks_durasi(jenis, start_time, now):
    if jenis == "lifetime":
        return (
            "𝗨𝘀𝗲𝗿𝗯𝗼𝘁 𝗔𝗸𝘁𝗶𝗳!\n\n"
            f"**Durasi:** `Lifetime`\n"
            f"**Sisa Durasi:** `Tidak terbatas`\n"
            f"**Habis Tanggal:** `-`"
        )
    total_durasi = konversi_ke_detik(jenis)
    sisa = total_durasi - (now - start_time)
    if sisa <= 0:
        return "**Durasi kamu sudah habis. Silakan hubungi @jPipis untuk perpanjangan userbot.**"

    habis_timestamp = start_time + total_durasi
    habis_tanggal = datetime.fromtimestamp(habis_timestamp).strftime("%d %B %Y")
    days = sisa // 86400
    hours = (sisa % 86400) // 3600
    minutes = (sisa % 3600) // 60
    seconds = sisa % 60

    return (
        "𝗨𝘀𝗲𝗿𝗯𝗼𝘁 𝗔𝗸𝘁𝗶𝗳!\n\n"
        f"**Durasi:** `{jenis}`\n"
        f"**Sisa Durasi:** `{days} hari, {hours} jam, {minutes} menit, {seconds} detik`\n"
        f"**Habis Tanggal:** `{habis_tanggal}`"
    )

# ==================== AUTO KIRIM DURASI SAAT JOIN ====================
@bot.on(events.ChatAction)
async def handler_auto_join(event):
    if event.user_joined or event.user_added:
        me = await bot.get_me()
        if event.user_id == me.id and event.chat_id == GROUP_ID_TUJUAN:
            await kirim_durasi(event.chat_id)

# ==================== AUTO KIRIM DURASI SAAT STARTUP ====================
async def send_durasi_startup():
    while not bot.is_connected():
        print("[LOG] Menunggu bot connect...")
        await asyncio.sleep(1)
    print("[LOG] Bot sudah connect, kirim durasi startup...")
    await kirim_durasi(GROUP_ID_TUJUAN)

# ==================== FUNGSI KIRIM DURASI ====================
async def kirim_durasi(chat_id):
    try:
        conn = await asyncpg.connect(DB_URI)
        await conn.execute("""
            ALTER TABLE bot_info
            ADD COLUMN IF NOT EXISTS notif_habis BOOLEAN DEFAULT FALSE;
        """)

        row = await conn.fetchrow("SELECT start_time, jenis, notif_habis FROM bot_info WHERE id=1")
        now = int(time.time())

        if not row:
            await bot.send_message(chat_id, "**Durasi belum disetel.**")
            await conn.close()
            return

        total_durasi = konversi_ke_detik(row['jenis'])
        sisa = total_durasi - (now - row['start_time'])

        if sisa <= 0 and not row.get('notif_habis', False):
            await bot.send_message(chat_id, "**Durasi kamu sudah habis. Silakan hubungi @jPipis untuk perpanjangan userbot.**")
            await conn.execute("UPDATE bot_info SET notif_habis = TRUE WHERE id=1")
        elif sisa > 0:
            teks = await buat_teks_durasi(row['jenis'], row['start_time'], now)
            await bot.send_message(chat_id, teks)

        await conn.close()
    except Exception as e:
        print(f"[ERROR] Gagal kirim durasi: {e}")
        await bot.send_message(chat_id, f"**Gagal kirim durasi:** `{e}`")

# Jalankan task startup
bot.loop.create_task(send_durasi_startup())

# ==================== HELP ====================
CMD_HELP.update({
    "cek_durasi": f"**Plugin :** `cek_durasi`\
    \n\n  »  **Perintah :** `{cmd}cekdurasi`\
    \n  »  **Fungsi :** Menampilkan durasi aktif userbot, dan otomatis kirim saat join grup & saat bot start.\
"
})
