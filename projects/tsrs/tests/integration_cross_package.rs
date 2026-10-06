/// Integration tests for cross-package analysis functionality
/// Tests real Python package scenarios to validate Phase 1 & 2 implementation
use tsrs::CallGraphAnalyzer;

#[test]
fn test_scenario_1_simple_app_utils() {
    // Scenario 1: Simple app + utils pattern
    // Expected: app imports from utils, identifies dead code in both packages

    let mut analyzer = CallGraphAnalyzer::new();

    // Analyze utils package
    let utils_code = r#"
def validate_email(email):
    """Validate email format"""
    return "@" in email

def format_date(date_str):
    """Format date string"""
    return date_str.replace("-", "/")

def unused_helper():
    """This function is never imported or called"""
    return "dead code"

def parse_json(data):
    """Parse JSON data"""
    import json
    return json.loads(data)
"#;

    analyzer.analyze_source("utils", utils_code).expect("Failed to analyze utils");

    // Analyze app package
    let app_code = r#"
from utils import validate_email, format_date, parse_json

def register_user(email, date_joined):
    """Register a new user"""
    if validate_email(email):
        formatted = format_date(date_joined)
        return {"email": email, "joined": formatted}
    return None

def process_data(json_string):
    """Process JSON data"""
    data = parse_json(json_string)
    return data

def local_dead_code():
    """This is dead code - never called anywhere"""
    return "unused"

def test_main():
    """Entry point - test function"""
    user = register_user("test@example.com", "2024-01-15")
    print(user)
"#;

    analyzer.analyze_source("app", app_code).expect("Failed to analyze app");

    // Register imports manually since analyze_source doesn't track cross-package imports yet
    analyzer.add_import("app".to_string(), "validate_email".to_string(),
                       "utils".to_string(), "validate_email".to_string());
    analyzer.add_import("app".to_string(), "format_date".to_string(),
                       "utils".to_string(), "format_date".to_string());
    analyzer.add_import("app".to_string(), "parse_json".to_string(),
                       "utils".to_string(), "parse_json".to_string());

    let _reachable = analyzer.compute_reachable();

    // Find dead code
    let dead_code = analyzer.find_dead_code();
    let dead_names: Vec<String> = dead_code.iter().map(|(_, name)| name.clone()).collect();

    // Verify dead code detection
    assert!(dead_names.contains(&"unused_helper".to_string()), "unused_helper should be dead code");
    assert!(dead_names.contains(&"local_dead_code".to_string()), "local_dead_code should be dead code");

    // Verify live functions exist
    assert!(!dead_names.contains(&"test_main".to_string()), "test_main should not be dead (entry point)");
    assert!(!dead_names.contains(&"register_user".to_string()), "register_user should be live (called from test_main)");
    assert!(!dead_names.contains(&"validate_email".to_string()), "validate_email should be live (called from register_user)");
}

