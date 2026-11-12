//! Minimal read-only X.509 summary for the admin Settings page: subject common
//! name and notAfter of DER certificates the service already loaded and verified.
//! No dependency; malformed input yields None, never a panic or an error.

/// (subject common name, notAfter as RFC 3339 UTC) when both can be read.
pub(crate) fn summary(der: &[u8]) -> (Option<String>, Option<String>) {
    let parsed = (|| {
        let (cert, _) = tlv(der, 0x30)?;
        let (tbs, _) = tlv(cert, 0x30)?;
        let mut rest = tbs;
        if rest.first() == Some(&0xA0) {
            rest = tlv(rest, 0xA0)?.1; // explicit version
        }
        rest = tlv(rest, 0x02)?.1; // serial
        rest = tlv(rest, 0x30)?.1; // signature algorithm
        rest = tlv(rest, 0x30)?.1; // issuer
        let (validity, rest) = tlv(rest, 0x30)?;
        let (subject, _) = tlv(rest, 0x30)?;
        let not_after = {
            let (_, after) = any(validity)?; // notBefore
            let (tag, value, _) = any_tagged(after)?;
            time(tag, value)
        };
        Some((common_name(subject), not_after))
    })();
    parsed.unwrap_or((None, None))
}

/// One TLV with the expected tag: (content, remainder).
fn tlv(input: &[u8], tag: u8) -> Option<(&[u8], &[u8])> {
    let (found, content, rest) = any_tagged(input)?;
    (found == tag).then_some((content, rest))
}
fn any(input: &[u8]) -> Option<(&[u8], &[u8])> {
    any_tagged(input).map(|(_, c, r)| (c, r))
}
fn any_tagged(input: &[u8]) -> Option<(u8, &[u8], &[u8])> {
    let tag = *input.first()?;
    let first = *input.get(1)? as usize;
    let (length, header) = if first < 0x80 {
        (first, 2)
    } else {
        let count = first & 0x7f;
        if count == 0 || count > 4 {
            return None;
        }
        let mut length = 0_usize;
        for i in 0..count {
            length = (length << 8) | *input.get(2 + i)? as usize;
        }
        (length, 2 + count)
    };
    let end = header.checked_add(length)?;
    Some((tag, input.get(header..end)?, input.get(end..)?))
}

/// Subject CN (OID 2.5.4.3) as UTF8String, PrintableString or IA5String.
fn common_name(mut name: &[u8]) -> Option<String> {
    while !name.is_empty() {
        let (set, rest) = tlv(name, 0x31)?;
        name = rest;
        let mut attrs = set;
        while !attrs.is_empty() {
            let (attr, rest) = tlv(attrs, 0x30)?;
            attrs = rest;
            let (oid, value) = tlv(attr, 0x06)?;
            if oid == [0x55, 0x04, 0x03] {
                let (tag, text, _) = any_tagged(value)?;
                if matches!(tag, 0x0C | 0x13 | 0x16) {
                    let text = std::str::from_utf8(text).ok()?;
                    if text.chars().all(|c| !c.is_control()) {
                        return Some(text.to_owned());
                    }
                }
                return None;
            }
        }
    }
    None
}

/// UTCTime (YYMMDDHHMMSSZ) or GeneralizedTime (YYYYMMDDHHMMSSZ) → RFC 3339.
fn time(tag: u8, value: &[u8]) -> Option<String> {
    let text = std::str::from_utf8(value).ok()?;
    let digits = text.strip_suffix('Z')?;
    if !digits.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    let full = match (tag, digits.len()) {
        (0x17, 12) => {
            let yy: u32 = digits[..2].parse().ok()?;
            format!("{}{}", if yy >= 50 { 19 } else { 20 }, digits)
        }
        (0x18, 14) => digits.to_owned(),
        _ => return None,
    };
    Some(format!(
        "{}-{}-{}T{}:{}:{}Z",
        &full[..4],
        &full[4..6],
        &full[6..8],
        &full[8..10],
        &full[10..12],
        &full[12..14]
    ))
}

#[cfg(test)]
mod tests {
    use super::summary;

    fn tlv(tag: u8, content: &[u8]) -> Vec<u8> {
        let mut out = vec![tag];
        if content.len() < 0x80 {
            out.push(content.len() as u8);
        } else {
            out.push(0x82);
            out.extend_from_slice(&(content.len() as u16).to_be_bytes());
        }
        out.extend_from_slice(content);
        out
    }
    fn cert(after: Vec<u8>, cn: Option<&str>, pad: usize) -> Vec<u8> {
        let name = match cn {
            Some(cn) => tlv(
                0x31,
                &tlv(
                    0x30,
                    &[tlv(0x06, &[0x55, 0x04, 0x03]), tlv(0x0C, cn.as_bytes())].concat(),
                ),
            ),
            None => Vec::new(),
        };
        let tbs = [
            tlv(0xA0, &tlv(0x02, &[2])),
            tlv(0x02, &[1]),
            tlv(0x30, &[]),
            tlv(0x30, &[]),
            tlv(0x30, &[tlv(0x17, b"250101000000Z"), after].concat()),
            tlv(0x30, &name),
            tlv(0x30, &vec![0; pad]), // long-form length coverage
        ]
        .concat();
        tlv(
            0x30,
            &[tlv(0x30, &tbs), tlv(0x30, &[]), tlv(0x03, &[0])].concat(),
        )
    }

    #[test]
    fn reads_common_name_and_expiry() {
        let utc = cert(tlv(0x17, b"301231235959Z"), Some("mover.example"), 300);
        assert_eq!(
            summary(&utc),
            (
                Some("mover.example".into()),
                Some("2030-12-31T23:59:59Z".into())
            )
        );
        let generalized = cert(tlv(0x18, b"20991231000000Z"), None, 0);
        assert_eq!(
            summary(&generalized),
            (None, Some("2099-12-31T00:00:00Z".into()))
        );
        let nineties = cert(tlv(0x17, b"991231000000Z"), Some("old"), 0);
        assert_eq!(
            summary(&nineties).1.as_deref(),
            Some("1999-12-31T00:00:00Z")
        );
    }

    #[test]
    fn malformed_input_is_none_not_a_panic() {
        let good = cert(tlv(0x17, b"301231235959Z"), Some("x"), 0);
        for cut in 0..good.len() {
            let _ = summary(&good[..cut]);
        }
        assert_eq!(summary(b""), (None, None));
        assert_eq!(summary(&[0x30, 0x84, 0xff, 0xff, 0xff, 0xff]), (None, None));
        let bad_time = cert(tlv(0x17, b"3012312359Z"), Some("x"), 0);
        assert_eq!(summary(&bad_time).1, None);
    }
}
