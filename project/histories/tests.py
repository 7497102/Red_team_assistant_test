import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .models import HistoryRecord, ImportRun


def source_record(record_id=1, **changes):
    row = {
        "id": record_id, "usersid_hash": "sample-key", "role": "user",
        "text": "  O‘zbekcha qo‘shiq qo‘y!  ", "actions": "",
        "createdAt": "2025-01-01 12:00:00", "updatedAt": "2025-01-01 12:00:00",
        "deletedAt": None, "userLanguage": "uz-UZ", "personality": "standard",
        "type": "others", "internet": None, "timeSTT": 0.831,
        "timeCache": 0.0, "timeGPT": 0.0, "user_request_type": None,
        "ai_response_type": None, "stt_quality": None, "ai_quality": None,
    }
    row.update(changes)
    return row


class HistoryImportTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "histories.json"

    def write_source(self, rows):
        self.path.write_text(json.dumps({"threadhistories": rows}, ensure_ascii=False), encoding="utf-8")

    def run_import(self, **options):
        call_command("import_histories", str(self.path), stdout=StringIO(), **options)

    def test_preserves_unicode_empty_text_nulls_dates_and_all_source_fields(self):
        rows = [source_record(), source_record(2, role="assistant", text="", actions="E1|",
                deletedAt="2025-02-01 00:00:00", userLanguage=None)]
        self.write_source(rows)
        self.run_import()
        for row in rows:
            record = HistoryRecord.objects.get(pk=row["id"])
            self.assertEqual(record.source_data, row)
            self.assertEqual(record.text, row["text"])
            self.assertEqual(record.created_at, row["createdAt"])
        self.assertEqual(HistoryRecord.objects.filter(deleted_at__isnull=True).count(), 1)
        self.assertEqual(ImportRun.objects.get().source_bytes, self.path.stat().st_size)

    def test_reimport_is_idempotent(self):
        self.write_source([source_record(), source_record(2)])
        self.run_import()
        self.run_import()
        self.assertEqual(HistoryRecord.objects.count(), 2)
        self.assertEqual(ImportRun.objects.count(), 1)
        self.assertEqual(ImportRun.objects.get().inserted_count, 0)
        self.assertEqual(ImportRun.objects.get().unchanged_count, 2)

    def test_duplicate_in_later_batch_rolls_back_entire_import(self):
        self.write_source([source_record(), source_record(2), source_record()])
        with self.assertRaisesMessage(CommandError, "Duplicate ID"):
            self.run_import(batch_size=1)
        self.assertFalse(HistoryRecord.objects.exists())
        self.assertFalse(ImportRun.objects.exists())

    def test_changed_existing_id_is_rejected_without_overwriting_source(self):
        self.write_source([source_record()])
        self.run_import()
        self.write_source([source_record(2), source_record(text="changed")])
        with self.assertRaisesMessage(CommandError, "different source content"):
            self.run_import(batch_size=1)
        self.assertEqual(HistoryRecord.objects.count(), 1)
        self.assertEqual(HistoryRecord.objects.get(pk=1).text, source_record()["text"])

    def test_invalid_later_date_rolls_back_earlier_batches(self):
        self.write_source([source_record(), source_record(2, createdAt="2025-02-30 00:00:00")])
        with self.assertRaises(CommandError):
            self.run_import(batch_size=1)
        self.assertFalse(HistoryRecord.objects.exists())

    def test_truncated_json_rolls_back_earlier_batches(self):
        self.write_source([source_record(), source_record(2)])
        self.path.write_text(self.path.read_text(encoding="utf-8")[:-2], encoding="utf-8")
        with self.assertRaises(CommandError):
            self.run_import(batch_size=1)
        self.assertFalse(HistoryRecord.objects.exists())

    def test_profile_hash_mismatch_is_rejected(self):
        self.write_source([source_record()])
        self.path.with_name("dataset-profile.json").write_text(json.dumps({"sha256": "0" * 64}))
        with self.assertRaisesMessage(CommandError, "SHA-256"):
            self.run_import()
        self.assertFalse(HistoryRecord.objects.exists())

    def test_missing_array_is_rejected(self):
        self.path.write_text('{"other": []}', encoding="utf-8")
        with self.assertRaisesMessage(CommandError, "No records"):
            self.run_import()


