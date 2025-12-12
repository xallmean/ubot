import asyncio
import time
from datetime import datetime
from telethon import events
from telethon.errors import FloodWaitError
from telethon.tl.types import Message
from telethon.tl.functions.messages import GetDiscussionMessageRequest

from AyiinXd import bot
from AyiinXd import CMD_HANDLER as cmd
from AyiinXd import CMD_HELP
from AyiinXd import BOTLOG_CHATID
from AyiinXd.ayiin import ayiin_cmd
from .sql_helper import autokomen_sql as db

# ─────────────────────────────────────────────────────────────
# STEALTH SETTINGS (FAST, NO MANUAL DELAY)
# ─────────────────────────────────────────────────────────────
# Cooldown per *destination discussion chat* (SKIP, no sleep)
COOLDOWN_SECONDS = 25

# Max memory for responded cache (prevents RAM growth)
RESPONDED_MAX = 8000

# TTL for responded keys (seconds)
RESPONDED_TTL = 6 * 60 * 60  # 6 hours

# Logging verbosity
STEALTH_SILENT = False  # True = minimize "me" spam errors


# ─────────────────────────────────────────────────────────────
# RUNTIME STATE
# ─────────────────────────────────────────────────────────────
stopped_channels = set()         # channel usernames "@xxx" which are inactive
polling_active = True            # we keep this flag for compatibility with commands

TRIGGER_CACHE = {}               # { "@channel": [komen_rows...] }
BLOCKWORDS_CACHE = []            # [ "word1", "word 2", ... ]
CACHE_READY = False

# message dedupe: {(src_chat_id, src_msg_id, trigger): timestamp}
RESPONDED = {}

# cooldown per destination chat id: {dest_chat_id: last_ts}
LAST_REPLY_TS = {}

STATE_LOCK = asyncio.Lock()


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def _now() -> float:
    return time.time()


def _normalize_text(t: str) -> str:
    return (t or "").lower().strip()


def _cleanup_responded():
    """Bound memory & TTL cleanup. O(1) most of the time."""
    if len(RESPONDED) <= RESPONDED_MAX:
        # still do light TTL cleanup rarely
        return

    cutoff = _now() - RESPONDED_TTL
    # remove old entries first
    old_keys = [k for k, ts in RESPONDED.items() if ts < cutoff]
    for k in old_keys:
        RESPONDED.pop(k, None)

    # if still too big, drop oldest by timestamp
    if len(RESPONDED) > RESPONDED_MAX:
        # sort only when needed (rare)
        items = sorted(RESPONDED.items(), key=lambda x: x[1])
        for k, _ts in items[: max(0, len(RESPONDED) - RESPONDED_MAX)]:
            RESPONDED.pop(k, None)


async def _safe_send_me(text: str):
    if STEALTH_SILENT:
        return
    try:
        await bot.send_message("me", text)
    except Exception:
        pass


async def refresh_cache(full: bool = True):
    """
    Refresh cache from DB.
    - full=True: reload triggers for all channels + blockwords + active/inactive status
    - full=False: reload only blockwords (or light refresh)
    """
    global BLOCKWORDS_CACHE, TRIGGER_CACHE, CACHE_READY, polling_active

    async with STATE_LOCK:
        # blockwords
        try:
            BLOCKWORDS_CACHE = [b.strip().lower() for b in (db.get_blockwords() or []) if str(b).strip()]
        except Exception:
            BLOCKWORDS_CACHE = []

        if not full:
            CACHE_READY = True
            return

        # stopped channels + active flag
        stopped_channels.clear()
        active_count = 0
        inactive_count = 0

        try:
            all_data = db.get_all_komen()
        except Exception as e:
            await _safe_send_me(f"⚠️ DB error get_all_komen: {e}")
            all_data = []

        # rebuild trigger cache per channel
        TRIGGER_CACHE.clear()

        for row in all_data:
            ch = row.channel_id
            if not ch:
                continue
            # normalize channel format
            if not str(ch).startswith("@"):
                ch = "@" + str(ch)

            # active / inactive
            if hasattr(row, "active") and (row.active is False):
                stopped_channels.add(ch)
                inactive_count += 1
            else:
                active_count += 1

            TRIGGER_CACHE.setdefault(ch, []).append(row)

        polling_active = active_count > 0
        CACHE_READY = True

        # minimal startup note (optional)
        if not STEALTH_SILENT:
            await bot.send_message(
                "me",
                f"✅ **AutoKomen Sync**\n"
                f"📊 Aktif: `{active_count}` | Nonaktif: `{inactive_count}`\n"
                f"🧱 Blockwords: `{len(BLOCKWORDS_CACHE)}`",
            )


