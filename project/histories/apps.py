from django.apps import AppConfig
from django.db.backends.signals import connection_created


def register_sqlite_functions(sender, connection, **kwargs):
    if connection.vendor == "sqlite":
        connection.connection.create_function("history_casefold", 1, str.casefold, deterministic=True)


class HistoriesConfig(AppConfig):
    name = "histories"

    def ready(self):
        connection_created.connect(register_sqlite_functions, dispatch_uid="histories.sqlite_functions")
