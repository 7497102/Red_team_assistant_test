from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("histories", "0004_remove_historyrecord_history_scope_cover_and_more")]
    operations = [migrations.RunSQL("ANALYZE", reverse_sql=migrations.RunSQL.noop)]
