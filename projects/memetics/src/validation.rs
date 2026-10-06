//! Run trusted manifest commands on a disposable copy, without host secrets or network.

use crate::config::strings;
use crate::error::Result;
use crate::git::{clean_env, run_with_timeout};
use serde_json::{Value, json};
use std::io::{Read, Seek, SeekFrom};
use std::path::Path;
use std::process::{Command, Stdio};
use std::time::Duration;
use wait_timeout::ChildExt;

const OUTPUT_TAIL: u64 = 16_000;

pub trait Validator: Send + Sync {
    fn run(&self, checkout: &Path, config: &Value) -> Result<Value>;
}

/// Copy a tree preserving symlinks and skipping every `.git` entry.
pub fn copy_tree(src: &Path, dst: &Path) -> Result<()> {
    std::fs::create_dir_all(dst)?;
    for entry in std::fs::read_dir(src)? {
        let entry = entry?;
        if entry.file_name() == ".git" {
            continue;
        }
        let from = entry.path();
        let to = dst.join(entry.file_name());
        let kind = entry.file_type()?;
        if kind.is_symlink() {
            std::os::unix::fs::symlink(std::fs::read_link(&from)?, &to)?;
        } else if kind.is_dir() {
            copy_tree(&from, &to)?;
        } else {
            std::fs::copy(&from, &to)?;
        }
    }
    Ok(())
}

pub struct DockerValidator;

impl DockerValidator {
    fn command(
        &self,
        workspace: &Path,
        image: &str,
        name: &str,
        command: &str,
        timeout: u64,
    ) -> Value {
        let mut log = match tempfile::tempfile() {
            Ok(f) => f,
            Err(e) => {
                return json!({"command": command, "exit_code": null, "output": e.to_string()});
            }
        };
        let (uid, gid) = unsafe { (libc::getuid(), libc::getgid()) };
        let spawned = log.try_clone().and_then(|stdout| {
            let stderr = log.try_clone()?;
            Command::new("docker")
                .args([
                    "run",
                    "--rm",
                    "--name",
                    name,
                    "--pull=never",
                    "--network=none",
                    "--cap-drop=ALL",
                ])
                .args([
                    "--security-opt=no-new-privileges",
                    "--read-only",
                    "--pids-limit=256",
                ])
                .args(["--memory=1g", "--cpus=2", "--user", &format!("{uid}:{gid}")])
                .args(["--tmpfs", "/tmp:rw,nosuid,size=256m", "--env", "HOME=/tmp"])
                .arg("--mount")
                .arg(format!(
                    "type=bind,src={},dst=/workspace",
                    workspace.display()
                ))
                .args(["--workdir", "/workspace", image, "sh", "-lc", command])
                .env_clear()
                .envs(clean_env())
                .stdin(Stdio::null())
                .stdout(stdout)
                .stderr(stderr)
                .spawn()
        });
        let mut child = match spawned {
            Ok(child) => child,
            Err(e) => {
                return json!({"command": command, "exit_code": null, "output": e.to_string()});
            }
        };
        let code = match child.wait_timeout(Duration::from_secs(timeout)) {
            Ok(Some(status)) => status.code(),
            Ok(None) => {
                let _ = child.kill();
                let _ = child.wait();
                return json!({"command": command, "exit_code": null,
                    "output": format!("Command timed out after {timeout} seconds")});
            }
            Err(e) => {
                return json!({"command": command, "exit_code": null, "output": e.to_string()});
            }
        };
        // A file prevents a noisy test from filling the worker's memory.
        let size = log.seek(SeekFrom::End(0)).unwrap_or(0);
        let _ = log.seek(SeekFrom::Start(size.saturating_sub(OUTPUT_TAIL)));
        let mut tail = Vec::new();
        let _ = log.read_to_end(&mut tail);
        json!({
            "command": command,
            "exit_code": code,
            "output": String::from_utf8_lossy(&tail),
            "output_truncated": size > OUTPUT_TAIL,
        })
    }
}

impl Validator for DockerValidator {
    fn run(&self, checkout: &Path, config: &Value) -> Result<Value> {
        let adaptation = &config["adaptation"];
        let image = adaptation["validation_image"]
            .as_str()
            .unwrap_or("python:3.13-slim");
        let timeout = adaptation["timeout_seconds"].as_u64().unwrap_or(120);
        let tmp = tempfile::Builder::new()
            .prefix("memetics-check-")
            .tempdir()?;
        let workspace = tmp.path().join("workspace");
        copy_tree(checkout, &workspace)?;
        let mut results = Vec::new();
        for command in strings(adaptation.get("validation_commands")) {
            let name = format!("memetics-{}", uuid::Uuid::new_v4().simple());
            results.push(self.command(&workspace, image, &name, &command, timeout));
            let mut cleanup = Command::new("docker");
            cleanup
                .args(["rm", "-f", &name])
                .env_clear()
                .envs(clean_env());
            let _ = run_with_timeout(&mut cleanup, Duration::from_secs(15), None);
        }
        let passed = results.iter().all(|r| r["exit_code"] == json!(0));
        Ok(json!({"passed": passed, "runner": "docker", "image": image, "results": results}))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn copy_skips_git_and_keeps_symlinks() {
        let src = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(src.path().join(".git")).unwrap();
        std::fs::create_dir_all(src.path().join("pkg/.git")).unwrap();
        std::fs::write(src.path().join("pkg/a.txt"), "a").unwrap();
        std::os::unix::fs::symlink("pkg/a.txt", src.path().join("link")).unwrap();
        let dst = tempfile::tempdir().unwrap();
        copy_tree(src.path(), &dst.path().join("w")).unwrap();
        let w = dst.path().join("w");
        assert!(!w.join(".git").exists() && !w.join("pkg/.git").exists());
        assert_eq!(std::fs::read_to_string(w.join("pkg/a.txt")).unwrap(), "a");
        assert!(
            w.join("link")
                .symlink_metadata()
                .unwrap()
                .file_type()
                .is_symlink()
        );
    }
}
