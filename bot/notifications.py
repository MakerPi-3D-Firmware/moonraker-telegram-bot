import configparser
import logging
import time
from datetime import timedelta

from apscheduler.schedulers.base import BaseScheduler
from telegram import ChatAction
from telegram.ext import Updater

from camera import Camera
from klippy import Klippy

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, config: configparser.ConfigParser, bot_updater: Updater, chat_id: int, klippy: Klippy, camera_wrapper: Camera, scheduler: BaseScheduler, logging_handler: logging.Handler = None,
                 debug_logging: bool = False):
        self._bot_updater: Updater = bot_updater
        self._chat_id: int = chat_id
        self._cam_wrap: Camera = camera_wrapper
        self._sched = scheduler
        self._klippy: Klippy = klippy

        self._percent: int = config.getint('progress_notification', 'percent', fallback=0)
        self._height: int = config.getint('progress_notification', 'height', fallback=0)
        self._interval: int = config.getint('progress_notification', 'time', fallback=0)
        self._notify_groups: list = [el.strip() for el in config.get('progress_notification', 'groups').split(',')] if 'progress_notification' in config and 'groups' in config[
            'progress_notification'] else list()
        self._group_only: bool = config.getboolean('progress_notification', 'group_only', fallback=False)

        self._silent_progress = config.getboolean('telegram_ui', 'silent_progress', fallback=True)
        self._silent_commands = config.getboolean('telegram_ui', 'silent_commands', fallback=True)
        self._silent_status = config.getboolean('telegram_ui', 'silent_status', fallback=True)

        self._last_height: int = 0
        self._last_percent: int = 0
        self._last_message: str = ''

        if logging_handler:
            logger.addHandler(logging_handler)
        if debug_logging:
            logger.setLevel(logging.DEBUG)

    @property
    def silent_commands(self):
        return self._silent_commands

    @property
    def silent_status(self):
        return self._silent_status

    @property
    def message(self):
        return self._last_message

    @message.setter
    def message(self, new_value: str):
        self._last_message = new_value

    @property
    def percent(self):
        return self._percent

    @percent.setter
    def percent(self, new_value: int):
        if new_value >= 0:
            self._percent = new_value

    @property
    def height(self):
        return self._percent

    @height.setter
    def height(self, new_value: float):
        if new_value >= 0:
            self._height = new_value

    @property
    def interval(self):
        return self._interval

    @interval.setter
    def interval(self, new_value: int):
        if new_value == 0:
            self._interval = new_value
            self.remove_notifier_timer()
        elif new_value > 0:
            self._interval = new_value
            self._reschedule_notifier_timer()

    def _send_message(self, message: str, silent: bool, group_only: bool = False):
        if not group_only:
            self._bot_updater.bot.send_chat_action(chat_id=self._chat_id, action=ChatAction.TYPING)
            self._bot_updater.bot.send_message(self._chat_id, text=message, disable_notification=silent)
        for group in self._notify_groups:
            self._bot_updater.bot.send_chat_action(chat_id=group, action=ChatAction.TYPING)
            self._bot_updater.bot.send_message(group, text=message, disable_notification=silent)

    def _notify(self, message: str, silent: bool, group_only: bool = False):
        if self._cam_wrap.enabled:
            with self._cam_wrap.take_photo() as photo:
                if not group_only:
                    self._bot_updater.bot.send_chat_action(chat_id=self._chat_id, action=ChatAction.UPLOAD_PHOTO)
                    self._bot_updater.bot.send_photo(self._chat_id, photo=photo, caption=message, disable_notification=silent)
                for group_ in self._notify_groups:
                    photo.seek(0)
                    self._bot_updater.bot.send_chat_action(chat_id=group_, action=ChatAction.UPLOAD_PHOTO)
                    self._bot_updater.bot.send_photo(group_, photo=photo, caption=message, disable_notification=silent)
                photo.close()
        else:
            self._send_message(message, silent)

    def send_error(self, message: str):
        self._sched.add_job(self._send_message, kwargs={'message': message, 'silent': False}, misfire_grace_time=None, coalesce=False, max_instances=6, replace_existing=False)

    def send_error_with_photo(self, message: str):
        self._sched.add_job(self._notify, kwargs={'message': message, 'silent': False}, misfire_grace_time=None, coalesce=False, max_instances=6, replace_existing=False)

    def send_notification(self, message: str):
        self._sched.add_job(self._send_message, kwargs={'message': message, 'silent': self._silent_status}, misfire_grace_time=None, coalesce=False, max_instances=6, replace_existing=False)

    def send_notification_with_photo(self, message: str):
        self._sched.add_job(self._notify, kwargs={'message': message, 'silent': self._silent_status}, misfire_grace_time=None, coalesce=False, max_instances=6, replace_existing=False)

    def reset_notifications(self) -> None:
        self._last_percent = 0
        self._last_height = 0
        self._klippy.printing_duration = 0
        self._last_message = ''

    def schedule_notification(self, progress: int = 0, position_z: int = 0):
        if not self._klippy.printing or self._klippy.printing_duration <= 0.0 or (self._height == 0 and self._percent == 0):
            return

        notifymsg = ''
        if progress != 0 and self._percent != 0:
            if progress < self._last_percent - self._percent:
                self._last_percent = progress
            if progress % self._percent == 0 and progress > self._last_percent:
                notifymsg = f"Printed {progress}%\n"
                self._last_percent = progress

        if position_z != 0 and self._height != 0:
            if position_z < self._last_height - self._height:
                self._last_height = position_z
            if position_z % self._height == 0 and position_z > self._last_height:
                notifymsg = f"Printed {position_z}mm\n"
                self._last_height = position_z

        if notifymsg:
            if self._last_message:
                notifymsg += f"{self._last_message}\n"
            notifymsg += f"{self._klippy.get_eta_message()}"

            self._sched.add_job(self._notify, kwargs={'message': notifymsg, 'silent': self._silent_progress, 'group_only': self._group_only}, misfire_grace_time=None, coalesce=False, max_instances=6,
                                replace_existing=False)

    def _notify_by_time(self):
        if not self._klippy.printing or self._klippy.printing_duration <= 0.0:
            return

        notifymsg = f"Printing for {timedelta(seconds=round(self._klippy.printing_duration))}\n"
        if self._last_message:
            notifymsg += f"{self._last_message}\n"
        notifymsg += f"{self._klippy.get_eta_message()}"
        self._notify(notifymsg, self._silent_progress, self._group_only)

    def add_notifier_timer(self):
        if self._interval > 0:
            # Todo: maybe check if ob exists?
            self._sched.add_job(self._notify_by_time, 'interval', seconds=self._interval, id='notifier_timer', replace_existing=True)

    def remove_notifier_timer(self):
        if self._sched.get_job('notifier_timer'):
            self._sched.remove_job('notifier_timer')

    def _reschedule_notifier_timer(self):
        if self._interval > 0 and self._sched.get_job('notifier_timer'):
            self._sched.add_job(self._notify_by_time, 'interval', seconds=self._interval, id='notifier_timer', replace_existing=True)

    def stop_all(self):
        self.reset_notifications()
        self.remove_notifier_timer()
