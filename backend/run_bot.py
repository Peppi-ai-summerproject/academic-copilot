from app.telegram.bot import create_bot


def main() -> None:
    bot = create_bot()

    print("Telegram bot is running...")
    print("Press Ctrl+C to stop.")

    bot.run_polling()


if __name__ == "__main__":
    main()