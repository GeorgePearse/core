//! Virtual environment slimming functionality

use crate::error::{Result, TsrsError};
use crate::imports::ImportCollector;
use crate::venv::VenvAnalyzer;
use std::fs;
use std::path::{Path, PathBuf};
use walkdir::WalkDir;

/// Creates slim versions of virtual environments
pub struct VenvSlimmer {
    code_directory: PathBuf,
    source_venv: PathBuf,
    output_venv: PathBuf,
}

impl VenvSlimmer {
    /// Create a new venv slimmer that analyzes `code_directory` and slims `source_venv`
    ///
    /// # Errors
    ///
    /// Returns an error if either path does not exist.
    pub fn new<P: AsRef<Path>>(code_directory: P, source_venv: P) -> Result<Self> {
        let code_dir = code_directory.as_ref().to_path_buf();
        let source = source_venv.as_ref().to_path_buf();

        if !code_dir.exists() {
            return Err(TsrsError::InvalidVenvPath(format!(
                "Code directory does not exist: {}",
                code_dir.display()
            )));
        }

        if !source.exists() {
            return Err(TsrsError::InvalidVenvPath(format!(
                "Source venv does not exist: {}",
                source.display()
            )));
        }

        // Default output is .venv-slim next to the source venv
        let mut output = source
            .parent()
            .map_or_else(|| PathBuf::from("."), Path::to_path_buf);
        output.push(".venv-slim");

        Ok(VenvSlimmer {
            code_directory: code_dir,
            source_venv: source,
            output_venv: output,
        })
    }

    /// Create a new venv slimmer with custom output path
    ///
    /// # Errors
    ///
    /// Returns an error if either path does not exist.
    pub fn new_with_output<P: AsRef<Path>>(
        code_directory: P,
        source_venv: P,
        output_venv: P,
    ) -> Result<Self> {
        let code_dir = code_directory.as_ref().to_path_buf();
        let source = source_venv.as_ref().to_path_buf();
        let output = output_venv.as_ref().to_path_buf();

        if !code_dir.exists() {
            return Err(TsrsError::InvalidVenvPath(format!(
                "Code directory does not exist: {}",
                code_dir.display()
            )));
        }

        if !source.exists() {
            return Err(TsrsError::InvalidVenvPath(format!(
                "Source venv does not exist: {}",
                source.display()
            )));
        }

        Ok(VenvSlimmer {
            code_directory: code_dir,
            source_venv: source,
            output_venv: output,
        })
    }

    /// Create a slim venv by analyzing code imports and copying only used packages
    ///
    /// # Errors
    ///
    /// Returns an error if the analysis or copying fails.
    pub fn slim(&self) -> Result<()> {
        tracing::info!("Starting venv slimming");
        tracing::info!("  Code directory: {}", self.code_directory.display());
        tracing::info!("  Source venv: {}", self.source_venv.display());
        tracing::info!("  Output venv: {}", self.output_venv.display());

        // Analyze source venv
        let analyzer = VenvAnalyzer::new(&self.source_venv)?;
        let venv_info = analyzer.analyze()?;
        tracing::info!("Found {} packages in source venv", venv_info.packages.len());

        // Collect all imports from the code directory
        let mut import_collector = ImportCollector::new();
        self.collect_imports_from_code(&mut import_collector);
        let used_imports = import_collector.get_imports();
        tracing::info!(
            "Found {} unique imports in code",
            used_imports.imports.len()
        );

        // Create base structure
        self.create_venv_structure()?;

        // Copy only packages that match imports
        self.copy_used_packages(&venv_info, &used_imports)?;

        tracing::info!("Successfully created slim venv");
        Ok(())
    }

    /// Collect all imports from Python files in the code directory
    #[allow(clippy::redundant_closure_for_method_calls)]
    fn collect_imports_from_code(&self, collector: &mut ImportCollector) {
        for entry in WalkDir::new(&self.code_directory)
            .into_iter()
            .filter_map(|e| e.ok())
            .filter(|e| e.path().extension().is_some_and(|ext| ext == "py"))
        {
            if let Err(e) = collector.collect_from_file(entry.path()) {
                tracing::warn!("Failed to parse {}: {}", entry.path().display(), e);
            }
        }
    }

