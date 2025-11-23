# Copyright (C) 2020 Catuserbot <https://github.com/sandy1709/catuserbot>
# Ported by @mrismanaziz
# FROM Man-Userbot <https://github.com/mrismanaziz/Man-Userbot>
# t.me/SharingUserbot & t.me/Lunatic0de

import asyncio

from telethon.tl import functions, types
from telethon.tl.functions.messages import GetStickerSetRequest
from telethon.utils import get_display_name

from AyiinXd import BOTLOG_CHATID
from AyiinXd import CMD_HANDLER as cmd
from AyiinXd import CMD_HELP, BLACKLIST_CHAT, LOGS
from AyiinXd.modules.sql_helper.globals import addgvar, gvarstatus
from AyiinXd.ayiin import ayiin_cmd, eod, eor
from AyiinXd.ayiin.tools import media_type
from Stringyins import get_string
from collections import defaultdict


async def spam_function(event, spammer, xnxx, sleeptimem, sleeptimet, DelaySpam=False):
    counter = int(xnxx[0])
    if len(xnxx) == 2:
        spam_message = str(xnxx[1])
        for _ in range(counter):
            if gvarstatus("spamwork") is None:
                return
            if event.reply_to_msg_id:
                await spammer.reply(spam_message)
            else:
                await event.client.send_message(event.chat_id, spam_message)
            await asyncio.sleep(sleeptimet)
    elif event.reply_to_msg_id and spammer.media:
        for _ in range(counter):
            if gvarstatus("spamwork") is None:
                return
            spammer = await event.client.send_file(
                event.chat_id, spammer, caption=spammer.text
            )
            await unsavegif(event, spammer)
            await asyncio.sleep(sleeptimem)
        if BOTLOG_CHATID:
            if DelaySpam is not True:
                if event.is_private:
                    await event.client.send_message(
                        BOTLOG_CHATID, get_string("spam_1").format(event.chat_id, counter)
                    )
                else:
                    await event.client.send_message(
                        BOTLOG_CHATID, get_string("spam_2").format(get_display_name(await event.get_chat()), event.chat_id, counter)
                    )
            elif event.is_private:
                await event.client.send_message(
                    BOTLOG_CHATID, get_string("spam_3").format(event.chat_id, counter, sleeptimet)
                )
            else:
                await event.client.send_message(
                    BOTLOG_CHATID, get_string("spam_4").format(get_display_name(await event.get_chat()), event.chat_id, counter, sleeptimet)
                )

            spammer = await event.client.send_file(BOTLOG_CHATID, spammer)
            await unsavegif(event, spammer)
        return
    elif event.reply_to_msg_id and spammer.text:
        spam_message = spammer.text
        for _ in range(counter):
            if gvarstatus("spamwork") is None:
                return
            await event.client.send_message(event.chat_id, spam_message)
            await asyncio.sleep(sleeptimet)
    else:
        return
    if DelaySpam is not True:
        if BOTLOG_CHATID:
            if event.is_private:
                await event.client.send_message(
                    BOTLOG_CHATID, get_string("spam_5").format(event.chat_id, counter, spam_message)
                )
            else:
                await event.client.send_message(
                    BOTLOG_CHATID, get_string("spam_6").format(get_display_name(await event.get_chat()), event.chat_id, counter, spam_message)
                )
    elif BOTLOG_CHATID:
        if event.is_private:
            await event.client.send_message(
                BOTLOG_CHATID, get_string("spam_7").format(event.chat_id, sleeptimet, counter, spam_message)
            )
        else:
            await event.client.send_message(
                BOTLOG_CHATID, get_string("spam_8").format(get_display_name(await event.get_chat()), event.chat_id, sleeptimet, counter, spam_message)
            )


@ayiin_cmd(pattern="spam ([\\s\\S]*)")
async def nyespam(event):
    if event.chat_id in BLACKLIST_CHAT:
        return await event.edit(get_string("ayiin_1"))
    spammer = await event.get_reply_message()
    xnxx = ("".join(event.text.split(maxsplit=1)[1:])).split(" ", 1)
    try:
        counter = int(xnxx[0])
    except Exception:
        return await eod(
            event, get_string("spam_9").format(cmd)
        )
    if counter > 50:
        sleeptimet = 0.5
        sleeptimem = 1
    else:
        sleeptimet = 0.1
        sleeptimem = 0.3
    await event.delete()
    addgvar("spamwork", True)
    await spam_function(event, spammer, xnxx, sleeptimem, sleeptimet)


