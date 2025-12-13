import asyncio
from telethon.errors import FloodWaitError
from telethon.tl.functions.messages import GetDiscussionMessageRequest

from AyiinXd import bot, CMD_HANDLER as cmd, CMD_HELP, BOTLOG_CHATID
from AyiinXd.ayiin import ayiin_cmd
from .sql_helper import autokomen_sql as db

# =========================================================
# CONFIG
# =========================================================
POLL_INTERVAL = 20

# =========================================================
# RUNTIME STATE
# =========================================================
polling_active = True
stopped_channels = set()

# Cache (Tahap 2)
TRIGGER_CACHE = {}      # { "@channel": [AutoKomenRow, ...] }
BLOCKWORD_CACHE = []    # [ "sfs", "jaseb", ... ]
CACHE_READY = False
CACHE_LOCK = asyncio.Lock()

# =========================================================
# UTILITIES
# =========================================================
def normalize(text: str) -> str:
    return (text or "").lower().strip()


def contains_blockword(text: str) -> bool:
    if not BLOCKWORD_CACHE:
        return False
    for bw in BLOCKWORD_CACHE:
        if bw and bw in text:
            return True
    return False


# =========================================================
# DB SYNC & CACHE
# =========================================================
async def sync_state():
    """Sync active / inactive channel state"""
    global polling_active
    stopped_channels.clear()

    rows = db.get_all_komen()
    active_count = 0

    for r in rows:
        ch = r.channel_id
        if not str(ch).startswith("@"):
            ch = "@" + str(ch)

        if not getattr(r, "active", True):
            stopped_channels.add(ch)
        else:
            active_count += 1

    polling_active = active_count > 0

    await bot.send_message(
        "me",
        f"✅ AutoKomen Sync\nAktif: {active_count} | Nonaktif: {len(stopped_channels)}"
    )


async def refresh_cache():
    """Refresh trigger & blockword cache"""
    global CACHE_READY
    async with CACHE_LOCK:
        TRIGGER_CACHE.clear()

        rows = db.get_all_komen()
        for r in rows:
            ch = r.channel_id
            if not str(ch).startswith("@"):
                ch = "@" + str(ch)
            TRIGGER_CACHE.setdefault(ch, []).append(r)

        BLOCKWORD_CACHE[:] = [
            str(b).lower().strip()
            for b in (db.get_blockwords() or [])
            if str(b).strip()
        ]

        CACHE_READY = True


# =========================================================
# SEND AUTOKOMEN (BEHAVIOR SAMA SEPERTI KODE LAMA YANG WORK)
# =========================================================
async def send_autokomen(event_or_msg, komen):
    try:
        discussion = await bot(
            GetDiscussionMessageRequest(
                peer=event_or_msg.chat_id,  # 🔥 JANGAN DIUBAH (ini yang paling stabil)
                msg_id=event_or_msg.id
            )
        )
        if not discussion.messages:
            return False

        reply_msg = discussion.messages[0]
        target_chat = reply_msg.to_id.channel_id  # 🔥 BIARIN SEPERTI KODE LAMA

        # ambil isi komen
        if getattr(komen, "msg_id", None) and getattr(komen, "msg_chat", None):
            src = await bot.get_messages(int(komen.msg_chat), ids=int(komen.msg_id))
            text = src.text or "💬 (Kosong)"
        else:
            text = getattr(komen, "reply", None)

        if not text:
            return False

        await bot.send_message(
            entity=target_chat,
            message=text,
            reply_to=reply_msg.id
        )
        return True

    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
        return False
    except Exception as e:
        await bot.send_message("me", f"[AutoKomen ERROR]\n{e}")
        return False


# =========================================================
# POLLING WORKER (FIX: BACA raw_text/caption JUGA)
# =========================================================
async def polling_worker():
    global polling_active

    while True:
        try:
            if not polling_active:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            if not CACHE_READY:
                await refresh_cache()

            for channel_id, triggers in TRIGGER_CACHE.items():
                if channel_id in stopped_channels:
                    continue

                try:
                    msgs = await bot.get_messages(channel_id, limit=1)
                    if not msgs:
                        continue

                    msg = msgs[0]

                    # 🔥 FIX UTAMA: jangan cuma msg.text
                    text = normalize(getattr(msg, "raw_text", None) or getattr(msg, "message", None) or getattr(msg, "text", None))
                    if not text:
                        continue

                    if contains_blockword(text):
                        continue

                    if not triggers:
                        continue

                    for komen in triggers:
                        # anti spam (pakai cache object juga)
                        if getattr(komen, "last_msg_id", None) == msg.id:
                            continue

                        trig = normalize(getattr(komen, "trigger", None))
                        if trig and trig in text:
                            ok = await send_autokomen(msg, komen)

                            if ok:
                                # update DB
                                try:
                                    db.update_last_msg(channel_id, komen.trigger, msg.id)
                                except Exception:
                                    pass

                                # update cache object biar loop berikutnya gak ulang
                                try:
                                    komen.last_msg_id = msg.id
                                except Exception:
                                    pass

                                # botlog optional
                                if BOTLOG_CHATID:
                                    try:
                                        await bot.send_message(
                                            BOTLOG_CHATID,
                                            f"📢 AutoKomen\nChannel: {channel_id}\nTrigger: {komen.trigger}\nMsg ID: {msg.id}",
                                            link_preview=False
                                        )
                                    except Exception:
                                        pass

                            break

                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
                except Exception:
                    continue

        except Exception as e:
            await bot.send_message("me", f"[Polling Fatal]\n{e}")

        await asyncio.sleep(POLL_INTERVAL)


