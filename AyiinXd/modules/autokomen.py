import asyncio
from telethon import events
from telethon.tl.types import Message
from telethon.tl.functions.messages import GetDiscussionMessageRequest
from AyiinXd import bot
from AyiinXd import CMD_HANDLER as cmd
from AyiinXd import CMD_HELP
from AyiinXd import BOTLOG_CHATID
from AyiinXd.ayiin import ayiin_cmd
from datetime import datetime
from .sql_helper import autokomen_sql as db

# ===== Interval polling (detik) =====
POLL_INTERVAL = 20

# ===== INIT STATE =====
stopped_channels = set()
polling_active = True
BLOCKWORD_CACHE = []
BLOCKWORD_READY = False

# ===== Sinkronisasi Status =====
async def sync_autokomen_state():
    """Sinkronisasi channel aktif/nonaktif dari database"""
    global stopped_channels, polling_active
    try:
        all_data = db.get_all_komen()
        active_count = 0
        inactive_count = 0
        stopped_channels.clear()

        for row in all_data:
            if not row.active:
                stopped_channels.add(row.channel_id)
                inactive_count += 1
            else:
                active_count += 1

        polling_active = active_count > 0
        await bot.send_message(
            "me",
            f"**AutoKomen Sync**\n"
            f"Aktif: `{active_count}` | Nonaktif: `{inactive_count}`",
        )
    except Exception as e:
        await bot.send_message("me", f"⚠️ Gagal sync status autokomen: {e}")

def refresh_blockwords():
    global BLOCKWORD_CACHE, BLOCKWORD_READY
    BLOCKWORD_CACHE = [
        b.strip().lower()
        for b in (db.get_blockwords() or [])
        if str(b).strip()
    ]
    BLOCKWORD_READY = True


# ===== POLLING MODE =====
async def polling_worker():
    global polling_active
    while True:
        try:
            if not polling_active:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            # ambil semua channel dari DB
            all_channels = db.get_all_channels()

            # ambil blockword global dari DB (multi kata support)
            if not BLOCKWORD_READY:
                refresh_blockwords()

            blockwords = BLOCKWORD_CACHE

            for ch in all_channels:
                channel_username = ch[0]
                if channel_username in stopped_channels:
                    continue

                try:
                    msgs = await bot.get_messages(channel_username, limit=1)
                    if not msgs:
                        continue

                    msg = msgs[0]
                    text = (msg.raw_text or msg.text or "").lower()

                    # ====== CEK BLOCKWORD GLOBAL ======
                    if blockwords:
                        for bw in blockwords:
                            if bw and bw in text:
                                print(f"[Polling] Skip {channel_username} (mengandung blockword: {bw})")
                                raise StopIteration  # langsung loncat channel berikut
                    # ==================================

                    triggers = db.get_triggers(channel_username)
                    if not triggers:
                        continue

                    for komen in triggers:
                        if komen.last_msg_id == msg.id:
                            continue

                        if komen.trigger.lower() in text:
                            await send_autokomen(msg, komen)
                            db.update_last_msg(channel_username, komen.trigger, msg.id)

                            # === Kirim notifikasi log ke BOTLOG_CHATID ===
                            if BOTLOG_CHATID != 0:
                                try:
                                    username_clean = channel_username.replace("@", "")
                                    waktu = datetime.now().strftime("%H:%M:%S")
                                    reply_preview = (komen.reply or "-")[:100]
                                    await bot.send_message(
                                        BOTLOG_CHATID,
                                        f"**Notification!**\n"
                                        f"━━━━━━━━━━━━━━━\n"
                                        f"**Channel:** `{channel_username}`\n"
                                        f"**Trigger:** `{komen.trigger}`\n"
                                        f"**Reply:** `{reply_preview}`\n"
                                        f"[Lihat Pesan](https://t.me/{username_clean}/{msg.id})",
                                        link_preview=False,
                                    )
                                except Exception as e:
                                    print(f"[LOG ERROR] Gagal kirim log ke BOTLOG_CHATID: {e}")

                            break  # selesai trigger cocok, lanjut channel berikut

                except StopIteration:
                    continue  # loncat ke channel berikut
                except Exception as e:
                    await bot.send_message("me", f"[Polling Error] {channel_username}: {e}")

        except Exception as e:
            await bot.send_message("me", f"[Polling Fatal] {e}")

        await asyncio.sleep(POLL_INTERVAL)


