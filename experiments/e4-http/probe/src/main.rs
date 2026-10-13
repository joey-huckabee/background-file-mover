fn main() -> Result<(), Box<dyn std::error::Error>> {
    let corpus = std::env::args_os().nth(1).ok_or("missing HTTP corpus")?;
    e4_http::exercise(std::path::Path::new(&corpus))?;
    e4_http::exercise_tcp(|r| if r.head.method == "POST" { 201 } else { 200 }, false)?;
    println!("RESULT PASS");
    Ok(())
}