# =========================================================
# STARTUP
# =========================================================
async def start():
    await asyncio.sleep(5)
    await sync_state()
    await refresh_cache()
    bot.loop.create_task(polling_worker())

bot.loop.create_task(start())


# =========================================================
# COMMANDS
# =========================================================
@ayiin_cmd(pattern="stopkomen(?: |$)(.*)")
async def _(event):
    """Stop auto komen (all or per channel)"""
    global polling_active
    target = (event.pattern_match.group(1) or "").strip()

    if not target:
        polling_active = False
        db.SESSION.query(db.AutoKomen).update({"active": False})
        db.SESSION.commit()
        stopped_channels.clear()
        await refresh_cache()
        return await event.edit("🛑 AutoKomen dihentikan di semua channel.")

    if not target.startswith("@"):
        target = "@" + target

    try:
        db.deactivate_channel(target)
    except Exception:
        db.SESSION.query(db.AutoKomen).filter_by(channel_id=target).update({"active": False})
        db.SESSION.commit()

    stopped_channels.add(target)
    await sync_state()
    await refresh_cache()
    return await event.edit(f"🛑 AutoKomen dimatikan untuk {target}.")


@ayiin_cmd(pattern="startkomen(?: |$)(.*)")
async def _(event):
    """Start auto komen (all or per channel)"""
    global polling_active
    target = (event.pattern_match.group(1) or "").strip()

    if not target:
        polling_active = True
        db.SESSION.query(db.AutoKomen).update({"active": True})
        db.SESSION.commit()
        stopped_channels.clear()
        await sync_state()
        await refresh_cache()
        return await event.edit("✅ AutoKomen dinyalakan untuk semua channel.")

    if not target.startswith("@"):
        target = "@" + target

    try:
        db.activate_channel(target)
    except Exception:
        db.SESSION.query(db.AutoKomen).filter_by(channel_id=target).update({"active": True})
        db.SESSION.commit()

    if target in stopped_channels:
        stopped_channels.remove(target)

    polling_active = True
    await sync_state()
    await refresh_cache()
    return await event.edit(f"✅ AutoKomen dinyalakan untuk {target}.")


@ayiin_cmd(pattern="setch(?: |$)(.*)")
async def _(event):
    parts = (event.pattern_match.group(1) or "").split()
    if len(parts) < 2:
        return await event.edit("Contoh: .setch <trigger> <@channel1 @channel2>")

    trigger = parts[0]
    channels = parts[1:]

    for ch in channels:
        if not ch.startswith("@"):
            ch = "@" + ch
        db.add_filter(ch, trigger)

    await refresh_cache()
    await event.edit("✅ Trigger disimpan.")


@ayiin_cmd(pattern="setkomen(?: |$)(.*)")
async def _(event):
    trigger = (event.pattern_match.group(1) or "").strip()
    if not trigger:
        return await event.edit("Contoh: .setkomen promo (reply ke pesan)")

    if not event.reply_to_msg_id:
        return await event.edit("❌ Harus reply ke pesan yang mau dijadiin komen!")

    reply_msg = await event.get_reply_message()
    if not reply_msg:
        return await event.edit("❌ Gagal ambil pesan reply.")

    rows = db.get_all_komen()
    for r in rows:
        if r.trigger == trigger:
            db.set_reply(r.channel_id, trigger, msg_id=reply_msg.id, msg_chat=str(reply_msg.chat_id))

    await refresh_cache()
    await event.edit("✅ Komen disimpan.")


@ayiin_cmd(pattern="delkomen(?: |$)(.*)")
async def _(event):
    args = (event.pattern_match.group(1) or "").split()
    if len(args) < 2:
        return await event.edit("Contoh: .delkomen <trigger> <@channel1 @channel2>")

    trig = args[0]
    channels = args[1:]
    for ch in channels:
        if not ch.startswith("@"):
            ch = "@" + ch
        db.delete_trigger(ch, trig)

    await refresh_cache()
    await event.edit("🗑️ Trigger dihapus.")


@ayiin_cmd(pattern="delch(?: |$)(.*)")
async def _(event):
    channels = (event.pattern_match.group(1) or "").split()
    if not channels:
        return await event.edit("Contoh: .delch <@channel1 @channel2>")

    for ch in channels:
        if not ch.startswith("@"):
            ch = "@" + ch
        db.delete_channel(ch)

    await refresh_cache()
    await event.edit("🗑️ Channel dihapus.")


@ayiin_cmd(pattern="addblock(?: |$)(.*)")
async def _(event):
    words = (event.pattern_match.group(1) or "").strip()
    if not words:
        return await event.edit("Contoh: .addblock sfs auto viu")

    db.add_blockwords_global(words)
    await refresh_cache()
    await event.edit("✅ Blockword ditambahkan.")


@ayiin_cmd(pattern="delblock(?: |$)(.*)")
async def _(event):
    word = (event.pattern_match.group(1) or "").strip()
    if not word:
        return await event.edit("Contoh: .delblock sfs")

    db.del_blockword_global(word)
    await refresh_cache()
    await event.edit("🗑️ Blockword dihapus.")


@ayiin_cmd(pattern="listblock$")
async def _(event):
    await event.edit("🚫 Blockword:\n" + "\n".join(BLOCKWORD_CACHE) if BLOCKWORD_CACHE else "🚫 Belum ada blockword.")


# =========================================================
# HELP
# =========================================================
CMD_HELP.update({
    "autokomen": (
        f"{cmd}setch, {cmd}setkomen, {cmd}startkomen, {cmd}stopkomen, "
        f"{cmd}addblock, {cmd}delblock"
    )
})