@ayiin_cmd(pattern="sspam$")
async def stickerpack_spam(event):
    if event.chat_id in BLACKLIST_CHAT:
        return await event.edit(get_string("ayiin_1"))
    reply = await event.get_reply_message()
    if not reply or media_type(
            reply) is None or media_type(reply) != "Sticker":
        return await eod(
            event, get_string("sspam_1")
        )
    try:
        stickerset_attr = reply.document.attributes[1]
        xyz = await eor(event, get_string("sspam_2"))
    except BaseException:
        await eod(event, get_string("sspam_3"))
        return
    try:
        get_stickerset = await event.client(
            GetStickerSetRequest(
                types.InputStickerSetID(
                    id=stickerset_attr.stickerset.id,
                    access_hash=stickerset_attr.stickerset.access_hash,
                )
            )
        )
    except Exception:
        return await eod(
            xyz, get_string("sspam_4")
        )
    reqd_sticker_set = await event.client(
        functions.messages.GetStickerSetRequest(
            stickerset=types.InputStickerSetShortName(
                short_name=f"{get_stickerset.set.short_name}"
            )
        )
    )
    addgvar("spamwork", True)
    for m in reqd_sticker_set.documents:
        if gvarstatus("spamwork") is None:
            return
        await event.client.send_file(event.chat_id, m)
        await asyncio.sleep(0.7)
    if BOTLOG_CHATID:
        if event.is_private:
            await event.client.send_message(
                BOTLOG_CHATID, get_string("sspam_5").format(event.chat_id)
            )
        else:
            await event.client.send_message(
                BOTLOG_CHATID, get_string("sspam_6").format(get_display_name(await event.get_chat()), event.chat_id)
            )
        await event.client.send_file(BOTLOG_CHATID, reqd_sticker_set.documents[0])


@ayiin_cmd(pattern="cspam ([\\s\\S]*)")
async def tmeme(event):
    if event.chat_id in BLACKLIST_CHAT:
        return await event.edit(get_string("ayiin_1"))
    cspam = "".join(event.text.split(maxsplit=1)[1:])
    message = cspam.replace(" ", "")
    await event.delete()
    addgvar("spamwork", True)
    for letter in message:
        if gvarstatus("spamwork") is None:
            return
        await event.respond(letter)
    if BOTLOG_CHATID:
        if event.is_private:
            await event.client.send_message(
                BOTLOG_CHATID, get_string("cspam_1").format(event.chat_id, message)
            )
        else:
            await event.client.send_message(
                BOTLOG_CHATID, get_string("cspam_2").format(get_display_name(await event.get_chat()), event.chat_id, message)
            )


@ayiin_cmd(pattern="wspam ([\\s\\S]*)")
async def tmeme(event):
    if event.chat_id in BLACKLIST_CHAT:
        return await event.edit(get_string("ayiin_1"))
    wspam = "".join(event.text.split(maxsplit=1)[1:])
    message = wspam.split()
    await event.delete()
    addgvar("spamwork", True)
    for word in message:
        if gvarstatus("spamwork") is None:
            return
        await event.respond(word)
    if BOTLOG_CHATID:
        if event.is_private:
            await event.client.send_message(
                BOTLOG_CHATID, get_string("wspam_1").format(event.chat_id, message)
            )
        else:
            await event.client.send_message(
                BOTLOG_CHATID, get_string("wspam_2").format(get_display_name(await event.get_chat()), event.chat_id, message)
            )


SPAM_STATUS = {}