#[test]
fn test_scenario_2_multi_layer_shared_library() {
    // Scenario 2: Multi-layer shared library pattern
    // shared -> core, helpers (two packages depend on same shared library)

    let mut analyzer = CallGraphAnalyzer::new();

    // Analyze shared package
    let shared_code = r#"
def get_db_connection():
    """Get database connection"""
    return {"host": "localhost", "port": 5432}

def log_message(msg):
    """Log a message"""
    print(f"[LOG] {msg}")

def unused_shared_function():
    """This is never used by any package"""
    return "dead"

def get_config():
    """Get configuration"""
    return {"debug": True, "version": "1.0"}
"#;

    analyzer.analyze_source("shared", shared_code).expect("Failed to analyze shared");

    // Analyze core package
    let core_code = r#"
from shared import get_db_connection, log_message

def initialize_db():
    """Initialize database"""
    conn = get_db_connection()
    log_message(f"Connecting to {conn['host']}")
    return conn

def query_users():
    """Query users from database"""
    conn = initialize_db()
    log_message("Fetching users")
    return []

def unused_core_function():
    """Never called"""
    return "dead"

def test_query():
    """Test function - entry point"""
    return query_users()
"#;

    analyzer.analyze_source("core", core_code).expect("Failed to analyze core");

    // Analyze helpers package
    let helpers_code = r#"
from shared import log_message, get_config

def format_output(data):
    """Format output data"""
    log_message("Formatting output")
    config = get_config()
    return {"data": data, "debug": config["debug"]}

def validate_input(data):
    """Validate input data"""
    if not data:
        log_message("Invalid input")
        return False
    return True

def dead_helper():
    """Never used"""
    return "dead"

def test_format():
    """Test function - entry point"""
    return format_output({})

def test_validate():
    """Test function - entry point"""
    return validate_input("test")
"#;

    analyzer.analyze_source("helpers", helpers_code).expect("Failed to analyze helpers");

    // Register imports
    analyzer.add_import("core".to_string(), "get_db_connection".to_string(),
                       "shared".to_string(), "get_db_connection".to_string());
    analyzer.add_import("core".to_string(), "log_message".to_string(),
                       "shared".to_string(), "log_message".to_string());

    analyzer.add_import("helpers".to_string(), "log_message".to_string(),
                       "shared".to_string(), "log_message".to_string());
    analyzer.add_import("helpers".to_string(), "get_config".to_string(),
                       "shared".to_string(), "get_config".to_string());

    let dead_code = analyzer.find_dead_code();
    let dead_names: Vec<String> = dead_code.iter().map(|(_, name)| name.clone()).collect();

    // Verify dead code detection
    assert!(dead_names.contains(&"unused_shared_function".to_string()), "unused_shared_function should be dead");
    assert!(dead_names.contains(&"unused_core_function".to_string()), "unused_core_function should be dead");
    assert!(dead_names.contains(&"dead_helper".to_string()), "dead_helper should be dead");

    // Verify live functions
    assert!(!dead_names.contains(&"test_query".to_string()), "test_query should be live (entry point)");
    assert!(!dead_names.contains(&"test_format".to_string()), "test_format should be live (entry point)");
    assert!(!dead_names.contains(&"test_validate".to_string()), "test_validate should be live (entry point)");
    assert!(!dead_names.contains(&"query_users".to_string()), "query_users should be live (called from test_query)");
    assert!(!dead_names.contains(&"format_output".to_string()), "format_output should be live (called from test_format)");
    assert!(!dead_names.contains(&"validate_input".to_string()), "validate_input should be live (called from test_validate)");
}

#[test]
fn test_scenario_3_service_pattern() {
    // Scenario 3: Service pattern
    // service imports from shared

    let mut analyzer = CallGraphAnalyzer::new();

    // Analyze shared package
    let shared_code = r#"
def get_config():
    """Get configuration"""
    return {"debug": True, "version": "2.0"}

def log_message(msg):
    """Log a message"""
    print(f"[LOG] {msg}")

def unused_shared_function():
    """This is never used by any package"""
    return "dead"
"#;

    analyzer.analyze_source("shared", shared_code).expect("Failed to analyze shared");

    // Analyze service package
    let service_code = r#"
from shared import get_config, log_message

def initialize_service():
    """Initialize service"""
    config = get_config()
    log_message(f"Service initialized with version {config['version']}")
    return config

def start_service():
    """Start the service"""
    config = initialize_service()
    log_message("Service started")
    return True

def handle_request(request_data):
    """Handle incoming request"""
    log_message(f"Processing request: {request_data}")
    return {"status": "ok", "data": request_data}

def unused_service_function():
    """Never called"""
    return "dead"

def test_service():
    """Test function - entry point"""
    start_service()
    handle_request({"test": "data"})
"#;

    analyzer.analyze_source("service", service_code).expect("Failed to analyze service");

    // Register imports
    analyzer.add_import("service".to_string(), "get_config".to_string(),
                       "shared".to_string(), "get_config".to_string());
    analyzer.add_import("service".to_string(), "log_message".to_string(),
                       "shared".to_string(), "log_message".to_string());

    let dead_code = analyzer.find_dead_code();
    let dead_names: Vec<String> = dead_code.iter().map(|(_, name)| name.clone()).collect();

    // Verify dead code detection
    assert!(dead_names.contains(&"unused_shared_function".to_string()), "unused_shared_function should be dead");
    assert!(dead_names.contains(&"unused_service_function".to_string()), "unused_service_function should be dead");

    // Verify live functions
    assert!(!dead_names.contains(&"test_service".to_string()), "test_service should be live (entry point)");
    assert!(!dead_names.contains(&"start_service".to_string()), "start_service should be live (called from test_service)");
    assert!(!dead_names.contains(&"handle_request".to_string()), "handle_request should be live (called from test_service)");
    assert!(!dead_names.contains(&"initialize_service".to_string()), "initialize_service should be live (called from start_service)");
}

