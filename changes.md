# Список изменений с версии 1.4.3

## Новые функции

* Добавлен флаг "-l" аналогично moonraker/klipper
* Добавлен параметр "upload_path" - путь сохранения загружаемых gcode файлов
* Добавлен параметр "hidden_bot_commands" для фильтрации добавляемых команд
* Добавлена возмодность выводить состояния всех moonraker power devices


## Добработки и мелкие исправления
* Исправлена загрузка превью gcode
* Текущая конфигурация бота записывается в лог при старте бота
* Кнопка удаления несобранных таймлапсов
* Убран параметр log_path
* Добавлен fan в секцию status_message_heater_fans
* Добавлен параметр progress_update_message


## Описать в документации
* Переименование "disabled_macros"->"hidden_macros"
* Переименование "show_hidden_macros"->"show_private_macros"
