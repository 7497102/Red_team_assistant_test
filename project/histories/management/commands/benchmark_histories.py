"""Local, read-only application timings. No external server or network required."""
import json
from statistics import median
from time import perf_counter
from django.core.management.base import BaseCommand
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext


class Command(BaseCommand):
    help = "Measure representative read-only requests against the current database."

    def handle(self, *args, **options):
        paths = ["/records/", "/api/records/", "/api/records/?q=музыку&role=user",
                 "/api/records/?deleted=null", "/api/records/?page=4000"]
        results = {}
        with override_settings(ALLOWED_HOSTS=["testserver"]):
            client = Client()
            for path in paths:
                durations = []
                for _ in range(3):
                    with CaptureQueriesContext(connection) as queries:
                        started = perf_counter()
                        response = client.get(path)
                        durations.append(perf_counter() - started)
                results[path] = {"status": response.status_code,
                                 "median_seconds": round(median(durations), 4),
                                 "queries": len(queries)}
        self.stdout.write(json.dumps(results, ensure_ascii=False, indent=2))