    /// Create the base venv structure
    fn create_venv_structure(&self) -> Result<()> {
        // Create lib/pythonX.Y/site-packages structure
        fs::create_dir_all(&self.output_venv)?;

        // Copy basic venv files
        self.copy_venv_basics()?;

        Ok(())
    }

    /// Copy basic venv structure (bin, etc)
    fn copy_venv_basics(&self) -> Result<()> {
        let dirs_to_copy = ["bin", "pyvenv.cfg"];

        for dir in &dirs_to_copy {
            let src = self.source_venv.join(dir);
            let dst = self.output_venv.join(dir);

            if src.exists() {
                if src.is_dir() {
                    self.copy_dir_recursive(&src, &dst)?;
                } else {
                    fs::copy(&src, &dst)?;
                }
            }
        }

        Ok(())
    }

    /// Copy used packages to slim venv
    fn copy_used_packages(
        &self,
        venv_info: &crate::venv::VenvInfo,
        used_imports: &crate::imports::ImportSet,
    ) -> Result<()> {
        // Find destination site-packages
        let dst_site_packages = self.find_or_create_site_packages(&self.output_venv)?;

        tracing::info!("Copying packages to {}", dst_site_packages.display());

        // Copy each used package
        for package in &venv_info.packages {
            let mut package_name = package
                .name
                .split('-')
                .next()
                .unwrap_or(&package.name)
                .to_string();
            if package_name.ends_with(".py") {
                package_name = package_name.trim_end_matches(".py").to_string();
            }

            if used_imports.imports.contains(&package_name) {
                let src = &package.path;
                let dst = if src.is_dir() {
                    dst_site_packages.join(&package.name)
                } else {
                    let filename = src
                        .file_name()
                        .map(|os| os.to_string_lossy().to_string())
                        .unwrap_or_else(|| package.name.clone());
                    dst_site_packages.join(filename)
                };

                tracing::debug!("Copying package: {}", package.name);
                if src.is_dir() {
                    self.copy_dir_recursive(src, &dst)?;
                } else {
                    fs::copy(src, &dst)?;
                }
            }
        }

        Ok(())
    }

    /// Find site-packages directory
    fn find_site_packages(venv_path: &Path) -> Result<PathBuf> {
        let lib_path = venv_path.join("lib");

        for entry in fs::read_dir(&lib_path)? {
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
            "Could not find site-packages".to_string(),
        ))
    }

    /// Find or create site-packages directory in output venv
    fn find_or_create_site_packages(&self, venv_path: &Path) -> Result<PathBuf> {
        // Copy the Python version from source
        let src_site_packages = Self::find_site_packages(&self.source_venv)?;
        let python_dir = src_site_packages
            .parent()
            .and_then(|p| p.file_name())
            .map(|n| n.to_string_lossy().to_string())
            .ok_or_else(|| {
                TsrsError::InvalidVenvPath("Could not determine Python version".to_string())
            })?;

        let lib_path = venv_path.join("lib");
        fs::create_dir_all(&lib_path)?;

        let python_path = lib_path.join(python_dir);
        fs::create_dir_all(&python_path)?;

        let site_packages = python_path.join("site-packages");
        fs::create_dir_all(&site_packages)?;

        Ok(site_packages)
    }

    /// Recursively copy a directory
    #[allow(clippy::only_used_in_recursion)]
    fn copy_dir_recursive(&self, src: &Path, dst: &Path) -> Result<()> {
        fs::create_dir_all(dst)?;

        for entry in fs::read_dir(src)? {
            let entry = entry?;
            let path = entry.path();
            let file_name = entry.file_name();
            let dst_path = dst.join(&file_name);

            if path.is_dir() {
                self.copy_dir_recursive(&path, &dst_path)?;
            } else {
                fs::copy(&path, &dst_path)?;
            }
        }

        Ok(())
    }
}
