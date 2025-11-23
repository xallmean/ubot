# modules/autokomen.py
import os
import asyncio
import random
import time
import re
from telethon import events, errors
from telethon.tl.types import Message
from telethon.tl.functions.messages import GetDiscussionMessageRequest
from AyiinXd import bot
from AyiinXd import CMD_HANDLER as cmd
from AyiinXd import CMD_HELP
from AyiinXd.ayiin import ayiin_cmd
from .sql_helper import autokomen_sql as db

BOTLOG_CHATID = int(os.getenv("BOTLOG_CHATID", "0"))

stopped_channels = set()
polling_active = True  # tetap ada untuk backward-compat (bisa dimatikan paksa)
_discussion_cache = {}
_channel_error_backoff = {}

async def get_discussion_message_id(client, channel_id, post_id):
    key = f"{channel_id}_{post_id}"
    if key in _discussion_cache:
        return _discussion_cache[key]
    try:
        discussion = await client(GetDiscussionMessageRequest(peer=channel_id, msg_id=post_id))
        if discussion and discussion.messages:
            discussion_id = discussion.messages[0].id
            _discussion_cache[key] = discussion_id
            return discussion_id
    except Exception:
        return None
    return None

async def safe_send(entity, message=None, reply_to=None):
    # random kecil supaya gak ke-FLOOD instan
    await asyncio.sleep(random.uniform(0.8, 1.2))
    try:
        if message is not None:
            await bot.send_message(entity=entity, message=message, reply_to=reply_to)
        else:
            await bot.send_message(entity=entity, message="💬 (kosong)", reply_to=reply_to)
        return True
    except errors.FloodWaitError as fw:
        secs = getattr(fw, "seconds", 5)
        try:
            await bot.send_message("me", f"[AutoKomen] FloodWait {secs}s, jeda kirim.")
        except Exception:
            pass
        await asyncio.sleep(min(secs, 30))
        return False
    except Exception as e:
        try:
            await bot.send_message("me", f"[AutoKomen] Error kirim: {e}")
        except Exception:
            pass
        return False

async def sync_autokomen_state():
    global stopped_channels, polling_active
    try:
        all_data = db.get_all_komen()
        active_count = 0
        inactive_count = 0
        stopped_channels.clear()
        for row in all_data:
            if getattr(row, "active", True) is False:
                stopped_channels.add(row.channel_id)
                inactive_count += 1
            else:
                active_count += 1
        polling_active = active_count > 0
        try:
            await bot.send_message("me", f"✅ AutoKomen sync. Aktif: {active_count} | Nonaktif: {inactive_count}")
        except Exception:
            pass
    except Exception as e:
        try:
            await bot.send_message("me", f"⚠️ Gagal sync status autokomen: {e}")
        except Exception:
            pass

# ---------- LISTENER ONLY ----------
@bot.on(events.NewMessage(incoming=True))
async def komen_listener(event):
    """Event-driven listener: langsung respons begitu ada pesan di channel"""
    if not polling_active:
        return
    if not isinstance(event.message, Message):
        return
    chat = event.chat

    # harus ada username, karena kita pakai @username sebagai key channel
    if not chat or not getattr(chat, "username", None):
        return

    # kalau channel atau group diskusi, dua2nya diterima
    if not (event.is_channel or event.is_group):
        return

    channel_id = f"@{event.chat.username}".lower()
    if channel_id in stopped_channels:
        return

    backoff = _channel_error_backoff.get(channel_id)
    if backoff and time.time() < backoff:
        return

    # ambil triggers / konfigurasi channel
    triggers = db.get_triggers(channel_id)
    if not triggers:
        return

    text = (event.raw_text or "").lower().strip()

    # cek per-channel blockwords
    blockwords = [b.strip().lower() for b in (db.get_blockwords(channel_id) or [])]
    for bw in blockwords:
        if bw and bw in text:
            print(f"[AutoKomen] Skip {channel_id} karena blockword: {bw}")
            return

    # cek global blockwords
    global_block = [b.strip().lower() for b in (db.get_blockwords(None) or [])]
    for bw in global_block:
        if bw and bw in text:
            print(f"[AutoKomen] Skip {channel_id} karena global blockword: {bw}")
            return

    for komen in triggers:
        try:
            if komen.trigger and komen.trigger.lower() in text:
                if getattr(komen, "active", True) is False:
                    continue
                await send_autokomen(event, komen)
                try:
                    db.update_last_msg(channel_id, komen.trigger, event.id)
                except Exception:
                    pass
                await notify_log(channel_id, komen, event)
                break
        except Exception as e:
            print(f"[AutoKomen] Error check trigger: {e}")
            continue

