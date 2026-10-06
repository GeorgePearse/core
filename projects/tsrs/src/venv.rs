//! Virtual environment analysis

use crate::error::{Result, TsrsError};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

/// Information about a Python virtual environment
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VenvInfo {
    /// Path to the venv
    pub path: PathBuf,
    /// Python version (if detectable)
    pub python_version: Option<String>,
    /// List of installed packages
    pub packages: Vec<PackageInfo>,
}

/// Information about an installed package
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub struct PackageInfo {
    /// Package name
    pub name: String,
    /// Package version
    pub version: Option<String>,
    /// Path to the package
    pub path: PathBuf,
}

/// Analyzes Python virtual environments
pub struct VenvAnalyzer {
    venv_path: PathBuf,
}

impl VenvAnalyzer {
    /// Create a new venv analyzer
    ///
    /// # Errors
    ///
    /// Returns an error if the path does not exist.
    pub fn new<P: AsRef<Path>>(path: P) -> Result<Self> {
        let venv_path = path.as_ref().to_path_buf();

        // Validate that this looks like a venv
        if !venv_path.exists() {
            return Err(TsrsError::InvalidVenvPath(format!(
                "Venv path does not exist: {}",
                venv_path.display()
            )));
        }

        Ok(VenvAnalyzer { venv_path })
    }

    /// Analyze the venv and collect package information
    ///
    /// # Errors
    ///
    /// Returns an error if the analysis fails.
    pub fn analyze(&self) -> Result<VenvInfo> {
        let site_packages_path = self.find_site_packages()?;
        let packages = Self::discover_packages(&site_packages_path)?;

        Ok(VenvInfo {
            path: self.venv_path.clone(),
            python_version: self.detect_python_version(),
            packages,
        })
    }

    /// Find the site-packages directory
    fn find_site_packages(&self) -> Result<PathBuf> {
        let lib_path = self.venv_path.join("lib");

        if !lib_path.exists() {
            return Err(TsrsError::InvalidVenvPath(
                "No lib directory found in venv".to_string(),
            ));
        }

        // Look for pythonX.Y/site-packages
        for entry in std::fs::read_dir(&lib_path)? {
            let entry = entry?;
            let path = entry.path();
            if path.is_dir() {
                let name = path.file_name().unwrap_or_default().to_string_lossy();
                if name.starts_with("python") {
                    let site_packages = path.join("site-packages");
                    if site_packages.exists() {
                        return Ok(site_packages);
                    }
                }
            }
        }

        Err(TsrsError::InvalidVenvPath(
            "Could not find site-packages directory".to_string(),
        ))
    }

    /// Discover all installed packages
    fn discover_packages(site_packages: &Path) -> Result<Vec<PackageInfo>> {
        let mut packages = Vec::new();
        let mut seen = std::collections::HashSet::new();

        for entry in std::fs::read_dir(site_packages)? {
            let entry = entry?;
            let path = entry.path();
            let name = path
                .file_name()
                .unwrap_or_default()
                .to_string_lossy()
                .to_string();

            // Skip special directories
            if name.starts_with('_') || name.starts_with('.') || name == "dist-info" {
                continue;
            }

            if path.is_dir() && !seen.contains(&name) {
                // Check if it has __init__.py or is a namespace package/dist-info
                if path.join("__init__.py").exists()
                    || name.ends_with(".dist-info")
                    || directory_contains_python(&path)?
                {
                    let version = Self::extract_version(&name);
                    packages.push(PackageInfo {
                        name: name.clone(),
                        version,
                        path: path.clone(),
                    });
                    seen.insert(name);
                }
            } else if path.is_file() && path.extension().is_some_and(|ext| ext == "py") {
                if seen.contains(&name) {
                    continue;
                }
                packages.push(PackageInfo {
                    name: name.clone(),
                    version: None,
                    path: path.clone(),
                });
                seen.insert(name);
            }
        }

        packages.sort_by(|a, b| a.name.cmp(&b.name));
        Ok(packages)
    }

    /// Extract version from dist-info directory name
    fn extract_version(name: &str) -> Option<String> {
        if name.ends_with(".dist-info") {
            let parts: Vec<&str> = name.rsplitn(2, '-').collect();
            if parts.len() == 2 {
                return Some(parts[0].to_string());
            }
        }
        None
    }

    /// Try to detect the Python version from the venv
    fn detect_python_version(&self) -> Option<String> {
        let lib_path = self.venv_path.join("lib");
        if let Ok(entries) = std::fs::read_dir(&lib_path) {
            for entry in entries.flatten() {
                let name = entry.file_name().to_string_lossy().to_string();
                if name.starts_with("python") {
                    return Some(name);
                }
            }
        }
        None
    }
}

fn directory_contains_python(path: &Path) -> Result<bool> {
    for entry in std::fs::read_dir(path)? {
        let entry = entry?;
        let child_path = entry.path();
        if (child_path.is_file() && child_path
            .extension()
            .is_some_and(|ext| ext.eq_ignore_ascii_case("py")))
            || (child_path.is_dir() && directory_contains_python(&child_path)?)
        {
            return Ok(true);
        }
    }
    Ok(false)
}
