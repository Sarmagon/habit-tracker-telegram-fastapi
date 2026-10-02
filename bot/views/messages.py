from telebot import types


def create_habit_keyboard(habit):
    keyboard = types.InlineKeyboardMarkup()
    habit_identifier = habit["identifier"]
    if habit.get("record_date"):
        record_date = habit["record_date"]
        keyboard.row(
            types.InlineKeyboardButton(
                "✅ Выполнено", callback_data=f"mark:{habit_identifier}:1:{record_date}"
            ),
            types.InlineKeyboardButton(
                "❌ Не выполнено",
                callback_data=f"mark:{habit_identifier}:0:{record_date}",
            ),
        )
    keyboard.row(
        types.InlineKeyboardButton(
            "Изменить", callback_data=f"edit:{habit_identifier}"
        ),
        types.InlineKeyboardButton(
            "История", callback_data=f"history:{habit_identifier}"
        ),
        types.InlineKeyboardButton(
            "Удалить", callback_data=f"delete:{habit_identifier}"
        ),
    )
    return keyboard


def format_habit_message(habit):
    status = {True: "✅ выполнено", False: "❌ не выполнено", None: "⏳ без отметки"}
    return (
        f"{habit['title']}\n{habit['description']}\n"
        f"Период: {habit['start_date']} — {habit['end_date'] or 'без ограничения'}\n"
        f"Выполнений: {habit['completion_count']}\n"
        f"Сегодня: {status[habit['completed']]}"
        + ("\nПривычка освоена 🎉" if habit["archived"] else "")
    )