#[test]
fn test_imports_tracking_across_packages() {
    // Verify that imports are correctly tracked and resolved
    let mut analyzer = CallGraphAnalyzer::new();

    let package_a_code = r#"
def function_a():
    """Function in package A"""
    return "a"
"#;

    let package_b_code = r#"
from package_a import function_a as func_a_alias

def function_b():
    """Function in package B"""
    return func_a_alias()
"#;

    analyzer.analyze_source("package_a", package_a_code).expect("Failed to analyze package_a");
    analyzer.analyze_source("package_b", package_b_code).expect("Failed to analyze package_b");

    // Register import manually
    analyzer.add_import("package_b".to_string(), "func_a_alias".to_string(),
                       "package_a".to_string(), "function_a".to_string());

    // Verify import resolution
    let imports = analyzer.get_imports_for_package("package_b");
    assert_eq!(imports.len(), 1, "package_b should have 1 import");

    let (local_name, source_pkg, source_func) = &imports[0];
    assert_eq!(local_name, "func_a_alias", "local name should match");
    assert_eq!(source_pkg, "package_a", "source package should match");
    assert_eq!(source_func, "function_a", "source function should match");

    // Verify resolve_call works
    let resolved = analyzer.resolve_call("package_b", "func_a_alias");
    assert!(resolved.is_some(), "Should resolve func_a_alias to package_a function_a");
    let (pkg, func) = resolved.unwrap();
    assert_eq!(pkg, "package_a", "Should resolve to package_a");
    assert_eq!(func, "function_a", "Should resolve to function_a");
}

#[test]
fn test_deep_call_chains_across_packages() {
    // Scenario: Deep call chains: A → B → C → D
    // Tests that reachability is correctly computed through multiple packages

    let mut analyzer = CallGraphAnalyzer::new();

    let package_d_code = r#"
def base_operation():
    """Base operation"""
    return "result"

def unused_in_d():
    """Never called"""
    return "dead"
"#;

    let package_c_code = r#"
from d import base_operation

def transform(data):
    """Transform data"""
    return base_operation()

def unused_in_c():
    """Never called"""
    return "dead"
"#;

    let package_b_code = r#"
from c import transform

def process(data):
    """Process data"""
    return transform(data)

def unused_in_b():
    """Never called"""
    return "dead"
"#;

    let package_a_code = r#"
from b import process

def test_main():
    """Entry point"""
    return process("input")
"#;

    analyzer.analyze_source("d", package_d_code).expect("Failed to analyze d");
    analyzer.analyze_source("c", package_c_code).expect("Failed to analyze c");
    analyzer.analyze_source("b", package_b_code).expect("Failed to analyze b");
    analyzer.analyze_source("a", package_a_code).expect("Failed to analyze a");

    // Register imports
    analyzer.add_import("c".to_string(), "base_operation".to_string(),
                       "d".to_string(), "base_operation".to_string());
    analyzer.add_import("b".to_string(), "transform".to_string(),
                       "c".to_string(), "transform".to_string());
    analyzer.add_import("a".to_string(), "process".to_string(),
                       "b".to_string(), "process".to_string());

    let dead_code = analyzer.find_dead_code();
    let dead_names: Vec<String> = dead_code.iter().map(|(_, name)| name.clone()).collect();

    // Verify dead code detection
    assert!(dead_names.contains(&"unused_in_d".to_string()), "unused_in_d should be dead");
    assert!(dead_names.contains(&"unused_in_c".to_string()), "unused_in_c should be dead");
    assert!(dead_names.contains(&"unused_in_b".to_string()), "unused_in_b should be dead");

    // Verify live functions through call chain
    assert!(!dead_names.contains(&"test_main".to_string()), "test_main should be live (entry point)");
    assert!(!dead_names.contains(&"process".to_string()), "process should be live (called from test_main)");
    assert!(!dead_names.contains(&"transform".to_string()), "transform should be live (called from process)");
    assert!(!dead_names.contains(&"base_operation".to_string()), "base_operation should be live (called from transform)");
}

