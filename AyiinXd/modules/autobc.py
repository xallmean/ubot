from AyiinXd import CMD_HANDLER as cmd
from AyiinXd import CMD_HELP, BOTLOG_CHATID, bot
from AyiinXd.ayiin import ayiin_cmd
from AyiinXd.modules.sql_helper import autobc_sql
from telethon import events, types
import asyncio, re

active_tasks = {"autobc": None, "autofw": None}

# ================================
# 🔧 PARSE LINK
# ================================
async def parse_tg_link(link):
    m = re.match(r"https?://t\.me/(c/)?([A-Za-z0-9_]+)/(\d+)", link)
    if not m:
        raise ValueError("Link Telegram tidak valid.")
    is_c = bool(m.group(1))
    chat_part = m.group(2)
    msg_id = int(m.group(3))
    if is_c and chat_part.isdigit():
        chat_id = int("-100" + chat_part)
    else:
        chat_id = chat_part
    return chat_id, msg_id


# ================================
# 🚫 .blgc
# ================================
@ayiin_cmd(pattern=r"blgc(?: |$)(.*)")
async def blgc_cmd(event):
    raw = event.pattern_match.group(1).strip()
    added = []

    # kalau diketik tanpa argumen di grup → blacklist grup itu
    if not raw:
        if event.is_group:
            gid = event.chat_id
            autobc_sql.add_blacklist(gid)
            return await event.edit(f"🚫 Grup ini berhasil ditambahkan ke blacklist.\nID`{gid}`")
        else:
            return await event.edit("✘ Contoh: `.blgc @grup`, `.blgc -100xxxx`, atau kirim di grup langsung tanpa argumen.")

    # kalau diketik dengan banyak argumen
    for t in raw.split():
        try:
            # support link t.me, username publik, dan id langsung
            if t.startswith("https://t.me/") or t.startswith("@"):
                ent = await event.client.get_entity(t)
                gid = int(str(ent.id))
            else:
                gid = int(t)

            if not str(gid).startswith("-100"):
                gid = int(f"-100{abs(gid)}")

            autobc_sql.add_blacklist(gid)
            added.append(str(gid))

        except Exception as e:
            print(f"[BLGC ERROR] {t}: {e}")

    if added:
        await event.edit(f"🚫 **Berhasil ditambahkan ke blacklist:**\n`{', '.join(added)}`")
    else:
        await event.edit("❌ Gagal menambahkan ke blacklist, pastikan link/ID valid dan akun udah join grup tersebut.")

# ================================
# 🧾 .gcbl (list blacklist)
# ================================
@ayiin_cmd(pattern="gcbl$")
async def listbl_cmd(event):
    bl = autobc_sql.get_blacklist()
    if not bl:
        return await event.edit("✅ Tidak ada grup di blacklist.")

    teks = "**🚫 Daftar Blacklist Grup:**\n"
    sukses, gagal = 0, 0

    for gid in bl:
        try:
            ent = await event.client.get_entity(int(gid))
            nama = getattr(ent, "title", None) or getattr(ent, "username", None) or "❓ Tidak diketahui"
            username = f"@{ent.username}" if getattr(ent, "username", None) else f"`{gid}`"
            teks += f"• {nama} — {username}\n"
            sukses += 1
        except Exception as e:
            print(f"[GCBL ERROR] {gid}: {e}")
            teks += f"• `{gid}` — ⚠️ Tidak dapat diakses\n"
            gagal += 1

    teks += f"\n✅ **Total Terbaca:** {sukses} | ⚠️ **Gagal:** {gagal}"
    await event.edit(teks)


# ================================
# ❌ .delbl
# ================================
@ayiin_cmd(pattern=r"delbl(?: |$)(.*)")
async def delbl_cmd(event):
    raw = event.pattern_match.group(1).strip()
    if not raw:
        return await event.edit("✘ Contoh: `.delbl @grup` atau `.delbl -100xxxx` atau `.delbl https://t.me/nama_grup`")

    targets = raw.split()
    removed, failed = 0, []

    for t in targets:
        try:
            # bisa handle link grup juga
            if "t.me/" in t:
                t = t.split("t.me/")[-1].replace("/", "")
            
            ent = await event.client.get_entity(t)
            gid = int(str(ent.id))
            if not str(gid).startswith("-100"):
                gid = int(f"-100{abs(gid)}")
            
            autobc_sql.remove_blacklist(gid)
            removed += 1
        except Exception as e:
            failed.append(t)
            print(f"[DELBL ERROR] {t}: {e}")

    teks = f"✅ **Berhasil hapus dari blacklist:** `{removed}` grup."
    if failed:
        teks += f"\n⚠️ **Gagal hapus:** {', '.join(failed)}"
    await event.edit(teks)