# ===== SEND AUTOKOMEN =====
async def send_autokomen(event_or_msg, komen):
    try:
        discussion = await bot(
            GetDiscussionMessageRequest(
                peer=event_or_msg.chat_id,
                msg_id=event_or_msg.id
            )
        )
        if not discussion.messages:
            return

        reply_msg = discussion.messages[0]
        reply_chat_id = reply_msg.to_id.channel_id

        if komen.msg_id and komen.msg_chat:
            try:
                msg = await bot.get_messages(int(komen.msg_chat), ids=int(komen.msg_id))
                await bot.send_message(
                    entity=reply_chat_id,
                    message=msg.text or "(Kosong / bukan teks)",
                    reply_to=reply_msg.id
                )
            except Exception as e:
                await bot.send_message("me", f"[ERROR Auto-Komen Msg]\n{e}")
        elif komen.reply:
            await bot.send_message(
                entity=reply_chat_id,
                message=komen.reply,
                reply_to=reply_msg.id
            )
    except Exception as e:
        await bot.send_message("me", f"[ERROR Auto-Komen]\n`{e}`")


# ===== COMMANDS =====

@ayiin_cmd(pattern="stopkomen(?: |$)(.*)")
async def _(event):
    """Berhentiin auto komen"""
    global polling_active
    target = event.pattern_match.group(1).strip()

    if not target:
        polling_active = False
        db.SESSION.query(db.AutoKomen).update({"active": False})
        db.SESSION.commit()
        stopped_channels.clear()
        return await event.edit("Auto-komen **dihentikan di semua channel.**")

    if not target.startswith("@"):
        target = "@" + target

    db.deactivate_channel(target)
    stopped_channels.add(target)
    await event.edit(f"Auto-komen dihentikan di channel {target}.")


@ayiin_cmd(pattern="startkomen(?: |$)(.*)")
async def _(event):
    """Lanjut auto komen lagi"""
    global polling_active
    target = event.pattern_match.group(1).strip()

    if not target:
        polling_active = True
        db.SESSION.query(db.AutoKomen).update({"active": True})
        db.SESSION.commit()
        stopped_channels.clear()
        return await event.edit("Auto-komen **dinyalakan kembali untuk semua channel.**")

    if not target.startswith("@"):
        target = "@" + target

    db.activate_channel(target)
    if target in stopped_channels:
        stopped_channels.remove(target)
        return await event.edit(f"Auto-komen diaktifkan kembali untuk {target}.")
    else:
        return await event.edit(f"Auto-komen di {target} sudah aktif.")


@ayiin_cmd(pattern="setch(?: |$)(.*)")
async def _(event):
    args = event.pattern_match.group(1)
    if not args:
        return await event.edit("Contoh: .setch <trigger> <@channel1 @channel2>")

    parts = args.split()
    trigger = parts[0]
    channels = parts[1:]

    if not channels:
        return await event.edit("Harap sebutkan minimal 1 @channel.")

    for ch in channels:
        if not ch.startswith("@"):
            ch = "@" + ch
        db.add_filter(ch, trigger)

    await event.edit(f"Trigger `{trigger}` disimpan di channel: `{', '.join(channels)}`")