async def send_autokomen(event_or_msg, komen):
    try:
        # dapatkan discussion id (reply thread) dan target entity
        peer = getattr(event_or_msg, "chat_id", None) or (f"@{getattr(event_or_msg.chat, 'username', '')}" if getattr(event_or_msg, "chat", None) else None)
        discussion_id = await get_discussion_message_id(bot, peer, event_or_msg.id)
        reply_to_id = discussion_id or getattr(event_or_msg, "id", None)
        target_entity = peer or getattr(event_or_msg, "chat_id", None) or getattr(event_or_msg, "peer_id", None)

        # prioritas: cached reply text (reply), else saved msg (msg_chat/msg_id)
        if getattr(komen, "reply", None):
            await safe_send(entity=target_entity, message=komen.reply, reply_to=reply_to_id)
        elif getattr(komen, "msg_chat", None) and getattr(komen, "msg_id", None):
            try:
                saved = await bot.get_messages(int(komen.msg_chat), ids=int(komen.msg_id))
                text = saved.text if saved and getattr(saved, "text", None) else "💬 (Kosong / bukan teks)"
                await safe_send(entity=target_entity, message=text, reply_to=reply_to_id)
            except Exception as e:
                await bot.send_message("me", f"[ERROR Auto-Komen Msg]\n{e}")
    except Exception as e:
        try:
            await bot.send_message("me", f"[ERROR Auto-Komen]\n`{e}`")
        except Exception:
            pass

async def notify_log(channel_username, komen, event_or_msg):
    if BOTLOG_CHATID == 0:
        return
    try:
        username_clean = channel_username.replace("@", "")
        trigger = getattr(komen, "trigger", "(unknown)")
        preview = "(Belum ada pesan)"
        if getattr(komen, "reply", None):
            preview = komen.reply
        elif getattr(komen, "msg_chat", None) and getattr(komen, "msg_id", None):
            try:
                saved = await bot.get_messages(int(komen.msg_chat), ids=int(komen.msg_id))
                if saved and getattr(saved, "text", None):
                    preview = saved.text
            except Exception:
                pass
        preview_short = (preview[:200] + "...") if len(preview) > 200 else preview
        msgid = getattr(event_or_msg, "id", getattr(event_or_msg, "id", None))
        await bot.send_message(
            BOTLOG_CHATID,
            f"📢 **Auto-Komen Aktif!**\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🏷️ **Channel:** `{channel_username}`\n"
            f"💬 **Trigger:** `{trigger}`\n"
            f"📨 **Komen:** `{preview_short}`\n"
            f"🔗 https://t.me/{username_clean}/{msgid}",
            link_preview=False,
        )
    except Exception as e:
        print(f"[LOG ERROR] Gagal kirim log ke BOTLOG_CHATID: {e}")

# ===== COMMANDS =====
@ayiin_cmd(pattern="stopkomen(?: |$)(.*)")
async def _(event):
    global polling_active
    target = event.pattern_match.group(1).strip()
    if not target:
        polling_active = False
        db.SESSION.query(db.AutoKomen).update({"active": False})
        db.SESSION.commit()
        stopped_channels.clear()
        return await event.edit("🛑 Auto-komen **dihentikan di semua channel.**")
    if not target.startswith("@"):
        target = "@" + target
    db.deactivate_channel(target)
    stopped_channels.add(target)
    await event.edit(f"🛑 Auto-komen dihentikan di channel {target}.")

@ayiin_cmd(pattern="startkomen(?: |$)(.*)")
async def _(event):
    global polling_active
    target = event.pattern_match.group(1).strip()
    if not target:
        polling_active = True
        db.SESSION.query(db.AutoKomen).update({"active": True})
        db.SESSION.commit()
        stopped_channels.clear()
        return await event.edit("✅ Auto-komen **dinyalakan kembali untuk semua channel.**")
    if not target.startswith("@"):
        target = "@" + target
    db.activate_channel(target)
    if target in stopped_channels:
        stopped_channels.remove(target)
        return await event.edit(f"✅ Auto-komen diaktifkan kembali untuk {target}.")
    else:
        return await event.edit(f"ℹ️ Auto-komen di {target} sudah aktif.")

