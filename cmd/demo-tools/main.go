// Package main implements MCP tool servers for the MITRITY governance demo.
// It supports three modes via --mode flag: fs, shell, api.
// Each mode exposes different tools over the MCP stdio protocol (JSON-RPC 2.0).
package main

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

type request struct {
	JSONRPC string          `json:"jsonrpc"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params,omitempty"`
	ID      json.RawMessage `json:"id"`
}

type response struct {
	JSONRPC string      `json:"jsonrpc"`
	Result  interface{} `json:"result"`
	ID      json.RawMessage `json:"id"`
}

type errorResponse struct {
	JSONRPC string      `json:"jsonrpc"`
	Error   interface{} `json:"error"`
	ID      json.RawMessage `json:"id"`
}

type tool struct {
	Name        string      `json:"name"`
	Description string      `json:"description"`
	InputSchema interface{} `json:"inputSchema"`
}

var (
	mode      string
	workspace string
)

func main() {
	flag.StringVar(&mode, "mode", "fs", "Tool mode: fs, shell, api")
	flag.StringVar(&workspace, "workspace", "/workspace", "Workspace root for fs mode")
	flag.Parse()

	scanner := bufio.NewScanner(os.Stdin)
	buf := make([]byte, 64*1024)
	scanner.Buffer(buf, 4*1024*1024)

	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}

		var req request
		if err := json.Unmarshal(line, &req); err != nil {
			writeJSON(os.Stdout, errorResponse{
				JSONRPC: "2.0",
				Error:   map[string]any{"code": -32700, "message": "Parse error"},
				ID:      nil,
			})
			continue
		}

		resp := handleRequest(&req)
		writeJSON(os.Stdout, resp)
	}
}

func handleRequest(req *request) interface{} {
	switch req.Method {
	case "initialize":
		return response{
			JSONRPC: "2.0",
			ID:      req.ID,
			Result: map[string]any{
				"protocolVersion": "2024-11-05",
				"capabilities":   map[string]any{"tools": map[string]any{"listChanged": false}},
				"serverInfo":     map[string]any{"name": "demo-tools-" + mode, "version": "1.0.0"},
			},
		}

	case "notifications/initialized":
		// No response needed for notifications.
		return nil

	case "tools/list":
		return response{
			JSONRPC: "2.0",
			ID:      req.ID,
			Result:  map[string]any{"tools": getTools()},
		}

	case "tools/call":
		return handleToolCall(req)

	default:
		return response{
			JSONRPC: "2.0",
			ID:      req.ID,
			Result:  map[string]any{"status": "ok"},
		}
	}
}

