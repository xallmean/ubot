from telethon import Button
from AyiinXd import (
    DEFAULT,
    DEVS,
    LOGS,
    LOOP,
    STRING_SESSION,
    blacklistayiin,
    bot,
    tgbot,
    BOTLOG_CHATID,
    BOTLOG,
)

async def startupmessage():
    """
    Start up message in telegram logger group
    """
    try:
        if BOTLOG:
            await tgbot.send_file(
                BOTLOG_CHATID,
                "https://telegra.ph/file/b17248930f58bbdaf2e23.jpg",
                caption="𝗜𝗫𝗔𝗟𝗟-Userbot.\n     **status : Active\n     ketik `.ping` untuk cek bot!**",
                buttons=[(Button.url("Store", "https://t.me/jasebxall")),
                         (Button.url("Support", "https://t.me/ixallsupport"))]
            )
    except Exception as e:
        LOGS.error(e)
        return None
