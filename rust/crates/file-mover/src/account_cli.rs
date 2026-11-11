//! Host-local offline account commands. Never bootstraps payloads or starts HTTP.
use crate::{
    Config,
    account::{self, NewCredentials, Record, SecretText},
};
use std::{
    io::{Read, Write},
    path::Path,
    time::Duration,
};
use tokio::{
    io::unix::AsyncFd,
    signal::unix::{Signal, SignalKind, signal},
};
use zeroize::{Zeroize, Zeroizing};
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Action {
    Init,
    Change,
    Status,
}
impl Action {
    pub fn from_flag(s: &str) -> Option<Self> {
        match s {
            "--admin-account-init" => Some(Self::Init),
            "--admin-password-change" => Some(Self::Change),
            "--admin-account-status" => Some(Self::Status),
            _ => None,
        }
    }
}

struct Signals {
    interrupt: Signal,
    terminate: Signal,
    hangup: Signal,
    quit: Signal,
    suspend: Signal,
}
impl Signals {
    fn new() -> std::io::Result<Self> {
        Ok(Self {
            interrupt: signal(SignalKind::interrupt())?,
            terminate: signal(SignalKind::terminate())?,
            hangup: signal(SignalKind::hangup())?,
            quit: signal(SignalKind::quit())?,
            suspend: signal(SignalKind::from_raw(20))?,
        })
    } // Linux SIGTSTP
    fn poll_cancelled(&mut self, cx: &mut std::task::Context<'_>) -> std::task::Poll<()> {
        for signal in [
            &mut self.interrupt,
            &mut self.terminate,
            &mut self.hangup,
            &mut self.quit,
            &mut self.suspend,
        ] {
            if signal.poll_recv(cx).is_ready() {
                return std::task::Poll::Ready(());
            }
        }
        std::task::Poll::Pending
    }
}
async fn until_cancelled<F: std::future::Future>(
    future: F,
    signals: &mut Signals,
) -> Option<F::Output> {
    use std::task::Poll;
    let mut future = std::pin::pin!(future);
    std::future::poll_fn(|cx| {
        if signals.poll_cancelled(cx).is_ready() {
            Poll::Ready(None)
        } else {
            future.as_mut().poll(cx).map(Some)
        }
    })
    .await
}

fn refused() -> Box<dyn std::error::Error> {
    "account custody or publication refused; inspect account status before retrying".into()
}
fn storage_error(e: mover_fs::ClaimError) -> Box<dyn std::error::Error> {
    match e{mover_fs::ClaimError::OutcomeUncertain=>"account publication outcome uncertain; do not retry automatically; inspect account status".into(),_=>refused()}
}

