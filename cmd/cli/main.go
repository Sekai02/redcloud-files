package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strconv"
	"strings"
)

var serverURL string

func init() {
	serverURL = os.Getenv("REDCLOUD_SERVER_URL")
	if serverURL == "" {
		serverURL = "http://localhost:8080"
	}
}

func main() {
	if len(os.Args) < 2 {
		printUsage()
		os.Exit(1)
	}

	command := os.Args[1]

	switch command {
	case "create":
		handleCreate(os.Args[2:])
	case "delete":
		handleDelete(os.Args[2:])
	case "read":
		handleRead(os.Args[2:])
	case "write":
		handleWrite(os.Args[2:])
	case "copy":
		handleCopy(os.Args[2:])
	case "import":
		handleImport(os.Args[2:])
	case "export":
		handleExport(os.Args[2:])
	case "tag-add":
		handleTagAdd(os.Args[2:])
	case "tag-remove":
		handleTagRemove(os.Args[2:])
	case "tag-list":
		handleTagList(os.Args[2:])
	case "devices":
		handleDevices(os.Args[2:])
	case "scope-create":
		handleScopeCreate(os.Args[2:])
	case "scope-add-source":
		handleScopeAddSource(os.Args[2:])
	case "scope-add-filter":
		handleScopeAddFilter(os.Args[2:])
	case "scope-list":
		handleScopeList(os.Args[2:])
	default:
		fmt.Printf("Unknown command: %s\n", command)
		printUsage()
		os.Exit(1)
	}
}

func printUsage() {
	fmt.Println("Usage: cli <command> [args]")
	fmt.Println("\nFile operations:")
	fmt.Println("  create --dev <device_id>")
	fmt.Println("  delete --dev <device_id> --file <file_id>")
	fmt.Println("  read --dev <device_id> --file <file_id> [--off <offset>] [--len <length>]")
	fmt.Println("  write --dev <device_id> --file <file_id> --data <data> [--off <offset>]")
	fmt.Println("  copy --dev <device_id> --file <file_id> --dst <dest_device_id>")
	fmt.Println("  import --dev <device_id> --path <os_file_path> [--tags <tag1,tag2,...>]")
	fmt.Println("  export --dev <device_id> --file <file_id> --path <os_file_path>")
	fmt.Println("\nTag operations:")
	fmt.Println("  tag-add --dev <device_id> --file <file_id> --tag <tag_name>")
	fmt.Println("  tag-remove --dev <device_id> --file <file_id> --tag <tag_name>")
	fmt.Println("  tag-list --dev <device_id> --file <file_id>")
	fmt.Println("\nDevice operations:")
	fmt.Println("  devices")
	fmt.Println("\nScope operations:")
	fmt.Println("  scope-create")
	fmt.Println("  scope-add-source --scope <scope_id> --source <source_id>")
	fmt.Println("  scope-add-filter --scope <scope_id> --tags <tag1,tag2,...>")
	fmt.Println("  scope-list --scope <scope_id>")
}

func handleCreate(args []string) {
	devID := parseFlag(args, "--dev")
	if devID == "" {
		fmt.Println("Error: --dev required")
		os.Exit(1)
	}

	dev, _ := strconv.ParseUint(devID, 10, 64)

	reqBody, _ := json.Marshal(map[string]uint64{"device_id": dev})
	resp, err := http.Post(serverURL+"/v1/files", "application/json", bytes.NewBuffer(reqBody))
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		os.Exit(1)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusCreated {
		body, _ := io.ReadAll(resp.Body)
		fmt.Printf("Error: %s\n", string(body))
		os.Exit(1)
	}

	var result map[string]uint64
	json.NewDecoder(resp.Body).Decode(&result)
	fmt.Printf("Created file ID: %d\n", result["file_id"])
}

func handleDelete(args []string) {
	devID := parseFlag(args, "--dev")
	fileID := parseFlag(args, "--file")

	if devID == "" || fileID == "" {
		fmt.Println("Error: --dev and --file required")
		os.Exit(1)
	}

	url := fmt.Sprintf("%s/v1/files/%s/%s", serverURL, devID, fileID)
	req, _ := http.NewRequest(http.MethodDelete, url, nil)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		os.Exit(1)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusNoContent {
		body, _ := io.ReadAll(resp.Body)
		fmt.Printf("Error: %s\n", string(body))
		os.Exit(1)
	}

	fmt.Println("File deleted")
}