#[test]
fn test_multiple_imports_with_aliases() {
    // Scenario: Multiple imports from same module with different aliases

    let mut analyzer = CallGraphAnalyzer::new();

    let utils_code = r#"
def util_alpha():
    """Utility function A"""
    return "alpha"

def util_beta():
    """Utility function B"""
    return "beta"

def util_gamma():
    """Utility function C"""
    return "gamma"

def unused_util():
    """Never used"""
    return "dead"
"#;

    let app_code = r#"
from utils import util_alpha as alpha, util_beta as beta, util_gamma

def test_mixed():
    """Test function"""
    return alpha() + beta()

def test_gamma_unused():
    """Imported but not used"""
    pass
"#;

    analyzer.analyze_source("utils", utils_code).expect("Failed to analyze utils");
    analyzer.analyze_source("app", app_code).expect("Failed to analyze app");

    // Register imports with different aliases
    analyzer.add_import("app".to_string(), "alpha".to_string(),
                       "utils".to_string(), "util_alpha".to_string());
    analyzer.add_import("app".to_string(), "beta".to_string(),
                       "utils".to_string(), "util_beta".to_string());
    analyzer.add_import("app".to_string(), "util_gamma".to_string(),
                       "utils".to_string(), "util_gamma".to_string());

    let imports = analyzer.get_imports_for_package("app");
    assert_eq!(imports.len(), 3, "app should have 3 imports");

    let dead_code = analyzer.find_dead_code();
    let dead_names: Vec<String> = dead_code.iter().map(|(_, name)| name.clone()).collect();

    // util_alpha and util_beta used through aliases in test_mixed
    assert!(!dead_names.contains(&"util_alpha".to_string()), "util_alpha should be live (called from test_mixed)");
    assert!(!dead_names.contains(&"util_beta".to_string()), "util_beta should be live (called from test_mixed)");

    // test_mixed is an entry point, test_gamma_unused is also an entry point but does nothing
    assert!(!dead_names.contains(&"test_mixed".to_string()), "test_mixed should be live (entry point)");
    assert!(!dead_names.contains(&"test_gamma_unused".to_string()), "test_gamma_unused should be live (entry point)");

    // unused_util never imported
    assert!(dead_names.contains(&"unused_util".to_string()), "unused_util should be dead");

    // Note: util_gamma is imported but may not be marked as dead due to conservative approach
    // This is acceptable - imported functions are treated conservatively
}

#[test]
fn test_diamond_dependency_pattern() {
    // Scenario: Diamond dependency - common library shared by two packages
    //
    //     app
    //    /   \
    //   b1   b2
    //    \   /
    //    common

    let mut analyzer = CallGraphAnalyzer::new();

    let common_code = r#"
def shared_utility():
    """Shared utility used by both b1 and b2"""
    return "shared"

def unused_common():
    """Never called"""
    return "dead"
"#;

    let b1_code = r#"
from common import shared_utility

def b1_function():
    """Function in b1"""
    return shared_utility()

def unused_b1():
    """Never called"""
    return "dead"
"#;

    let b2_code = r#"
from common import shared_utility

def b2_function():
    """Function in b2"""
    return shared_utility()

def unused_b2():
    """Never called"""
    return "dead"
"#;

    let app_code = r#"
from b1 import b1_function
from b2 import b2_function

def test_diamond():
    """Entry point"""
    b1_function()
    b2_function()
"#;

    analyzer.analyze_source("common", common_code).expect("Failed to analyze common");
    analyzer.analyze_source("b1", b1_code).expect("Failed to analyze b1");
    analyzer.analyze_source("b2", b2_code).expect("Failed to analyze b2");
    analyzer.analyze_source("app", app_code).expect("Failed to analyze app");

    // Register imports
    analyzer.add_import("b1".to_string(), "shared_utility".to_string(),
                       "common".to_string(), "shared_utility".to_string());
    analyzer.add_import("b2".to_string(), "shared_utility".to_string(),
                       "common".to_string(), "shared_utility".to_string());
    analyzer.add_import("app".to_string(), "b1_function".to_string(),
                       "b1".to_string(), "b1_function".to_string());
    analyzer.add_import("app".to_string(), "b2_function".to_string(),
                       "b2".to_string(), "b2_function".to_string());

    let dead_code = analyzer.find_dead_code();
    let dead_names: Vec<String> = dead_code.iter().map(|(_, name)| name.clone()).collect();

    // Verify dead code
    assert!(dead_names.contains(&"unused_common".to_string()), "unused_common should be dead");
    assert!(dead_names.contains(&"unused_b1".to_string()), "unused_b1 should be dead");
    assert!(dead_names.contains(&"unused_b2".to_string()), "unused_b2 should be dead");

    // Verify live functions
    assert!(!dead_names.contains(&"test_diamond".to_string()), "test_diamond should be live (entry point)");
    assert!(!dead_names.contains(&"b1_function".to_string()), "b1_function should be live (called from app)");
    assert!(!dead_names.contains(&"b2_function".to_string()), "b2_function should be live (called from app)");
    assert!(!dead_names.contains(&"shared_utility".to_string()), "shared_utility should be live (called from b1 and b2)");
}

