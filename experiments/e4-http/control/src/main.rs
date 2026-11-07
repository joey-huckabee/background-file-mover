use std::error::Error;
use std::fs::{self, File};
use std::io::{Read, Write};
use std::path::PathBuf;
use std::thread;
use std::time::{Duration, Instant, SystemTime};

fn main() -> Result<(), Box<dyn Error>> {
    let directory = PathBuf::from(
        std::env::args_os()
            .nth(1)
            .ok_or("usage: e2-control <directory>")?,
    );
    fs::create_dir_all(&directory)?;
    let path = directory.join("control.txt");
    let mut file = File::create(&path)?;
    file.write_all(b"glibc-2.22-control")?;
    file.sync_all()?;
    drop(file);
    let mut value = String::new();
    File::open(path)?.read_to_string(&mut value)?;
    assert_eq!(value, "glibc-2.22-control");
    let started = Instant::now();
    let handle = thread::spawn(|| {
        thread::sleep(Duration::from_millis(1));
        SystemTime::now().duration_since(SystemTime::UNIX_EPOCH)
    });
    handle.join().map_err(|_| "control worker panicked")??;
    assert!(started.elapsed() >= Duration::from_millis(1));
    println!("PASS std filesystem, sync, reopen, threads, monotonic/realtime clocks");
    println!("RESULT PASS");
    Ok(())
}