func getTools() []tool {
	switch mode {
	case "fs":
		return []tool{
			{
				Name:        "read_file",
				Description: "Read the contents of a file",
				InputSchema: map[string]any{
					"type": "object",
					"properties": map[string]any{
						"path": map[string]any{"type": "string", "description": "File path to read"},
					},
					"required": []string{"path"},
				},
			},
			{
				Name:        "write_file",
				Description: "Write content to a file",
				InputSchema: map[string]any{
					"type": "object",
					"properties": map[string]any{
						"path":    map[string]any{"type": "string", "description": "File path to write"},
						"content": map[string]any{"type": "string", "description": "Content to write"},
					},
					"required": []string{"path", "content"},
				},
			},
			{
				Name:        "list_directory",
				Description: "List contents of a directory",
				InputSchema: map[string]any{
					"type": "object",
					"properties": map[string]any{
						"path": map[string]any{"type": "string", "description": "Directory path to list"},
					},
					"required": []string{"path"},
				},
			},
			{
				Name:        "delete_file",
				Description: "Delete a file",
				InputSchema: map[string]any{
					"type": "object",
					"properties": map[string]any{
						"path": map[string]any{"type": "string", "description": "File path to delete"},
					},
					"required": []string{"path"},
				},
			},
		}

	case "shell":
		return []tool{
			{
				Name:        "run_command",
				Description: "Execute a shell command and return its output",
				InputSchema: map[string]any{
					"type": "object",
					"properties": map[string]any{
						"command": map[string]any{"type": "string", "description": "Shell command to execute"},
					},
					"required": []string{"command"},
				},
			},
		}

	case "api":
		return []tool{
			{
				Name:        "call_api",
				Description: "Make an HTTP API request",
				InputSchema: map[string]any{
					"type": "object",
					"properties": map[string]any{
						"url":    map[string]any{"type": "string", "description": "API endpoint URL"},
						"method": map[string]any{"type": "string", "description": "HTTP method (GET, POST, etc.)"},
						"body":   map[string]any{"type": "string", "description": "Request body (optional)"},
					},
					"required": []string{"url", "method"},
				},
			},
			{
				Name:        "query_database",
				Description: "Execute a SQL query against the application database",
				InputSchema: map[string]any{
					"type": "object",
					"properties": map[string]any{
						"query": map[string]any{"type": "string", "description": "SQL query to execute"},
					},
					"required": []string{"query"},
				},
			},
			{
				Name:        "send_notification",
				Description: "Send a notification message to a channel",
				InputSchema: map[string]any{
					"type": "object",
					"properties": map[string]any{
						"channel": map[string]any{"type": "string", "description": "Notification channel (e.g., #ops, #alerts)"},
						"message": map[string]any{"type": "string", "description": "Notification message text"},
					},
					"required": []string{"channel", "message"},
				},
			},
			// connect_database — Phase 6 (credential broker demo).
			//
			// The connection_string arg is expected to carry a
			// ${credential:demo_db_password} placeholder that the
			// MITRITY gateway substitutes BEFORE this tool runs. If
			// we see a raw placeholder reach the tool, injection
			// mis-wired and we fail loudly; otherwise we redact the
			// password and return a short hash so the demo can prove
			// substitution AND prove rotation produced a new value.
			{
				Name:        "connect_database",
				Description: "Open a database connection with the given connection string. Demonstrates MITRITY credential broker substitution of ${credential:demo_db_password} placeholders.",
				InputSchema: map[string]any{
					"type": "object",
					"properties": map[string]any{
						"connection_string": map[string]any{
							"type":        "string",
							"description": "Database URL (e.g., postgres://user:${credential:demo_db_password}@host:5432/db)",
						},
					},
					"required": []string{"connection_string"},
				},
			},
		}

	}
	return nil
}

func handleToolCall(req *request) interface{} {
	var params struct {
		Name      string         `json:"name"`
		Arguments map[string]any `json:"arguments"`
	}
	if req.Params != nil {
		_ = json.Unmarshal(req.Params, &params)
	}

	var result string
	var err error

	switch mode {
	case "fs":
		result, err = handleFSTool(params.Name, params.Arguments)
	case "shell":
		result, err = handleShellTool(params.Name, params.Arguments)
	case "api":
		result, err = handleAPITool(params.Name, params.Arguments)
	default:
		err = fmt.Errorf("unknown mode: %s", mode)
	}

	if err != nil {
		return errorResponse{
			JSONRPC: "2.0",
			Error: map[string]any{
				"code":    -32000,
				"message": err.Error(),
			},
			ID: req.ID,
		}
	}

	return response{
		JSONRPC: "2.0",
		ID:      req.ID,
		Result: map[string]any{
			"content": []map[string]any{
				{"type": "text", "text": result},
			},
		},
	}
}

// --- Filesystem tools ---

func handleFSTool(name string, args map[string]any) (string, error) {
	path, _ := args["path"].(string)
	if path == "" {
		return "", fmt.Errorf("path is required")
	}

	// Resolve to absolute path. If not absolute, treat as relative to workspace.
	if !filepath.IsAbs(path) {
		path = filepath.Join(workspace, path)
	}
	path = filepath.Clean(path)

	switch name {
	case "read_file":
		data, err := os.ReadFile(path)
		if err != nil {
			return "", fmt.Errorf("failed to read %s: %w", path, err)
		}
		return string(data), nil

	case "write_file":
		content, _ := args["content"].(string)
		dir := filepath.Dir(path)
		if err := os.MkdirAll(dir, 0755); err != nil {
			return "", fmt.Errorf("failed to create directory %s: %w", dir, err)
		}
		if err := os.WriteFile(path, []byte(content), 0644); err != nil {
			return "", fmt.Errorf("failed to write %s: %w", path, err)
		}
		return fmt.Sprintf("Written %d bytes to %s", len(content), path), nil

	case "list_directory":
		entries, err := os.ReadDir(path)
		if err != nil {
			return "", fmt.Errorf("failed to list %s: %w", path, err)
		}
		var lines []string
		for _, e := range entries {
			info, _ := e.Info()
			typeStr := "file"
			size := int64(0)
			if e.IsDir() {
				typeStr = "dir"
			} else if info != nil {
				size = info.Size()
			}
			lines = append(lines, fmt.Sprintf("%s\t%s\t%d bytes", e.Name(), typeStr, size))
		}
		if len(lines) == 0 {
			return "(empty directory)", nil
		}
		return strings.Join(lines, "\n"), nil

	case "delete_file":
		if err := os.Remove(path); err != nil {
			return "", fmt.Errorf("failed to delete %s: %w", path, err)
		}
		return fmt.Sprintf("Deleted %s", path), nil

	default:
		return "", fmt.Errorf("unknown fs tool: %s", name)
	}
}