class AnalysisRuleTests(TestCase):
    def test_repeats_do_not_cross_keys_and_empty_text_does_not_match(self):
        from .analysis import screen
        rows = [{"id": i, "usersid_hash": key, "role": "user", "text": text,
                 "created_at": "2025-01-01 00:00:00"}
                for i, key, text in [(1, "a", "Hello"), (2, "b", "Hello"), (3, "b", ""), (4, "b", "")]]
        self.assertEqual(screen(rows)[1], [])

    def test_inclusive_window_and_intervening_assistant(self):
        from .analysis import screen
        rows = [{"id": i, "usersid_hash": "a", "role": role, "text": text, "created_at": date}
                for i, role, text, date in [
                    (1, "user", "Включи музыку!", "2025-01-01 00:00:00"),
                    (2, "assistant", "", "2025-01-01 00:00:01"),
                    (3, "user", " включи МУЗЫКУ ", "2025-01-01 00:02:00")]]
        self.assertEqual(screen(rows, 119)[1], [])
        match = screen(rows, 120)[1][0]
        self.assertEqual(match["previous_id"], 1)
        self.assertEqual(match["intervening_assistant_ids"], [2])

    def test_media_requires_topic_and_command_in_both_languages(self):
        from .analysis import media_match
        self.assertTrue(media_match("Включи музыку"))
        self.assertTrue(media_match("musiqa qoʻyib ber"))
        self.assertFalse(media_match("Что такое музыка?"))
        self.assertFalse(media_match("Включи свет"))

    def test_sample_is_independent_of_input_order(self):
        from .analysis import sample
        rows = [{"id": i} for i in range(40)]
        self.assertEqual(sample(rows), sample(list(reversed(rows))))


