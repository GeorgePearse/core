pub mod callgraph;
pub mod error;
pub mod imports;
pub mod minify;
pub mod reporting;
pub mod slim;
pub mod venv;

pub use callgraph::{CallGraphAnalyzer, FunctionRef, PackageCallGraph};
pub use imports::{ImportCollector, ImportSet};
pub use minify::{FunctionPlan as MinifyFunctionPlan, Minifier, MinifyPlan, RenameEntry};
pub use reporting::{CallGraphDot, DeadCodeReport, DeadFunction};
pub use slim::VenvSlimmer;
pub use venv::{VenvAnalyzer, VenvInfo};

#[cfg(feature = "python-extension")]
use pyo3::prelude::*;

/// Tree-shaking module for Python
/// Provides functionality to identify and remove unused code exports
/// from Python modules and packages.
#[cfg(feature = "python-extension")]
#[pymodule]
fn tsrs(py: Python, m: &PyModule) -> PyResult<()> {
    m.add("__doc__", "Tree-shaking in Rust for Python")?;

    m.add_class::<PyVenvAnalyzer>()?;
    m.add_class::<PyVenvSlimmer>()?;

    Ok(())
}

#[cfg(feature = "python-extension")]
#[pyclass]
pub struct PyVenvAnalyzer {
    analyzer: VenvAnalyzer,
}

#[cfg(feature = "python-extension")]
#[pymethods]
impl PyVenvAnalyzer {
    #[new]
    fn new(venv_path: String) -> PyResult<Self> {
        let analyzer = VenvAnalyzer::new(venv_path)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        Ok(PyVenvAnalyzer { analyzer })
    }

    fn analyze(&self) -> PyResult<String> {
        let info = self
            .analyzer
            .analyze()
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        Ok(serde_json::to_string(&info)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?)
    }
}

#[cfg(feature = "python-extension")]
#[pyclass]
pub struct PyVenvSlimmer {
    slimmer: VenvSlimmer,
}

#[cfg(feature = "python-extension")]
#[pymethods]
impl PyVenvSlimmer {
    #[new]
    fn new(venv_path: String, output_path: String) -> PyResult<Self> {
        let slimmer = VenvSlimmer::new(venv_path, output_path)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        Ok(PyVenvSlimmer { slimmer })
    }

    fn slim(&self) -> PyResult<String> {
        self.slimmer
            .slim()
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e.to_string()))?;
        Ok("Slim venv created successfully".to_string())
    }
}