@ayiin_cmd(pattern="setch(?: |$)(.*)")
async def _(event):
    args = event.pattern_match.group(1)
    if not args:
        return await event.edit("Contoh: `.setch <trigger> <@channel1 @channel2>`")
    parts = args.split()
    trigger = parts[0]
    channels = parts[1:]
    if not channels:
        return await event.edit("Harap sebutkan minimal 1 @channel.")
    normalized = []
    for ch in channels:
        if not ch.startswith("@"):
            ch = "@" + ch
        db.add_filter(ch, trigger)
        normalized.append(ch)
    await event.edit(f"✅ Trigger `{trigger}` disimpan di channel: `{', '.join(normalized)}`")

@ayiin_cmd(pattern="setkomen(?: |$)(.*)")
async def _(event):
    """
    Baru: .setkomen <trigger> <teks autokomen...>
    Mendukung multiline & hyperlink. Tidak perlu reply ke pesan.
    """
    # ambil remainder pesan (mendukung multiline)
    payload = event.pattern_match.group(1) or ""
    if not payload.strip():
        # fallback: ambil raw_text dan hapus command prefix
        raw = (event.raw_text or event.message.message or "")
        # hapus awalan command (misal ".setkomen " atau "/setkomen ")
        payload = re.sub(r'^\S+\s+', '', raw, count=1)
    payload = payload.strip()
    if not payload:
        return await event.edit("Contoh: `.setkomen jaseb Keren banget promonya\nBisa multiline & hyperlink`")

    # pisah trigger dan teks (trigger = kata pertama, sisanya = teks komen)
    parts = payload.split(None, 1)
    if len(parts) < 2 or not parts[0].strip() or not parts[1].strip():
        return await event.edit("Format: `.setkomen <trigger> <teks autokomen...>`\nContoh:\n`.setkomen jaseb Keren banget promonya\nBisa multiline & hyperlink`")
    trigger = parts[0].strip()
    reply_text = parts[1]

    # cari semua channel yg punya trigger ini, lalu simpan reply text ke field reply
    all_data = db.get_all_komen()
    channels = [d.channel_id for d in all_data if d.trigger == trigger]
    if not channels:
        return await event.edit("❌ Belum ada channel untuk trigger ini. Gunakan `.setch` dulu.")
    saved = 0
    for ch in channels:
        # simpan reply text; clear msg_id/msg_chat to prefer reply text
        db.set_reply(ch, trigger, reply=reply_text, msg_id=None, msg_chat=None)
        saved += 1
    await event.edit(f"✅ Disimpan di `{saved}` channel: Trigger `{trigger}` (reply teks tersimpan).")

@ayiin_cmd(pattern="delkomen(?: |$)(.*)")
async def _(event):
    args = event.pattern_match.group(1).split()
    if len(args) < 2:
        return await event.edit("Contoh: `.delkomen <trigger> <@channel1> <@channel2> ...`")
    trig = args[0]
    channels = args[1:]
    deleted, not_found = [], []
    all_channels_db = [c[0] for c in db.get_all_channels()]
    for ch in channels:
        if not ch.startswith("@"):
            ch = "@" + ch
        if ch in all_channels_db:
            db.delete_trigger(ch, trig)
            deleted.append(ch)
        else:
            not_found.append(ch)
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
    all_channels_db = [c[0] for c in db.get_all_channels()]
    for ch in channels:
        if not ch.startswith("@"):
            ch = "@" + ch
        if ch in all_channels_db:
            db.delete_channel(ch)
            deleted.append(ch)
        else:
            not_found.append(ch)
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
        grouped.setdefault(trigger, []).append(row)
    msg = "**📋 Daftar List Auto Komen :**\n\n"
    for trigger, items in grouped.items():
        channels = []
        replies = set()
        for row in items:
            ch = row.channel_id
            channels.append(f"{ch}" if ch.startswith("@") else f"@{ch}")
            if row.reply:
                replies.add(row.reply)
            elif row.msg_chat and row.msg_id:
                try:
                    saved = await bot.get_messages(int(row.msg_chat), ids=int(row.msg_id))
                    if saved and getattr(saved, "text", None):
                        replies.add(saved.text)
                    else:
                        replies.add("(Belum ada pesan)")
                except Exception:
                    replies.add("(Belum ada pesan)")
            else:
                replies.add("(Belum ada pesan)")
        channels_str = " ".join(channels)
        replies_str = "\n".join([f'Pesan : "{r}"' for r in replies])
        msg += f"Channel : {channels_str}\nTrigger : \"{trigger}\"\n{replies_str}\n\n"
    await event.edit(msg)