// --- Shell tools ---

func handleShellTool(name string, args map[string]any) (string, error) {
	if name != "run_command" {
		return "", fmt.Errorf("unknown shell tool: %s", name)
	}

	command, _ := args["command"].(string)
	if command == "" {
		return "", fmt.Errorf("command is required")
	}

	cmd := exec.Command("sh", "-c", command)
	cmd.Dir = workspace
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Sprintf("Command failed: %s\nOutput: %s", err, string(output)), nil
	}
	return string(output), nil
}

// --- API tools (mock responses) ---

func handleAPITool(name string, args map[string]any) (string, error) {
	switch name {
	case "call_api":
		url, _ := args["url"].(string)
		method, _ := args["method"].(string)

		if strings.Contains(url, "production") {
			return fmt.Sprintf("[MOCK] %s %s\nResponse: {\"status\": \"deploying\", \"environment\": \"production\", \"version\": \"v1.2.0\"}", method, url), nil
		}
		return fmt.Sprintf("[MOCK] %s %s\nResponse: {\"status\": \"ok\", \"data\": {\"items\": 42, \"last_updated\": \"2026-03-15T10:00:00Z\"}}", method, url), nil

	case "query_database":
		query, _ := args["query"].(string)

		upperQuery := strings.ToUpper(query)
		if strings.Contains(upperQuery, "SELECT") {
			return fmt.Sprintf("[MOCK] Executed: %s\nResult: [{\"id\": 1, \"name\": \"Alice\", \"role\": \"admin\"}, {\"id\": 2, \"name\": \"Bob\", \"role\": \"editor\"}]", query), nil
		}
		return fmt.Sprintf("[MOCK] Executed: %s\nRows affected: 1", query), nil

	case "send_notification":
		channel, _ := args["channel"].(string)
		message, _ := args["message"].(string)
		return fmt.Sprintf("[MOCK] Notification sent to %s: \"%s\"", channel, message), nil

	case "connect_database":
		return handleConnectDatabase(args)

	default:
		return "", fmt.Errorf("unknown api tool: %s", name)
	}
}

// handleConnectDatabase is Phase 6's mock target. The MITRITY gateway
// is expected to substitute any ${credential:demo_db_password}
// placeholder in connection_string before this function runs. If a
// raw placeholder reaches us, injection is mis-wired and we fail
// loudly. On success we redact the password and return a short hash
// of it so the demo can prove that:
//
//  1. Substitution happened (no placeholder visible in output).
//  2. The value actually flowed through (hash != hash of placeholder).
//  3. Rotation works (hash changes between runs after rotating in
//     the dashboard).
func handleConnectDatabase(args map[string]any) (string, error) {
	conn, _ := args["connection_string"].(string)
	if conn == "" {
		return "", fmt.Errorf("connection_string is required")
	}
	if strings.Contains(conn, "${credential:") {
		return "", fmt.Errorf("connection_string still contains an unresolved credential placeholder — gateway credential injection appears mis-wired (credentials.injection_enabled? grant configured?)")
	}
	u, err := url.Parse(conn)
	if err != nil {
		return "", fmt.Errorf("parse connection_string: %w", err)
	}
	password, _ := u.User.Password()
	if password == "" {
		return "", fmt.Errorf("connection_string has no password component to verify substitution")
	}
	sum := sha256.Sum256([]byte(password))
	hash := hex.EncodeToString(sum[:])[:12]
	redacted := strings.Replace(conn, ":"+password+"@", ":***@", 1)
	return fmt.Sprintf(
		"[MOCK] Connected to %s\n  → password hash: %s (substitution verified)\n  → after rotation this hash will change without restarting the agent",
		redacted, hash,
	), nil
}

func writeJSON(f *os.File, v interface{}) {
	if v == nil {
		return
	}
	b, _ := json.Marshal(v)
	_, _ = fmt.Fprintf(f, "%s\n", b)
}