class WebAndAPITests(TestCase):
    def create_record(self, pk=1, key="key-a", role="user", text="Включи МУЗЫКУ", date="2025-01-01 12:00:00", deleted=None, language="ru-RU"):
        return HistoryRecord.objects.create(id=pk, usersid_hash=key, role=role, text=text, actions="E1|",
            created_at=date, updated_at=date, deleted_at=deleted, user_language=language,
            source_data={"id": pk, "text": text})

    def test_combined_filters_and_scope_counts(self):
        self.create_record()
        self.create_record(2, role="assistant")
        self.create_record(3, deleted="2025-01-02 00:00:00")
        self.create_record(4, date="2025-01-02 00:00:00")
        response = self.client.get("/api/records/", {"q": "музыку", "role": "user", "deleted": "null", "end": "2025-01-01", "language": "ru-RU"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["counts"], {"records": 1, "keys": 1, "user": 1, "assistant": 0})
        self.assertEqual(data["results"][0]["id"], 1)
        self.assertNotIn("source_data", data["results"][0])

    def test_unicode_search_and_literal_wildcards(self):
        self.create_record(text="ПРИВЕТ O‘ZBEK 100%")
        self.assertEqual(self.client.get("/api/records/", {"q": "привет o‘zbek"}).json()["count"], 1)
        self.assertEqual(self.client.get("/api/records/", {"q": "%"}).json()["count"], 1)
        self.assertEqual(self.client.get("/api/records/", {"q": "_"}).json()["count"], 0)

    def test_pagination_stable_and_bounded(self):
        for pk in range(1, 54):
            self.create_record(pk)
        first = self.client.get("/api/records/").json()
        second = self.client.get("/api/records/?page=2").json()
        self.assertEqual(first["count"], 53)
        self.assertEqual(len(first["results"]), 50)
        self.assertEqual([r["id"] for r in second["results"]], [51, 52, 53])
        self.assertEqual(self.client.get("/api/records/?page=3").status_code, 404)

    def test_context_respects_key_ties_and_limit(self):
        for pk in range(1, 15):
            self.create_record(pk, deleted="2025-01-02 00:00:00")
        self.create_record(99, key="unrelated")
        data = self.client.get("/api/records/7/?deleted=null").json()
        self.assertEqual([r["id"] for r in data["before"]], [2, 3, 4, 5, 6])
        self.assertEqual([r["id"] for r in data["after"]], [8, 9, 10, 11, 12])
        self.assertEqual(data["record"]["id"], 7)
        self.assertIn("source_data", data["record"])
        self.assertNotIn("source_data", data["before"][0])

    def test_invalid_filters_are_400_in_html_and_api(self):
        for params in [{"start": "2025-02-30"}, {"start": "2025-02-01", "end": "2025-01-01"}, {"id": "oops"}, {"role": "system"}, {"deleted": "maybe"}, {"page": "0"}]:
            for url in ["/records/", "/api/records/"]:
                with self.subTest(params=params, url=url):
                    self.assertEqual(self.client.get(url, params).status_code, 400)

    def test_empty_scope_null_language_and_id(self):
        self.create_record(language=None)
        self.assertEqual(self.client.get("/api/records/?language=__null__&id=1").json()["count"], 1)
        self.assertEqual(self.client.get("/api/records/?id=2").json()["count"], 0)
        self.assertContains(self.client.get("/records/?id=2"), "записей нет")
        self.assertEqual(self.client.get("/records/2/").status_code, 404)

    def test_source_text_is_escaped_in_html(self):
        self.create_record(text="<script>alert(1)</script>")
        for url in ["/records/", "/records/1/"]:
            response = self.client.get(url)
            self.assertContains(response, "&lt;script&gt;")
            self.assertNotContains(response, "<script>")

    def test_research_pages_and_api_keep_fixed_scope(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertContains(self.client.get("/research/media/"), "Область зафиксирована")
        first = self.client.get("/api/research/media/").json()
        filtered = self.client.get("/api/research/media/?deleted=null").json()
        self.assertEqual(first["counts"], filtered["counts"])
        self.assertTrue(first["examples"][0]["url"].startswith("/records/"))
        self.assertEqual(self.client.get("/research/unknown/").status_code, 404)
        self.assertEqual(self.client.post("/api/records/", {}).status_code, 405)


class FilterErrorPresentationTests(TestCase):
    def test_date_range_error_is_plain_russian_text(self):
        response = self.client.get("/records/", {"start": "2026-11-01", "end": "2026-01-01"})
        self.assertContains(response, "Начальная дата должна быть не позже конечной.", status_code=400)
        self.assertNotContains(response, "ErrorDetail", status_code=400)
        self.assertNotContains(response, "non_field_errors", status_code=400)

    def test_field_errors_have_labels_and_keep_entered_values(self):
        response = self.client.get("/records/", {"id": "invalid-id", "start": "2026-02-30"})
        self.assertContains(response, "<strong>ID записи:</strong>", status_code=400)
        self.assertContains(response, "<strong>С даты:</strong>", status_code=400)
        self.assertContains(response, 'value="invalid-id"', status_code=400)
        self.assertNotContains(response, "ErrorDetail", status_code=400)


class SearchIndexTests(TestCase):
    create_record = WebAndAPITests.create_record
    def test_index_matches_literal_casefold_and_tracks_changes(self):
        texts = ['Straße МУЗЫКА', 'musiqa qoʻy', 'a"b%c_d', 'hello world', '👩🏽test', 'a', 'xx']
        for pk, text in enumerate(texts, 1):
            self.create_record(pk, text=text)
        for term in ['STRASSE', 'муз', 'qoʻ', 'a"b', '%c_', 'world', '👩🏽t', 'a', 'xx', 'notfound']:
            expected = [i for i, text in enumerate(texts, 1) if term.casefold() in text.casefold()]
            result = self.client.get('/api/records/', {'q': term}).json()
            self.assertEqual([r['id'] for r in result['results']], expected, term)
        HistoryRecord.objects.filter(pk=1).update(text='replacement')
        self.assertEqual(self.client.get('/api/records/?q=STRASSE').json()['count'], 0)
        self.assertEqual(self.client.get('/api/records/?q=replacement').json()['count'], 1)
        HistoryRecord.objects.filter(pk=1).delete()
        self.assertEqual(self.client.get('/api/records/?q=replacement').json()['count'], 0)

    def test_list_uses_one_aggregate_and_one_page_query(self):
        self.create_record()
        with self.assertNumQueries(2):
            response = self.client.get('/api/records/')
        self.assertEqual(response.json()['count'], 1)
