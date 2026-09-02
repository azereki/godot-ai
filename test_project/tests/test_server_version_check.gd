@tool
extends McpTestSuite


func suite_name() -> String:
	return "server_version_check"


func test_exact_v4_version_is_compatible() -> void:
	var result := McpServerVersionCheck.evaluate("4.0.0", "4.0.0")
	assert_true(result.compatible)
	assert_eq(result.reason, "")


func test_missing_or_different_version_fails_closed() -> void:
	assert_eq(McpServerVersionCheck.evaluate("", "4.0.0").reason, "missing_version")
	assert_eq(
		McpServerVersionCheck.evaluate("3.9.0", "4.0.0").reason,
		"version_mismatch",
	)
