from marshmallow import Schema, fields, post_dump
from nxdrive.wui.translator import Translator
from dateutil.tz import tzlocal
from datetime import datetime
import calendar
import time


class ServerBindingSettingsSchema(Schema):
    web_authentication = fields.Boolean()
    server_url = fields.Str()
    username = fields.Str()
    need_password_update = fields.Boolean(attribute='pwd_update_required')
    initialized = fields.Boolean()
    server_version = fields.Str()


class ActionSchema(Schema):
    name = fields.Str(attribute='type')
    percent = fields.Function(lambda obj: obj.get_percent())
    size = fields.Integer()
    filename = fields.Str()
    filepath = fields.Str()

    def export(self, action):
        return self.dump(action).data

    @post_dump(pass_many=False)
    def remove_unneccessary_fields(self, data):
        # should it remove all None fields?
        for key in ["percent", "size", "filename", "filepath"]:
            try:
                if data[key] is None:
                    del data[key]
            except KeyError:
                pass


class WorkerSchema(Schema):
    thread_id = fields.Str(attribute='_thread_id')
    name = fields.Str(attribute='_name')
    paused = fields.Function(lambda obj: obj.is_paused())
    started = fields.Function(lambda obj: obj.is_started())
    action = fields.Nested(ActionSchema)

    @post_dump(pass_many=False)
    def remove_unneccessary_fields(self, data):
        # should it remove all None fields?
        try:
            if data["action"] is None:
                del data["action"]
        except KeyError:
            pass

    def export(self, worker):
        return self.dump(worker).data


class StateSchema(Schema):
    state = fields.Str(attribute="pair_state")
    last_sync_direction = fields.Function(lambda obj: "download" if obj.last_local_updated > obj.last_remote_updated else "upload")
    last_sync = fields.Method('get_last_sync')
    last_sync_date = fields.Method('get_last_sync_date')
    name = fields.Function(lambda state: state.local_name if state.local_name is not None else state.remote_name)
    remote_name = fields.Str()
    last_error = fields.Str()
    local_path = fields.Str()
    local_parent_path = fields.Str()
    remote_ref = fields.Str()
    folderish = fields.Boolean()
    last_transfer = fields.Date()
    id = fields.Str()

    def _get_date_from_sqlite(self, d):
        if d is None:
            return 0
        format_date = "%Y-%m-%d %H:%M:%S"
        return datetime.strptime(str(d.split(".")[0]), format_date)

    def _get_timestamp_from_date(self, d):
        if d == 0:
            return 0
        return int(calendar.timegm(d.timetuple()))

    def _get_timestamp_from_sqlite(self, d):
        return int(calendar.timegm(self.get_date_from_sqlite(d).timetuple()))

    def get_last_sync(self, state):
        current_time = int(time.time())
        date_time = self._get_date_from_sqlite(state.last_sync_date)
        sync_time = self._get_timestamp_from_date(date_time)
        return current_time - sync_time

    def get_last_sync_date(self, state):
        date_time = self._get_date_from_sqlite(state.last_sync_date)
        return Translator.format_datetime(date_time + tzlocal._dst_offset) if date_time != 0 else ""

    @post_dump(pass_many=False)
    def update_last_transfer(self, data):
        if "last_transfer" not in data or data["last_transfer"] is None:
            data["last_transfer"] = data["last_sync_direction"]

    def export(self, state):
        return self.dump(state).data


class NotificationSchema(Schema):
    level = fields.Function(lambda obj: obj.get_level())
    uid = fields.Function(lambda obj: obj.get_uid())
    title = fields.Function(lambda obj: obj.get_title())
    description = fields.Function(lambda obj: obj.get_description())
    discardable = fields.Function(lambda obj: obj.is_discardable())
    discard = fields.Function(lambda obj: obj.is_discard())
    systray = fields.Function(lambda obj: obj.is_systray())
    replacements = fields.Function(lambda obj: obj.get_replacements())

    def export(self, notification):
        return self.dump(notification).data


class EngineSchema(Schema):
    uid = fields.Str(attribute='_uid')
    type = fields.Str(attribute='_type')
    name = fields.Str(attribute='_name')
    offline = fields.Function(lambda obj: obj.is_offline())
    metrics = fields.Function(lambda obj: obj.get_metrics())
    started = fields.Function(lambda obj: obj.is_started())
    syncing = fields.Function(lambda obj: obj.is_syncing())
    paused = fields.Function(lambda obj: obj.is_paused())
    local_folder = fields.Str(attribute='_local_folder')
    queue = fields.Function(lambda obj: obj.get_queue_manager().get_metrics())
    binder = fields.Nested(ServerBindingSettingsSchema)
    threads = fields.Nested(WorkerSchema, many=True)

    @post_dump(pass_many=False)
    def flatten_binder(self, data):
        # flatten the 'binder' dict from from the data dict
        for key, value in data["binder"].items():
            data[key] = value
        del data["binder"]

    def export(self, engine):
        return self.dump(engine).data
