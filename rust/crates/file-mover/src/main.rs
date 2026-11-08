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
    if path == "--migrate-state" {
        let config_path = args.next().ok_or("configuration path required")?;
        if args.next().as_deref() != Some("--backup-dir") {
            return Err("usage: file-mover --migrate-state CONFIG.json --backup-dir NEW_ABSOLUTE_DIRECTORY [--confirm]".into());
        }
        let output = args
            .next()
            .ok_or("new absolute backup directory required")?;
        let confirm = match args.next().as_deref() {
            None => false,
            Some("--confirm") => true,
            _ => return Err("unexpected migration argument".into()),
        };
        if args.next().is_some() {
            return Err("unexpected migration argument".into());
        }
        let config = read_config(&config_path)?;
        let instance = mover_fs::InstanceGuard::for_database(&config.state_database)?;
        instance.validate_database(&config.state_database)?;
        instance.prepare_workers()?;
        let state = mover_store::StateInspection::open(&config.state_database)?;
        let pairing = mover_fs::validate_inspected_state(&state)?;
        let version = state.summary().schema_version;
        let mut excluded = state.payload_roots()?;
        excluded.extend([
            config.source_root,
            config.destination_root,
            instance.state_directory().into(),
        ]);
        // Preview validates lexical/local placement, without creating output.
        mover_fs::BackupOutput::check_location(&output, &excluded)?;
        if !confirm || version == 12 {
            println!(
                "{}",
                serde_json::json!({"schema_version":version,"target_schema":12,"conversion_required":version==11,"converted":false,"preview":!confirm,"backup_directory":output,"pairing_state":pairing,"payload_filesystem_inspected":false})
            );
            return Ok(());
        }
        let backup = mover_fs::BackupOutput::create(&output, &excluded)?;
        backup.copy(&state)?;
        instance.validate_database(&config.state_database)?;
        let snapshot = backup.database_path();
        let receipt = backup.finish(&state, pairing)?;
        instance.validate_database(&config.state_database)?;
        let summary = state.migrate_legacy(&config.state_database,&snapshot,|stage| {
            instance.validate_database(&config.state_database).map_err(|e|std::io::Error::other(e.to_string()))?;
            mover_fs::qualification_pause(stage).map_err(|e|std::io::Error::other(e.to_string()))?;
            #[cfg(feature="nfs-qualification")]
            if std::env::var("FILE_MOVER_QUALIFICATION_MIGRATION_FAULT").ok().as_deref()==Some(stage) {
                return Err(std::io::Error::from_raw_os_error(5));
            }
            Ok(())
        }).map_err(|e|format!("migration failed ({e}); preserve original state and backup, run guarded --check-state; commit may have completed; never automatically restore"))?;
        let target = mover_store::StateInspection::open(&config.state_database)?;
        if mover_fs::validate_inspected_state(&target)? != pairing {
            return Err("postmigration pairing mismatch; preserve state and inspect".into());
        }
        instance.validate_database(&config.state_database)?;
        println!(
            "{}",
            serde_json::json!({"converted":true,"schema_version":summary.schema_version,"instance_id":summary.instance_id,"retained_jobs":summary.retained_jobs,"backup_directory":output,"backup_receipt":receipt,"payload_filesystem_inspected":false})
        );
        return Ok(());
    }
    if path == "--check-state" || path == "--backup-state" {
        let config_path = args.next().ok_or("configuration path required")?;
        let output = if path == "--backup-state" {
            Some(
                args.next()
                    .ok_or("new absolute backup directory required")?,
            )
        } else {
            None
        };
        if args.next().is_some() {
            return Err("usage: file-mover --check-state CONFIG.json | --backup-state CONFIG.json NEW_DIRECTORY".into());
        }
        let config = read_config(&config_path)?;
        // No bootstrap, source/destination access or workers. Lifetime admission
        // precedes SQLite, and guard destruction follows connection closure.
        let instance = mover_fs::InstanceGuard::for_database(&config.state_database)?;
        instance.validate_database(&config.state_database)?;
        instance.prepare_workers()?;
        let state = mover_store::StateInspection::open(&config.state_database)?;
        let pairing = mover_fs::validate_inspected_state(&state)?;
        instance.validate_database(&config.state_database)?;
        if let Some(output) = output {
            let mut excluded = state.payload_roots()?;
            excluded.extend([
                config.source_root,
                config.destination_root,
                instance.state_directory().into(),
            ]);
            let backup = mover_fs::BackupOutput::create(&output, &excluded)?;
            backup.copy(&state)?;
            instance.validate_database(&config.state_database)?;
            let receipt = backup.finish(&state, pairing)?;
            instance.validate_database(&config.state_database)?;
            println!(
                "{}",
                serde_json::json!({"verified":true,"directory":output,"receipt":receipt})
            );
        } else {
            println!(
                "{}",
                serde_json::json!({"schema_version":state.summary().schema_version,"instance_id":state.summary().instance_id,"retained_jobs":state.summary().retained_jobs,"pairing_state":pairing,"migration_apply_enabled":false,"payload_filesystem_inspected":false})
            );
        }
        return Ok(());
    }
    if path == "--clear-history" {
        let config_path = args.next().ok_or("configuration path required")?;
        let mut confirm = false;
        let mut job_ids = Vec::new();
        for value in args {
            if value == "--confirm" && !confirm {
                confirm = true;
                continue;
            }
            let id: i64 = value
                .parse()
                .map_err(|_| "canonical positive job ID required")?;
            if id <= 0 || id.to_string() != value || job_ids.len() == 256 {
                return Err("1-256 canonical positive job IDs required".into());
            }
            job_ids.push(id);
        }
        if job_ids.is_empty() {
            return Err(
                "usage: file-mover --clear-history CONFIG.json JOB_ID... [--confirm]".into(),
            );
        }
        let config = read_config(&config_path)?;
        // No filesystem worker subprocesses or payload-root access. Admission
        // excludes the daemon and surviving groups before SQLite. Register this
        // process too: its SQLite owner must outlive any early flock closure.
        let instance = mover_fs::InstanceGuard::for_database(&config.state_database)?;
        file_mover::check_state_compatibility(&config, &instance, false)?;
        if confirm {
            let store = mover_store::Store::open_for_history_clear(&config.state_database)?;
            instance.validate_database(&config.state_database)?;
            eprintln!(
                "Clear selected jobs {job_ids:?}: forget history, replay and all file tracking; files stay in place and leave mover management."
            );
            let cleared = store.clear_completed_history(&job_ids)?;
            println!("{}", serde_json::json!({"cleared_count":cleared}));
        } else {
            // Read-only schema/state validation; no fresh database or migration.
            let _store = mover_store::Store::open_read_only(&config.state_database)?;
            println!(
                "{}",
                serde_json::json!({"selected_job_ids":job_ids,"confirmation_required":true,"effect":"Forget history, replay and all file tracking. Files stay in place and leave mover management. Only committed jobs can currently be cleared. Rerun with --confirm."})
            );
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
        file_mover::check_state_compatibility(&config, &instance, true)?;
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
        file_mover::check_state_compatibility(&config, &instance, false)?;
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