# ================================
# 📢 AUTOBC LOOP (ambil grup otomatis)
# ================================
async def autobc_loop(client, delay):
    try:
        while True:
            data = autobc_sql.get_autobc()
            if not data or not data.is_active:
                break

            try:
                msg = await client.get_messages(data.last_chat_id, ids=data.last_msg_id)
            except Exception as e:
                print(f"[AUTOBC SOURCE ERROR] {e}")
                autobc_sql.stop_autobc()
                break

            # 🔹 Ambil semua grup yang userbot join
            dialogs = await client.get_dialogs()
            groups = [
                int(d.id)
                for d in dialogs
                if (
                    getattr(d, "is_group", False)
                    or (getattr(d, "is_channel", False) and getattr(d.entity, "megagroup", False))
                )
            ]

            bl = set(map(int, autobc_sql.get_blacklist() or []))
            targets = [g for g in groups if g not in bl]

            sukses, gagal = [], []
            tasks = []

            for g in targets:
                async def send_target(gid=g):
                    try:
                        if data.mode == "Forward":
                            await client.forward_messages(int(gid), msg)
                        else:
                            if msg.media and not isinstance(msg.media, types.MessageMediaWebPage):
                                await client.send_file(int(gid), msg.media, caption=msg.text or "")
                            else:
                                await client.send_message(int(gid), msg.text or "", link_preview=False)
                        sukses.append(gid)
                    except Exception as e:
                        gagal.append((gid, str(e)))
                        print(f"[AUTOBC ERROR] {gid}: {e}")

                tasks.append(send_target())

            await asyncio.gather(*tasks)

            log = (
                f"**AUTOBC AKTIF**\n"
                f"Mode: `{data.mode}`\n"
                f"Terkirim: {len(sukses)} | Gagal: {len(gagal)}"
            )
            try:
                await client.send_message(BOTLOG_CHATID, log)
            except:
                pass

            await asyncio.sleep(delay)
    except asyncio.CancelledError:
        pass


# ================================
# 🔁 AUTOFW LOOP (ambil grup otomatis)
# ================================
async def autofw_loop(client, delay, chat_id, msg_id):
    try:
        while True:
            data = autobc_sql.get_autofw()
            if not data or not data.is_active:
                break

            try:
                msg = await client.get_messages(chat_id, ids=msg_id)
            except Exception as e:
                print(f"[AUTOFW SOURCE ERROR] {e}")
                autobc_sql.stop_autofw()
                break

            # 🔹 Ambil semua grup yang userbot join
            dialogs = await client.get_dialogs()
            groups = [
                int(d.id)
                for d in dialogs
                if (
                    getattr(d, "is_group", False)
                    or (getattr(d, "is_channel", False) and getattr(d.entity, "megagroup", False))
                )
            ]

            bl = set(map(int, autobc_sql.get_blacklist() or []))
            targets = [g for g in groups if g not in bl]

            sukses, gagal = [], []
            tasks = []

            for g in targets:
                async def send_fw(gid=g):
                    try:
                        await client.forward_messages(int(gid), msg)
                        sukses.append(gid)
                    except Exception as e:
                        gagal.append((gid, str(e)))
                        print(f"[AUTOFW ERROR] {gid}: {e}")
                tasks.append(send_fw())

            await asyncio.gather(*tasks)

            log = f"**AUTOFW AKTIF**\nTerkirim: {len(sukses)} | Gagal: {len(gagal)}"
            try:
                await client.send_message(BOTLOG_CHATID, log)
            except:
                pass

            await asyncio.sleep(delay)
    except asyncio.CancelledError:
        pass

# ================================
# 📢 .autobc
# ================================
@ayiin_cmd(pattern=r"autobc (\d+)(?: |$)(fw|send)?")
async def autobc_cmd(event):
    delay = int(event.pattern_match.group(1))
    mode = event.pattern_match.group(2) or "Basic"
    reply = await event.get_reply_message()
    if not reply:
        return await event.edit("✘ Balas pesan/media yang mau disebar.")
    autobc_sql.add_or_update_autobc(delay, reply.chat_id, reply.id, bool(reply.media), mode)
    await event.edit(f"AutoBC Aktif | Mode: `{mode}` | Delay: `{delay}`s")

    task = active_tasks.get("autobc")
    if task:
        task.cancel()
    active_tasks["autobc"] = asyncio.create_task(autobc_loop(event.client, delay))