#[test]
fn test_exported_functions_with_exports() {
    // Scenario: Test that exported functions are protected from being marked dead
    // even if they're not called internally

    let mut analyzer = CallGraphAnalyzer::new();

    let library_code = r#"
__all__ = ['public_api', 'exported_helper']

def public_api():
    """Public API function"""
    return "public"

def exported_helper():
    """Exported but not used internally"""
    return "helper"

def internal_only():
    """Internal function"""
    return "internal"

def unused_function():
    """Not exported and not used"""
    return "dead"

def test_library():
    """Test function"""
    return internal_only()
"#;

    analyzer.analyze_source("library", library_code).expect("Failed to analyze library");

    let dead_code = analyzer.find_dead_code();
    let dead_names: Vec<String> = dead_code.iter().map(|(_, name)| name.clone()).collect();

    // Verify export protection
    assert!(!dead_names.contains(&"public_api".to_string()), "public_api should be protected (in __all__)");
    assert!(!dead_names.contains(&"exported_helper".to_string()), "exported_helper should be protected (in __all__)");

    // Verify dead code detection for non-exported
    assert!(dead_names.contains(&"unused_function".to_string()), "unused_function should be dead");
    // test_library is an entry point, internal_only is called from it
    assert!(!dead_names.contains(&"internal_only".to_string()), "internal_only should be live (called from test_library)");
}

#[test]
fn test_multiple_test_entry_points() {
    // Scenario: Package with multiple test functions as entry points
    // Each tests a different code path

    let mut analyzer = CallGraphAnalyzer::new();

    let code = r#"
def setup():
    """Setup function"""
    return {}

def feature_a():
    """Feature A"""
    return "a"

def feature_b():
    """Feature B"""
    return "b"

def shared_helper():
    """Used by both features"""
    return "shared"

def unused_feature():
    """Never used"""
    return "dead"

def test_feature_a():
    """Test entry point A"""
    setup()
    shared_helper()
    return feature_a()

def test_feature_b():
    """Test entry point B"""
    setup()
    shared_helper()
    return feature_b()

def test_unused():
    """Another test entry point"""
    pass
"#;

    analyzer.analyze_source("module", code).expect("Failed to analyze module");

    let dead_code = analyzer.find_dead_code();
    let dead_names: Vec<String> = dead_code.iter().map(|(_, name)| name.clone()).collect();

    // Entry points
    assert!(!dead_names.contains(&"test_feature_a".to_string()), "test_feature_a should be live (entry point)");
    assert!(!dead_names.contains(&"test_feature_b".to_string()), "test_feature_b should be live (entry point)");
    assert!(!dead_names.contains(&"test_unused".to_string()), "test_unused should be live (entry point)");

    // Called from entry points
    assert!(!dead_names.contains(&"setup".to_string()), "setup should be live (called from test_feature_a and test_feature_b)");
    assert!(!dead_names.contains(&"shared_helper".to_string()), "shared_helper should be live");
    assert!(!dead_names.contains(&"feature_a".to_string()), "feature_a should be live (called from test_feature_a)");
    assert!(!dead_names.contains(&"feature_b".to_string()), "feature_b should be live (called from test_feature_b)");

    // Dead code
    assert!(dead_names.contains(&"unused_feature".to_string()), "unused_feature should be dead");
}

