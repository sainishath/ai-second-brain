import requests
import json
import time
import os
from pathlib import Path

BASE_URL = "http://127.0.0.1:8000"

def log_test(name, success, message=""):
    status = "SUCCESS" if success else "FAILED"
    print(f"[{status}] {name} {message}")
    if not success:
        raise AssertionError(f"Test {name} failed: {message}")

def run_tests():
    print("=== STARTING ADVANCED VERIFICATION SUITE ===")
    
    # ─── Test 1: Ingestion & Import Deduplication ───
    print("\n--- Test 1: Ingestion & Import Deduplication ---")
    url = "https://example.com"
    print(f"Importing URL: {url} ...")
    
    # Run import
    resp = requests.post(f"{BASE_URL}/api/import", json={"url": url})
    if resp.status_code == 200:
        data = resp.json()
        print(f"Imported successfully: {data}")
        log_test("Import URL first time", True)
    else:
        log_test("Import URL first time", False, f"Status: {resp.status_code}, Body: {resp.text}")
        
    # Import again (deduplication check)
    print("Importing same URL again...")
    resp2 = requests.post(f"{BASE_URL}/api/import", json={"url": url})
    if resp2.status_code == 200:
        data2 = resp2.json()
        print(f"Deduplication response: {data2}")
        if data2.get("status") == "exists":
            log_test("URL Import Deduplication", True, f"Correctly detected existing: {data2.get('name')}")
        else:
            log_test("URL Import Deduplication", False, f"Expected status 'exists', got: {data2}")
    else:
        log_test("URL Import Deduplication", False, f"Status: {resp2.status_code}, Body: {resp2.text}")
        
    # Import invalid URL (error robustness check)
    print("Importing invalid URL...")
    resp_invalid = requests.post(f"{BASE_URL}/api/import", json={"url": "http://invalid-url-that-does-not-exist-12345.com"})
    if resp_invalid.status_code == 502:
        log_test("Invalid URL Handled (502)", True)
    else:
        log_test("Invalid URL Handled (502)", False, f"Expected 502, got: {resp_invalid.status_code}")
        
    # Verify server is still alive
    resp_alive = requests.get(f"{BASE_URL}/api/overview")
    if resp_alive.status_code == 200:
        log_test("Server Alive Check", True)
    else:
        log_test("Server Alive Check", False)

    # ─── Test 2: Note CRUD, Status Polling, Soft-Delete & Restore ───
    print("\n--- Test 2: Note CRUD, Status Polling, Soft-Delete & Restore ---")
    note_name = "temp_test_note"
    note_payload = {
        "name": note_name,
        "content": "---\ntype: note\ntags:\n  - test-tag\n---\nThis is a temporary test note about [[zettelkasten_intro]].",
        "type": "note",
        "overwrite": True,
        "tags": ["test-tag"]
    }
    
    print(f"Creating note: {note_name} ...")
    resp_create = requests.post(f"{BASE_URL}/api/note", json=note_payload)
    if resp_create.status_code == 200:
        log_test("Create Note", True)
    else:
        log_test("Create Note", False, f"Status: {resp_create.status_code}, Body: {resp_create.text}")
        
    # Poll status
    print("Polling note status...")
    status = "indexing"
    for i in range(40):
        resp_status = requests.get(f"{BASE_URL}/api/note/{note_name}/status")
        if resp_status.status_code == 200:
            status = resp_status.json().get("status")
            print(f"  Attempt {i+1}: status is '{status}'")
            if status == "indexed":
                break
        else:
            print(f"  Failed status query: {resp_status.status_code}")
        time.sleep(1.5)
        
    if status == "indexed":
        log_test("Status Polling (Transitions to indexed)", True)
    else:
        log_test("Status Polling (Transitions to indexed)", False, f"Last status: {status}")

    # Check graph includes note
    print("Checking if graph includes note...")
    resp_graph = requests.get(f"{BASE_URL}/api/notes/graph")
    graph_nodes = [n["id"] for n in resp_graph.json().get("nodes", [])]
    if note_name in graph_nodes:
        log_test("Graph inclusion check", True)
    else:
        log_test("Graph inclusion check", False, "Note not found in graph nodes")

    # Soft Delete
    print("Performing soft-delete...")
    resp_delete = requests.delete(f"{BASE_URL}/api/note/{note_name}?hard=false")
    if resp_delete.status_code == 200 and resp_delete.json().get("status") == "archived":
        log_test("Soft Delete note", True)
    else:
        log_test("Soft Delete note", False, f"Response: {resp_delete.text}")
        
    # Check graph excludes note
    resp_graph2 = requests.get(f"{BASE_URL}/api/notes/graph")
    graph_nodes2 = [n["id"] for n in resp_graph2.json().get("nodes", [])]
    if note_name not in graph_nodes2:
        log_test("Soft deleted note excluded from graph", True)
    else:
        log_test("Soft deleted note excluded from graph", False, "Archived note still present in graph")

    # Restore (Unmodified) -> Should skip re-indexing
    print("Restoring note (unmodified)...")
    resp_restore = requests.post(f"{BASE_URL}/api/note/{note_name}/restore")
    if resp_restore.status_code == 200:
        r_data = resp_restore.json()
        print(f"Restore response: {r_data}")
        if r_data.get("indexed") == True:
            log_test("Restore Unmodified (Skips Indexing)", True)
        else:
            log_test("Restore Unmodified (Skips Indexing)", False, "Re-indexed when hash was unmodified")
    else:
        log_test("Restore Unmodified (Skips Indexing)", False, f"Status: {resp_restore.status_code}")

    # Verify status is indexed immediately
    resp_status_restored = requests.get(f"{BASE_URL}/api/note/{note_name}/status")
    if resp_status_restored.status_code == 200 and resp_status_restored.json().get("status") == "indexed":
        log_test("Restored note status immediately indexed", True)
    else:
        log_test("Restored note status immediately indexed", False, f"Status: {resp_status_restored.text}")

    # Soft Delete again
    requests.delete(f"{BASE_URL}/api/note/{note_name}?hard=false")

    # Modify file on disk to trigger re-indexing on restore
    print("Modifying note file content on disk to simulate change...")
    notes_dir = Path("./data/notes")
    note_file = notes_dir / f"{note_name}.md"
    current_content = note_file.read_text(encoding="utf-8")
    modified_content = current_content + "\n\nAdded some new text here to change hash."
    note_file.write_text(modified_content, encoding="utf-8")

    # Restore (Modified) -> Should trigger indexing
    print("Restoring note (modified)...")
    resp_restore_mod = requests.post(f"{BASE_URL}/api/note/{note_name}/restore")
    if resp_restore_mod.status_code == 200:
        r_mod_data = resp_restore_mod.json()
        print(f"Restore response: {r_mod_data}")
        if r_mod_data.get("indexed") == False:
            log_test("Restore Modified (Triggers Indexing)", True)
        else:
            log_test("Restore Modified (Triggers Indexing)", False, "Skipped indexing even though content changed")
    else:
        log_test("Restore Modified (Triggers Indexing)", False, f"Status: {resp_restore_mod.status_code}")

    # Poll status for modified note until indexed
    print("Polling status for restored modified note...")
    status_mod = "indexing"
    for i in range(40):
        resp_status = requests.get(f"{BASE_URL}/api/note/{note_name}/status")
        if resp_status.status_code == 200:
            status_mod = resp_status.json().get("status")
            print(f"  Attempt {i+1}: status is '{status_mod}'")
            if status_mod == "indexed":
                break
        else:
            print(f"  Failed status query: {resp_status.status_code}")
        time.sleep(1.5)
        
    if status_mod == "indexed":
        log_test("Modified note re-indexed successfully", True)
    else:
        log_test("Modified note re-indexed successfully", False, f"Last status: {status_mod}")

    # Hard Delete
    print("Performing hard-delete...")
    resp_hard = requests.delete(f"{BASE_URL}/api/note/{note_name}?hard=true")
    if resp_hard.status_code == 200 and resp_hard.json().get("status") == "deleted":
        log_test("Hard Delete Note", True)
    else:
        log_test("Hard Delete Note", False, f"Response: {resp_hard.text}")

    # Verify 404 for deleted note
    resp_missing = requests.get(f"{BASE_URL}/api/note/{note_name}")
    if resp_missing.status_code == 404:
        log_test("Get missing note returns 404", True)
    else:
        log_test("Get missing note returns 404", False, f"Got status: {resp_missing.status_code}")

    # New Test: Immediate Restore (before indexing completes)
    print("\n--- Test: Immediate Restore (before indexing completes) ---")
    imm_note_name = "temp_imm_restore_note"
    imm_payload = {
        "name": imm_note_name,
        "content": "---\ntype: note\ntags:\n  - test-tag\n---\nImmediate restore test note content.",
        "type": "note",
        "overwrite": True,
        "tags": ["test-tag"]
    }
    
    print(f"Creating note: {imm_note_name} ...")
    resp_imm_create = requests.post(f"{BASE_URL}/api/note", json=imm_payload)
    if resp_imm_create.status_code == 200:
        log_test("Create Note for Immediate Restore", True)
    else:
        log_test("Create Note for Immediate Restore", False, f"Status: {resp_imm_create.status_code}")
        
    print("Immediately calling restore...")
    resp_imm_restore = requests.post(f"{BASE_URL}/api/note/{imm_note_name}/restore")
    if resp_imm_restore.status_code == 200:
        imm_data = resp_imm_restore.json()
        print(f"Immediate restore response: {imm_data}")
        # Assert that the response contains indexed: False
        if imm_data.get("indexed") == False:
            log_test("Immediate Restore returns indexed: False", True)
        else:
            log_test("Immediate Restore returns indexed: False", False, f"Expected indexed: False, got: {imm_data.get('indexed')}")
    else:
        log_test("Immediate Restore returns indexed: False", False, f"Status: {resp_imm_restore.status_code}")
        
    print("Polling status until indexed...")
    imm_status = "indexing"
    for i in range(40):
        resp_imm_status = requests.get(f"{BASE_URL}/api/note/{imm_note_name}/status")
        if resp_imm_status.status_code == 200:
            imm_status = resp_imm_status.json().get("status")
            print(f"  Attempt {i+1}: status is '{imm_status}'")
            if imm_status == "indexed":
                break
        else:
            print(f"  Failed status query: {resp_imm_status.status_code}")
        time.sleep(1.5)
        
    if imm_status == "indexed":
        log_test("Immediate Restore Note eventually indexed", True)
    else:
        log_test("Immediate Restore Note eventually indexed", False, f"Last status: {imm_status}")
        
    # Clean up the test note
    print("Cleaning up immediate restore test note...")
    requests.delete(f"{BASE_URL}/api/note/{imm_note_name}?hard=true")

    # ─── Test 3: Error Handling ───
    print("\n--- Test 3: Error Handling ---")
    resp_err = requests.get(f"{BASE_URL}/api/note/totally_non_existent_note_123")
    if resp_err.status_code == 404:
        log_test("Clean 404 for non-existent note", True)
    else:
        log_test("Clean 404 for non-existent note", False, f"Expected 404, got: {resp_err.status_code}")

    print("\n=== ALL TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    run_tests()