# ================================
# 🔁 .autofw
# ================================
@ayiin_cmd(pattern="autofw(?: |$)(.*)")
async def autofw_cmd(event):
    args = event.pattern_match.group(1).split(" ", 1)
    if len(args) < 2:
        return await event.edit("**Gunakan:** `.autofw <delay> <link_post>`")

    delay = int(args[0])
    link = args[1].strip()

    try:
        chat_id, msg_id = await parse_tg_link(link)
        entity = await event.client.get_entity(chat_id)
    except Exception as e:
        return await event.edit(f"❌ Gagal ambil data channel: `{e}`")

    autobc_sql.add_autofw(delay, str(chat_id), int(msg_id))
    await event.edit(
        f"**AutoFW aktif**\n"
        f"Channel: `{entity.title}`\n"
        f"Post: `{msg_id}`\n"
        f"Delay: `{delay}s`"
    )

    task = active_tasks.get("autofw")
    if task:
        task.cancel()
    active_tasks["autofw"] = asyncio.create_task(autofw_loop(event.client, delay, chat_id, msg_id))


# ================================
# 🛑 .stopbc
# ================================
@ayiin_cmd(pattern="stopbc$")
async def stopbc_cmd(event):
    stopped = []
    for name in ("autobc", "autofw"):
        t = active_tasks.get(name)
        if t:
            t.cancel()
            active_tasks[name] = None
            getattr(autobc_sql, f"stop_{name}")()
            stopped.append(name)
    if stopped:
        await event.edit(f"Berhasil Memberhentikan: `{', '.join(stopped)}`")
    else:
        await event.edit("Tidak ada proses aktif.")


# ================================
# 🧠 AUTO RESUME (FIXED)
# ================================
async def auto_resume_all():
    await asyncio.sleep(8)

    # ===== AutoBC Resume =====
    data = autobc_sql.get_autobc()
    if data and data.is_active:
        print("[AUTOBC] Resume aktif")
        # buat task & simpan biar bisa di-stop
        task = asyncio.create_task(autobc_loop(bot, data.delay))
        active_tasks["autobc"] = task

    # ===== AutoFW Resume =====
    af = autobc_sql.get_autofw()
    if af and af.is_active:
        print("[AUTOFW] Resume aktif")
        task = asyncio.create_task(autofw_loop(bot, af.delay, af.chat_id, af.msg_id))
        active_tasks["autofw"] = task
        
bot.loop.create_task(auto_resume_all())


# ================================
# 📚 Help
# ================================
CMD_HELP.update({
    "autobc": f"**Plugin :** `autobc`\
    \n\n  »  **Perintah :** `{cmd}blgc <@grup> <grup> <linkgrup>`\
    \n  »  **Fungsi :** Menambahkan grup ke daftar blacklist agar tidak menerima pesan broadcast.\
    \n\n  »  **Perintah :** `{cmd}gcbl`\
    \n  »  **Fungsi :** Menampilkan semua grup yang ada di daftar blacklist.\
    \n\n  »  **Perintah :** `{cmd}delbl <@grup> <linkgrup>`\
    \n  »  **Fungsi :** Menghapus grup dari daftar blacklist.\
    \n\n  »  **Perintah :** `{cmd}autobc <delay> <reply teks/media>`\
    \n  »  **Fungsi :** Mengirim pesan teks otomatis ke semua grup yang telah tergabung (kecuali blacklist).\
    \n  »  **Contoh :** `{cmd}autobc 10 <reply>` (kirim tiap 10 detik).\
    \n\n  »  **Perintah :** `{cmd}autofw <delay> <link>`\
    \n  »  **Fungsi :** Forward otomatis dari postingan channel ke semua grup yang telah tergabung (kecuali blacklist).\
    \n  »  **Contoh :** `{cmd}autofw 10 https://t.me/Jasebxall/655`\
    \n\n  »  **Perintah :** `{cmd}stopbc`\
    \n  »  **Fungsi :** Menghentikan semua proses AutoBC & AutoFW yang sedang berjalan.\
"
})
