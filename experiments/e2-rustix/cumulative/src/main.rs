mod sqlite;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args_os().collect();
    if args.len() != 3 {
        return Err("usage: e2-cumulative <directory> <rename|fallback|enosys|notsup>".into());
    }
    let directory = std::path::Path::new(&args[1]);
    std::fs::create_dir_all(directory)?;
    e2_rustix::exercise(
        &directory.join("files"),
        args[2].to_str().ok_or("invalid mode")?,
    )?;
    // State remains on the local runtime filesystem even when recordings use NFS.
    sqlite::exercise(&directory.join("state.db"))?;
    println!("PASS cumulative rustix and SQLite configuration");
    println!("RESULT PASS");
    Ok(())
}