@ayiin_cmd(pattern="setkomen(?: |$)(.*)")
async def _(event):
    raw = event.text
    if not raw:
        return await event.edit(
            f"Format yang benar:\n"
            f"`{cmd}setkomen <trigger> <pesan>`"
        )

    # contoh raw:
    # .setkomen promo ini pesan
    parts = raw.split(maxsplit=2)
    if len(parts) < 3:
        return await event.edit(
            "Format yang benar.\n"
            f"Contoh:\n`{cmd}setkomen promo Ini isi komen`"
        )

    trigger = parts[1].strip().lower()

    # ambil SEMUA teks setelah trigger (multiline aman)
    reply_text = raw.split(parts[0] + " " + parts[1], 1)[1].strip()

    if not reply_text:
        return await event.edit("Pesan komen tidak boleh kosong.")

    # ambil channel yang pakai trigger ini
    all_data = db.get_all_komen()
    channels = [d.channel_id for d in all_data if d.trigger == trigger]

    if not channels:
        return await event.edit(
            f"Trigger `{trigger}` belum dipakai.\n"
            f"Pakai `{cmd}setch {trigger} @channel` dulu."
        )

    for ch in channels:
        db.set_reply(
            ch,
            trigger,
            reply=reply_text,
            msg_id=None,
            msg_chat=None
        )

    await event.edit(
        f"**Berhasil disimpan**\n"
        f"Trigger: `{trigger}`\n"
        f"Channel: `{len(channels)}`\n\n"
        f"Preview:\n{reply_text[:500]}"
    )


@ayiin_cmd(pattern="delkomen(?: |$)(.*)")
async def _(event):
    args = event.pattern_match.group(1).split()
    if len(args) < 2:
        return await event.edit("Contoh: .delkomen <trigger> <@channel1> <@channel2> ...")

    trig = args[0]
    channels = args[1:]
    deleted, not_found = [], []

    for ch in channels:
        if not ch.startswith("@"):
            ch = "@" + ch
        all_channels = [c[0] for c in db.get_all_channels()]
        if ch in all_channels:
            db.delete_trigger(ch, trig)
            deleted.append(ch)
        else:
            not_found.append(ch)

    msg = ""
    if deleted:
        msg += f"Trigger `{trig}` berhasil dihapus dari: {', '.join(deleted)}\n"
    if not_found:
        msg += f"Channel tidak ditemukan di database: {', '.join(not_found)}"

    await event.edit(msg)


@ayiin_cmd(pattern="delch(?: |$)(.*)")
async def _(event):
    text = event.pattern_match.group(1).strip()
    if not text:
        return await event.edit("Harap masukkan minimal 1 channel.")

    channels = text.split()
    deleted, not_found = [], []

    for ch in channels:
        if not ch.startswith("@"):
            ch = "@" + ch
        all_channels = [c[0] for c in db.get_all_channels()]
        if ch in all_channels:
            db.delete_channel(ch)
            deleted.append(ch)
        else:
            not_found.append(ch)

    msg = ""
    if deleted:
        msg += f"Trigger & komen berhasil dihapus dari: {', '.join(deleted)}\n"
    if not_found:
        msg += f"Channel tidak ditemukan di database: {', '.join(not_found)}"

    await event.edit(msg)


@ayiin_cmd(pattern="listkomen$")
async def _(event):
    data = db.get_all_komen()
    if not data:
        return await event.edit("Belum ada data auto komen.")

    grouped = {}
    for row in data:
        trigger = row.trigger
        channel = row.channel_id
        reply = row.reply or ""
        if not str(channel).startswith("@"):
            channel = "@" + str(channel)
        grouped.setdefault(trigger, []).append((channel, reply))

    msg = "**Daftar Auto Komen :**\n\n"

    for trigger, items in grouped.items():
        # channel unik
        channels = sorted({ch for ch, _ in items})

        # pesan unik (hindari dobel karena multi channel)
        seen = set()
        pesan_list = []
        for _ch, reply in items:
            r = reply.strip()
            if r and r not in seen:
                seen.add(r)
                pesan_list.append(r)

        msg += f"**Trigger :** `{trigger}`\n"
        msg += f"**Channel :** {' '.join(channels)}\n"
        msg += "**pesan :**\n"

        for p in pesan_list:
            # potong kalau kepanjangan, tetap aman multiline
            if len(p) > 1000:
                p = p[:1000] + "…"
            msg += f"{p}\n\n"

        msg += "──────────────\n\n"

    await event.edit(msg)

