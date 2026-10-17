use std::sync::{Arc, atomic::AtomicBool};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let Some(path) = args.next() else {
        return Err("usage: file-mover CONFIG.json | --check-platform".into());
    };
    if path == "--internal-source-space-worker" {
        if args.next().is_some() {
            return Err("internal worker takes no arguments".into());
        }
        return file_mover::source_space::worker();
    }
    if path == "--internal-bootstrap-worker" {
        if args.next().is_some() {
            return Err("internal worker takes no arguments".into());
        }
        return file_mover::bootstrap::worker();
    }
    if path == "--internal-enrollment-worker" {
        if args.next().is_some() {
            return Err("internal worker takes no arguments".into());
        }
        return file_mover::enrollment::worker();
    }
    if path == "--internal-payload-worker" {
        if args.next().is_some() {
            return Err("internal worker takes no arguments".into());
        }
        return file_mover::payload::worker();
    }
    if path == "--internal-claim-worker" {
        if args.next().is_some() {
            return Err("internal worker takes no arguments".into());
        }
        return file_mover::claim_worker::worker();
    }
    if path == "--internal-delivery-worker" {
        if args.next().is_some() {
            return Err("internal worker takes no arguments".into());
        }
        return file_mover::delivery_worker::worker();
    }
    if path == "--check-platform" && args.next().is_none() {
        let mode = if mover_fs::nfs_qualification_enabled() {
            "nfs-qualification"
        } else {
            "production"
        };
        println!("file-mover 0.1.0 local-claim prototype build={mode}");
        return Ok(());
    }
    if mover_fs::nfs_qualification_enabled() {
        eprintln!("NFS QUALIFICATION BUILD: isolated testing only; not approved for deployment");
    }
    if path == "--stop" || path == "--status" {
        let config_path = args.next().ok_or("configuration path required")?;
        if args.next().is_some() {
            return Err("usage: file-mover --stop|--status CONFIG.json".into());
        }
        let config = read_config(&config_path)?;
        let (snapshot, success) = tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()?
            .block_on(file_mover::control::command(
                &config.state_database,
                path == "--stop",
            ))?;
        println!("{}", serde_json::to_string(&snapshot)?);
        if !success {
            std::process::exit(2);
        }
        return Ok(());
    }
    if path == "--initialize-source" {
        let config_path = args.next().ok_or("configuration path required")?;
        if args.next().is_some() {
            return Err("usage: file-mover --initialize-source CONFIG.json".into());
        }
        let config = read_config(&config_path)?;
        let instance = Arc::new(mover_fs::InstanceGuard::for_database(
            &config.state_database,
        )?);
        let stop = AtomicBool::new(false);
        let mut guard = file_mover::bootstrap::acquire(
            &config.source_root,
            &config.source_binding,
            &stop,
            &instance,
        )?;
        instance.prepare_database(&config.state_database)?;
        let store = mover_store::Store::open(&config.state_database)?;
        file_mover::enrollment::authorize(&config, &store, &mut guard, true, &stop)?;
        println!("Source enrollment active; original database required for restart");
        return Ok(());
    }
    if path == "--transfer-one" {
        let config_path = args.next().ok_or("configuration path required")?;
        let job: i64 = args.next().ok_or("job ID required")?.parse()?;
        if args.next().is_some() {
            return Err("usage: file-mover --transfer-one CONFIG.json JOB_ID".into());
        }
        let config = read_config(&config_path)?;
        let instance = Arc::new(mover_fs::InstanceGuard::for_database(
            &config.state_database,
        )?);
        let mut guard = file_mover::bootstrap::acquire(
            &config.source_root,
            &config.source_binding,
            &AtomicBool::new(false),
            &instance,
        )?;
        instance.prepare_database(&config.state_database)?;
        let store = mover_store::Store::open(&config.state_database)?;
        file_mover::enrollment::authorize(
            &config,
            &store,
            &mut guard,
            false,
            &AtomicBool::new(false),
        )?;
        store.require_destination_bindings()?;
        let result = mover_fs::transfer_one_with_guard(&store, job, &guard)?;
        let committed = store
            .get(job)?
            .ok_or("unknown job")?
            .recording
            .is_committed();
        println!(
            "{}",
            serde_json::json!({"job_id":job.to_string(),"state":"Published","sha256":result.sha256,"size_bytes":result.stage.size,"source_retained":true,"committed":committed})
        );
        return Ok(());
    }
    if args.next().is_some() {
        return Err("one configuration path required".into());
    }
    let config = read_config(&path)?;
    let lifecycle = file_mover::control::Lifecycle::new(
        Arc::new(AtomicBool::new(false)),
        config.shutdown_wait_seconds,
    );
    tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()?
        .block_on(async {
            let mut terminate =
                tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())?;
            let terminate_stop = lifecycle.clone();
            tokio::spawn(async move {
                while terminate.recv().await.is_some() {
                    terminate_stop.request_stop();
                }
            });
            let signal_stop = lifecycle.clone();
            tokio::spawn(async move {
                while tokio::signal::ctrl_c().await.is_ok() {
                    signal_stop.request_stop();
                }
            });
            let listener = tokio::net::TcpListener::bind(config.bind).await?;
            file_mover::serve_controlled(listener, config, lifecycle).await
        })
}

fn read_config(path: &str) -> Result<file_mover::Config, Box<dyn std::error::Error>> {
    use std::io::Read;
    let mut bytes = Vec::new();
    std::fs::File::open(path)?
        .take(16385)
        .read_to_end(&mut bytes)?;
    if bytes.len() > 16384 {
        return Err("configuration too large".into());
    }
    let config: file_mover::Config = serde_json::from_slice(&bytes)?;
    config.validate()?;
    Ok(config)
}
