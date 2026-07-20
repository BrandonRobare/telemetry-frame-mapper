from __future__ import annotations

from sqlalchemy import Connection


def install_session_search_schema(connection: Connection) -> None:
    """Install and backfill the SQLite FTS5 index used by session search.

    It is intentionally a small, feature-specific index: one document per
    session, log entry, and defect.  SQLite triggers keep it in sync after
    the initial backfill.
    """
    connection.exec_driver_sql("""
        CREATE VIRTUAL TABLE IF NOT EXISTS session_search
        USING fts5(document_id UNINDEXED, session_id UNINDEXED, source UNINDEXED, content)
    """)
    connection.exec_driver_sql("""
        CREATE TRIGGER IF NOT EXISTS session_search_sessions_ai
        AFTER INSERT ON sessions BEGIN
          INSERT INTO session_search VALUES ('session:' || NEW.id, NEW.id, 'session',
            trim(coalesce(NEW.name, '') || ' ' || coalesce(NEW.tags, '') || ' '
              || coalesce(NEW.notes, '')));
        END
    """)
    connection.exec_driver_sql("""
        CREATE TRIGGER IF NOT EXISTS session_search_sessions_au AFTER UPDATE ON sessions BEGIN
          DELETE FROM session_search WHERE document_id = 'session:' || OLD.id;
          INSERT INTO session_search VALUES ('session:' || NEW.id, NEW.id, 'session',
            trim(coalesce(NEW.name, '') || ' ' || coalesce(NEW.tags, '') || ' '
              || coalesce(NEW.notes, '')));
        END
    """)
    connection.exec_driver_sql("""
        CREATE TRIGGER IF NOT EXISTS session_search_sessions_ad AFTER DELETE ON sessions BEGIN
          DELETE FROM session_search WHERE document_id = 'session:' || OLD.id;
        END
    """)
    connection.exec_driver_sql("""
        CREATE TRIGGER IF NOT EXISTS session_search_logs_ai
        AFTER INSERT ON session_log_entries BEGIN
          INSERT INTO session_search
          SELECT 'log:' || NEW.id, NEW.session_id, 'log',
            trim(coalesce(NEW.event_type, '') || ' ' || coalesce(NEW.message, ''))
          WHERE NEW.session_id IS NOT NULL;
        END
    """)
    connection.exec_driver_sql("""
        CREATE TRIGGER IF NOT EXISTS session_search_logs_au
        AFTER UPDATE ON session_log_entries BEGIN
          DELETE FROM session_search WHERE document_id = 'log:' || OLD.id;
          INSERT INTO session_search
          SELECT 'log:' || NEW.id, NEW.session_id, 'log',
            trim(coalesce(NEW.event_type, '') || ' ' || coalesce(NEW.message, ''))
          WHERE NEW.session_id IS NOT NULL;
        END
    """)
    connection.exec_driver_sql("""
        CREATE TRIGGER IF NOT EXISTS session_search_logs_ad
        AFTER DELETE ON session_log_entries BEGIN
          DELETE FROM session_search WHERE document_id = 'log:' || OLD.id;
        END
    """)
    connection.exec_driver_sql("""
        CREATE TRIGGER IF NOT EXISTS session_search_defects_ai AFTER INSERT ON defects BEGIN
          INSERT INTO session_search VALUES ('defect:' || NEW.id, NEW.session_id, 'defect',
            trim(coalesce(NEW.category, '') || ' ' || coalesce(NEW.severity, '') || ' '
              || coalesce(NEW.note, '')));
        END
    """)
    connection.exec_driver_sql("""
        CREATE TRIGGER IF NOT EXISTS session_search_defects_au AFTER UPDATE ON defects BEGIN
          DELETE FROM session_search WHERE document_id = 'defect:' || OLD.id;
          INSERT INTO session_search VALUES ('defect:' || NEW.id, NEW.session_id, 'defect',
            trim(coalesce(NEW.category, '') || ' ' || coalesce(NEW.severity, '') || ' '
              || coalesce(NEW.note, '')));
        END
    """)
    connection.exec_driver_sql("""
        CREATE TRIGGER IF NOT EXISTS session_search_defects_ad AFTER DELETE ON defects BEGIN
          DELETE FROM session_search WHERE document_id = 'defect:' || OLD.id;
        END
    """)
    connection.exec_driver_sql("DELETE FROM session_search")
    connection.exec_driver_sql("""
        INSERT INTO session_search (document_id, session_id, source, content)
        SELECT 'session:' || id, id, 'session',
          trim(coalesce(name, '') || ' ' || coalesce(tags, '') || ' ' || coalesce(notes, ''))
        FROM sessions
        UNION ALL
        SELECT 'log:' || id, session_id, 'log',
          trim(coalesce(event_type, '') || ' ' || coalesce(message, ''))
        FROM session_log_entries WHERE session_id IS NOT NULL
        UNION ALL
        SELECT 'defect:' || id, session_id, 'defect',
          trim(coalesce(category, '') || ' ' || coalesce(severity, '') || ' ' || coalesce(note, ''))
        FROM defects
    """)
