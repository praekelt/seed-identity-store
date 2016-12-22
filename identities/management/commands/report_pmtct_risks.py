import csv
from six.moves import zip

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Generate reports for PMTCT risks.'

    def query(self, query_string):
        cursor = connection.cursor()
        cursor.execute(query_string)
        col_names = [desc[0] for desc in cursor.description]
        while True:
            row = cursor.fetchone()
            if row is None:
                break

            row_dict = dict(zip(col_names, row))
            yield row_dict

        return

    def query_to_csv(self, fp, column_names, query):
        records = self.query(query)
        writer = csv.DictWriter(fp, column_names)
        writer.writeheader()
        for record in records:
            writer.writerow(record)

    def handle(self, *args, **kwargs):
        query = """
        SELECT DISTINCT
         details->'pmtct'->'risk_status' AS risk_status,
         count(*) as count
        FROM
         identities_identity
        WHERE
         details->>'source' = 'pmtct'
        GROUP BY
         risk_status
        """
        self.query_to_csv(
            self.stdout,
            ['risk_status', 'count'],
            query)