#[test]
fn test_large_dependency_graph() {
    // Scenario: Larger graph with multiple packages and complex interdependencies
    // Tests scalability of the dead code detection

    let mut analyzer = CallGraphAnalyzer::new();

    // Package: core - provides foundational operations
    let core_code = r#"
def parse_input(data):
    return {"parsed": data}

def format_output(result):
    return str(result)

def unused_core_fn():
    return "dead"
"#;

    // Package: processing - depends on core
    let processing_code = r#"
from core import parse_input, format_output

def preprocess(data):
    parsed = parse_input(data)
    return processed

def unused_processing_fn():
    return "dead"

def test_processing():
    return preprocess("test")
"#;

    // Package: output - depends on core
    let output_code = r#"
from core import format_output

def render(data):
    return format_output(data)

def unused_output_fn():
    return "dead"

def test_output():
    return render("test")
"#;

    // Package: orchestrator - depends on processing and output
    let orchestrator_code = r#"
from processing import preprocess
from output import render

def pipeline(input_data):
    processed = preprocess(input_data)
    result = render(processed)
    return result

def unused_orchestrator_fn():
    return "dead"

def test_pipeline():
    return pipeline("data")
"#;

    analyzer.analyze_source("core", core_code).expect("Failed to analyze core");
    analyzer.analyze_source("processing", processing_code).expect("Failed to analyze processing");
    analyzer.analyze_source("output", output_code).expect("Failed to analyze output");
    analyzer.analyze_source("orchestrator", orchestrator_code).expect("Failed to analyze orchestrator");

    // Register imports
    analyzer.add_import("processing".to_string(), "parse_input".to_string(),
                       "core".to_string(), "parse_input".to_string());
    analyzer.add_import("processing".to_string(), "format_output".to_string(),
                       "core".to_string(), "format_output".to_string());
    analyzer.add_import("output".to_string(), "format_output".to_string(),
                       "core".to_string(), "format_output".to_string());
    analyzer.add_import("orchestrator".to_string(), "preprocess".to_string(),
                       "processing".to_string(), "preprocess".to_string());
    analyzer.add_import("orchestrator".to_string(), "render".to_string(),
                       "output".to_string(), "render".to_string());

    let dead_code = analyzer.find_dead_code();
    let dead_names: Vec<String> = dead_code.iter().map(|(_, name)| name.clone()).collect();

    // Verify all dead functions detected
    assert!(dead_names.contains(&"unused_core_fn".to_string()), "unused_core_fn should be dead");
    assert!(dead_names.contains(&"unused_processing_fn".to_string()), "unused_processing_fn should be dead");
    assert!(dead_names.contains(&"unused_output_fn".to_string()), "unused_output_fn should be dead");
    assert!(dead_names.contains(&"unused_orchestrator_fn".to_string()), "unused_orchestrator_fn should be dead");

    // Verify key functions are live
    assert!(!dead_names.contains(&"pipeline".to_string()), "pipeline should be live");
    assert!(!dead_names.contains(&"preprocess".to_string()), "preprocess should be live");
    assert!(!dead_names.contains(&"render".to_string()), "render should be live");
}

#[test]
fn test_numpy_like_package_structure() {
    // Scenario: NumPy-like package with core, linalg, and polynomial modules
    // Simulates realistic scientific computing library structure

    let mut analyzer = CallGraphAnalyzer::new();

    // Core array operations
    let core_code = r#"
def create_array(shape):
    """Create array"""
    return {"shape": shape, "data": []}

def reshape_array(arr, shape):
    """Reshape array"""
    return {"shape": shape, "data": arr["data"]}

def sum_array(arr):
    """Sum array elements"""
    return 0

def unused_core_helper():
    """Never used"""
    return "dead"

def test_core():
    """Test entry point"""
    arr = create_array((2, 3))
    return reshape_array(arr, (3, 2))
"#;

    // Linear algebra module
    let linalg_code = r#"
from core import create_array, reshape_array

def dot_product(a, b):
    """Compute dot product"""
    arr1 = create_array((3,))
    arr2 = create_array((3,))
    return 0

def matrix_inverse(m):
    """Compute matrix inverse"""
    reshape_array(m, (3, 3))
    return m

def unused_linalg_fn():
    """Dead code"""
    return "dead"

def test_linalg():
    """Test entry point"""
    return dot_product(None, None)
"#;

    // Polynomial module
    let poly_code = r#"
from core import create_array

def polynomial_fit(x, y, degree):
    """Fit polynomial"""
    create_array((degree + 1,))
    return []

def polynomial_eval(p, x):
    """Evaluate polynomial"""
    return 0

def unused_poly_fn():
    """Dead code"""
    return "dead"

def test_poly():
    """Test entry point"""
    return polynomial_fit([1, 2, 3], [1, 4, 9], 2)
"#;

    analyzer.analyze_source("core", core_code).expect("Failed to analyze core");
    analyzer.analyze_source("linalg", linalg_code).expect("Failed to analyze linalg");
    analyzer.analyze_source("poly", poly_code).expect("Failed to analyze poly");

    // Register imports
    analyzer.add_import("linalg".to_string(), "create_array".to_string(),
                       "core".to_string(), "create_array".to_string());
    analyzer.add_import("linalg".to_string(), "reshape_array".to_string(),
                       "core".to_string(), "reshape_array".to_string());
    analyzer.add_import("poly".to_string(), "create_array".to_string(),
                       "core".to_string(), "create_array".to_string());

    let dead_code = analyzer.find_dead_code();
    let dead_names: Vec<String> = dead_code.iter().map(|(_, name)| name.clone()).collect();

    // Verify dead functions
    assert!(dead_names.contains(&"unused_core_helper".to_string()), "unused_core_helper should be dead");
    assert!(dead_names.contains(&"unused_linalg_fn".to_string()), "unused_linalg_fn should be dead");
    assert!(dead_names.contains(&"unused_poly_fn".to_string()), "unused_poly_fn should be dead");
    // sum_array is defined but never called
    assert!(dead_names.contains(&"sum_array".to_string()), "sum_array should be dead (unused)");
    assert!(dead_names.contains(&"matrix_inverse".to_string()), "matrix_inverse should be dead (unused)");
    assert!(dead_names.contains(&"polynomial_eval".to_string()), "polynomial_eval should be dead (unused)");

    // Verify live functions
    assert!(!dead_names.contains(&"test_core".to_string()), "test_core should be live (entry point)");
    assert!(!dead_names.contains(&"test_linalg".to_string()), "test_linalg should be live (entry point)");
    assert!(!dead_names.contains(&"test_poly".to_string()), "test_poly should be live (entry point)");
    assert!(!dead_names.contains(&"create_array".to_string()), "create_array should be live (called from linalg and poly)");
    assert!(!dead_names.contains(&"reshape_array".to_string()), "reshape_array should be live (called from linalg)");
    assert!(!dead_names.contains(&"dot_product".to_string()), "dot_product should be live (called from test_linalg)");
    assert!(!dead_names.contains(&"polynomial_fit".to_string()), "polynomial_fit should be live (called from test_poly)");
}

