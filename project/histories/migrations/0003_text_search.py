from django.db import migrations


def create_search(apps, schema_editor):
    if schema_editor.connection.vendor != "sqlite":
        raise RuntimeError("This application's search index requires SQLite FTS5.")
    statements = [
        "CREATE VIRTUAL TABLE history_text_search USING fts5(text, tokenize='trigram case_sensitive 1')",
        "INSERT INTO history_text_search(rowid,text) SELECT id,history_casefold(text) FROM histories_historyrecord",
        "CREATE TRIGGER history_search_insert AFTER INSERT ON histories_historyrecord BEGIN INSERT INTO history_text_search(rowid,text) VALUES(new.id,history_casefold(new.text)); END",
        "CREATE TRIGGER history_search_delete AFTER DELETE ON histories_historyrecord BEGIN DELETE FROM history_text_search WHERE rowid=old.id; END",
        "CREATE TRIGGER history_search_update AFTER UPDATE OF id,text ON histories_historyrecord BEGIN DELETE FROM history_text_search WHERE rowid=old.id; INSERT INTO history_text_search(rowid,text) VALUES(new.id,history_casefold(new.text)); END",
    ]
    for statement in statements:
        schema_editor.execute(statement)


def drop_search(apps, schema_editor):
    for name in ["insert", "delete", "update"]:
        schema_editor.execute(f"DROP TRIGGER history_search_{name}")
    schema_editor.execute("DROP TABLE history_text_search")


class Migration(migrations.Migration):
    dependencies = [("histories", "0002_historyrecord_history_scope_cover")]
    operations = [migrations.RunPython(create_search, drop_search)]
