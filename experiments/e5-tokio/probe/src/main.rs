fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args_os().collect();
    if args.len() != 3 {
        return Err("usage: e5-tokio <self|idle|active|cycle> <directory>".into());
    }
    let work = e5_tokio::file_work(std::path::Path::new(&args[2]))?;
    e5_tokio::run(args[1].to_str().ok_or("mode")?, work)?;
    println!("RESULT PASS");
    Ok(())
}
