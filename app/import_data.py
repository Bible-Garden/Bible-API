"""
Import data from admin-api into cep_public

GET /api/import[?translation=alias] — loads data from admin-api
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
import httpx
from database import create_connection
from auth import RequireAPIKey
from models import ImportReportModel
from config import ADMIN_API_URL, ADMIN_API_KEY

router = APIRouter()

# Table order for TRUNCATE (respecting foreign keys)
TABLES_ORDER = [
    'translation_notes',
    'translation_titles',
    'voice_alignments',
    'voices',
    'translation_verses',
    'translation_books',
    'translations',
    'bible_books',
    'languages',
]

# Insert order (reversed — reference tables first)
INSERT_ORDER = [
    'languages',
    'bible_books',
    'translations',
    'translation_books',
    'translation_verses',
    'translation_titles',
    'translation_notes',
    'voices',
    'voice_alignments',
]


def fetch_data_from_admin(translation: Optional[str] = None) -> dict:
    """Fetches data from admin-api"""
    url = f"{ADMIN_API_URL}/api/data"
    params = {}
    if translation:
        params['translation'] = translation

    headers = {}
    if ADMIN_API_KEY:
        headers['X-API-Key'] = ADMIN_API_KEY

    with httpx.Client(timeout=300.0) as client:
        response = client.get(url, params=params, headers=headers)

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"admin-api returned status {response.status_code}: {response.text[:500]}"
        )

    return response.json()


BATCH_SIZE = 5000


def insert_rows(cursor, table: str, rows: list[dict]):
    """Inserts rows into a table in batches"""
    if not rows:
        return 0

    columns = list(rows[0].keys())
    placeholders = ', '.join(['%s'] * len(columns))
    columns_str = ', '.join(f'`{c}`' for c in columns)

    sql = f"INSERT INTO `{table}` ({columns_str}) VALUES ({placeholders})"

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        values = [tuple(row[c] for c in columns) for row in batch]
        cursor.executemany(sql, values)

    return len(rows)


def replace_rows(cursor, table: str, rows: list[dict]):
    """REPLACE INTO for reference tables in batches"""
    if not rows:
        return 0

    columns = list(rows[0].keys())
    placeholders = ', '.join(['%s'] * len(columns))
    columns_str = ', '.join(f'`{c}`' for c in columns)

    sql = f"REPLACE INTO `{table}` ({columns_str}) VALUES ({placeholders})"

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        values = [tuple(row[c] for c in columns) for row in batch]
        cursor.executemany(sql, values)

    return len(rows)


def delete_translation_data(cursor, translation_code: int):
    """Deletes data for a specific translation from cep_public"""
    # Delete in dependency order (from dependent to parent tables)

    # voice_alignments for voices of this translation
    cursor.execute("""
        DELETE va FROM voice_alignments va
        INNER JOIN voices v ON va.voice = v.code
        WHERE v.translation = %s
    """, (translation_code,))

    # voices of this translation
    cursor.execute("DELETE FROM voices WHERE translation = %s", (translation_code,))

    # translation_notes for verses of this translation
    cursor.execute("""
        DELETE tn FROM translation_notes tn
        INNER JOIN translation_verses tv ON tn.translation_verse = tv.code
        WHERE tv.translation = %s
    """, (translation_code,))

    # translation_notes for titles of this translation
    cursor.execute("""
        DELETE tn FROM translation_notes tn
        INNER JOIN translation_titles tt ON tn.translation_title = tt.code
        INNER JOIN translation_verses tv ON tt.before_translation_verse = tv.code
        WHERE tv.translation = %s
    """, (translation_code,))

    # translation_titles for verses of this translation
    cursor.execute("""
        DELETE tt FROM translation_titles tt
        INNER JOIN translation_verses tv ON tt.before_translation_verse = tv.code
        WHERE tv.translation = %s
    """, (translation_code,))

    # translation_verses of this translation
    cursor.execute("DELETE FROM translation_verses WHERE translation = %s", (translation_code,))

    # translation_books of this translation
    cursor.execute("DELETE FROM translation_books WHERE translation = %s", (translation_code,))

    # the translation itself
    cursor.execute("DELETE FROM translations WHERE code = %s", (translation_code,))


@router.get('/import', response_model=ImportReportModel, operation_id="importData", tags=["Import"])
def import_data(
    translation: Optional[str] = Query(None, description="Translation alias for partial import"),
    api_key: bool = RequireAPIKey
):
    """
    Import data from admin-api

    Without parameters: full resync (TRUNCATE + INSERT)
    With translation parameter: update a single translation
    """
    # Fetch data from admin-api
    data = fetch_data_from_admin(translation)

    connection = create_connection()
    cursor = connection.cursor(dictionary=True)
    report = {}

    try:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

        if translation is None:
            # Full resync
            for table in TABLES_ORDER:
                cursor.execute(f"TRUNCATE TABLE `{table}`")

            for table in INSERT_ORDER:
                rows = data.get(table, [])
                count = insert_rows(cursor, table, rows)
                report[table] = count
        else:
            # Partial import of a single translation
            # Determine the translation code from the data
            translations_data = data.get('translations', [])
            if not translations_data:
                raise HTTPException(status_code=404, detail=f"Translation '{translation}' not found in admin-api data")

            translation_code = translations_data[0].get('code')

            # Delete old translation data
            delete_translation_data(cursor, translation_code)

            # Reference tables — REPLACE INTO (update without deleting)
            for table in ['languages', 'bible_books']:
                rows = data.get(table, [])
                count = replace_rows(cursor, table, rows)
                report[table] = count

            # Translation data — INSERT
            for table in ['translations', 'translation_books', 'translation_verses',
                          'translation_titles', 'translation_notes', 'voices', 'voice_alignments']:
                rows = data.get(table, [])
                count = insert_rows(cursor, table, rows)
                report[table] = count

        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        connection.commit()

        return ImportReportModel(
            status="ok",
            translation=translation,
            tables=report
        )

    except HTTPException:
        raise
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")
    finally:
        try:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        except Exception:
            pass
        cursor.close()
        connection.close()
