from contextlib import contextmanager
import base64
import json
import sqlite3
import time
import urllib


def compound_pks_from_path(path):
    return [
        urllib.parse.unquote_plus(b) for b in path.split(',')
    ]


def path_from_row_pks(row, pks, use_rowid):
    if use_rowid:
        return urllib.parse.quote_plus(str(row['rowid']))
    bits = []
    for pk in pks:
        bits.append(
            urllib.parse.quote_plus(str(row[pk]))
        )
    return ','.join(bits)


def build_where_clauses(args):
    sql_bits = []
    params = {}
    for i, (key, value) in enumerate(sorted(args.items())):
        if '__' in key:
            column, lookup = key.rsplit('__', 1)
        else:
            column = key
            lookup = 'exact'
        template = {
            'exact': '"{}" = :{}',
            'contains': '"{}" like :{}',
            'endswith': '"{}" like :{}',
            'startswith': '"{}" like :{}',
            'gt': '"{}" > :{}',
            'gte': '"{}" >= :{}',
            'lt': '"{}" < :{}',
            'lte': '"{}" <= :{}',
            'glob': '"{}" glob :{}',
            'like': '"{}" like :{}',
        }[lookup]
        numeric_operators = {'gt', 'gte', 'lt', 'lte'}
        value_convert = {
            'contains': lambda s: '%{}%'.format(s),
            'endswith': lambda s: '%{}'.format(s),
            'startswith': lambda s: '{}%'.format(s),
        }.get(lookup, lambda s: s)
        converted = value_convert(value)
        if lookup in numeric_operators and converted.isdigit():
            converted = int(converted)
        param_id = 'p{}'.format(i)
        sql_bits.append(
            template.format(column, param_id)
        )
        params[param_id] = converted
    return sql_bits, params


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, sqlite3.Row):
            return tuple(obj)
        if isinstance(obj, sqlite3.Cursor):
            return list(obj)
        if isinstance(obj, bytes):
            # Does it encode to utf8?
            try:
                return obj.decode('utf8')
            except UnicodeDecodeError:
                return {
                    '$base64': True,
                    'encoded': base64.b64encode(obj).decode('latin1'),
                }
        return json.JSONEncoder.default(self, obj)


@contextmanager
def sqlite_timelimit(conn, ms):
    deadline = time.time() + (ms / 1000)

    def handler():
        if time.time() >= deadline:
            return 1
    conn.set_progress_handler(handler, 10000)
    yield
    conn.set_progress_handler(None, 10000)


class InvalidSql(Exception):
    pass


def validate_sql_select(sql):
    sql = sql.strip().lower()
    if not sql.startswith('select '):
        raise InvalidSql('Statement must begin with SELECT')
    if 'pragma' in sql:
        raise InvalidSql('Statement may not contain PRAGMA')


def path_with_added_args(request, args):
    current = request.raw_args.copy()
    current.update(args)
    return request.path + '?' + urllib.parse.urlencode(current)
