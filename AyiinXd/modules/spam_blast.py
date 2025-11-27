from AyiinXd import CMD_HANDLER as cmd
from AyiinXd import CMD_HELP
from AyiinXd.ayiin import ayiin_cmd
from AyiinXd.modules.sql_helper import spam_sql
from AyiinXd.modules.sql_helper import SESSION
from asyncio import sleep
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.messages import GetMessagesRequest
from telethon.tl.types import InputPeerChannel, InputMessageID
from telethon.errors import FloodWaitError
from datetime import datetime
from AyiinXd import BOTLOG_CHATID
from AyiinXd import bot
from telethon import events
import re
import asyncio

@ayiin_cmd(pattern=r"setgrup (\S+)\s+([\s\S]+)")
async def setgrup(event):
    nama = event.pattern_match.group(1).strip()
    raw_input = event.pattern_match.group(2).strip()

    grups = []
    for line in raw_input.split():
        line = line.strip()
        if not line:
            continue
        if line.startswith("https://t.me/"):
            username = line.replace("https://t.me/", "").strip("/")
            if not username.startswith("@"):
                username = f"@{username}"
            grups.append(username)
        elif line.startswith("@"):
            grups.append(line)
        else:
            grups.append(f"@{line}")

    if not grups:
        return await event.edit("✘ Grup tidak ditemukan.")

    # ⬇⬇⬇ Fix-nya di sini
    spam_sql.add_list(nama, "biasa", "-", 0)  # Tambahkan data ke spam_list
    spam_sql.add_groups_to_list(nama, grups)  # Tambahkan grup ke spam_group

    await event.edit(f"✓ Berhasil menambahkan `{len(grups)}` grup ke list `{nama}`.")
active_spams = {}

@ayiin_cmd(pattern=r"onspam (\d+)\s+(\S+)\s+([\s\S]+)")
async def onspamloop(event):
    delay = int(event.pattern_match.group(1))
    nama  = event.pattern_match.group(2).strip()
    teks  = event.pattern_match.group(3).strip()

    # =============== AMBIL MEDIA DARI REPLY (SEBAGAI BYTES) ===============
    reply = await event.get_reply_message()
    media_bytes = None
    if reply and reply.media:
        media_bytes = await reply.download_media(bytes)

    # SIMPAN KE SQL
    spam_sql.update_list(
        nama,
        type="basic",
        delay=delay,
        content=teks,
        media=media_bytes,
        active=True
    )

    if nama in active_spams:
        return await event.edit(f"∅ spam `{nama}` sudah berjalan!")

    await event.edit(f"⎋ spam basic `{nama}` sedang dimulai!")

    # =============== LOOP SPAM ===============
    async def spam_loop():
        loop_ke = spam_sql.get_loop(nama)

        try:
            while True:
                loop_ke += 1
                spam_sql.set_loop(nama, loop_ke)

                grups = spam_sql.get_groups(nama)
                berhasil, gagal = [], []

                for g in grups:
                    try:
                        # === KIRIM MEDIA ===
                        if media_bytes:
                            await event.client.send_file(
                                g,
                                media_bytes,
                                caption=teks or "",
                                force_document=False
                            )

                        # === KIRIM TEKS SAJA ===
                        else:
                            await event.client.send_message(g, teks)

                        berhasil.append(g)

                    except Exception as e:
                        gagal.append((g, str(e)))

                # =============== LOG KE BOTLOG ===============
                log = (
                    f"⎈ SPAM BASIC `{nama}`\n"
                    f"🌀 Loop ke: {loop_ke}\n\n"
                )

                if berhasil:
                    log += "✓ Berhasil:\n" + "\n".join(f"• {x}" for x in berhasil)
                else:
                    log += "✓ Berhasil:\n• tidak ada"

                log += "\n\n✘ Gagal:\n"
                if gagal:
                    log += "\n".join(f"• {x} karena {err}" for x, err in gagal)
                else:
                    log += "• tidak ada"

                try:
                    await event.client.send_message(BOTLOG_CHATID, log)
                except Exception as logerr:
                    print(f"[SPAM LOG ERROR] {logerr}")

                await asyncio.sleep(delay)

        except asyncio.CancelledError:
            print(f"[SPAM] Loop `{nama}` dihentikan.")

    # JALANKAN TASK
    active_spams[nama] = asyncio.create_task(spam_loop())
    