func handleRead(args []string) {
	devID := parseFlag(args, "--dev")
	fileID := parseFlag(args, "--file")
	off := parseFlag(args, "--off")
	length := parseFlag(args, "--len")

	if devID == "" || fileID == "" {
		fmt.Println("Error: --dev and --file required")
		os.Exit(1)
	}

	url := fmt.Sprintf("%s/v1/files/%s/%s?", serverURL, devID, fileID)
	if off != "" {
		url += fmt.Sprintf("off=%s&", off)
	}
	if length != "" {
		url += fmt.Sprintf("len=%s", length)
	}

	resp, err := http.Get(url)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		os.Exit(1)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		fmt.Printf("Error: %s\n", string(body))
		os.Exit(1)
	}

	data, _ := io.ReadAll(resp.Body)
	fmt.Printf("%s", string(data))
}

func handleWrite(args []string) {
	devID := parseFlag(args, "--dev")
	fileID := parseFlag(args, "--file")
	data := parseFlag(args, "--data")
	off := parseFlag(args, "--off")

	if devID == "" || fileID == "" || data == "" {
		fmt.Println("Error: --dev, --file, and --data required")
		os.Exit(1)
	}

	url := fmt.Sprintf("%s/v1/files/%s/%s?", serverURL, devID, fileID)
	if off != "" {
		url += fmt.Sprintf("off=%s", off)
	}

	req, _ := http.NewRequest(http.MethodPut, url, strings.NewReader(data))
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		os.Exit(1)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		fmt.Printf("Error: %s\n", string(body))
		os.Exit(1)
	}

	var result map[string]int
	json.NewDecoder(resp.Body).Decode(&result)
	fmt.Printf("Wrote %d bytes\n", result["written"])
}

func handleCopy(args []string) {
	devID := parseFlag(args, "--dev")
	fileID := parseFlag(args, "--file")
	dstID := parseFlag(args, "--dst")

	if devID == "" || fileID == "" || dstID == "" {
		fmt.Println("Error: --dev, --file, and --dst required")
		os.Exit(1)
	}

	url := fmt.Sprintf("%s/v1/files/%s/%s/copy?dst=%s", serverURL, devID, fileID, dstID)
	resp, err := http.Post(url, "application/json", nil)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		os.Exit(1)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		fmt.Printf("Error: %s\n", string(body))
		os.Exit(1)
	}

	var result map[string]uint64
	json.NewDecoder(resp.Body).Decode(&result)
	fmt.Printf("Copied to file ID: %d\n", result["file_id"])
}

func handleTagAdd(args []string) {
	devID := parseFlag(args, "--dev")
	fileID := parseFlag(args, "--file")
	tag := parseFlag(args, "--tag")

	if devID == "" || fileID == "" || tag == "" {
		fmt.Println("Error: --dev, --file, and --tag required")
		os.Exit(1)
	}

	url := fmt.Sprintf("%s/v1/tags/%s/%s", serverURL, devID, fileID)
	reqBody, _ := json.Marshal(map[string]string{"name": tag})
	resp, err := http.Post(url, "application/json", bytes.NewBuffer(reqBody))
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		os.Exit(1)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusNoContent {
		body, _ := io.ReadAll(resp.Body)
		fmt.Printf("Error: %s\n", string(body))
		os.Exit(1)
	}

	fmt.Println("Tag added")
}

func handleTagRemove(args []string) {
	devID := parseFlag(args, "--dev")
	fileID := parseFlag(args, "--file")
	tag := parseFlag(args, "--tag")

	if devID == "" || fileID == "" || tag == "" {
		fmt.Println("Error: --dev, --file, and --tag required")
		os.Exit(1)
	}

	url := fmt.Sprintf("%s/v1/tags/%s/%s?name=%s", serverURL, devID, fileID, tag)
	req, _ := http.NewRequest(http.MethodDelete, url, nil)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		os.Exit(1)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusNoContent {
		body, _ := io.ReadAll(resp.Body)
		fmt.Printf("Error: %s\n", string(body))
		os.Exit(1)
	}

	fmt.Println("Tag removed")
}

func handleTagList(args []string) {
	devID := parseFlag(args, "--dev")
	fileID := parseFlag(args, "--file")

	if devID == "" || fileID == "" {
		fmt.Println("Error: --dev and --file required")
		os.Exit(1)
	}

	url := fmt.Sprintf("%s/v1/tags/%s/%s", serverURL, devID, fileID)
	resp, err := http.Get(url)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		os.Exit(1)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		fmt.Printf("Error: %s\n", string(body))
		os.Exit(1)
	}

	var result map[string][]string
	json.NewDecoder(resp.Body).Decode(&result)
	fmt.Printf("Tags: %v\n", result["tags"])
}

func handleDevices(args []string) {
	resp, err := http.Get(serverURL + "/v1/devices")
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		os.Exit(1)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		fmt.Printf("Error: %s\n", string(body))
		os.Exit(1)
	}

	var result map[string][]uint64
	json.NewDecoder(resp.Body).Decode(&result)
	fmt.Printf("Devices: %v\n", result["devices"])
}

