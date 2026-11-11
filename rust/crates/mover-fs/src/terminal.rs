//! Nonblocking no-echo controlling terminal; caller handles catchable signals.
use super::*;
use rustix::termios::{self, OptionalActions, Termios};
use std::{
    cell::Cell,
    fs::File,
    io::{Read, Write},
    os::fd::{AsFd, AsRawFd, BorrowedFd, RawFd},
};

pub struct SecretTerminal {
    file: File,
    original: Termios,
    active: Cell<bool>,
}
impl SecretTerminal {
    pub fn open() -> Result<Self> {
        // Fixed system path, still exclude an individually mounted NFS leaf.
        super::instance::ingress_local(std::path::Path::new("/dev/tty"))?;
        let fd = fs::open(
            "/dev/tty",
            OFlags::RDWR | OFlags::NOFOLLOW | OFlags::NONBLOCK | OFlags::CLOEXEC,
            Mode::empty(),
        )?;
        let file = File::from(fd);
        if termios::tcgetpgrp(&file)? != rustix::process::getpgrp() {
            return Err(ClaimError::Blocked(
                "foreground controlling terminal required",
            ));
        }
        Self::configure(file)
    }
    fn configure(file: File) -> Result<Self> {
        let original = termios::tcgetattr(&file)?;
        let mut raw = original.clone();
        raw.make_raw();
        termios::tcsetattr(&file, OptionalActions::Now, &raw)?;
        Ok(Self {
            file,
            original,
            active: Cell::new(true),
        })
    }
    pub fn restore(&self) -> Result<()> {
        if self.active.get() {
            termios::tcsetattr(&self.file, OptionalActions::Now, &self.original)?;
            self.active.set(false);
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rustix::pty::{self, OpenptFlags};
    #[test]
    fn raw_secret_input_has_no_echo_and_explicit_or_drop_restore() {
        for explicit in [true, false] {
            let master =
                pty::openpt(OpenptFlags::RDWR | OpenptFlags::NOCTTY | OpenptFlags::CLOEXEC)
                    .unwrap();
            pty::grantpt(&master).unwrap();
            pty::unlockpt(&master).unwrap();
            let path = pty::ptsname(&master, Vec::new()).unwrap();
            let slave = fs::open(
                path.as_c_str(),
                OFlags::RDWR | OFlags::NOCTTY | OFlags::NONBLOCK | OFlags::CLOEXEC,
                Mode::empty(),
            )
            .unwrap();
            let file = File::from(slave);
            let observed = file.try_clone().unwrap();
            let before = termios::tcgetattr(&observed).unwrap();
            let terminal = SecretTerminal::configure(file).unwrap();
            let raw = termios::tcgetattr(&observed).unwrap();
            assert!(!raw.local_modes.contains(termios::LocalModes::ECHO));
            assert!(!raw.local_modes.contains(termios::LocalModes::ICANON));
            let mut master = File::from(master);
            master.write_all(b"disposable").unwrap();
            let mut bytes = [0u8; 10];
            let mut reader = &terminal;
            let mut count = 0;
            let until = std::time::Instant::now() + std::time::Duration::from_secs(2);
            while count < bytes.len() {
                match reader.read(&mut bytes[count..]) {
                    Ok(n) => {
                        assert_ne!(n, 0);
                        count += n;
                    }
                    Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                        assert!(std::time::Instant::now() < until);
                        std::thread::sleep(std::time::Duration::from_millis(2));
                    }
                    Err(e) => panic!("{e}"),
                }
            }
            assert_eq!(&bytes, b"disposable");
            fs::fcntl_setfl(
                &master,
                fs::fcntl_getfl(&master).unwrap() | OFlags::NONBLOCK,
            )
            .unwrap();
            assert_eq!(
                master.read(&mut [0u8; 1]).unwrap_err().kind(),
                std::io::ErrorKind::WouldBlock
            );
            if explicit {
                terminal.restore().unwrap();
            }
            drop(terminal);
            let after = termios::tcgetattr(&observed).unwrap();
            assert_eq!(after.local_modes, before.local_modes);
            assert_eq!(after.input_modes, before.input_modes);
            assert_eq!(after.output_modes, before.output_modes);
        }
    }
}
impl Drop for SecretTerminal {
    fn drop(&mut self) {
        let _ = self.restore();
    }
}
impl AsRawFd for SecretTerminal {
    fn as_raw_fd(&self) -> RawFd {
        self.file.as_raw_fd()
    }
}
impl AsFd for SecretTerminal {
    fn as_fd(&self) -> BorrowedFd<'_> {
        self.file.as_fd()
    }
}
impl Read for &SecretTerminal {
    fn read(&mut self, b: &mut [u8]) -> std::io::Result<usize> {
        (&self.file).read(b)
    }
}
impl Write for &SecretTerminal {
    fn write(&mut self, b: &[u8]) -> std::io::Result<usize> {
        (&self.file).write(b)
    }
    fn flush(&mut self) -> std::io::Result<()> {
        (&self.file).flush()
    }
}
