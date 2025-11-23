# Ayiin - Userbot
# Copyright (C) 2022-2023 @AyiinXd
#
# This file is a part of < https://github.com/AyiinXd/Ayiin-Userbot >
# PLease read the GNU Affero General Public License in
# <https://www.github.com/AyiinXd/Ayiin-Userbot/blob/main/LICENSE/>.
#
# FROM Ayiin-Userbot <https://github.com/AyiinXd/Ayiin-Userbot>
# t.me/AyiinXdSupport & t.me/AyiinSupport

# ========================×========================
#            Jangan Hapus Credit Ngentod
# ========================×========================

import time
from datetime import datetime
from secrets import choice


from AyiinXd import CMD_HANDLER as cmd
from AyiinXd import CMD_HELP, StartTime
from AyiinXd import DEVS
from AyiinXd.events import register
from .ping import get_readable_time


absen = [
    "**hadir xall**",
    "**hadir bang**",
    "**hadir ni**",
    "**gua disini coii**",
    "**hadir boss**",
    "**apa xall?**",
    "**oit gua disini**",
    "**hadir lah**",
    "**hadir paduka ixall**",
    "**apa xall? gua lagi ngewe**",
    "**apa xall? gua lagi coli**",
    "**apa kontol**",
    "**hadir anjing, berisik**",
    "**sorry, kenapa ngentot?**",
    "**kenapa sayang**",
    "**ah ah ngewe**",
    "**apa**",
]

ixallkece = [
    "**muka lu kek kontol**",
    "**buset jungkok juga malah gantengnya bang**",
    "**iya ganteng sayang**",
    "**ganteng ih jadi pengen gua ewe**",
    "**berisik jelek**",
]


@register(incoming=True, from_users=DEVS, pattern=r"^Cping$")
async def _(ping):
    uptime = await get_readable_time((time.time() - StartTime))
    start = datetime.now()
    end = datetime.now()
    duration = (end - start).microseconds / 1000
    user = await ping.client.get_me()
    message = "**♘ 𝗜𝗫𝗔𝗟𝗟-Userbot**\n\n├ 私 **ᴘɪɴɢᴇʀ :** `{} ms`\n├ さ **ᴜᴘᴛɪᴍᴇ :** `{}`\n├ ふ **ᴏᴡɴᴇʀ :** `{}`\n├ 尔 **ɪᴅ :** `{}`"
    await ping.reply(message.format(duration, uptime, user.first_name, user.id)
                     )


# KALO NGEFORK absen ini GA USAH DI HAPUS YA GOBLOK 😡
# JANGAN DI HAPUS GOBLOK 😡 LU COPY AJA TINGGAL TAMBAHIN
# DI HAPUS GUA GBAN YA 🥴 GUA TANDAIN LU AKUN TELENYA 😡

# Absen by : mrismanaziz <https://github.com/mrismanaziz/man-userbot>

@register(incoming=True, from_users=DEVS, pattern=r"^Absen$")
async def kazuabsen(ganteng):
    await ganteng.reply(choice(absen))

@register(incoming=True, from_users=DEVS, pattern=r"^Update$")
async def naya(naya):
    await naya.reply(".update deploy")

@register(incoming=True, from_users=DEVS, pattern=r"^Gua ganteng kan$")
async def kazu(ganteng):
    await ganteng.reply(choice(ixallkece))


# ========================×========================
#            Jangan Hapus Credit Ngentod
# ========================×========================


CMD_HELP.update(
    {
        "yinsping": f"**Plugin:** `Kazuping`\
        \n\n  »  **Perintah : **`Perintah Ini Hanya Untuk Devs 𝗜𝗫𝗔𝗟𝗟-Userbot Tod.`\
        \n  »  **Kegunaan :** __Silahkan Ketik `{cmd}ping` Untuk Publik.__\
    "
    }
)