@ayiin_cmd(pattern=r"onfw (\d+)\s+(\S+)\s+(https?://t\.me/[^\s]+)")
async def onfwloop(event):
    delay = int(event.pattern_match.group(1))
    nama  = event.pattern_match.group(2).strip()
    link  = event.pattern_match.group(3).strip()

    spam_sql.update_list(nama, "forward", delay, link)
    data = spam_sql.get_list(nama)
    data.is_active = True
    SESSION.commit()

    if nama in active_spams:
        return await event.edit(f"∅ spam forward `{nama}` sudah berjalan!")

    m = re.match(r"https://t.me/(c/)?(-?\d+|\w+)/(\d+)", link)
    if not m:
        return await event.edit("✘ Link tidak valid!")

    chat_part, msg_id = m.group(2), int(m.group(3))
    chat_id = int("-100" + chat_part) if m.group(1) == "c/" else \
              (int(chat_part) if chat_part.isdigit() else chat_part)

    msg = await event.client.get_messages(chat_id, ids=msg_id)
    await event.edit(f"⎋ forward `{nama}` sedang dimulai!")

    async def forward_loop():
        loop_ke = spam_sql.get_loop(nama)

        try:
            while True:
                loop_ke += 1
                spam_sql.set_loop(nama, loop_ke)

                grups = spam_sql.get_groups(nama)
                berhasil, gagal = [], []

                for g in grups:
                    try:
                        await event.client.forward_messages(g, msg)
                        berhasil.append(g)
                    except Exception as e:
                        gagal.append((g, str(e)))

                log = f"⎈ **FORWARD `{nama}`**\n"
                log += f"🌀 **Loop ke:** `{loop_ke}`\n\n"

                if berhasil:
                    log += "✓ **Berhasil:**\n" + "\n".join(f"• `{x}`" for x in berhasil)
                if gagal:
                    log += "\n\n✘ **Gagal:**\n" + "\n".join(
                        f"• `{x}` karena `{e}`"
                        for x, e in gagal
                    )

                try:
                    await event.client.send_message(BOTLOG_CHATID, log)
                except Exception as logerr:
                    print(f"[FW LOG ERROR] {logerr}")

                await asyncio.sleep(delay)

        except asyncio.CancelledError:
            print(f"[FW] Loop `{nama}` dihentikan.")

    active_spams[nama] = asyncio.create_task(forward_loop())


@ayiin_cmd(pattern=r"stopspam (.+)")
async def stopspam(event):
    nama = event.pattern_match.group(1).strip()
    task = active_spams.get(nama)
    data = spam_sql.get_list(nama)
    if data:
        data.is_active = False              # ⬅️ matikan auto resume
        SESSION.commit()
        
    if not task:
        return await event.edit(f"✘ Spam `{nama}` tidak sedang berjalan.")
    task.cancel()
    active_spams.pop(nama)
    await event.edit(f"∅ Spam `{nama}` berhasil dihentikan.")
    
@ayiin_cmd(pattern="listspam$")
async def list_all_spam(event):
    lists = spam_sql.get_all_lists()
    if not lists:
        return await event.edit("✘ Tidak ada data spam tersimpan.")

    teks = "**⎉ Daftar List Spam:**\n\n"
    for l in lists:
        grups = spam_sql.get_groups(l.name)
        status = "Aktif ✓" if l.name in active_spams else "Nonaktif ❌"
        teks += f"• `{l.name}` [{l.type}] - {status}\n"
        teks += f"   Grup: {len(grups)} | Delay: {l.delay}s\n\n"
    await event.edit(teks)

