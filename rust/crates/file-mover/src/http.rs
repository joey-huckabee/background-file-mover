// Bounded HTTP framing adapted from the E4/E5 qualification adapter.
use std::collections::BTreeMap;
const MAX_HEAD: usize = 8192;
const MAX_BODY: usize = 65536;

#[derive(Debug)]
pub struct Head {
    pub method: String,
    pub target: Vec<u8>,
    pub headers: BTreeMap<String, Vec<u8>>,
    pub consumed: usize,
}
#[derive(Debug)]
pub enum HeadResult {
    Complete(Head),
    NeedMore,
    Bad,
    TooLarge,
}
#[derive(Debug)]
pub struct Request {
    pub head: Head,
    pub body: Vec<u8>,
}
#[derive(Debug)]
pub enum Frame {
    Complete(Request),
    NeedMore,
    Reject(u16),
}

pub fn head(input: &[u8], max_head: usize) -> HeadResult {
    let window = &input[..input.len().min(max_head.saturating_add(4))];
    let Some(end) = window.windows(4).position(|w| w == b"\r\n\r\n") else {
        return if input.len() > max_head {
            HeadResult::TooLarge
        } else {
            HeadResult::NeedMore
        };
    };
    let consumed = end + 4;
    if consumed > max_head {
        return HeadResult::TooLarge;
    }
    let bytes = &input[..consumed];
    // httparse permits bare LF and leading empty lines. Preserve strict CRLF.
    for (i, b) in bytes.iter().enumerate() {
        if (*b == b'\n' && (i == 0 || bytes[i - 1] != b'\r'))
            || (*b == b'\r' && bytes.get(i + 1) != Some(&b'\n'))
        {
            return HeadResult::Bad;
        }
    }
    let line_end = bytes.windows(2).position(|w| w == b"\r\n").unwrap();
    let parts: Vec<_> = bytes[..line_end].split(|b| *b == b' ').collect();
    if parts.len() != 3
        || parts[0].is_empty()
        || parts[0].len() > 16
        || !parts[0].iter().all(u8::is_ascii_uppercase)
        || parts[1].first() != Some(&b'/')
        || parts[1].iter().any(|b| *b <= 0x20 || *b == 0x7f)
        || !matches!(parts[2], b"HTTP/1.1")
    {
        return HeadResult::Bad;
    }
    let mut slots = [httparse::EMPTY_HEADER; 64];
    let mut parsed = httparse::Request::new(&mut slots);
    // C++ accepts arbitrary non-control target bytes, but httparse exposes a
    // UTF-8 &str. Validate original bytes above; substitute only non-ASCII
    // target bytes in a bounded temporary head for upstream syntax parsing.
    // Offsets stay identical and the returned target always uses original bytes.
    let mut sanitized;
    let parser_input = if std::str::from_utf8(parts[1]).is_err() {
        sanitized = bytes.to_vec();
        let start = parts[0].len() + 1;
        for b in &mut sanitized[start..start + parts[1].len()] {
            if !b.is_ascii() {
                *b = b'?';
            }
        }
        sanitized.as_slice()
    } else {
        bytes
    };
    match parsed.parse(parser_input) {
        Ok(httparse::Status::Complete(n)) if n == consumed => (),
        _ => return HeadResult::Bad,
    }
    let mut headers = BTreeMap::new();
    for header in parsed.headers.iter() {
        if !header
            .name
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_'))
        {
            return HeadResult::Bad;
        }
        let name = header.name.to_ascii_lowercase();
        let value = header.value;
        let start = value
            .iter()
            .position(|b| !matches!(b, b' ' | b'\t'))
            .unwrap_or(value.len());
        let end = value
            .iter()
            .rposition(|b| !matches!(b, b' ' | b'\t'))
            .map_or(start, |i| i + 1);
        let value = &value[start..end];
        if value.iter().any(|b| *b < 0x20 || *b == 0x7f) || headers.contains_key(&name) {
            return HeadResult::Bad;
        }
        headers.insert(name, value.to_vec());
    }
    HeadResult::Complete(Head {
        method: parsed.method.unwrap().into(),
        target: parts[1].to_vec(),
        headers,
        consumed,
    })
}

pub fn content_length(h: &Head) -> Result<usize, u16> {
    if h.headers.contains_key("transfer-encoding") {
        return Err(400);
    }
    let Some(value) = h.headers.get("content-length") else {
        return Ok(0);
    };
    if value.is_empty() {
        return Err(400);
    }
    let mut n = 0_u64;
    for b in value {
        if !b.is_ascii_digit() {
            return Err(400);
        }
        n = n
            .checked_mul(10)
            .and_then(|n| n.checked_add(u64::from(*b - b'0')))
            .ok_or(413_u16)?;
    }
    if n > MAX_BODY as u64 {
        return Err(413);
    }
    Ok(n as usize)
}

pub fn frame(input: &[u8]) -> Frame {
    match head(input, MAX_HEAD) {
        HeadResult::NeedMore => Frame::NeedMore,
        HeadResult::Bad => Frame::Reject(400),
        HeadResult::TooLarge => Frame::Reject(431),
        HeadResult::Complete(head) => match content_length(&head) {
            Err(status) => Frame::Reject(status),
            Ok(n) if input.len() < head.consumed + n => Frame::NeedMore,
            Ok(n) if input.len() > head.consumed + n => Frame::Reject(400),
            Ok(_) => {
                let body = input[head.consumed..].to_vec();
                Frame::Complete(Request { head, body })
            }
        },
    }
}