@ayiin_cmd(pattern="(delayspam|dspam|dlspam|spamd) ([\\s\\S]*)")
async def dlyspam(event):
    if event.chat_id in BLACKLIST_CHAT:
        return await event.edit(get_string("ayiin_1"))

    reply = await event.get_reply_message()
    input_str = "".join(event.text.split(maxsplit=1)[1:]).split(" ", 2)

    try:
        sleeptimet = sleeptimem = float(input_str[0])
    except Exception:
        return await eod(
            event, get_string("dspam_1").format(event.pattern_match.group(1))
        )

    try:
        count = int(input_str[1])
    except Exception:
        return await eod(
            event, get_string("dspam_1").format(event.pattern_match.group(1))
        )

    # Ambil teks tambahan kalau ada
    text = input_str[2] if len(input_str) > 2 else None

    await event.delete()
    SPAM_STATUS[event.chat_id] = True

    async def delay_spam_function(event, reply, count, text, sleeptimem, sleeptimet, chat_id=None):
        from asyncio import sleep

        for _ in range(count):
            if SPAM_STATUS.get(chat_id) is False:
                break

            if reply and reply.media:
                if reply.text:
                    # Kalau media ada caption, spam media + caption sebanyak count
                    await event.client.send_file(chat_id, reply.media, caption=reply.text)
                else:
                    # Kalau media tanpa caption, spam media + teks (kalau ada)
                    await event.client.send_file(chat_id, reply.media, caption=text or "")
            else:
                if text:
                    await event.client.send_message(chat_id, text)

            await sleep(sleeptimet)

    await delay_spam_function(event, reply, count, text, sleeptimem, sleeptimet, chat_id=event.chat_id)
    
    if BOTLOG_CHATID:
        try:
            chat = await event.get_chat()
            name = get_display_name(chat)
        except Exception:
            name = "Tidak diketahui"

    if event.is_private:
        await event.client.send_message(
            BOTLOG_CHATID,
            get_string("spam_7").format(
                event.chat_id,   # user_id
                sleeptimet,           # delay detik
                count,          # jumlah pesan
                text or (reply.text if reply else "")  # isi pesan
            )
        )
    else:
        await event.client.send_message(
            BOTLOG_CHATID,
            get_string("spam_8").format(
                name,            # nama chat
                event.chat_id,   # chat_id
                sleeptimet,           # delay detik
                count,          # jumlah pesan
                text or (reply.text if reply else "")  # isi pesan
            )
        )
            

@ayiin_cmd(pattern="stopdspam(?:\\s+([\\s\\S]+))?")
async def stop_dlyspam(event):
    args = event.pattern_match.group(1)
    if not args:
        target_chat = event.chat_id
    else:
        if args.startswith("@") or args.isalpha():
            try:
                entity = await event.client.get_entity(args)
                target_chat = entity.id
            except Exception:
                return await event.edit(f"❌ Gagal menemukan grup `{args}`. Pastikan bot sudah join grup tersebut.")
        else:
            try:
                target_chat = int(args)
            except ValueError:
                return await event.edit("⚠️ Format chat ID atau username salah.")

    if target_chat in SPAM_STATUS and SPAM_STATUS[target_chat]:
        SPAM_STATUS[target_chat] = False
        await event.edit(f"🛑 Delay spam di `{target_chat}` berhasil dihentikan.")
    else:
        await event.edit(f"🚫 Tidak ada delay spam aktif di `{target_chat}`.")

@ayiin_cmd(pattern="listdspam$")
async def list_dspam(event):
    if not SPAM_STATUS:
        return await event.edit("✅ Tidak ada delay spam yang aktif.")

    active_chats = [cid for cid, status in SPAM_STATUS.items() if status]
    if not active_chats:
        return await event.edit("✅ Tidak ada delay spam yang aktif.")

    text = "**📋 List Delay Spam Aktif:**\n"
    for cid in active_chats:
        try:
            entity = await event.client.get_entity(int(cid))
            name = entity.title
        except Exception:
            name = "Tidak diketahui"
        text += f"• `{cid}` [{name}]\n"

    await event.edit(text)

async def delay_spam_function(event, reply, xnxx, sleeptimem, sleeptimet, chat_id):
    try:
        counter = int(xnxx[0])
        spam_text = str(xnxx[1]) if len(xnxx) > 1 else reply.text if reply else None
    except Exception:
        return await eod(event, "⚠️ Format salah. Coba lagi.")

    if not spam_text:
        return await eod(event, "⚠️ Tidak ada teks untuk di-spam.")

    for _ in range(counter):
        if not SPAM_STATUS.get(chat_id, False):
            break
        await event.client.send_message(chat_id, spam_text)
        await asyncio.sleep(sleeptimem)


