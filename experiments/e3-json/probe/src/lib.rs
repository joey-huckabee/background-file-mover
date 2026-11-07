use serde::de::{self, DeserializeSeed, MapAccess, SeqAccess, Visitor};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::fmt;
use std::path::Path;

#[derive(Clone, Copy)]
pub struct Limits {
    depth: usize,
    input: usize,
    string: usize,
    members: usize,
    elements: usize,
}

impl Default for Limits {
    fn default() -> Self {
        Self {
            depth: 4,
            input: 65536,
            string: 4096,
            members: 64,
            elements: 64,
        }
    }
}

// Policy guard only: serde_json still owns JSON syntax, UTF-8 and escaping.
// deserialize_any represents integer spelling -0 as f64. Reject decimal and
// exponent spellings first, so accepting its zero value cannot admit floats.
fn integer_spellings(input: &[u8]) -> Result<(), String> {
    let mut quoted = false;
    let mut escaped = false;
    let mut i = 0;
    while i < input.len() {
        let c = input[i];
        if quoted {
            if escaped {
                escaped = false;
            } else if c == b'\\' {
                escaped = true;
            } else if c == b'"' {
                quoted = false;
            }
            i += 1;
        } else if c == b'"' {
            quoted = true;
            i += 1;
        } else if c == b'-' || c.is_ascii_digit() {
            let start = i;
            while i < input.len()
                && !matches!(input[i], b' ' | b'\t' | b'\r' | b'\n' | b',' | b']' | b'}')
            {
                i += 1;
            }
            let token = std::str::from_utf8(&input[start..i]).map_err(|e| e.to_string())?;
            token
                .parse::<i64>()
                .map_err(|_| "integer spelling or range".to_string())?;
        } else {
            i += 1;
        }
    }
    Ok(())
}

#[derive(Clone, Copy)]
struct Seed {
    limits: Limits,
    depth: usize,
}

impl<'de> DeserializeSeed<'de> for Seed {
    type Value = Value;
    fn deserialize<D: de::Deserializer<'de>>(self, d: D) -> Result<Value, D::Error> {
        if self.depth > self.limits.depth {
            return Err(de::Error::custom("depth limit"));
        }
        d.deserialize_any(self)
    }
}

impl Seed {
    fn child(self) -> Self {
        Self {
            depth: self.depth + 1,
            ..self
        }
    }
    fn string<E: de::Error>(&self, value: &str) -> Result<(), E> {
        if value.len() > self.limits.string || value.contains('\0') {
            return Err(E::custom("string limit or NUL"));
        }
        Ok(())
    }
}

impl<'de> Visitor<'de> for Seed {
    type Value = Value;
    fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
        f.write_str("bounded strict JSON")
    }
    fn visit_bool<E: de::Error>(self, v: bool) -> Result<Value, E> {
        Ok(Value::Bool(v))
    }
    fn visit_i64<E: de::Error>(self, v: i64) -> Result<Value, E> {
        Ok(Value::from(v))
    }
    fn visit_u64<E: de::Error>(self, v: u64) -> Result<Value, E> {
        let v = i64::try_from(v).map_err(|_| E::custom("signed integer range"))?;
        Ok(Value::from(v))
    }
    fn visit_f64<E: de::Error>(self, v: f64) -> Result<Value, E> {
        if v == 0.0 {
            Ok(Value::from(0))
        } else {
            Err(E::custom("floating point forbidden"))
        }
    }
    fn visit_str<E: de::Error>(self, v: &str) -> Result<Value, E> {
        self.string(v)?;
        Ok(Value::String(v.to_owned()))
    }
    fn visit_string<E: de::Error>(self, v: String) -> Result<Value, E> {
        self.string(&v)?;
        Ok(Value::String(v))
    }
    fn visit_map<M: MapAccess<'de>>(self, mut m: M) -> Result<Value, M::Error> {
        let mut values = Map::new();
        while let Some(key) = m.next_key::<String>()? {
            self.string(&key)?;
            if values.len() >= self.limits.members {
                return Err(de::Error::custom("member limit"));
            }
            if values.contains_key(&key) {
                return Err(de::Error::custom("duplicate key"));
            }
            let value = m.next_value_seed(self.child())?;
            values.insert(key, value);
        }
        Ok(Value::Object(values))
    }
    fn visit_seq<S: SeqAccess<'de>>(self, mut s: S) -> Result<Value, S::Error> {
        let mut values = Vec::new();
        loop {
            // Reject the next element before it can descend or allocate a value.
            let seed = if values.len() >= self.limits.elements {
                Seed {
                    depth: self.limits.depth + 1,
                    ..self
                }
            } else {
                self.child()
            };
            match s.next_element_seed(seed)? {
                Some(value) => values.push(value),
                None => break,
            }
        }
        Ok(Value::Array(values))
    }
}

pub fn parse(input: &[u8], limits: Limits) -> Result<Value, String> {
    if input.len() > limits.input {
        return Err("input limit".into());
    }
    std::str::from_utf8(input).map_err(|e| e.to_string())?;
    if input
        .iter()
        .find(|b| !matches!(**b, b' ' | b'\t' | b'\n' | b'\r'))
        != Some(&b'{')
    {
        return Err("top-level object required".into());
    }
    integer_spellings(input)?;
    let mut d = serde_json::Deserializer::from_slice(input);
    let value = Seed { limits, depth: 1 }
        .deserialize(&mut d)
        .map_err(|e| e.to_string())?;
    d.end().map_err(|e| e.to_string())?;
    Ok(value)
}

#[derive(Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
struct Submit {
    source: String,
    dest: String,
}

