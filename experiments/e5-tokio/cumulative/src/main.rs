mod rustix_probe;
mod sqlite;
use serde::Deserialize;
use std::sync::Arc;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Submit {
    source: String,
    dest: String,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args_os().collect();
    if args.len() != 5 {
        return Err("usage: e5-cumulative <mode> <directory> <HTTP corpus> <JSON corpus>".into());
    }
    let mode = args[1].to_str().ok_or("mode")?;
    let dir = std::path::Path::new(&args[2]);
    std::fs::create_dir_all(dir)?;
    if mode == "self" {
        e5_http::exercise(std::path::Path::new(&args[3]))?;
        e5_http::exercise_tcp(|r| if r.head.method == "POST" { 201 } else { 200 }, false)?;
        e5_json::exercise(std::path::Path::new(&args[4]))?;
        rustix_probe::exercise(&dir.join("files"), "rename")?;
        rustix_probe::exercise(&dir.join("fallback"), "fallback")?;
        sqlite::exercise(&dir.join("state.db"))?;
    }
    let db = dir.join("runtime.db");
    let connection = rusqlite::Connection::open(&db)?;
    connection.execute_batch("PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; CREATE TABLE jobs(id INTEGER PRIMARY KEY, payload TEXT NOT NULL); CREATE TABLE requests(source TEXT NOT NULL,dest TEXT NOT NULL);")?;
    drop(connection);
    let path = db.clone();
    let completed = e5_tokio::run(
        mode,
        Arc::new(move |i| {
            let mut c = rusqlite::Connection::open(&path).map_err(|e| e.to_string())?;
            c.busy_timeout(std::time::Duration::from_millis(100))
                .map_err(|e| e.to_string())?;
            c.execute_batch("PRAGMA synchronous=FULL;")
                .map_err(|e| e.to_string())?;
            let t = c.transaction().map_err(|e| e.to_string())?;
            t.execute(
                "INSERT INTO jobs(id,payload) VALUES(?1,'committed')",
                [i as i64],
            )
            .map_err(|e| e.to_string())?;
            t.commit().map_err(|e| e.to_string())
        }),
    )?;
    let c = rusqlite::Connection::open(&db)?;
    let rows: i64 = c.query_row("SELECT count(*) FROM jobs", [], |r| r.get(0))?;
    assert_eq!(
        rows, completed as i64,
        "every finished blocking transaction persists after shutdown"
    );
    drop(c);
    if mode == "self" {
        let path = db.clone();
        let rt = e5_tokio::runtime()?;
        rt.block_on(e5_tokio::tcp_once(move |bytes| {
            let e5_http::Frame::Complete(request) = e5_http::frame(&bytes) else {
                panic!("framing")
            };
            e5_json::parse(&request.body, e5_json::Limits::default()).unwrap();
            let data: Submit = serde_json::from_slice(&request.body).unwrap();
            let mut c = rusqlite::Connection::open(path).unwrap();
            c.execute_batch("PRAGMA synchronous=FULL;").unwrap();
            let t = c.transaction().unwrap();
            t.execute(
                "INSERT INTO requests(source,dest) VALUES(?1,?2)",
                rusqlite::params![data.source, data.dest],
            )
            .unwrap();
            t.commit().unwrap();
            e5_tokio::reply()
        }))?;
        rt.shutdown_timeout(std::time::Duration::from_secs(2));
        let c = rusqlite::Connection::open(&db)?;
        let row: (String, String) = c.query_row("SELECT source,dest FROM requests", [], |r| {
            Ok((r.get(0)?, r.get(1)?))
        })?;
        assert_eq!(row, ("a".into(), "b".into()));
        println!(
            "PASS Tokio TCP -> httparse -> strict typed JSON -> blocking SQLite commit before 201"
        );
    }
    println!("PASS cumulative SQLite completed jobs={rows} after runtime shutdown");
    println!("RESULT PASS");
    Ok(())
}
