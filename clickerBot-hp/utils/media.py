from pathlib import Path

from aiogram.types import FSInputFile, Message, User

from utils.formatting import format_user_link


ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


async def send_click_image(
    msg: Message,
    caption: str,
    image_name: str,
    user: User | None = None,
) -> None:
    selected_user = user or msg.from_user
    user_text = format_user_link(selected_user)
    full_caption = f"{user_text} {caption}"

    path = ASSETS_DIR / image_name
    if path.is_file():
        await msg.answer_photo(FSInputFile(path), caption=full_caption)
    else:
        await msg.reply(full_caption)