#[test]
fn test_requests_like_http_library() {
    // Scenario: Requests-like library with models, adapters, and utilities
    // Simulates realistic HTTP client library

    let mut analyzer = CallGraphAnalyzer::new();

    // Models for requests/responses
    let models_code = r#"
def prepare_request(method, url, headers):
    """Prepare HTTP request"""
    return {"method": method, "url": url, "headers": headers}

def parse_response(status, body):
    """Parse HTTP response"""
    return {"status": status, "body": body}

def validate_url(url):
    """Validate URL format"""
    return True

def unused_model_fn():
    """Never used"""
    return "dead"

def test_models():
    """Test entry point"""
    return prepare_request("GET", "http://example.com", {})
"#;

    // HTTP adapter
    let adapters_code = r#"
from models import prepare_request, parse_response, validate_url

def send_http_request(req):
    """Send HTTP request"""
    validate_url(req["url"])
    return parse_response(200, "")

def retry_request(req, times):
    """Retry failed request"""
    for i in range(times):
        send_http_request(req)
    return None

def unused_adapter_fn():
    """Never used"""
    return "dead"

def test_adapters():
    """Test entry point"""
    req = prepare_request("GET", "http://example.com", {})
    return send_http_request(req)
"#;

    // Main request function
    let session_code = r#"
from models import prepare_request
from adapters import send_http_request, retry_request

def get(url, headers=None):
    """HTTP GET request"""
    req = prepare_request("GET", url, headers or {})
    return send_http_request(req)

def post(url, data):
    """HTTP POST request"""
    req = prepare_request("POST", url, {})
    return send_http_request(req)

def unused_session_fn():
    """Never used"""
    return "dead"

def test_session():
    """Test entry point"""
    return get("http://example.com", {"User-Agent": "test"})
"#;

    analyzer.analyze_source("models", models_code).expect("Failed to analyze models");
    analyzer.analyze_source("adapters", adapters_code).expect("Failed to analyze adapters");
    analyzer.analyze_source("session", session_code).expect("Failed to analyze session");

    // Register imports
    analyzer.add_import("adapters".to_string(), "prepare_request".to_string(),
                       "models".to_string(), "prepare_request".to_string());
    analyzer.add_import("adapters".to_string(), "parse_response".to_string(),
                       "models".to_string(), "parse_response".to_string());
    analyzer.add_import("adapters".to_string(), "validate_url".to_string(),
                       "models".to_string(), "validate_url".to_string());
    analyzer.add_import("session".to_string(), "prepare_request".to_string(),
                       "models".to_string(), "prepare_request".to_string());
    analyzer.add_import("session".to_string(), "send_http_request".to_string(),
                       "adapters".to_string(), "send_http_request".to_string());
    analyzer.add_import("session".to_string(), "retry_request".to_string(),
                       "adapters".to_string(), "retry_request".to_string());

    let dead_code = analyzer.find_dead_code();
    let dead_names: Vec<String> = dead_code.iter().map(|(_, name)| name.clone()).collect();

    // Verify dead functions
    assert!(dead_names.contains(&"unused_model_fn".to_string()), "unused_model_fn should be dead");
    assert!(dead_names.contains(&"unused_adapter_fn".to_string()), "unused_adapter_fn should be dead");
    assert!(dead_names.contains(&"unused_session_fn".to_string()), "unused_session_fn should be dead");
    assert!(dead_names.contains(&"post".to_string()), "post should be dead (not called from test)");

    // Note: retry_request and parse_response are imported but may be marked as live due to conservative approach

    // Verify live functions
    assert!(!dead_names.contains(&"test_models".to_string()), "test_models should be live (entry point)");
    assert!(!dead_names.contains(&"test_adapters".to_string()), "test_adapters should be live (entry point)");
    assert!(!dead_names.contains(&"test_session".to_string()), "test_session should be live (entry point)");
    assert!(!dead_names.contains(&"prepare_request".to_string()), "prepare_request should be live (used by all)");
    assert!(!dead_names.contains(&"send_http_request".to_string()), "send_http_request should be live");
    assert!(!dead_names.contains(&"get".to_string()), "get should be live (called from test_session)");
}

