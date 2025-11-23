import asyncio
from telethon import events, types, errors
from telethon.tl.functions.channels import EditBannedRequest, GetParticipantsRequest
from telethon.tl.types import ChatBannedRights, ChannelParticipantsAdmins, ChannelParticipantsSearch
from AyiinXd import CMD_HANDLER as cmd
from AyiinXd import CMD_HELP
from AyiinXd import BOTLOG_CHATID

from AyiinXd import bot
from AyiinXd.ayiin import ayiin_cmd
from AyiinXd.modules.sql_helper.autoban_sql import (
    add_channel,
    add_or_update_channel,
    get_all_channels,
    get_prev_members,
    add_banned_user,
    get_banned_users,
    remove_channel,
)

# ---------------- COMMAND ---------------- #

@ayiin_cmd(pattern=r"autoban(?: |$)(.*)")
async def enable_autoban(e):
    input_str = e.pattern_match.group(1)
    if not input_str.startswith("@"):
        return await e.edit("❌ Gunakan format: `.autoban @username_channel`")

    await e.edit("⏳ Mengaktifkan auto-ban...")
    try:
        entity = await bot.get_entity(input_str)
        participants = await bot.get_participants(entity)
        user_ids = [u.id for u in participants]

        add_channel(entity.id, input_str)
        add_or_update_channel(entity.id, input_str, user_ids)

        await e.edit(f"✅ Auto-ban aktif di {input_str}.")
    except Exception as err:
        await e.edit(f"❌ Gagal: {err}")


@ayiin_cmd(pattern=r"stopban(?: |$)(.*)")
async def stop_autoban(e):
    input_str = e.pattern_match.group(1)
    if not input_str.startswith("@"):
        return await e.edit("❌ Gunakan format: `.stopban @username_channel`")

    try:
        entity = await bot.get_entity(input_str)
        remove_channel(entity.id)
        await e.edit(f"🛑 Auto-ban dimatikan dari {input_str}.")
    except Exception as err:
        await e.edit(f"❌ Gagal: {err}")


@ayiin_cmd(pattern="listban$")
async def list_autoban(e):
    try:
        chans = get_all_channels()
        if not chans:
            return await e.edit("📭 Belum ada channel yang aktif auto-ban.")

        teks = "📌 **Auto-ban aktif di channel:**\n\n"
        for c in chans:
            teks += f"• `{c.channel_username}`\n"

        await e.edit(teks)
    except Exception as err:
        await e.edit(f"❌ Error: {err}")


# ---------------- HANDLER OTOMATIS ---------------- #

async def ban_user(chat_id, user_id, chan_username):
    try:
        me = await bot.get_me()
        admins = await bot.get_participants(chat_id, filter=ChannelParticipantsAdmins)
        if me.id not in [a.id for a in admins]:
            print(f"[AutoBan] Bot bukan admin di {chat_id}, skip ban user {user_id}")
            return False

        await bot(EditBannedRequest(
            chat_id,
            user_id,
            ChatBannedRights(until_date=None, view_messages=True)
        ))
        add_banned_user(chan_username, user_id)
        print(f"[AutoBan] User {user_id} dibanned di {chan_username}")
        await asyncio.sleep(1)
        return True
    except errors.FloodWaitError as f:
        print(f"[AutoBan Flood] Tunggu {f.seconds}s")
        await asyncio.sleep(f.seconds + 1)
    except Exception as err:
        print(f"[AutoBan Error] {err}")
    return False


# Grup / Supergroup
@bot.on(events.ChatAction)
async def autoban_trigger(event):
    if not (event.user_left or event.user_kicked):
        return
    if not event.user_id:
        return

    try:
        all_channels = get_all_channels()
        for chan in all_channels:
            if event.chat_id != chan.channel_id:
                continue

            prev_members = get_prev_members(chan.channel_id)
            banned_users = get_banned_users()

            if event.user_id in prev_members:
                continue

            if (chan.channel_username, event.user_id) not in banned_users:
                await ban_user(event.chat_id, event.user_id, chan.channel_username)
    except Exception as err:
        print(f"[AutoBan Main Error] {err}")


# ---------------- LOOP UNTUK BROADCAST CHANNEL ---------------- #

async def autoban_channel_loop():
    await bot.connect()
    print("[AutoBan] Background loop aktif untuk broadcast channel.")

    while True:
        try:
            all_channels = get_all_channels()

            channels = [
                {"id": c.channel_id, "username": c.channel_username}
                for c in all_channels
            ]

            for chan in channels:
                try:
                    try:
                        entity = await bot.get_entity(int(chan["id"]))
                    except Exception:
                        entity = await bot.get_entity(chan["username"])

                    if not getattr(entity, "broadcast", False):
                        continue  # skip kalau bukan broadcast

                    prev_members = set(get_prev_members(chan["id"]))
                    new_members = set()

                    offset = 0
                    while True:
                        participants = await bot(GetParticipantsRequest(
                            entity,
                            ChannelParticipantsSearch(""),
                            offset,
                            200,
                            hash=0
                        ))
                        if not participants.users:
                            break
                        for user in participants.users:
                            new_members.add(user.id)
                        offset += len(participants.users)

                    left_users = prev_members - new_members
                    if left_users:
                        print(f"[AutoBan] Deteksi {len(left_users)} user keluar di {chan['username']}")
                        for uid in left_users:
                            banned_users = get_banned_users()
                            if (chan["username"], uid) in banned_users:
                                continue
                            await ban_user(chan["id"], uid, chan["username"])

                    add_or_update_channel(chan["id"], chan["username"], list(new_members))
                    await asyncio.sleep(2)

                except Exception as sub_err:
                    print(f"[AutoBan SubLoop Error] {sub_err}")

        except Exception as err:
            print(f"[AutoBan Loop Error] {err}")

        await asyncio.sleep(30)


# Jalankan loop di background
bot.loop.create_task(autoban_channel_loop())

CMD_HELP.update(
    {
        "autoban": f"**Plugin :** `autoban`\
\n\n  »  **Perintah :** `{cmd}autoban <@usnchannel>`\
\n  »  **Kegunaan :** Aktifkan fitur autoban di channel.\
\n\n  »  **Perintah :** `{cmd}stopban <@usnchannel>`\
\n  »  **Kegunaan :** Nonaktifkan autoban dari channel.\
\n\n  »  **Perintah :** `{cmd}listban`\
\n  »  **Kegunaan :** Lihat daftar channel yang sedang aktif autoban.\
\n\n**NOTE:**\
\n• Akun userbot harus **admin** di channel agar bisa mem-ban.\
\n• Aktifkan semua perizinan **admin**.\
\n• Pastikan akun userbot sudah **join ke channel** yang diaktifkan."
    }
)