@ayiin_cmd(pattern="statuskomen$")
async def _(event):
    """Lihat status aktif/nonaktif auto-komen tiap channel"""
    data = db.get_all_komen()
    if not data:
        return await event.edit("Belum ada data auto-komen.")

    aktif, nonaktif = [], []

    for row in data:
        if getattr(row, "active", True):
            if row.channel_id not in aktif:
                aktif.append(row.channel_id)
        else:
            if row.channel_id not in nonaktif:
                nonaktif.append(row.channel_id)

    msg = "**Status AutoKomen**\n\n"
    if aktif:
        msg += f"**Aktif** ({len(aktif)}):\n" + "\n".join(aktif) + "\n\n"
    if nonaktif:
        msg += f"**Nonaktif** ({len(nonaktif)}):\n" + "\n".join(nonaktif)
    if not aktif and not nonaktif:
        msg += "_Belum ada data channel._"

    await event.edit(msg)


# ===== BLOCKWORD COMMANDS =====
@ayiin_cmd(pattern="addblock(?: |$)(.*)")
async def _(event):
    words = event.pattern_match.group(1)
    if not words:
        return await event.edit("Contoh: `.addblock sfs auto`")

    count = db.add_blockwords_global(words)
    refresh_blockwords()
    await event.edit(f"{count} kata ditambahkan.")


@ayiin_cmd(pattern="delblock(?: |$)(.*)")
async def _(event):
    word = event.pattern_match.group(1).strip().lower()
    if not word:
        return await event.edit("Contoh: `.delblock sfs`")

    db.del_blockword_global(word)
    refresh_blockwords()
    await event.edit(f"Blockword `{word}` dihapus.")


@ayiin_cmd(pattern="listblock$")
async def _(event):
    blocks = db.get_blockwords()
    if not blocks:
        return await event.edit("Belum ada blockword.")
    msg = "**Daftar Blockword:**\n" + "\n".join([f"- {b}" for b in blocks])
    await event.edit(msg)


# ===== STARTUP POLLING =====
async def start_polling():
    await asyncio.sleep(10)
    await sync_autokomen_state()
    refresh_blockwords()
    bot.loop.create_task(polling_worker())

bot.loop.create_task(start_polling())

CMD_HELP.update({
    "autokomen": f"Plugin : autokomen\
\n\n  »  Perintah : {cmd}setch <trigger> <@channel>\
\n  »  Kegunaan : Set trigger untuk satu atau lebih channel.\
\n\n  »  Perintah : {cmd}setkomen <trigger> <pesan autokomen>\
\n  »  Kegunaan : Set isi komen untuk trigger tertentu.\
\n\n  »  Perintah : {cmd}stopkomen\
\n  »  Kegunaan : Stop auto komen ke semua channel.\
\n  »  Kegunaan : Aktifkan auto komen di channel tertentu.\
\n\n  »  Perintah : {cmd}startkomen\
\n  »  Kegunaan : Aktifkan auto komen ke semua channel.\
\n\n  »  Perintah : {cmd}delkomen <trigger> <@channel>\
\n  »  Kegunaan : Menghapus trigger dari channel tertentu.\
\n\n  »  Perintah : {cmd}delch <@channel>\
\n  »  Kegunaan : Menghapus semua data trigger & komen channel.\
\n\n  »  Perintah : {cmd}listkomen\
\n  »  Kegunaan : Melihat daftar list auto komen.\
\n\n  »  Perintah : {cmd}statuskomen\
\n  »  Kegunaan : Melihat status aktif/nonaktif tiap channel.\
\n\n  »  Perintah : {cmd}addblock <kata>\
\n  »  Kegunaan : Tambahkan blockword agar pesan dengan kata itu di-skip.\
\n\n  »  Perintah : {cmd}delblock <kata>\
\n  »  Kegunaan : Hapus blockword dari channel.\
\n\n  »  Perintah : {cmd}listblock\
\n  »  Kegunaan : Lihat semua blockword pada channel."
})