fn options(args: Vec<String>, action: Action, allow_stdin: bool) -> Result<(String, bool)> {
    let mut directory = None;
    let mut stdin = false;
    let mut args = args.into_iter();
    while let Some(arg) = args.next() {
        match arg.as_str(){"--account-dir" if directory.is_none()=>directory=Some(args.next().ok_or("account directory required")?),"--stdin" if allow_stdin&&!stdin&&action!=Action::Status=>stdin=true,_=>return Err("usage: account command CONFIG.json --account-dir EXISTING_PRIVATE_DIRECTORY [--stdin]".into())}
    }
    Ok((directory.ok_or("explicit --account-dir required")?, stdin))
}
fn emit(value: &serde_json::Value) -> Result<()> {
    let mut out = std::io::stdout().lock();
    serde_json::to_writer(&mut out, value)?;
    out.write_all(b"\n")?;
    out.flush()?;
    Ok(())
}
fn worker_inner(config: Config, action: Action, args: Vec<String>) -> Result<()> {
    let (directory, _) = options(args, action, false)?;
    let instance = mover_fs::InstanceGuard::for_database(&config.state_database)?;
    crate::check_state_compatibility(&config, &instance, false)?;
    let state = mover_store::StateInspection::open(&config.state_database)?;
    if state.summary().schema_version != 12
        || mover_fs::validate_inspected_state(&state)? != "RecordedActive"
    {
        return Err(
            "initialized current state with recorded active source pairing required".into(),
        );
    }
    let instance_id = state.summary().instance_id.clone();
    let mut excluded = state.payload_roots()?;
    excluded.extend([
        config.source_root.clone(),
        config.destination_root.clone(),
        instance.state_directory().to_owned(),
    ]);
    if let Some(p) = &config.protected_ingress {
        for path in [&p.producer_socket, &p.operator_socket] {
            excluded.push(
                Path::new(path)
                    .parent()
                    .ok_or("endpoint parent required")?
                    .to_string_lossy()
                    .into_owned(),
            );
        }
    }
    if let Some(n) = &config.native_ingress {
        for path in std::iter::once(n.operator_socket()).chain(n.credential_paths()) {
            excluded.push(
                Path::new(path)
                    .parent()
                    .ok_or("credential parent required")?
                    .to_string_lossy()
                    .into_owned(),
            );
        }
    }
    drop(state);
    let area = mover_fs::account_file::open(&directory, &excluded).map_err(storage_error)?;
    let old = area.read().map_err(storage_error)?.map(Zeroizing::new);
    let record = old
        .as_ref()
        .map(|b| Record::decode(b, &instance_id))
        .transpose()?;
    match action {
        Action::Status => {
            return emit(
                &record
                    .as_ref()
                    .map(Record::status)
                    .unwrap_or_else(|| serde_json::json!({"provisioned":false})),
            );
        }
        Action::Init if record.is_some() => return Err("account already provisioned".into()),
        Action::Change if record.is_none() => return Err("existing account required".into()),
        _ => (),
    }
    emit(&serde_json::json!({"account_ready":true}))?;
    let mut raw = Zeroizing::new(Vec::new());
    std::io::stdin()
        .take((account::MAX_INPUT + 1) as u64)
        .read_to_end(&mut raw)
        .map_err(|_| "account input read failed")?;
    let credentials = NewCredentials::decode(&raw, action == Action::Init)?;
    let next = if let Some(record) = record {
        record.replace_password(&credentials.password)?
    } else {
        Record::create(
            &instance_id,
            credentials.username.ok_or("username required")?,
            &credentials.password,
        )?
    };
    let bytes = next.encode()?;
    area.publish(&bytes, old.as_deref().map(|b| b.as_slice()))
        .map_err(storage_error)?;
    emit(&next.status())
}
/// Private same-executable worker owns state/account locks through actual exit.
/// Direct invocation has the same full validation and grants no remote authority.
pub fn worker(config: Config, action: Action, args: Vec<String>) -> Result<()> {
    match worker_inner(config, action, args) {
        Ok(()) => Ok(()),
        Err(error) => {
            let diagnostic = error.to_string();
            let code = if diagnostic.contains("outcome uncertain") {
                "outcome_uncertain"
            } else if diagnostic.contains("owns state") {
                "instance_busy"
            } else {
                "account_refused"
            };
            let _ = emit(&serde_json::json!({"account_error":code}));
            Err("account command refused".into())
        }
    }
}
struct Helper {
    child: Option<std::process::Child>,
    output: std::io::BufReader<std::process::ChildStdout>,
}
impl Helper {
    fn start(path: &str, action: Action, directory: &str) -> Result<Self> {
        use std::process::{Command, Stdio};
        let flag = match action {
            Action::Init => "--admin-account-init",
            Action::Change => "--admin-password-change",
            Action::Status => "--admin-account-status",
        };
        let mut child = Command::new(std::env::current_exe()?)
            .arg("--internal-admin-account-worker")
            .arg(flag)
            .arg(path)
            .arg("--account-dir")
            .arg(directory)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()?;
        let output = std::io::BufReader::with_capacity(
            1024,
            child
                .stdout
                .take()
                .ok_or("account worker pipe unavailable")?,
        );
        Ok(Self {
            child: Some(child),
            output,
        })
    }
    fn ready(&mut self) -> Result<()> {
        let mut line = Vec::new();
        let mut byte = [0u8; 1];
        loop {
            if self.output.read(&mut byte)? == 0 {
                return Err("account preflight refused; check initialized state and private account directory".into());
            }
            line.push(byte[0]);
            if byte[0] == b'\n' {
                break;
            }
            if line.len() > 1024 {
                return Err("account worker response exceeds bound".into());
            }
        }
        let value: serde_json::Value =
            serde_json::from_slice(&line).map_err(|_| "invalid account worker response")?;
        if value == serde_json::json!({"account_ready":true}) {
            Ok(())
        } else {
            Err(response_error(&value))
        }
    }
    fn send(&mut self, credentials: &NewCredentials) -> Result<()> {
        let bytes = credentials.encode_for_worker()?;
        let mut input = self
            .child
            .as_mut()
            .and_then(|c| c.stdin.take())
            .ok_or("account worker input unavailable")?;
        input
            .write_all(&bytes)
            .map_err(|_| "account worker input failed; outcome may be uncertain")?;
        drop(input);
        Ok(())
    }
    fn finish(mut self) -> Result<serde_json::Value> {
        drop(self.child.as_mut().and_then(|c| c.stdin.take()));
        let mut bytes = Vec::new();
        self.output.by_ref().take(4097).read_to_end(&mut bytes)?;
        if bytes.len() > 4096 {
            if let Some(child) = &mut self.child {
                let _ = child.kill();
            }
            return Err("account worker output exceeds bound; outcome uncertain".into());
        }
        let status = self
            .child
            .as_mut()
            .ok_or("account helper missing")?
            .wait()?;
        self.child.take();
        let value: serde_json::Value = serde_json::from_slice(&bytes)
            .map_err(|_| "account worker response missing; publication outcome may be uncertain")?;
        if !status.success() || value.get("account_error").is_some() {
            return Err(response_error(&value));
        }
        let object = value.as_object().ok_or("invalid account worker status")?;
        if object.keys().any(|k| {
            !matches!(
                k.as_str(),
                "provisioned" | "version" | "username" | "revision"
            )
        }) || !value["provisioned"].is_boolean()
        {
            return Err("invalid account worker status".into());
        }
        Ok(value)
    }
}
impl Drop for Helper {
    fn drop(&mut self) {
        if let Some(child) = &mut self.child {
            drop(child.stdin.take());
            let _ = child.wait();
        }
    }
}
fn response_error(value: &serde_json::Value) -> Box<dyn std::error::Error> {
    match value.get("account_error").and_then(|v|v.as_str()){
 Some("instance_busy")=>"local instance or surviving worker already owns state; stop mover and wait for actual exit".into(),
 Some("outcome_uncertain")=>"account publication outcome uncertain; do not retry automatically; inspect account status".into(),
 _=>"account setup refused; check initialized state, selected command and private account custody".into()
}
}
pub fn run(config_path: String, action: Action, args: Vec<String>) -> Result<()> {
    use std::io::IsTerminal;
    let (directory, stdin) = options(args, action, true)?;
    let supplied = if stdin {
        if std::io::stdin().is_terminal() {
            return Err("--stdin requires a nonterminal input; use the no-echo prompt".into());
        }
        let mut raw = Zeroizing::new(Vec::new());
        std::io::stdin()
            .take((account::MAX_INPUT + 1) as u64)
            .read_to_end(&mut raw)
            .map_err(|_| "account stdin read failed")?;
        Some(NewCredentials::decode(&raw, action == Action::Init)?)
    } else {
        None
    };
    let mut helper = Helper::start(&config_path, action, &directory)?;
    if action == Action::Status {
        return emit(&helper.finish()?);
    }
    helper.ready()?;
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()?;
    runtime.block_on(async {
        let mut signals = Signals::new()?;
        let credentials = if let Some(input) = supplied {
            input
        } else {
            prompt(action == Action::Init, &mut signals).await?
        };
        helper.send(&credentials)?;
        drop(credentials);
        let mut finish = tokio::task::spawn_blocking(move || helper.finish().map_err(|_|
            "account helper failed or publication outcome is uncertain; inspect status before retrying"));
        let status = match until_cancelled(&mut finish, &mut signals).await {
            Some(result) => result.map_err(|_| "account helper monitor failed; inspect status")??,
            None => {
                let _ = finish.await;
                return Err("account command interrupted after submission; publication outcome uncertain; inspect status".into());
            }
        };
        emit(&status)
    })
}

