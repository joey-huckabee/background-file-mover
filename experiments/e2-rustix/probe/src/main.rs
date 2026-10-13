fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<_> = std::env::args_os().collect();
    if args.len() != 3 {
        return Err("usage: e2-rustix <directory> <rename|fallback|enosys|notsup>".into());
    }
    e2_rustix::exercise(
        std::path::Path::new(&args[1]),
        args[2].to_str().ok_or("invalid mode")?,
    )?;
    println!("RESULT PASS");
    Ok(())
}