SPAMFW_STATUS = {}

@ayiin_cmd(pattern="(delayspamfw|dspamfw|dlspamfw|dlyspamfw) ([\s\S]*)")
async def dlyspamfw(event):
    if event.chat_id in BLACKLIST_CHAT:
        return await event.edit(get_string("ayiin_1"))

    input_str = "".join(event.text.split(maxsplit=1)[1:]).split(" ", 2)  
    try:  
        sleeptimet = sleeptimem = float(input_str[0])  
    except Exception:  
        return await eod(event, get_string("dspam_1").format(cmd))  

    try:  
        counter = int(input_str[1])  
    except Exception:  
        return await eod(event, get_string("dspam_1").format(cmd))  

    channel_message_link = input_str[2]  

    try:  
        message_id = int(channel_message_link.split('/')[-1])  
        channel_username = channel_message_link.split('/')[3]  
        channel = await event.client.get_entity(channel_username)  
        message = await event.client.get_messages(channel, ids=message_id)  
    except Exception as e:  
        return await eod(event, f"Error: {str(e)}")  

    await event.delete()  
    addgvar("spamwork", True)  

    for _ in range(counter):  
        if gvarstatus("spamwork") is None:  
            return  
        await event.client.forward_messages(event.chat_id, message.id, channel)  
        await asyncio.sleep(sleeptimem)  

    if BOTLOG_CHATID:  
        if event.is_private:  
            await event.client.send_message(  
                BOTLOG_CHATID, get_string("dspamfw_1").format(event.chat_id, counter, message.text)  
            )  
        else:  
            await event.client.send_message(  
                BOTLOG_CHATID, get_string("dspamfw_2").format(get_display_name(await event.get_chat()), event.chat_id, counter, message.text)  
    )


@ayiin_cmd(pattern="stopfw(?:\\s+([\\s\\S]+))?")
async def stop_fwspam(event):
    args = event.pattern_match.group(1)
    if not args:
        target_chat = event.chat_id
    else:
        if args.startswith("@") or args.isalpha():
            try:
                entity = await event.client.get_entity(args)
                target_chat = entity.id
            except Exception:
                return await event.edit(f"❌ Gagal menemukan grup `{args}`.")
        else:
            try:
                target_chat = int(args)
            except ValueError:
                return await event.edit("⚠️ Format chat ID atau username salah.")

    if target_chat in SPAMFW_STATUS and SPAMFW_STATUS[target_chat]:
        SPAMFW_STATUS[target_chat] = False
        await event.edit(f"🛑 Forward spam di `{target_chat}` berhasil dihentikan.")
    else:
        await event.edit(f"🚫 Tidak ada forward spam aktif di `{target_chat}`.")


@ayiin_cmd(pattern="listfw$")
async def list_fwspam(event):
    if not SPAMFW_STATUS:
        return await event.edit("✅ Tidak ada forward spam yang aktif.")

    active_chats = [cid for cid, status in SPAMFW_STATUS.items() if status]
    if not active_chats:
        return await event.edit("✅ Tidak ada forward spam yang aktif.")

    text = "**📋 List Forward Spam Aktif:**\n"
    for cid in active_chats:
        try:
            entity = await event.client.get_entity(int(cid))
            name = entity.title
        except Exception:
            name = "Tidak diketahui"
        text += f"• `{cid}` [{name}]\n"

    await event.edit(text)
    

@ayiin_cmd(pattern=r"^.setgc (\S+) (\S+)")
async def set_gc(event):
    list_name = event.pattern_match.group(1)
    target = event.pattern_match.group(2)
    try:
        entity = await event.client.get_entity(target)
        group_list[list_name].append(entity.id)
        await event.edit(f"✅ Grup **{entity.title}** (`{entity.id}`) berhasil ditambahkan ke list `{list_name}`.")
    except Exception as e:
        await event.edit(f"❌ Gagal: {e}")

# Perhatikan bahwa saya menghapus bagian penggunaan `MessageEdited` karena itu tidak perlu di sini.