async fn prompt(initialize: bool, signals: &mut Signals) -> Result<NewCredentials> {
    let terminal =
        AsyncFd::new(mover_fs::terminal::SecretTerminal::open().map_err(
            |_| "a controlling terminal is required; use explicit --stdin for automation",
        )?)?;
    let input = match until_cancelled(
        tokio::time::timeout(
            Duration::from_secs(300),
            prompt_fields(&terminal, initialize),
        ),
        signals,
    )
    .await
    {
        Some(Ok(input)) => input,
        Some(Err(_)) => Err("account prompt timed out".into()),
        None => Err("account prompt interrupted".into()),
    };
    terminal
        .get_ref()
        .restore()
        .map_err(|_| "terminal restoration failed; restore terminal settings before continuing")?;
    input
}
async fn prompt_fields(
    terminal: &AsyncFd<mover_fs::terminal::SecretTerminal>,
    initialize: bool,
) -> Result<NewCredentials> {
    let username = if initialize {
        Some(line(terminal, b"Username (input hidden): ", 128).await?)
    } else {
        None
    };
    let password = line(terminal, b"New password: ", 4096).await?;
    let confirm = line(terminal, b"Repeat new password: ", 4096).await?;
    Ok(NewCredentials::from_text(
        username, password, confirm, initialize,
    )?)
}
async fn line(
    terminal: &AsyncFd<mover_fs::terminal::SecretTerminal>,
    label: &[u8],
    maximum: usize,
) -> Result<SecretText> {
    let mut writer = terminal.get_ref();
    writer
        .write_all(label)
        .map_err(|_| "terminal prompt write failed")?;
    let mut bytes = Zeroizing::new(Vec::new());
    loop {
        let mut ready = terminal.readable().await?;
        let mut b = [0u8; 1];
        let n = match ready.try_io(|fd| {
            let mut reader = fd.get_ref();
            reader.read(&mut b)
        }) {
            Ok(result) => result.map_err(|_| "terminal read failed")?,
            Err(_) => continue,
        };
        if n == 0 {
            return Err("terminal input closed".into());
        }
        match b[0] {
            b'\r' | b'\n' => break,
            3 | 4 | 26 => return Err("account prompt interrupted".into()),
            8 | 127 => {
                if !bytes.is_empty() {
                    let mut i = bytes.len() - 1;
                    while i > 0 && bytes[i] & 0xc0 == 0x80 {
                        i -= 1;
                    }
                    bytes[i..].zeroize();
                    bytes.truncate(i);
                }
            }
            21 => bytes.zeroize(),
            c => {
                if bytes.len() == maximum {
                    return Err("terminal input exceeds byte bound".into());
                }
                bytes.push(c);
            }
        }
    }
    writer
        .write_all(b"\r\n")
        .map_err(|_| "terminal prompt write failed")?;
    let text = std::str::from_utf8(&bytes).map_err(|_| "terminal input must be UTF-8")?;
    Ok(SecretText(Zeroizing::new(text.to_owned())))
}
