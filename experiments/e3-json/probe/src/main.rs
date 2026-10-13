fn main() -> Result<(), Box<dyn std::error::Error>> {
    let corpus = std::env::args_os().nth(1).ok_or("missing corpus path")?;
    e3_json::exercise(std::path::Path::new(&corpus))?;
    println!("RESULT PASS");
    Ok(())
}