@ayiin_cmd(pattern="statuskomen$")
async def _(event):
    data = db.get_all_komen()
    if not data:
        return await event.edit("❌ Belum ada data auto-komen.")
    aktif, nonaktif = [], []
    for row in data:
        if getattr(row, "active", True):
            if row.channel_id not in aktif:
                aktif.append(row.channel_id)
        else:
            if row.channel_id not in nonaktif:
                nonaktif.append(row.channel_id)
    msg = "**📊 Status AutoKomen**\n\n"
    if aktif:
        msg += f"✅ **Aktif** ({len(aktif)}):\n" + "\n".join(aktif) + "\n\n"
    if nonaktif:
        msg += f"🛑 **Nonaktif** ({len(nonaktif)}):\n" + "\n".join(nonaktif)
    if not aktif and not nonaktif:
        msg += "_Belum ada data channel._"
    await event.edit(msg)

@ayiin_cmd(pattern="addblock(?: |$)(.*)")
async def _(event):
    args = event.pattern_match.group(1).split()
    if len(args) < 1:
        return await event.edit("Contoh: `.addblock <kata1 kata2 ...>` atau `.addblock <@channel> <kata1 kata2 ...>`")
    if args[0].startswith("@"):
        ch = args[0]
        words = " ".join(args[1:]).strip()
        if not words:
            return await event.edit("Contoh: `.addblock <@channel> <kata1 kata2 ...>`")
        for w in words.split():
            db.add_blockword(ch, w)
        await event.edit(f"🚫 Blockword ditambahkan ke `{ch}`: `{words}`")
    else:
        words = " ".join(args).strip()
        added = db.add_blockwords_global(words)
        await event.edit(f"🚫 Blockword global ditambahkan ({added} kata): `{words}`")

@ayiin_cmd(pattern="delblock(?: |$)(.*)")
async def _(event):
    args = event.pattern_match.group(1).split()
    if len(args) < 1:
        return await event.edit("Contoh: `.delblock <kata>` atau `.delblock <@channel> <kata>`")
    if args[0].startswith("@"):
        ch = args[0]
        word = " ".join(args[1:]).strip()
        if not word:
            return await event.edit("Contoh: `.delblock <@channel> <kata>`")
        db.del_blockword(ch, word)
        await event.edit(f"✅ Blockword `{word}` dihapus dari `{ch}`.")
    else:
        word = " ".join(args).strip()
        db.del_blockword_global(word)
        await event.edit(f"✅ Blockword global `{word}` dihapus.")

@ayiin_cmd(pattern="listblock(?: |$)(.*)")
async def _(event):
    ch = event.pattern_match.group(1).strip()
    if not ch:
        blocks = db.get_blockwords(None)
        if not blocks:
            return await event.edit("❌ Belum ada blockword global.")
        msg = "🚫 **Blockword (global):**\n" + "\n".join([f"- {b}" for b in blocks])
        return await event.edit(msg)
    if not ch.startswith("@"):
        ch = "@" + ch
    blocks = db.get_blockwords(ch)
    if not blocks:
        return await event.edit(f"❌ `{ch}` belum punya blockword.")
    msg = f"🚫 **Blockword di {ch}:**\n" + "\n".join([f"- {b}" for b in blocks])
    await event.edit(msg)

# sync initial state on startup
async def start_sync():
    await asyncio.sleep(4)
    await sync_autokomen_state()

bot.loop.create_task(start_sync())

CMD_HELP.update({
    "autokomen": f"**Plugin :** `autokomen`\
\n\n  »  **Perintah :** `{cmd}setch <trigger> <@channel>`\
\n  »  **Perintah :** `{cmd}setkomen <trigger> <teks...>` (langsung, mendukung multiline & hyperlink)\
\n  »  **Perintah :** `{cmd}stopkomen <@channel>` / `{cmd}stopkomen`\
\n  »  **Perintah :** `{cmd}startkomen <@channel>` / `{cmd}startkomen`\
\n  »  **Perintah :** `{cmd}delkomen <trigger> <@channel1> <@channel2> ...`\
\n  »  **Perintah :** `{cmd}delch <@channel1> <@channel2> ...`\
\n  »  **Perintah :** `{cmd}listkomen` / `{cmd}statuskomen`\
\n  »  **Perintah :** `{cmd}addblock <kata...>` (global) or `{cmd}addblock @ch <kata...>`\
\n  »  **Perintah :** `{cmd}delblock <kata>` (global) or `{cmd}delblock @ch <kata>`\
\n  »  **Perintah :** `{cmd}listblock [@channel]`"
})
