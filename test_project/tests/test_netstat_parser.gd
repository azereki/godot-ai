@tool
extends McpTestSuite

const SAMPLE := """
  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:8000           0.0.0.0:0              LISTENING       57865
  TCP    127.0.0.1:49701        127.0.0.1:8000         ESTABLISHED     12345
  TCP    [::]:80                [::]:0                 LISTENING       980
"""


func suite_name() -> String:
	return "netstat_parser"


func test_returns_only_listeners_on_the_exact_local_port() -> void:
	assert_eq(McpPortResolver.parse_windows_netstat_pid(SAMPLE, 8000), 57865)
	assert_eq(McpPortResolver.parse_windows_netstat_pid(SAMPLE, 9999), 0)
	assert_eq(McpPortResolver.parse_windows_netstat_pid("", 8000), 0)


func test_returns_every_unique_listener() -> void:
	var sample := (
		"TCP 127.0.0.1:8001 0.0.0.0:0 LISTENING 36936\n"
		+ "TCP 127.0.0.1:8001 0.0.0.0:0 LISTENING 46396\n"
		+ "TCP 127.0.0.1:8001 0.0.0.0:0 LISTENING 46396\n"
	)
	assert_eq(McpPortResolver.parse_windows_netstat_pids(sample, 8001), [36936, 46396])


func test_ignores_remote_port_substrings_and_non_listeners() -> void:
	var sample := (
		"TCP 127.0.0.1:7070 127.0.0.1:8000 ESTABLISHED 1\n"
		+ "TCP 0.0.0.0:80001 0.0.0.0:0 LISTENING 2\n"
		+ "TCP 0.0.0.0:8000 0.0.0.0:0 LISTENING 3\n"
	)
	assert_eq(McpPortResolver.parse_windows_netstat_pid(sample, 8000), 3)


func test_ipv6_and_localized_listener_state_use_wildcard_foreign_address() -> void:
	var sample := (
		"TCP [::]:8000 [::]:0 ÉCOUTE 777\n"
		+ "TCP 0.0.0.0:8000 0.0.0.0:0 ABHÖREN 888\n"
	)
	assert_eq(McpPortResolver.parse_windows_netstat_pids(sample, 8000), [777, 888])


func test_whitespace_and_pid_line_parsers_are_strict() -> void:
	assert_eq(
		McpPortResolver.split_on_whitespace("TCP\t  0.0.0.0:8000  LISTENING"),
		PackedStringArray(["TCP", "0.0.0.0:8000", "LISTENING"]),
	)
	assert_eq(
		McpPortResolver.parse_pid_lines("19088\nnoise\n19088\n40064\n"),
		[19088, 40064],
	)


func test_powershell_result_requires_successful_nonempty_pid_output() -> void:
	assert_eq(
		McpPortResolver.windows_listener_pids_from_execute_result(
			0, ["19088\r\n40064\r\n19088\r\n"]
		),
		[19088, 40064],
	)
	assert_false(McpPortResolver.windows_listener_execute_result_in_use(0, [""]))
	assert_false(McpPortResolver.windows_listener_execute_result_in_use(1, ["19088"]))