#[test]
fn test_flask_like_web_framework() {
    // Scenario: Flask-like web framework with app, routing, and middleware
    // Simulates realistic web framework structure

    let mut analyzer = CallGraphAnalyzer::new();

    // Routing module
    let routing_code = r#"
def route(path, methods=None):
    """Route decorator"""
    return {}

def url_for(endpoint, **kwargs):
    """Generate URL"""
    return f"/path/{endpoint}"

def redirect(url):
    """Redirect response"""
    return {"redirect": url}

def unused_routing_fn():
    """Never used"""
    return "dead"

def test_routing():
    """Test entry point"""
    return route("/index", ["GET"])
"#;

    // Middleware module
    let middleware_code = r#"
def before_request():
    """Before request hook"""
    return {}

def after_request(response):
    """After request hook"""
    return response

def error_handler(error):
    """Handle errors"""
    return {"error": str(error)}

def unused_middleware_fn():
    """Never used"""
    return "dead"

def test_middleware():
    """Test entry point"""
    return before_request()
"#;

    // Application core
    let app_code = r#"
from routing import route, url_for
from middleware import before_request, after_request

def create_app():
    """Create Flask app"""
    app = {}
    route("/", ["GET"])
    return app

def run_app(app, host="localhost"):
    """Run Flask app"""
    before_request()
    return "Running"

def register_blueprint(app, blueprint):
    """Register blueprint"""
    return app

def unused_app_fn():
    """Never used"""
    return "dead"

def test_app():
    """Test entry point"""
    app = create_app()
    return run_app(app)
"#;

    analyzer.analyze_source("routing", routing_code).expect("Failed to analyze routing");
    analyzer.analyze_source("middleware", middleware_code).expect("Failed to analyze middleware");
    analyzer.analyze_source("app", app_code).expect("Failed to analyze app");

    // Register imports
    analyzer.add_import("app".to_string(), "route".to_string(),
                       "routing".to_string(), "route".to_string());
    analyzer.add_import("app".to_string(), "url_for".to_string(),
                       "routing".to_string(), "url_for".to_string());
    analyzer.add_import("app".to_string(), "before_request".to_string(),
                       "middleware".to_string(), "before_request".to_string());
    analyzer.add_import("app".to_string(), "after_request".to_string(),
                       "middleware".to_string(), "after_request".to_string());

    let dead_code = analyzer.find_dead_code();
    let dead_names: Vec<String> = dead_code.iter().map(|(_, name)| name.clone()).collect();

    // Verify dead functions
    assert!(dead_names.contains(&"unused_routing_fn".to_string()), "unused_routing_fn should be dead");
    assert!(dead_names.contains(&"unused_middleware_fn".to_string()), "unused_middleware_fn should be dead");
    assert!(dead_names.contains(&"unused_app_fn".to_string()), "unused_app_fn should be dead");
    assert!(dead_names.contains(&"redirect".to_string()), "redirect should be dead (not called)");
    assert!(dead_names.contains(&"error_handler".to_string()), "error_handler should be dead (not called)");
    assert!(dead_names.contains(&"register_blueprint".to_string()), "register_blueprint should be dead (not called)");

    // Note: url_for and after_request are imported but may be marked as live due to conservative approach

    // Verify live functions
    assert!(!dead_names.contains(&"test_routing".to_string()), "test_routing should be live (entry point)");
    assert!(!dead_names.contains(&"test_middleware".to_string()), "test_middleware should be live (entry point)");
    assert!(!dead_names.contains(&"test_app".to_string()), "test_app should be live (entry point)");
    assert!(!dead_names.contains(&"create_app".to_string()), "create_app should be live (called from test_app)");
    assert!(!dead_names.contains(&"run_app".to_string()), "run_app should be live (called from test_app)");
    assert!(!dead_names.contains(&"route".to_string()), "route should be live (called from create_app)");
    assert!(!dead_names.contains(&"before_request".to_string()), "before_request should be live");
}