@ayiin_cmd(pattern="listsave (.+)")
async def list_save(event):
    nama = event.pattern_match.group(1).strip()
    data = spam_sql.get_list(nama)
    if not data:
        return await event.edit(f"✘ List `{nama}` tidak ditemukan.")

    grups = spam_sql.get_groups(nama)

    me = await event.client.get_me()
    akun_sebar = f"@{me.username}" if me.username else me.first_name

    teks = f"⎉ **List:** `{nama}`\n"
    teks += f"• Jenis : `{data.type}`\n"
    teks += f"• Delay : `{data.delay}` detik\n"
    teks += f"• Grup  : {len(grups)}\n"
    teks += f"• Akun Sebar : {akun_sebar}\n"
    teks += f"• List Sebar:\n{data.content}\n"
    teks += "\n⎋ **Daftar Grup:**\n"
    for g in grups:
        teks += f" - `{g}`\n"
    await event.edit(teks)

@ayiin_cmd(pattern=r"delgrup (.+?) (.+)")
async def delgrup(event):
    nama = event.pattern_match.group(1).strip()
    grup = event.pattern_match.group(2).strip()
    spam_sql.delete_group(nama, grup)
    await event.edit(f"✓ Grup `{grup}` dihapus dari `{nama}`.")

@ayiin_cmd(pattern=r"dellist (.+)")
async def dellist(event):
    nama = event.pattern_match.group(1).strip()
    spam_sql.delete_list(nama)
    await event.edit(f"♺ List `{nama}` dan semua isinya dihapus.")

@ayiin_cmd(pattern="slist$")
async def show_all_spam_lists(event):
    lists = spam_sql.get_all_lists()
    if not lists:
        return await event.edit("✘ Belum ada list yang disimpan.")

    teks = "**♺ Semua Nama List Spam yang Punya Grup:**\n\n"
    count = 0
    for l in lists:
        grups = spam_sql.get_groups(l.name)
        if grups:
            count += 1
            teks += f"• `{l.name}` ({len(grups)} grup)\n"

    if count == 0:
        teks = "✘ Belum ada list yang punya grup."
        
    await event.edit(teks)

import asyncio


async def auto_resume_spam_startup():
    await asyncio.sleep(10)  # kasih jeda koneksi
    lists = spam_sql.get_all_lists()
    resumed = []

    for l in lists:
        if not l.is_active:
            continue

        grups = spam_sql.get_groups(l.name)
        downloaded_bytes = l.media
        if not grups:
            continue

        # ambil media dari SQL
        media_bytes = getattr(l, "media", None)

        if l.type == "basic":

            async def loop_resume_spam(nama, teks, delay, grups, media_bytes):
                loop_ke = spam_sql.get_loop(nama)

                while True:
                    loop_ke += 1
                    spam_sql.set_loop(nama, loop_ke)

                    berhasil, gagal = [], []

                    for g in grups:
                        try:
                            if media_bytes:
                                await bot.send_file(
                                    g,
                                    media_bytes,
                                    caption=teks or "",
                                    force_document=False
                                )
                            else:
                                await bot.send_message(g, teks)

                            berhasil.append(g)

                        except Exception as e:
                            gagal.append((g, str(e)))

                    # LOG TANPA FORMAT MARKDOWN
                    log = (
                        f"⎈ BASIC {nama}\n\n"
                        f"✓ Berhasil Putaran ke : {loop_ke}\n"
                    )

                    if berhasil:
                        log += "\n".join(f"• {x}" for x in berhasil)
                    else:
                        log += "• tidak ada"

                    log += "\n\n✘ Gagal:\n"
                    if gagal:
                        log += "\n".join(f"• {x} karena `{err}`" for x, err in gagal)
                    else:
                        log += "• tidak ada"

                    try:
                        await bot.send_message(BOTLOG_CHATID, log)
                    except Exception as logerr:
                        print(f"[AUTO RESUME SPAM LOG ERROR] {logerr}")

                    await asyncio.sleep(delay)

            active_spams[l.name] = asyncio.create_task(
                loop_resume_spam(l.name, l.content, l.delay, grups, media_bytes)
                    )

        # ======================================================
        # AUTO RESUME FORWARD
        # ======================================================
        elif l.type == "forward":
            try:
                m = re.match(r"https://t.me/(c/)?(-?\d+|\w+)/(\d+)", l.content)
                if not m:
                    continue

                chat_part, msg_id = m.group(2), int(m.group(3))
                chat_id = int("-100" + chat_part) if m.group(1) == "c/" else \
                          (int(chat_part) if chat_part.isdigit() else chat_part)

                msg = await bot.get_messages(chat_id, ids=msg_id)

                async def loop_resume_forward(nama, msg, delay, grups):
                    loop_ke = spam_sql.get_loop(nama)

                    while True:
                        loop_ke += 1
                        spam_sql.set_loop(nama, loop_ke)
                        berhasil, gagal = [], []

                        for g in grups:
                            try:
                                await bot.forward_messages(g, msg)
                                berhasil.append(g)
                            except Exception as e:
                                gagal.append((g, str(e)))

                        # === LOG KE BOTLOG_CHATID ===
                        log = (
                            f"⎈ FORWARD `{nama}`\n\n"
                            f"✓ **Berhasil Putaran ke :** `{loop_ke}`\n"
                        )

                        if berhasil:
                            log += "\n".join(f"• `{x}`" for x in berhasil)
                        else:
                            log += "• tidak ada"

                        log += "\n\n✘ **Gagal:**\n"
                        if gagal:
                            log += "\n".join(f"• `{x}` karena `{err}`" for x, err in gagal)
                        else:
                            log += "• tidak ada"

                        try:
                            await bot.send_message(BOTLOG_CHATID, log, parse_mode="md")
                        except Exception as logerr:
                            print(f"[AUTO RESUME FW LOG ERROR] {logerr}")

                        await asyncio.sleep(delay)

                active_spams[l.name] = asyncio.create_task(
                    loop_resume_forward(l.name, msg, l.delay, grups)
                )
                resumed.append(l.name)

            except Exception as e:
                print(f"[AutoResume FW Error] {e}")

    # ======================================================
    # NOTIF AUTO RESUME
    # ======================================================
    if resumed:
        text = "♻️ **Spam Loop sudah aktif kembali!:**\n" + "\n".join(
            f"• `{x}`" for x in resumed
        )
        try:
            await bot.send_message(BOTLOG_CHATID, text)
        except Exception:
            print(text)