fn submit(input: &[u8]) -> Result<Submit, String> {
    parse(input, Limits::default())?;
    serde_json::from_slice(input).map_err(|e| e.to_string())
}

pub fn exercise(corpus: &Path) -> Result<(), Box<dyn std::error::Error>> {
    let expected: std::collections::BTreeMap<_, _> =
        std::fs::read_to_string(corpus.join("oracle.tsv"))?
            .lines()
            .map(|line| {
                let (name, outcome) = line.split_once('\t').expect("oracle row");
                (name.to_owned(), outcome == "ACCEPT")
            })
            .collect();
    let mut files: Vec<_> = std::fs::read_dir(corpus)?.collect::<Result<_, _>>()?;
    files.retain(|f| f.file_name() != "oracle.tsv");
    files.sort_by_key(|f| f.file_name());
    let mut seeds = Vec::new();
    for file in &files {
        let bytes = std::fs::read(file.path())?;
        let accepted = expected[&file.file_name().to_string_lossy().into_owned()];
        assert_eq!(
            parse(&bytes, Limits::default()).is_ok(),
            accepted,
            "corpus {:?}",
            file.file_name()
        );
        seeds.push(bytes);
    }
    assert_eq!(
        files.len(),
        38,
        "corpus changed: review expected membership"
    );
    println!("PASS corpus {} accepted/rejected fixtures", files.len());
    for bytes in [
        b"\xef\xbb\xbf{}".as_slice(),
        b"{\"x\":\"a\0b\"}".as_slice(),
        b"{\"x\":\"\xff\"}".as_slice(),
    ] {
        assert!(parse(bytes, Limits::default()).is_err());
    }

    for text in [
        r#"{"x":-0}"#,
        r#"{"x":9223372036854775807,"y":-9223372036854775808}"#,
        r#"{"x":{"y":{"z":1}}}"#,
        r#"{"0":"1.0e2","x":"-0"}"#,
    ] {
        let value = parse(text.as_bytes(), Limits::default())?;
        let encoded = serde_json::to_vec(&value)?;
        assert_eq!(parse(&encoded, Limits::default())?, value);
    }
    for text in [
        r#"{"x":0.0}"#,
        r#"{"x":-0.0}"#,
        r#"{"x":0e0}"#,
        r#"{"x":1E0}"#,
        r#"{"x":9223372036854775808}"#,
        r#"{"x":-9223372036854775809}"#,
        r#"{"x":null}"#,
        r#"{"x":{"a":1,"\u0061":2}}"#,
        r#"{"x":{"y":{"z":[1]}}}"#,
        r#"{"\u0000":1}"#,
        r#"{"x":"\u0000"}"#,
        r#"{"x":1}{}"#,
    ] {
        assert!(
            parse(text.as_bytes(), Limits::default()).is_err(),
            "rejection {text}"
        );
    }
    println!("PASS signed int64, negative zero, lexical float/exponent rejection, nested/escaped duplicate keys, depth, NUL, and whole input");

    for count in [4096, 4097] {
        let text = format!("{{\"x\":\"{}\"}}", "x".repeat(count));
        assert_eq!(
            parse(text.as_bytes(), Limits::default()).is_ok(),
            count == 4096
        );
    }
    for count in [64, 65] {
        let members = (0..count)
            .map(|i| format!("\"k{i}\":1"))
            .collect::<Vec<_>>()
            .join(",");
        let object = format!("{{{members}}}");
        assert_eq!(
            parse(object.as_bytes(), Limits::default()).is_ok(),
            count == 64
        );
        let array = format!("{{\"x\":[{}]}}", vec!["1"; count].join(","));
        assert_eq!(
            parse(array.as_bytes(), Limits::default()).is_ok(),
            count == 64
        );
    }
    let mut sized = b"{}".to_vec();
    sized.resize(65536, b' ');
    assert!(parse(&sized, Limits::default()).is_ok());
    sized.push(b' ');
    assert!(parse(&sized, Limits::default()).is_err());
    let deep = format!("{{\"x\":{}0{}}}", "[".repeat(10000), "]".repeat(10000));
    assert!(parse(deep.as_bytes(), Limits::default()).is_err());
    println!("PASS exact input/string/member/element bounds and 10000-level adversarial input");

    let request = Submit {
        source: "ä/🎧/\"\\\n\t".into(),
        dest: "/out/音楽".into(),
    };
    assert_eq!(submit(&serde_json::to_vec(&request)?)?, request);
    for text in [
        r#"{"source":"a"}"#,
        r#"{"source":1,"dest":"b"}"#,
        r#"{"source":"a","dest":"b","extra":true}"#,
        r#"{"source":"a","source":"x","dest":"b"}"#,
    ] {
        assert!(submit(text.as_bytes()).is_err());
    }
    println!("PASS derived typed API, unknown/missing/wrong/duplicate fields and Unicode/control-character roundtrip");

    let mut state = 0x13_10_2026_u64;
    for index in 0..10000 {
        state = state.wrapping_mul(6364136223846793005).wrapping_add(1);
        let mut bytes = seeds[index % seeds.len()].clone();
        let offset = state as usize % (bytes.len() + 1);
        match index % 3 {
            0 => bytes.insert(offset, (state >> 32) as u8),
            1 if offset < bytes.len() => {
                bytes.remove(offset);
            }
            _ if offset < bytes.len() => bytes[offset] ^= (state >> 32) as u8,
            _ => bytes.push(0),
        }
        if let Ok(value) = parse(&bytes, Limits::default()) {
            assert_eq!(
                parse(&serde_json::to_vec(&value)?, Limits::default())?,
                value
            );
        }
    }
    println!("PASS 10000 deterministic corpus mutations without panic; accepted values serialize and reparse");
    Ok(())
}