func handleScopeCreate(args []string) {
	resp, err := http.Post(serverURL+"/v1/scopes", "application/json", nil)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		os.Exit(1)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusCreated {
		body, _ := io.ReadAll(resp.Body)
		fmt.Printf("Error: %s\n", string(body))
		os.Exit(1)
	}

	var result map[string]uint64
	json.NewDecoder(resp.Body).Decode(&result)
	fmt.Printf("Created scope ID: %d\n", result["scope_id"])
}

func handleScopeAddSource(args []string) {
	scopeID := parseFlag(args, "--scope")
	sourceID := parseFlag(args, "--source")

	if scopeID == "" || sourceID == "" {
		fmt.Println("Error: --scope and --source required")
		os.Exit(1)
	}

	source, _ := strconv.ParseUint(sourceID, 10, 64)
	url := fmt.Sprintf("%s/v1/scopes/%s/sources", serverURL, scopeID)
	reqBody, _ := json.Marshal(map[string]uint64{"source_id": source})
	resp, err := http.Post(url, "application/json", bytes.NewBuffer(reqBody))
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		os.Exit(1)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusNoContent {
		body, _ := io.ReadAll(resp.Body)
		fmt.Printf("Error: %s\n", string(body))
		os.Exit(1)
	}

	fmt.Println("Source added")
}

func handleScopeAddFilter(args []string) {
	scopeID := parseFlag(args, "--scope")
	tagsStr := parseFlag(args, "--tags")

	if scopeID == "" || tagsStr == "" {
		fmt.Println("Error: --scope and --tags required")
		os.Exit(1)
	}

	tags := strings.Split(tagsStr, ",")
	url := fmt.Sprintf("%s/v1/scopes/%s/filters", serverURL, scopeID)
	reqBody, _ := json.Marshal(map[string][]string{"tags": tags})
	resp, err := http.Post(url, "application/json", bytes.NewBuffer(reqBody))
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		os.Exit(1)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusNoContent {
		body, _ := io.ReadAll(resp.Body)
		fmt.Printf("Error: %s\n", string(body))
		os.Exit(1)
	}

	fmt.Println("Filters added")
}

func handleScopeList(args []string) {
	scopeID := parseFlag(args, "--scope")

	if scopeID == "" {
		fmt.Println("Error: --scope required")
		os.Exit(1)
	}

	url := fmt.Sprintf("%s/v1/scopes/%s/list", serverURL, scopeID)
	resp, err := http.Get(url)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		os.Exit(1)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		fmt.Printf("Error: %s\n", string(body))
		os.Exit(1)
	}

	var result map[string]interface{}
	json.NewDecoder(resp.Body).Decode(&result)
	fmt.Printf("Files: %v\n", result["files"])
}

func handleImport(args []string) {
	devID := parseFlag(args, "--dev")
	path := parseFlag(args, "--path")
	tagsStr := parseFlag(args, "--tags")

	if devID == "" || path == "" {
		fmt.Println("Error: --dev and --path required")
		os.Exit(1)
	}

	dev, _ := strconv.ParseUint(devID, 10, 64)

	tags := []string{}
	if tagsStr != "" {
		tags = strings.Split(tagsStr, ",")
	}

	reqBody, _ := json.Marshal(map[string]interface{}{
		"device_id": dev,
		"path":      path,
		"tags":      tags,
	})

	resp, err := http.Post(serverURL+"/v1/import", "application/json", bytes.NewBuffer(reqBody))
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		os.Exit(1)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusCreated {
		body, _ := io.ReadAll(resp.Body)
		fmt.Printf("Error: %s\n", string(body))
		os.Exit(1)
	}

	var result map[string]interface{}
	json.NewDecoder(resp.Body).Decode(&result)
	fmt.Printf("Imported file '%s' with ID: %.0f\n", result["filename"], result["file_id"])
}

func handleExport(args []string) {
	devID := parseFlag(args, "--dev")
	fileID := parseFlag(args, "--file")
	path := parseFlag(args, "--path")

	if devID == "" || fileID == "" || path == "" {
		fmt.Println("Error: --dev, --file, and --path required")
		os.Exit(1)
	}

	url := fmt.Sprintf("%s/v1/export/%s/%s", serverURL, devID, fileID)
	reqBody, _ := json.Marshal(map[string]string{"path": path})
	resp, err := http.Post(url, "application/json", bytes.NewBuffer(reqBody))
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		os.Exit(1)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusNoContent {
		body, _ := io.ReadAll(resp.Body)
		fmt.Printf("Error: %s\n", string(body))
		os.Exit(1)
	}

	fmt.Printf("Exported file to: %s\n", path)
}

func parseFlag(args []string, flag string) string {
	for i, arg := range args {
		if arg == flag && i+1 < len(args) {
			return args[i+1]
		}
	}
	return ""
}
