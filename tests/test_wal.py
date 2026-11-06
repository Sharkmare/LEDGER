import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ledger import store

SYNCHRONOUS_NORMAL = 1


def open_with_ticket(directory: str, name: str = "wal.db"):
    connection = store.connect(Path(directory) / name)
    store.create_project(connection, "WAL", "Wal")
    store.create_ticket(connection, "WAL", "kept")
    return connection


def ticket_count(path: Path) -> int:
    connection = store.connect(path)
    try:
        return connection.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    finally:
        connection.close()


def copy_database_files(source_directory: str, target_directory: str, suffixes: tuple[str, ...], name: str = "wal.db") -> Path:
    for suffix in suffixes:
        source = Path(source_directory) / (name + suffix)
        if source.exists():
            shutil.copyfile(source, Path(target_directory) / (name + suffix))
    return Path(target_directory) / name


class WalModeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def test_memory_database_keeps_its_own_journal(self):
        connection = store.connect(":memory:")
        self.addCleanup(connection.close)
        self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "memory")

    def test_file_database_is_wal_with_normal_sync(self):
        connection = store.connect(Path(self.directory.name) / "wal.db")
        self.addCleanup(connection.close)
        self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.assertEqual(connection.execute("PRAGMA synchronous").fetchone()[0], SYNCHRONOUS_NORMAL)

    def test_every_connection_gets_the_settings(self):
        path = Path(self.directory.name) / "wal.db"
        first, second = store.connect(path), store.connect(path)
        self.addCleanup(first.close)
        self.addCleanup(second.close)
        for connection in (first, second):
            self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            self.assertEqual(connection.execute("PRAGMA synchronous").fetchone()[0], SYNCHRONOUS_NORMAL)

    def test_an_old_rollback_journal_database_is_converted(self):
        path = Path(self.directory.name) / "old.db"
        legacy = sqlite3.connect(str(path))
        self.assertEqual(legacy.execute("PRAGMA journal_mode").fetchone()[0], "delete")
        legacy.execute("CREATE TABLE marker (value TEXT)")
        legacy.execute("INSERT INTO marker VALUES ('survives')")
        legacy.commit()
        legacy.close()
        converted = store.connect(path)
        self.addCleanup(converted.close)
        self.assertEqual(converted.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.assertEqual(converted.execute("SELECT value FROM marker").fetchone()[0], "survives")

    def test_commits_are_visible_to_a_second_connection_at_once(self):
        writer = open_with_ticket(self.directory.name)
        self.addCleanup(writer.close)
        reader = store.connect(Path(self.directory.name) / "wal.db")
        self.addCleanup(reader.close)
        self.assertEqual(reader.execute("SELECT COUNT(*) FROM tickets").fetchone()[0], 1)
        store.create_ticket(writer, "WAL", "second")
        self.assertEqual(reader.execute("SELECT COUNT(*) FROM tickets").fetchone()[0], 2)

    def test_reader_is_not_blocked_by_an_open_write_transaction(self):
        writer = open_with_ticket(self.directory.name)
        self.addCleanup(writer.close)
        reader = store.connect(Path(self.directory.name) / "wal.db")
        self.addCleanup(reader.close)
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("UPDATE tickets SET title = 'half written'")
        self.assertEqual(reader.execute("SELECT title FROM tickets").fetchone()[0], "kept")
        writer.rollback()


class WalDurabilityTests(unittest.TestCase):
    def setUp(self):
        self.source = tempfile.TemporaryDirectory()
        self.target = tempfile.TemporaryDirectory()
        self.addCleanup(self.source.cleanup)
        self.addCleanup(self.target.cleanup)
        self.connection = open_with_ticket(self.source.name)
        self.addCleanup(self.connection.close)

    def test_write_ahead_file_exists_while_the_database_is_open(self):
        self.assertTrue((Path(self.source.name) / "wal.db-wal").exists())

    def test_copy_of_all_three_files_taken_mid_run_has_the_commit(self):
        copy = copy_database_files(self.source.name, self.target.name, ("", "-wal", "-shm"))
        self.assertEqual(ticket_count(copy), 1)

    def test_copy_of_the_wal_without_the_shm_still_recovers(self):
        copy = copy_database_files(self.source.name, self.target.name, ("", "-wal"))
        self.assertEqual(ticket_count(copy), 1)

    def test_copy_of_the_main_file_alone_misses_uncheckpointed_commits(self):
        copy = copy_database_files(self.source.name, self.target.name, ("",))
        self.assertEqual(ticket_count_or_none(copy), None)

    def test_main_file_alone_is_complete_after_a_checkpoint(self):
        self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        copy = copy_database_files(self.source.name, self.target.name, ("",))
        self.assertEqual(ticket_count(copy), 1)

    def test_clean_close_leaves_the_main_file_complete(self):
        self.connection.close()
        copy = copy_database_files(self.source.name, self.target.name, ("",))
        self.assertEqual(ticket_count(copy), 1)

    def test_reopen_after_close_keeps_every_ticket(self):
        for index in range(20):
            store.create_ticket(self.connection, "WAL", f"ticket {index}")
        self.connection.close()
        self.assertEqual(ticket_count(Path(self.source.name) / "wal.db"), 21)


def ticket_count_or_none(path: Path):
    connection = sqlite3.connect(str(path))
    try:
        return connection.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    except sqlite3.OperationalError:
        return None
    finally:
        connection.close()


if __name__ == "__main__":
    unittest.main()