# Fungsi untuk menampilkan daftar target grup dan list yang disebar dengan username
@ayiin_cmd(pattern="listset$")
async def list_set(event):
    if event.chat_id in BLACKLIST_CHAT:
        return await event.edit("Dilarang di sini.")

    # Ambil semua chat_id dari database untuk daftar target grup
    cursor.execute("SELECT chat_id FROM spam_targets")
    targets = cursor.fetchall()

    if not targets:
        await event.reply("❌ Tidak ada grup dalam daftar target spam.")
        return

    # Ambil username untuk setiap chat_id
    target_usernames = []
    for target in targets:
        try:
            group = await event.client.get_entity(target[0])
            target_usernames.append(f"@{group.username}" if group.username else f"ID: {group.id}")
        except Exception as e:
            target_usernames.append(f"ID: {target[0]} (gagal ambil username)")

    # Format username menjadi string yang bisa ditampilkan
    target_usernames_str = "\n".join(target_usernames)

    # Ambil list yang sudah disebar
    cursor.execute("SELECT list_name FROM spam_lists")
    spam_lists = cursor.fetchall()

    if not spam_lists:
        await event.reply(f"📝 Daftar grup dalam target spam:\n{target_usernames_str}\n\n❌ Belum ada list yang disebar.")
        return

    # Format list yang sudah disebar menjadi string
    list_names = "\n".join([spam_list[0] for spam_list in spam_lists])

    # Menampilkan daftar target grup dan list yang disebar
    await event.reply(f"📝 Daftar grup dalam target spam:\n{target_usernames_str}\n\n📜 List yang telah disebar:\n{list_names}")

# Fungsi untuk menghapus grup berdasarkan username atau chat_id
@ayiin_cmd(pattern="delgc (@\w+|\-?\d+)$")
async def del_gc(event):
    if event.chat_id in BLACKLIST_CHAT:
        return await event.edit("Dilarang di sini.")

    # Ambil username atau chat_id
    group_identifier = event.pattern_match.group(1)

    # Cek apakah identifier yang diberikan berupa username atau chat_id
    if group_identifier.startswith('@'):
        username = group_identifier
        try:
            group = await event.client.get_entity(username)
            chat_id = group.id
        except Exception:
            return await event.reply(f"❌ Gagal menemukan grup dengan username `{username}`.")
    else:
        chat_id = int(group_identifier)

    # Cek apakah grup ada dalam daftar target spam
    cursor.execute("SELECT chat_id FROM spam_targets WHERE chat_id = ?", (chat_id,))
    existing = cursor.fetchone()

    if not existing:
        return await event.reply(f"❌ Grup dengan ID `{chat_id}` tidak ditemukan dalam daftar target.")

    # Menghapus grup dari daftar target
    cursor.execute("DELETE FROM spam_targets WHERE chat_id = ?", (chat_id,))
    conn.commit()

    await event.reply(f"✅ Grup dengan ID `{chat_id}` berhasil dihapus dari daftar target.")

# Fungsi untuk spam forward menggunakan link langsung
@ayiin_cmd(pattern="spamfw (\d+) (\S+)$")
async def spamfw(event):
    if event.chat_id in BLACKLIST_CHAT:
        return await event.edit("Dilarang di sini.")

    # Ambil delay dan link pesan channel yang diberikan
    delay = event.pattern_match.group(1)
    channel_message_link = event.pattern_match.group(2)

    try:
        sleeptimem = float(delay)  # Mengonversi delay menjadi angka float
    except ValueError:
        return await event.reply("❌ Format delay salah. Harus berupa angka.")

    try:
        # Ambil message_id dan channel_username dari link
        message_id = int(channel_message_link.split('/')[-1])
        channel_username = channel_message_link.split('/')[3]
        channel = await event.client.get_entity(channel_username)
        message = await event.client.get_messages(channel, ids=message_id)
    except Exception as e:
        return await event.reply(f"❌ Error: {str(e)}")

    # Ambil semua grup yang terdaftar untuk spam forward
    cursor.execute("SELECT chat_id FROM spamfw_targets")
    targets = cursor.fetchall()

    if not targets:
        return await event.reply("❌ Tidak ada grup dalam daftar target spam forward.")

    await event.delete()
    SPAMFW_STATUS[event.chat_id] = True  # Menandakan spam sedang berjalan

    # Lakukan forward spam ke setiap grup
    for target in targets:
        chat_id = target[0]
        try:
            await event.client.forward_messages(chat_id, message.id, channel)
            await asyncio.sleep(sleeptimem)
        except Exception as e:
            await event.reply(f"❌ Gagal forward ke grup dengan ID `{chat_id}`: {str(e)}")

    if BOTLOG_CHATID:
        log_msg = "Spam forward selesai." if event.is_private else "Spam forward selesai di grup."
        await event.client.send_message(
            BOTLOG_CHATID, log_msg.format(event.chat_id)
        )
        
