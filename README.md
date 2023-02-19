# wilhelm

Simple [Telegram bot](https://github.com/python-telegram-bot/python-telegram-bot) client for [Diplomacy](https://en.wikipedia.org/wiki/Diplomacy_(game)) games hosted on [playdiplomacy.com](https://www.playdiplomacy.com/) using [MechanicalSoup](https://mechanicalsoup.readthedocs.io/en/stable/).

Its main functionality is the `\tell` command, which tells the time that is left until the next round.

Auxiliary functionalities include:

* Periodic reminders activated via `\enable` and disabled via `\disable`
* Map image fetching via `\fetch` and animation via `\animate`
* Fun messages from the bot admin dispersed via `\megaphone`

To get started, install the requirements (plus `ffmpeg`), set environment variables appropriately, and run the script.