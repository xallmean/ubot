import asyncio
from datetime import datetime
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
DISCUSSION_CACHE = {}   # {(chat_id, msg_id): reply_msg}
DISCUSSION_CACHE_MAX = 2000

# =========================================================
# UTILITIES
# =========================================================
def normalize(text: str) -> str:
    return (text or "").lower().strip()


def contains_blockword(text: str) -> bool:
    for bw in BLOCKWORD_CACHE:
        if bw and bw in text:
            return True
    return False

def _cache_put(key, value):
    if len(DISCUSSION_CACHE) >= DISCUSSION_CACHE_MAX:
        # buang item lama (FIFO sederhana)
        DISCUSSION_CACHE.pop(next(iter(DISCUSSION_CACHE)))
    DISCUSSION_CACHE[key] = value


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
    """Refresh trigger & blockword cache (SAFE)"""
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
            b.lower().strip()
            for b in (db.get_blockwords() or [])
            if str(b).strip()
        ]

        CACHE_READY = True


# =========================================================
# SEND AUTOKOMEN (⚠️ CORE BEHAVIOR JANGAN DIUBAH)
# =========================================================
async def send_autokomen(event_or_msg, komen):
    try:
        key = (event_or_msg.chat_id, event_or_msg.id)

        if key in DISCUSSION_CACHE:
            reply_msg = DISCUSSION_CACHE[key]
        else:
            discussion = await bot(
                GetDiscussionMessageRequest(
                    peer=event_or_msg.chat_id,  # 🔥 tetap sama
                    msg_id=event_or_msg.id
                )
            )
            if not discussion.messages:
                return False

            reply_msg = discussion.messages[0]
            _cache_put(key, reply_msg)

        target_chat = reply_msg.to_id.channel_id  # 🔥 tetap sama

        if komen.msg_id and komen.msg_chat:
            src = await bot.get_messages(
                int(komen.msg_chat),
                ids=int(komen.msg_id)
            )
            text = src.text or "💬 (Kosong)"
        else:
            text = komen.reply

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
# POLLING WORKER (BERSIH, CACHE, STABLE)
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
                    text = normalize(msg.text)
                    if not text:
                        continue

                    if contains_blockword(text):
                        continue

                    for komen in triggers:
                        if komen.last_msg_id == msg.id:
                            continue

                        if normalize(komen.trigger) in text:
                            ok = await send_autokomen(msg, komen)

                            if ok:
                                db.update_last_msg(
                                    channel_id,
                                    komen.trigger,
                                    msg.id
                                )

                                if BOTLOG_CHATID:
                                    await bot.send_message(
                                        BOTLOG_CHATID,
                                        f"📢 AutoKomen\n"
                                        f"Channel: {channel_id}\n"
                                        f"Trigger: {komen.trigger}\n"
                                        f"Msg ID: {msg.id}"
                                    )
                            break

                except Exception:
                    continue

        except Exception as e:
            await bot.send_message("me", f"[Polling Fatal]\n{e}")

        await asyncio.sleep(POLL_INTERVAL)


# =========================================================
# STARTUP
# =========================================================
async def start():
    DISCUSSION_CACHE.clear()
    await asyncio.sleep(5)
    await sync_state()
    await refresh_cache()
    bot.loop.create_task(polling_worker())

bot.loop.create_task(start())


# =========================================================
# COMMANDS (PERILAKU SAMA, CUMA REFRESH CACHE)
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

    # matiin hanya channel target
    try:
        db.deactivate_channel(target)  # pastikan fungsi ini ada di sql
    except Exception:
        # fallback kalau belum punya function: update manual
        db.SESSION.query(db.AutoKomen).filter_by(channel_id=target).update({"active": False})
        db.SESSION.commit()

    stopped_channels.add(target)

    # polling tetap hidup kalau masih ada channel aktif lain
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
        db.activate_channel(target)  # pastikan fungsi ini ada di sql
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
    args = event.pattern_match.group(1).split()
    trigger = args[0]
    channels = args[1:]

    for ch in channels:
        if not ch.startswith("@"):
            ch = "@" + ch
        db.add_filter(ch, trigger)

    await refresh_cache()
    await event.edit("✅ Trigger disimpan.")


@ayiin_cmd(pattern="setkomen(?: |$)(.*)")
async def _(event):
    trigger = event.pattern_match.group(1).strip()
    reply_msg = await event.get_reply_message()

    rows = db.get_all_komen()
    for r in rows:
        if r.trigger == trigger:
            db.set_reply(
                r.channel_id,
                trigger,
                msg_id=reply_msg.id,
                msg_chat=str(reply_msg.chat_id)
            )

    await refresh_cache()
    await event.edit("✅ Komen disimpan.")


@ayiin_cmd(pattern="delkomen(?: |$)(.*)")
async def _(event):
    args = event.pattern_match.group(1).split()
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
    channels = event.pattern_match.group(1).split()
    for ch in channels:
        if not ch.startswith("@"):
            ch = "@" + ch
        db.delete_channel(ch)

    await refresh_cache()
    await event.edit("🗑️ Channel dihapus.")


@ayiin_cmd(pattern="addblock(?: |$)(.*)")
async def _(event):
    db.add_blockwords_global(event.pattern_match.group(1))
    await refresh_cache()
    await event.edit("✅ Blockword ditambahkan.")


@ayiin_cmd(pattern="delblock(?: |$)(.*)")
async def _(event):
    db.del_blockword_global(event.pattern_match.group(1))
    await refresh_cache()
    await event.edit("🗑️ Blockword dihapus.")


@ayiin_cmd(pattern="listblock$")
async def _(event):
    await event.edit(
        "🚫 Blockword:\n" + "\n".join(BLOCKWORD_CACHE)
    )


# =========================================================
# HELP
# =========================================================
CMD_HELP.update({
    "autokomen": (
        f"{cmd}setch, {cmd}setkomen, {cmd}startkomen, {cmd}stopkomen, "
        f"{cmd}addblock, {cmd}delblock"
    )
})