# Jalankan otomatis saat userbot start
asyncio.get_event_loop().create_task(auto_resume_spam_startup())
        
CMD_HELP.update(
    {
        "spamloop": f"**Plugin : **`spamloop`\
        \n\n  »  **Perintah :** `{cmd}onspam <delay> <namalist> <teks sebar>`\
        \n  »  **Kegunaan :** Spam teks ke semua grup di list. Bisa reply media juga.\
        \n\n  »  **Perintah :** `{cmd}onfw <delay> <namalist> <link bbc dari channel>`\
        \n  »  **Kegunaan :** Spam forward pesan dari channel ke semua grup di list.\
        \n\n  »  **Perintah :** `{cmd}stopspam <namalist>`\
        \n  »  **Kegunaan :** Memberhentikan spam yang sedang berjalan di list tersebut.\
        \n\n  »  **Perintah :** `{cmd}setgrup <namalist> <@usergrup1> <@usergrup2>`\
        \n  »  **Kegunaan :** Menyimpan banyak grup ke dalam satu list.\
        \n\n  »  **Perintah :** `{cmd}listspam`\
        \n  »  **Kegunaan :** Menampilkan semua list spam yang sedang berjalan.\
        \n\n  »  **Perintah :** `{cmd}listsave <namalist>`\
        \n  »  **Kegunaan :** Menampilkan detail isi list (grup & teks sebar).\
        \n\n  »  **Perintah :** `{cmd}slist`\
        \n  »  **Kegunaan :** Menampilkan semua nama list spam yang tersimpan.\
        \n\n  »  **Perintah :** `{cmd}delgrup <namalist> <@usergrup>`\
        \n  »  **Kegunaan :** Menghapus grup tertentu dari nama list.\
        \n\n  »  **Perintah :** `{cmd}dellist <namalist>`\
        \n  »  **Kegunaan :** Menghapus seluruh list beserta grup & teksnya.\
        \n\n  •  **NOTE :**\
        \n    - Jangan ada spasi di antara `|`\
        \n    - Delay dalam detik (angka)\
        \n    - Bisa spam media (reply dulu pesan yang ingin disebar)\
        \n    - Gunakan dengan bijak, spam berlebihan bisa dibanned telegram!"
    }
    )