# Fungsi untuk menghentikan forward spam pada grup (stoplist untuk spamfw)
@ayiin_cmd(pattern="stoplistfw (@\w+|\-?\d+)$")
async def stop_listfw(event):
    if event.chat_id in BLACKLIST_CHAT:
        return await event.edit("Dilarang di sini.")

    # Ambil username atau chat_id
    group_identifier = event.pattern_match.group(1)

    # Cek apakah identifier yang diberikan berupa username atau chat_id
    if group_identifier.startswith('@'):
        username = group_identifier
        try:
            group = await event.client.get_entity(username)
            chat_id = group.id
        except Exception:
            return await event.reply(f"❌ Gagal menemukan grup dengan username `{username}`.")
    else:
        chat_id = int(group_identifier)

    # Cek apakah grup ada dalam daftar target spam forward
    cursor.execute("SELECT chat_id FROM spamfw_targets WHERE chat_id = ?", (chat_id,))
    existing = cursor.fetchone()

    if not existing:
        return await event.reply(f"❌ Grup dengan ID `{chat_id}` tidak ditemukan dalam daftar target spam forward.")

    # Menghapus grup dari daftar target spam forward (stop list)
    cursor.execute("DELETE FROM spamfw_targets WHERE chat_id = ?", (chat_id,))
    conn.commit()

    await event.reply(f"✅ Spam forward dihentikan di grup dengan ID `{chat_id}`. Grup ini telah dihapus dari daftar target.")


CMD_HELP.update(
    {
        "spam": f"**Plugin :** `spam`\
\n\n  »  **Perintah :** `{cmd}spam` <jumlah> <teks>\
\n  »  **Kegunaan :** Membanjiri chat dengan teks berulang sebanyak jumlah yang ditentukan.\
\n\n  »  **Perintah :** `{cmd}cspam` <teks>\
\n  »  **Kegunaan :** Spam karakter satu per satu dari teks yang diberikan.\
\n\n  »  **Perintah :** `{cmd}sspam` <balas stiker>\
\n  »  **Kegunaan :** Spam semua stiker dari sticker pack yang dibalas.\
\n\n  »  **Perintah :** `{cmd}wspam` <teks>\
\n  »  **Kegunaan :** Spam kata per kata dari teks.\
\n\n  »  **Perintah :** `{cmd}picspam` <jumlah> <link_gambar>\
\n  »  **Kegunaan :** Spam gambar/foto/gif dari link yang diberikan.\
\n\n  »  **Perintah :** `{cmd}delayspam` <delay> <jumlah> <teks>\
\n  »  **Kegunaan :** Spam teks dengan jeda antar pesan.\
\n\n  »  **Perintah :** `{cmd}stopdspam`\
\n  »  **Kegunaan :** Menghentikan spam delay di grup saat ini.\
\n\n  »  **Perintah :** `{cmd}listdspam`\
\n  »  **Kegunaan :** Menampilkan semua spam delay yang aktif.\
\n\n  »  **Perintah :** `{cmd}dspamfw` <delay> <jumlah> <link_post_channel>\
\n  »  **Kegunaan :** Spam konten dari post channel berkali-kali dengan delay.\
\n\n  »  **Perintah :** `{cmd}stopfw`\
\n  »  **Kegunaan :** Menghentikan spam forward di grup saat ini.\
\n\n  »  **Perintah :** `{cmd}listfw`\
\n  »  **Kegunaan :** Menampilkan semua spam forward yang sedang aktif.\
\n\n  •  **NOTE :** Spam dengan Risiko Anda sendiri. Jangan salah gunakan!"
    }
)
