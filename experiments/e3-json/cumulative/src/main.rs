mod rustix_probe;
mod sqlite;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args_os().collect();
    if args.len() != 4 {
        return Err("usage: e3-cumulative <corpus> <directory> <rename|fallback>".into());
    }
    e3_json::exercise(std::path::Path::new(&args[1]))?;
    let directory = std::path::Path::new(&args[2]);
    std::fs::create_dir_all(directory)?;
    rustix_probe::exercise(&directory.join("files"), args[3].to_str().ok_or("mode")?)?;
    sqlite::exercise(&directory.join("state.db"))?;
    println!("RESULT PASS");
    Ok(())
}
