use rusqlite::{params, Connection, ErrorCode, OpenFlags};
use std::error::Error;
use std::path::Path;
use std::thread;
use std::time::Duration;

type ProbeResult<T> = Result<T, Box<dyn Error>>;

fn open(path: &Path) -> rusqlite::Result<Connection> {
    let connection = Connection::open_with_flags(
        path,
        OpenFlags::SQLITE_OPEN_READ_WRITE
            | OpenFlags::SQLITE_OPEN_CREATE
            | OpenFlags::SQLITE_OPEN_FULL_MUTEX,
    )?;
    connection.busy_timeout(Duration::from_secs(5))?;
    connection.pragma_update(None, "journal_mode", "WAL")?;
    connection.pragma_update(None, "synchronous", "FULL")?;
    connection.pragma_update(None, "foreign_keys", "ON")?;
    Ok(connection)
}

fn configuration(connection: &Connection) -> ProbeResult<()> {
    let journal: String = connection.pragma_query_value(None, "journal_mode", |row| row.get(0))?;
    let sync: i64 = connection.pragma_query_value(None, "synchronous", |row| row.get(0))?;
    let foreign_keys: i64 =
        connection.pragma_query_value(None, "foreign_keys", |row| row.get(0))?;
    assert_eq!(journal, "wal");
    assert_eq!(sync, 2);
    assert_eq!(foreign_keys, 1);
    println!("PASS journal_mode=wal synchronous=2 foreign_keys=1");

    for option in [
        "THREADSAFE=1",
        "OMIT_LOAD_EXTENSION",
        "DQS=0",
        "DEFAULT_MEMSTATUS=0",
        "ENABLE_API_ARMOR",
    ] {
        let present: i64 =
            connection.query_row("SELECT sqlite_compileoption_used(?1)", [option], |row| {
                row.get(0)
            })?;
        assert_eq!(
            present, 1,
            "required SQLite compile option missing: {option}"
        );
        println!("PASS compile_option={option}");
    }
    let mut options = connection.prepare("PRAGMA compile_options")?;
    for option in options.query_map([], |row| row.get::<_, String>(0))? {
        println!("SQLITE_OPTION {}", option?);
    }
    assert!(connection
        .query_row("SELECT \"not_a_column\"", [], |row| row.get::<_, String>(0))
        .is_err());
    let extension_error = connection
        .query_row("SELECT load_extension('e1-must-not-load')", [], |row| {
            row.get::<_, String>(0)
        })
        .expect_err("load_extension must not exist");
    assert!(extension_error
        .to_string()
        .contains("no such function: load_extension"));
    println!("PASS double-quoted strings rejected; extension loading function absent");
    println!("SQLITE_VERSION {}", rusqlite::version());
    Ok(())
}

fn write(path: &Path) -> ProbeResult<()> {
    if path.exists() {
        return Err("write phase requires a fresh database path".into());
    }
    let mut connection = open(path)?;
    configuration(&connection)?;
    connection.execute_batch(
        "CREATE TABLE record (id INTEGER PRIMARY KEY, payload TEXT NOT NULL);
         CREATE TABLE child (record_id INTEGER NOT NULL REFERENCES record(id));",
    )?;
    {
        let transaction = connection.transaction()?;
        transaction.execute(
            "INSERT INTO record VALUES (1, ?1)",
            ["durable across processes"],
        )?;
        transaction.commit()?;
    }
    {
        let transaction = connection.transaction()?;
        transaction.execute("INSERT INTO record VALUES (2, 'must be rolled back')", [])?;
        transaction.rollback()?;
    }
    let rolled_back: i64 =
        connection.query_row("SELECT count(*) FROM record WHERE id=2", [], |r| r.get(0))?;
    assert_eq!(rolled_back, 0);
    let foreign_error = connection
        .execute("INSERT INTO child VALUES (999)", [])
        .expect_err("foreign key must fail");
    assert_eq!(
        foreign_error.sqlite_error_code(),
        Some(ErrorCode::ConstraintViolation)
    );
    println!("PASS commit, rollback, and foreign-key enforcement");

    let blocked = open(path)?;
    blocked.busy_timeout(Duration::from_millis(100))?;
    connection.execute_batch("BEGIN IMMEDIATE")?;
    let busy_error = blocked
        .execute("INSERT INTO record VALUES (3, 'contended')", [])
        .expect_err("held write lock must return SQLITE_BUSY");
    assert_eq!(
        busy_error.sqlite_error_code(),
        Some(ErrorCode::DatabaseBusy)
    );
    connection.execute_batch("ROLLBACK")?;
    blocked.execute("INSERT INTO record VALUES (3, 'after contention')", [])?;
    println!("PASS busy timeout and successful write after lock release");
    drop(blocked);

    let mut workers = Vec::new();
    for worker in 0..4 {
        let worker_path = path.to_owned();
        workers.push(thread::spawn(move || -> rusqlite::Result<()> {
            let mut db = open(&worker_path)?;
            let transaction = db.transaction()?;
            for row in 0..10 {
                transaction.execute(
                    "INSERT INTO record VALUES (?1, ?2)",
                    params![
                        100 + worker * 10 + row,
                        format!("worker-{worker}-row-{row}")
                    ],
                )?;
            }
            transaction.commit()
        }));
    }
    for worker in workers {
        worker.join().map_err(|_| "SQLite worker panicked")??;
    }
    let total: i64 = connection.query_row("SELECT count(*) FROM record", [], |r| r.get(0))?;
    assert_eq!(total, 42);
    println!("PASS four concurrent connections committed 40 worker records");
    let integrity: String = connection.query_row("PRAGMA integrity_check", [], |r| r.get(0))?;
    assert_eq!(integrity, "ok");
    let (busy, _, _): (i64, i64, i64) =
        connection.query_row("PRAGMA wal_checkpoint(TRUNCATE)", [], |r| {
            Ok((r.get(0)?, r.get(1)?, r.get(2)?))
        })?;
    assert_eq!(busy, 0);
    connection.close().map_err(|(_, error)| error)?;
    println!("PASS integrity_check and WAL checkpoint");
    Ok(())
}

fn read(path: &Path) -> ProbeResult<()> {
    // No CREATE: a missing persisted database must fail, not become an empty one.
    let connection = Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
    let payload: String =
        connection.query_row("SELECT payload FROM record WHERE id=1", [], |r| r.get(0))?;
    let total: i64 = connection.query_row("SELECT count(*) FROM record", [], |r| r.get(0))?;
    assert_eq!(payload, "durable across processes");
    assert_eq!(total, 42);
    let integrity: String = connection.query_row("PRAGMA integrity_check", [], |r| r.get(0))?;
    assert_eq!(integrity, "ok");
    println!("PASS separate-process reopen: 42 rows and integrity_check=ok");
    Ok(())
}

pub fn exercise(path: &Path) -> ProbeResult<()> {
    write(path)?;
    read(path)?;
    Ok(())
}