def _contains_blockword(text: str) -> bool:
    if not BLOCKWORDS_CACHE:
        return False
    for bw in BLOCKWORDS_CACHE:
        if bw and bw in text:
            return True
    return False


def _cooldown_hit(dest_chat_id: int) -> bool:
    """Return True if should SKIP (no delay)."""
    last = LAST_REPLY_TS.get(dest_chat_id, 0.0)
    now = _now()
    if now - last < COOLDOWN_SECONDS:
        return True
    return False


def _mark_cooldown(dest_chat_id: int):
    LAST_REPLY_TS[dest_chat_id] = _now()


def _responded_key(src_chat_id: int, src_msg_id: int, trigger: str):
    return (int(src_chat_id), int(src_msg_id), str(trigger or "").lower())


def _already_responded(key) -> bool:
    ts = RESPONDED.get(key)
    if not ts:
        return False
    # TTL check
    if _now() - ts > RESPONDED_TTL:
        RESPONDED.pop(key, None)
        return False
    return True


def _mark_responded(key):
    RESPONDED[key] = _now()
    _cleanup_responded()


async def _log_botlog(channel_username: str, msg_id: int, trigger: str, reply_preview: str):
    if BOTLOG_CHATID == 0:
        return
    try:
        username_clean = channel_username.replace("@", "")
        waktu = datetime.now().strftime("%H:%M:%S")
        await bot.send_message(
            BOTLOG_CHATID,
            f"📢 **Auto-Komen Notification!**\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🕒 **Waktu:** `{waktu}`\n"
            f"🏷️ **Channel:** `{channel_username}`\n"
            f"💬 **Trigger:** `{trigger}`\n"
            f"📨 **Reply:** `{(reply_preview or '-')[:100]}`\n"
            f"🔗 [Lihat Pesan](https://t.me/{username_clean}/{msg_id})",
            link_preview=False,
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# CORE: SEND AUTOKOMEN (DISCUSSION REPLY)
# ─────────────────────────────────────────────────────────────
async def send_autokomen(event_or_msg, komen):
    try:
        src_chat_id = event_or_msg.chat_id
        src_msg_id = event_or_msg.id

        # Ambil teks reply
        if komen.msg_id and komen.msg_chat:
            src = await bot.get_messages(int(komen.msg_chat), ids=int(komen.msg_id))
            out_text = src.text or "💬"
        else:
            out_text = komen.reply

        if not out_text:
            return False

        peer = await event_or_msg.get_input_chat()

        # ================================
        # 1️⃣ PAKSA BANGUN DISCUSSION
        # ================================
        discussion = await bot(GetDiscussionMessageRequest(
            peer=peer,
            msg_id=src_msg_id
        ))

        # Kalau discussion belum ada → paksa
        if not discussion.messages:
            # kirim dummy (stealth)
            dummy = await bot.send_message(
                entity=src_chat_id,
                message="hmu",
                reply_to=src_msg_id
            )
            # hapus dummy
            await dummy.delete()

            # ambil ulang discussion
            discussion = await bot(GetDiscussionMessageRequest(
                peer=peer,
                msg_id=src_msg_id
            ))

        if not discussion.messages:
            return False  # ini HARUSNYA hampir gak pernah kejadian

        reply_msg = discussion.messages[0]
        dest_chat_id = reply_msg.to_id.channel_id

        # cooldown
        if _cooldown_hit(dest_chat_id):
            return False

        # ================================
        # 2️⃣ KIRIM AUTOKOMEN ASLI
        # ================================
        await bot.send_message(
            entity=dest_chat_id,
            message=out_text,
            reply_to=reply_msg.id
        )

        _mark_cooldown(dest_chat_id)
        return True

    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
        return False
    except Exception as e:
        await _safe_send_me(f"[AUTO-KOMEN ERROR] {e}")
        return False


# ─────────────────────────────────────────────────────────────
# LISTENER MODE (STEALTH: ONLY THIS)
# ─────────────────────────────────────────────────────────────
@bot.on(events.NewMessage)
async def komen_listener(event):
    await bot.send_message("me", f"✅ handler kepanggil: chat_id={event.chat_id} msg_id={event.id}")

    global polling_active

    if not polling_active:
        return
    if not isinstance(event.message, Message):
        return
    if not event.is_channel:
        return
    chat = await event.get_chat()
    username = getattr(chat, "username", None)
    if not username:
        return
    channel_id = f"@{username}"

    # Ensure cache loaded
    if not CACHE_READY:
        await refresh_cache(full=True)

    channel_id = f"@{event.chat.username}"

    # skip if stopped
    if channel_id in stopped_channels:
        return

    text = _normalize_text(event.raw_text)

    # global blockword
    if _contains_blockword(text):
        return

    # triggers from cache (fast) or fallback DB
    triggers = TRIGGER_CACHE.get(channel_id)
    if triggers is None:
        try:
            triggers = db.get_triggers(channel_id) or []
            TRIGGER_CACHE[channel_id] = triggers
        except Exception:
            return

    if not triggers:
        return

    # trigger match
    for komen in triggers:
        trig = getattr(komen, "trigger", None)
        if not trig:
            continue
        trig_norm = str(trig).lower()

        # skip if already handled this message for this trigger
        key = _responded_key(event.chat_id, event.id, trig_norm)
        if _already_responded(key):
            continue

        # match
        if trig_norm in text:
            ok = await send_autokomen(event, komen)
            if ok:
                _mark_responded(key)

                # update DB last_msg_id (fix from old version)
                try:
                    db.update_last_msg(channel_id, trig_norm, event.id)
                except Exception:
                    pass

                # botlog
                reply_preview = getattr(komen, "reply", None) or ""
                await _log_botlog(channel_id, event.id, trig_norm, reply_preview)

            # only one trigger response per message
            break


# ─────────────────────────────────────────────────────────────
# COMMANDS
# ─────────────────────────────────────────────────────────────
@ayiin_cmd(pattern="stopkomen(?: |$)(.*)")
async def _(event):
    """Stop auto komen (all or per channel)"""
    global polling_active
    target = event.pattern_match.group(1).strip()

    if not target:
        polling_active = False
        db.SESSION.query(db.AutoKomen).update({"active": False})
        db.SESSION.commit()

        async with STATE_LOCK:
            stopped_channels.clear()
            TRIGGER_CACHE.clear()

        return await event.edit("🛑 Auto-komen **dihentikan di semua channel.**")

    if not target.startswith("@"):
        target = "@" + target

    db.deactivate_channel(target)

    async with STATE_LOCK:
        stopped_channels.add(target)

    await event.edit(f"🛑 Auto-komen dihentikan di channel {target}.")


@ayiin_cmd(pattern="startkomen(?: |$)(.*)")
async def _(event):
    """Start auto komen (all or per channel)"""
    global polling_active
    target = event.pattern_match.group(1).strip()

    if not target:
        polling_active = True
        db.SESSION.query(db.AutoKomen).update({"active": True})
        db.SESSION.commit()

        async with STATE_LOCK:
            stopped_channels.clear()

        await refresh_cache(full=True)
        return await event.edit("✅ Auto-komen **dinyalakan kembali untuk semua channel.**")

    if not target.startswith("@"):
        target = "@" + target

    db.activate_channel(target)

    async with STATE_LOCK:
        if target in stopped_channels:
            stopped_channels.remove(target)

    await refresh_cache(full=True)
    return await event.edit(f"✅ Auto-komen diaktifkan kembali untuk {target}.")


@ayiin_cmd(pattern="setch(?: |$)(.*)")
async def _(event):
    args = event.pattern_match.group(1)
    if not args:
        return await event.edit("Contoh: .setch <trigger> <@channel1 @channel2>")

    parts = args.split()
    trigger = parts[0].strip()
    channels = parts[1:]

    if not trigger or not channels:
        return await event.edit("Contoh: .setch <trigger> <@channel1 @channel2>")

    norm_channels = []
    for ch in channels:
        if not ch.startswith("@"):
            ch = "@" + ch
        db.add_filter(ch, trigger)
        norm_channels.append(ch)

    await refresh_cache(full=True)
    await event.edit(f"✅ Trigger `{trigger}` disimpan di channel: `{', '.join(norm_channels)}`")


@ayiin_cmd(pattern="setkomen(?: |$)(.*)")
async def _(event):
    trigger = event.pattern_match.group(1).strip()
    if not trigger:
        return await event.edit("Contoh: .setkomen promo (balas ke pesan juga)")

    if not event.reply_to_msg_id:
        return await event.edit("❌ Harus reply ke pesan yang mau dijadiin komen!")

    reply_msg = await event.get_reply_message()
    if not reply_msg:
        return await event.edit("❌ Gagal ambil pesan yang direply.")

    all_data = db.get_all_komen()
    channels = []
    for d in all_data:
        if d.trigger == trigger:
            ch = d.channel_id
            if not str(ch).startswith("@"):
                ch = "@" + str(ch)
            channels.append(ch)

    if not channels:
        return await event.edit("❌ Belum ada channel untuk trigger ini. Gunakan `.setch` dulu.")

    for ch in channels:
        db.set_reply(ch, trigger, msg_id=reply_msg.id, msg_chat=str(reply_msg.chat_id))

    try:
        link_preview = f"https://t.me/c/{str(reply_msg.chat_id)[4:]}/{reply_msg.id}"
    except Exception:
        link_preview = "pesan"

    await refresh_cache(full=True)
    await event.edit(
        f"✅ Disimpan di `{len(channels)}` channel:\n🔑 Trigger: `{trigger}`\n💬 Komen: [link]({link_preview})",
        link_preview=False
    )


@ayiin_cmd(pattern="delkomen(?: |$)(.*)")
async def _(event):
    args = event.pattern_match.group(1).split()
    if len(args) < 2:
        return await event.edit("Contoh: .delkomen <trigger> <@channel1> <@channel2> ...")

    trig = args[0].strip()
    channels = args[1:]
    deleted, not_found = [], []

    all_channels = [c[0] for c in db.get_all_channels()]

    for ch in channels:
        if not ch.startswith("@"):
            ch = "@" + ch
        if ch in all_channels:
            db.delete_trigger(ch, trig)
            deleted.append(ch)
        else:
            not_found.append(ch)

    await refresh_cache(full=True)

    msg = ""
    if deleted:
        msg += f"🗑️ Trigger `{trig}` berhasil dihapus dari: {', '.join(deleted)}\n"
    if not_found:
        msg += f"❌ Channel tidak ditemukan di database: {', '.join(not_found)}"

    await event.edit(msg)


@ayiin_cmd(pattern="delch(?: |$)(.*)")
async def _(event):
    text = event.pattern_match.group(1).strip()
    if not text:
        return await event.edit("❌ Harap masukkan minimal 1 channel.")

    channels = text.split()
    deleted, not_found = [], []

    all_channels = [c[0] for c in db.get_all_channels()]

    for ch in channels:
        if not ch.startswith("@"):
            ch = "@" + ch
        if ch in all_channels:
            db.delete_channel(ch)
            deleted.append(ch)
        else:
            not_found.append(ch)

    await refresh_cache(full=True)

    msg = ""
    if deleted:
        msg += f"🗑️ Trigger & komen berhasil dihapus dari: {', '.join(deleted)}\n"
    if not_found:
        msg += f"❌ Channel tidak ditemukan di database: {', '.join(not_found)}"

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
        reply = row.reply or "(Belum ada pesan)"
        if not str(channel).startswith("@"):
            channel = "@" + str(channel)
        grouped.setdefault(trigger, []).append((channel, reply))

    msg = "**📋 Daftar List Auto Komen :**\n\n"
    for trigger, items in grouped.items():
        channels = sorted({ch for ch, _r in items})
        replies = sorted({(r or "").strip() for _ch, r in items})

        msg += f"**Channel :** {' '.join(channels)}\n"
        msg += f"**Trigger :** \"{trigger}\"\n"
        for r in replies:
            rr = (r[:400] + "...") if len(r) > 400 else r
            msg += f'Pesan : "{rr}"\n'
        msg += "\n"

    await event.edit(msg)


@ayiin_cmd(pattern="statuskomen$")
async def _(event):
    data = db.get_all_komen()
    if not data:
        return await event.edit("❌ Belum ada data auto-komen.")

    aktif, nonaktif = [], []

    for row in data:
        ch = row.channel_id
        if not str(ch).startswith("@"):
            ch = "@" + str(ch)
        if getattr(row, "active", True):
            if ch not in aktif:
                aktif.append(ch)
        else:
            if ch not in nonaktif:
                nonaktif.append(ch)

    msg = "**📊 Status AutoKomen**\n\n"
    if aktif:
        msg += f"✅ **Aktif** ({len(aktif)}):\n" + "\n".join(aktif) + "\n\n"
    if nonaktif:
        msg += f"🛑 **Nonaktif** ({len(nonaktif)}):\n" + "\n".join(nonaktif)
    if not aktif and not nonaktif:
        msg += "_Belum ada data channel._"

    await event.edit(msg)


# ─────────────────────────────────────────────────────────────
# BLOCKWORD COMMANDS (GLOBAL)
# ─────────────────────────────────────────────────────────────
@ayiin_cmd(pattern="addblock(?: |$)(.*)")
async def _(event):
    words = event.pattern_match.group(1)
    if not words:
        return await event.edit("⚠️ Contoh: `.addblock sfs auto viu jaseb telegram`")

    count = db.add_blockwords_global(words)
    await refresh_cache(full=False)
    await event.edit(f"✅ {count} kata ditambahkan ke daftar blockword global.")


@ayiin_cmd(pattern="delblock(?: |$)(.*)")
async def _(event):
    word = event.pattern_match.group(1).strip().lower()
    if not word:
        return await event.edit("⚠️ Contoh: `.delblock sfs`")

    db.del_blockword_global(word)
    await refresh_cache(full=False)
    await event.edit(f"🗑️ Blockword `{word}` dihapus dari semua channel.")


@ayiin_cmd(pattern="listblock$")
async def _(event):
    blocks = db.get_blockwords()
    if not blocks:
        return await event.edit("🚫 Belum ada blockword global.")
    msg = "🚫 **Daftar Blockword Global:**\n" + "\n".join([f"- {b}" for b in blocks])
    await event.edit(msg)


# ─────────────────────────────────────────────────────────────
# STARTUP (STEALTH: cache only, no polling)
# ─────────────────────────────────────────────────────────────
async def start_stealth():
    await asyncio.sleep(5)
    await refresh_cache(full=True)

bot.loop.create_task(start_stealth())


# ─────────────────────────────────────────────────────────────
# HELP
# ─────────────────────────────────────────────────────────────
CMD_HELP.update({
    "autokomen": f"Plugin : autokomen"
    f"\n\n  »  Perintah : {cmd}setch <trigger> <@channel>"
    f"\n  »  Kegunaan : Set trigger untuk satu atau lebih channel."
    f"\n\n  »  Perintah : {cmd}setkomen <trigger> (balas ke pesan)"
    f"\n  »  Kegunaan : Set isi komen (teks/media) untuk trigger tertentu."
    f"\n\n  »  Perintah : {cmd}stopkomen"
    f"\n  »  Kegunaan : Stop auto komen ke semua channel / channel tertentu."
    f"\n\n  »  Perintah : {cmd}startkomen"
    f"\n  »  Kegunaan : Aktifkan auto komen ke semua channel / channel tertentu."
    f"\n\n  »  Perintah : {cmd}delkomen <trigger> <@channel>"
    f"\n  »  Kegunaan : Menghapus trigger dari channel tertentu."
    f"\n\n  »  Perintah : {cmd}delch <@channel>"
    f"\n  »  Kegunaan : Menghapus semua data trigger & komen channel."
    f"\n\n  »  Perintah : {cmd}listkomen"
    f"\n  »  Kegunaan : Melihat daftar list auto komen."
    f"\n\n  »  Perintah : {cmd}statuskomen"
    f"\n  »  Kegunaan : Melihat status aktif/nonaktif tiap channel."
    f"\n\n  »  Perintah : {cmd}addblock <kata>"
    f"\n  »  Kegunaan : Tambahkan blockword agar pesan dengan kata itu di-skip."
    f"\n\n  »  Perintah : {cmd}delblock <kata>"
    f"\n  »  Kegunaan : Hapus blockword global."
    f"\n\n  »  Perintah : {cmd}listblock"
    f"\n  »  Kegunaan : Lihat semua blockword global."
})
