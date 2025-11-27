# modules/spam_blast.py
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
import os

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

    spam_sql.add_list(nama, "basic", "-", 0)
    spam_sql.add_groups_to_list(nama, grups)

    await event.edit(f"✓ Berhasil menambahkan `{len(grups)}` grup ke list `{nama}`.")

active_spams = {}

@ayiin_cmd(pattern=r"onspam (\d+)\s+(\S+)\s+([\s\S]+)")
async def onspamloop(event):
    delay = int(event.pattern_match.group(1))
    nama  = event.pattern_match.group(2).strip()
    teks  = event.pattern_match.group(3).strip()

    # ambil reply media -> SIMPAN PATH
    reply = await event.get_reply_message()
    media_path = None

    if reply and reply.media:
        save_dir = "./spam_media"
        os.makedirs(save_dir, exist_ok=True)

        media_path = await reply.download_media(file=save_dir)

    # ================ UPDATE LIST ================
    spam_sql.update_list(nama, "spam", delay, teks)

    # update media hanya kalau ada
    if media_path:
        spam_sql.update_media(nama, media_path)

    spam_sql.set_active(nama, True)

    if nama in active_spams:
        return await event.edit(f"∅ spam `{nama}` sudah berjalan!")

    await event.edit(f"⎋ spam basic `{nama}` sedang dimulai!")

    # ================= LOOP ================
    async def spam_loop():
        loop_ke = spam_sql.get_loop(nama)

        try:
            while True:
                loop_ke += 1
                spam_sql.set_loop(nama, loop_ke)

                grups = spam_sql.get_groups(nama)
                berhasil, gagal = []

                data = spam_sql.get_list(nama)
                media_path_local = data.media if data else None
                teks_local = data.content if data else teks

                berhasil, gagal = [], []

                for g in grups:
                    try:
                        if media_path_local:
                            await event.client.send_file(
                                g,
                                media_path_local,
                                caption=teks_local or ""
                            )
                        else:
                            await event.client.send_message(g, teks_local)

                        berhasil.append(g)

                    except Exception as e:
                        gagal.append((g, str(e)))

                # ============== LOG ==============
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
                except:
                    pass

                await asyncio.sleep(delay)

        except asyncio.CancelledError:
            print(f"[SPAM] Loop `{nama}` dihentikan.")

    active_spams[nama] = asyncio.create_task(spam_loop())

@ayiin_cmd(pattern=r"onfw (\d+)\s+(\S+)\s+(https?://t\.me/[^\s]+)")
async def onfwloop(event):
    delay = int(event.pattern_match.group(1))
    nama  = event.pattern_match.group(2).strip()
    link  = event.pattern_match.group(3).strip()

    spam_sql.update_list(nama, "forward", delay, link)
    spam_sql.set_active(nama, True)

    if nama in active_spams:
        return await event.edit(f"∅ spam forward `{nama}` sudah berjalan!")

    m = re.match(r"https://t.me/(c/)?(-?\d+|\w+)/(\d+)", link)
    if not m:
        return await event.edit("✘ Link tidak valid!")

    chat_part, msg_id = m.group(2), int(m.group(3))
    chat_id = int("-100"+chat_part) if m.group(1)=="c/" else \
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

                log = (
                    f"⎈ FORWARD `{nama}`\n"
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
        spam_sql.set_active(nama, False)
    if task:
        task.cancel()
        active_spams.pop(nama)
        await event.edit(f"∅ Spam `{nama}` berhasil dihentikan.")
    else:
        await event.edit(f"✘ Spam `{nama}` tidak sedang berjalan.")

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

# -----------------------------
# AUTO RESUME AT STARTUP
# -----------------------------
async def auto_resume_spam_startup():
    await asyncio.sleep(10)
    lists = spam_sql.get_all_lists()
    resumed = []

    for l in lists:
        if not l.is_active:
            continue

        grups = spam_sql.get_groups(l.name)
        if not grups:
            continue

        media_path = l.media  # PATH string
        # cek apakah media_path masih ada di storage (Heroku bisa hapus file)

        if media_path and not os.path.exists(media_path):
            print(f"[AUTO-RESUME] Media hilang: {media_path}")
            spam_sql.update_media(nama, None)
            media_path = None
    
        if l.type == "basic":
            async def loop_resume_spam(nama, teks, delay, grups, media_path):
                loop_ke = spam_sql.get_loop(nama)
                while True:
                    loop_ke += 1
                    spam_sql.set_loop(nama, loop_ke)
                    berhasil, gagal = [], []

                    for g in grups:
                        try:
                            if media_path:
                                await bot.send_file(g, media_path, caption=teks or "")
                            else:
                                await bot.send_message(g, teks)
                            berhasil.append(g)
                        except Exception as e:
                            gagal.append((g, str(e)))

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
                        log += "\n".join(f"• {x} karena {err}" for x, err in gagal)
                    else:
                        log += "• tidak ada"

                    try:
                        await bot.send_message(BOTLOG_CHATID, log)
                    except Exception as logerr:
                        print(f"[AUTO RESUME SPAM LOG ERROR] {logerr}")

                    await asyncio.sleep(delay)

            active_spams[l.name] = asyncio.create_task(
                loop_resume_spam(l.name, l.content, l.delay, grups, media_path)
            )
            resumed.append(l.name)

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

                        log = (
                            f"⎈ FORWARD `{nama}`\n\n"
                            f"✓ Berhasil Putaran ke : {loop_ke}\n"
                        )

                        if berhasil:
                            log += "\n".join(f"• {x}" for x in berhasil)
                        else:
                            log += "• tidak ada"

                        log += "\n\n✘ Gagal:\n"
                        if gagal:
                            log += "\n".join(f"• {x} karena {err}" for x, err in gagal)
                        else:
                            log += "• tidak ada"

                        try:
                            await bot.send_message(BOTLOG_CHATID, log)
                        except Exception as logerr:
                            print(f"[AUTO RESUME FW LOG ERROR] {logerr}")

                        await asyncio.sleep(delay)

                active_spams[l.name] = asyncio.create_task(
                    loop_resume_forward(l.name, msg, l.delay, grups)
                )
                resumed.append(l.name)
            except Exception as e:
                print(f"[AutoResume FW Error] {e}")

    # notif resume summary
    if resumed:
        text = "♻️ Spam Loop sudah aktif kembali:\n" + "\n".join(f"• {x}" for x in resumed)
        try:
            await bot.send_message(BOTLOG_CHATID, text)
        except Exception:
            print(text)

# jalankan auto resume
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
        \n    - Delay dalam detik (angka)\
        \n    - Bisa spam media (reply dulu pesan yang ingin disebar)\
        \n    - Media disimpan sebagai file path agar auto-resume bisa mengirim media kembali\
        \n    - Gunakan dengan bijak, spam berlebihan bisa dibanned telegram!"
    }
                )
