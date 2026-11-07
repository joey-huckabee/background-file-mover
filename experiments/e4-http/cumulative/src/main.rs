mod rustix_probe;
mod sqlite;
use serde::Deserialize;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Submit {
    source: String,
    dest: String,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args_os().collect();
    if args.len() != 5 {
        return Err(
            "usage: e4-cumulative <HTTP corpus> <JSON corpus> <directory> <rename|fallback>".into(),
        );
    }
    e4_http::exercise(std::path::Path::new(&args[1]))?;
    e4_json::exercise(std::path::Path::new(&args[2]))?;
    let directory = std::path::Path::new(&args[3]);
    std::fs::create_dir_all(directory)?;
    rustix_probe::exercise(&directory.join("files"), args[4].to_str().ok_or("mode")?)?;
    sqlite::exercise(&directory.join("state.db"))?;
    let db = directory.join("http.db");
    let connection = rusqlite::Connection::open(&db)?;
    connection.execute_batch("PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA foreign_keys=ON; CREATE TABLE requests(id INTEGER PRIMARY KEY, source TEXT NOT NULL, dest TEXT NOT NULL);")?;
    drop(connection);
    let path = db.clone();
    e4_http::exercise_tcp(
        move |request| {
            if request.head.method == "GET" && request.head.target == b"/api/status" {
                return 200;
            }
            if request.head.method != "POST" || request.head.target != b"/api/jobs" {
                return 400;
            }
            if e4_json::parse(&request.body, e4_json::Limits::default()).is_err() {
                return 400;
            }
            let Ok(payload) = serde_json::from_slice::<Submit>(&request.body) else {
                return 400;
            };
            let mut connection = rusqlite::Connection::open(&path).unwrap();
            connection
                .execute_batch("PRAGMA synchronous=FULL; PRAGMA foreign_keys=ON;")
                .unwrap();
            let transaction = connection.transaction().unwrap();
            transaction
                .execute(
                    "INSERT INTO requests(source,dest) VALUES(?1,?2)",
                    rusqlite::params![payload.source, payload.dest],
                )
                .unwrap();
            transaction.commit().unwrap();
            201
        },
        true,
    )?;
    let connection = rusqlite::Connection::open(&db)?;
    let row: (i64, String, String) =
        connection.query_row("SELECT count(*),source,dest FROM requests", [], |r| {
            Ok((r.get(0)?, r.get(1)?, r.get(2)?))
        })?;
    assert_eq!(row, (1, "a".into(), "b".into()));
    println!("PASS cumulative HTTP -> strict typed JSON -> SQLite commit before 201; hostile payload creates no row");
    println!("RESULT PASS");
    Ok(())
}
