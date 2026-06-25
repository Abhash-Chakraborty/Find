//! Tauri backend supervision for Find desktop application.
//! Spawns, health-checks, and supervises the configured FastAPI API and Worker processes separately.
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tauri::Emitter;
use tauri::Manager;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

const API_COMMAND: &str = "find-api";
const WORKER_COMMAND: &str = "find-worker";

/// Shared state tracking the backend processes (API and Worker) and running status.
#[derive(Default)]
struct BackendState {
    api_running: bool,
    worker_running: bool,
    api_child: Option<CommandChild>,
    worker_child: Option<CommandChild>,
}

type SharedState = Arc<Mutex<BackendState>>;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let state: SharedState = Arc::new(Mutex::new(BackendState::default()));
    let state_for_exit = state.clone();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(move |app| {
            app.manage(state.clone());
            let app_handle = app.handle().clone();
            let state_clone = state.clone();

            tauri::async_runtime::spawn(async move {
                supervise_backend(app_handle, state_clone).await;
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(move |_app_handle, event| {
            if let tauri::RunEvent::Exit = event {
                stop_all_backends(&state_for_exit, "App exiting");
            }
        });
}

/// Stops the current API and Worker processes.
fn stop_all_backends(state: &SharedState, reason: &str) {
    log::info!("{} - terminating backend processes.", reason);
    let mut s = state.lock().unwrap();

    if let Some(child) = s.api_child.take() {
        let _ = child.kill();
        log::info!("API process killed.");
    }
    s.api_running = false;

    if let Some(child) = s.worker_child.take() {
        let _ = child.kill();
        log::info!("Worker process killed.");
    }
    s.worker_running = false;
}

/// Stops a specific backend process (API or Worker).
fn stop_backend(state: &SharedState, process_name: &str, reason: &str) {
    log::info!("{} - terminating {} process.", reason, process_name);
    let mut s = state.lock().unwrap();

    if process_name == "api" {
        if let Some(child) = s.api_child.take() {
            let _ = child.kill();
            log::info!("API process killed.");
        }
        s.api_running = false;
    } else if process_name == "worker" {
        if let Some(child) = s.worker_child.take() {
            let _ = child.kill();
            log::info!("Worker process killed.");
        }
        s.worker_running = false;
    }
}

/// Supervises the backend processes in controlled order: API first, then Worker.
async fn supervise_backend(app: tauri::AppHandle, state: SharedState) {
    const MAX_RETRIES: u32 = 5;
    const RETRY_DELAY_SECS: u64 = 2;
    let mut retry_count = 0;

    loop {
        log::info!("Starting backend processes (attempt {})...", retry_count + 1);

        // Step 1: Start API
        log::info!("Starting API process...");
        match start_process(&app, &state, API_COMMAND, "api").await {
            Ok(_) => {
                log::info!("API process started successfully.");
            }
            Err(e) => {
                log::error!("API process failed: {}", e);
                stop_all_backends(&state, "API startup failed");
                retry_count += 1;

                if retry_count >= MAX_RETRIES {
                    log::error!("Backend failed {} times - giving up.", MAX_RETRIES);
                    let _ = app.emit("backend-failed", format!("API startup failed: {}", e));
                    break;
                }

                tokio::time::sleep(Duration::from_secs(RETRY_DELAY_SECS)).await;
                continue;
            }
        }

        // Step 2: Start Worker
        log::info!("Starting Worker process...");
        match start_process(&app, &state, WORKER_COMMAND, "worker").await {
            Ok(_) => {
                log::info!("Worker process started successfully.");
                log::info!("All backend processes ready - emitting backend-ready.");
                let _ = app.emit("backend-ready", ());
                break;
            }
            Err(e) => {
                log::error!("Worker process failed: {}", e);
                stop_all_backends(&state, "Worker startup failed");
                retry_count += 1;

                if retry_count >= MAX_RETRIES {
                    log::error!("Backend failed {} times - giving up.", MAX_RETRIES);
                    let _ = app.emit("backend-failed", format!("Worker startup failed: {}", e));
                    break;
                }

                tokio::time::sleep(Duration::from_secs(RETRY_DELAY_SECS)).await;
            }
        }
    }
}

/// Polls a backend health endpoint until it responds or times out.
async fn wait_for_health(health_url: &str, process_name: &str) -> Result<(), String> {
    const MAX_ATTEMPTS: u32 = 30;
    const POLL_INTERVAL_MS: u64 = 500;

    for attempt in 1..=MAX_ATTEMPTS {
        tokio::time::sleep(Duration::from_millis(POLL_INTERVAL_MS)).await;
        match reqwest::get(health_url).await {
            Ok(resp) if resp.status().is_success() => {
                log::info!(
                    "{} health check passed on attempt {}.",
                    process_name,
                    attempt
                );
                return Ok(());
            }
            _ => {
                log::info!(
                    "{} health check attempt {}/{} - not ready yet.",
                    process_name,
                    attempt,
                    MAX_ATTEMPTS
                );
            }
        }
    }

    Err(format!(
        "{} did not become healthy after {} attempts.",
        process_name, MAX_ATTEMPTS
    ))
}

/// Spawns a backend process, waits for health, then monitors output until termination.
async fn start_process(
    app: &tauri::AppHandle,
    state: &SharedState,
    command: &str,
    process_name: &str,
) -> Result<(), String> {
    let shell = app.shell();
    let (mut rx, child) = shell
        .command(command)
        .spawn()
        .map_err(|e| format!("Failed to spawn {} command: {}", process_name, e))?;

    {
        let mut s = state.lock().unwrap();
        if process_name == "api" {
            s.api_running = true;
            s.api_child = Some(child);
        } else if process_name == "worker" {
            s.worker_running = true;
            s.worker_child = Some(child);
        }
    }

    log::info!("{} process spawned. Waiting for health check...", process_name);

    // Determine health endpoint based on process type
    let health_url = match process_name {
        "api" => "http://127.0.0.1:8000/health",
        "worker" => "http://127.0.0.1:8001/health", // Worker on different port
        _ => "http://127.0.0.1:8000/health",
    };

    match wait_for_health(health_url, process_name).await {
        Ok(_) => {
            log::info!("{} is healthy.", process_name);
        }
        Err(e) => {
            log::error!("Health check failed for {}: {}", process_name, e);
            stop_backend(state, process_name, "Health check failed");
            let _ = app.emit("backend-failed", e.clone());
            return Err(e);
        }
    }

    // Monitor process output
    while let Some(event) = rx.recv().await {
        match event {
            CommandEvent::Stdout(line) => {
                log::info!("[{}] {}", process_name, String::from_utf8_lossy(&line).trim());
            }
            CommandEvent::Stderr(line) => {
                log::warn!(
                    "[{} err] {}",
                    process_name,
                    String::from_utf8_lossy(&line).trim()
                );
            }
            CommandEvent::Error(err) => {
                return Err(format!("{} command error: {}", process_name, err))
            }
            CommandEvent::Terminated(payload) => {
                let code = payload.code.unwrap_or(-1);
                stop_backend(state, process_name, "Process terminated");
                return if code == 0 {
                    Ok(())
                } else {
                    Err(format!("{} exited with code {}", process_name, code))
                };
            }
            _ => {}
        }
    }

    Err(format!("{} process channel closed unexpectedly.", process_name))
}