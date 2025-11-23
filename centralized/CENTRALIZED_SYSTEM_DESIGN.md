# Centralized System Design (Single Chunkserver)

This document describes an alternative, **centralized** design of the tag-based file system with a **single Chunkserver**.
There is:

- one **Controller** that owns all metadata and coordination, and
- one **Chunkserver** that stores all file chunks.

Both the Controller and the Chunkserver run as **Docker containers** attached to the same Docker Swarm **overlay network**.  
There can be **multiple clients (CLIs)** running on external machines, all connecting to the single Controller.

This design is intentionally simple and centralized; it does **not** satisfy the project’s AP requirements, and is mainly for comparison and documentation.

---

## 1. High-Level Architecture (Centralized Controller + Single Chunkserver)

In this centralized design:

- All **clients (CLIs)** send their commands directly to a **Controller container**.
- The Controller:
  - maintains all **metadata** (files, tags, chunk layout),
  - coordinates all operations,
  - sends all chunk reads/writes to a single **Chunkserver container**.
- The **Chunkserver** stores all chunks on its local disk and performs checksum verification.

Conceptual diagram:

```text
      Multiple CLIs (clients)
      on external machines
           |      |
           v      v
        +-----------+
        | Controller|   (Docker container on overlay network)
        | (Metadata |
        |  + Logic) |
        +-----+-----+
              |
              v
        +-----------+
        |Chunkserver|   (single Docker container on overlay network)
        |  (single) |
        +-----------+
```

Logically there is **one Controller** and **one Chunkserver**, each in its own container on the overlay network.

---

## 2. Components and Responsibilities

### 2.1 CLI (Client)

- Runs outside Docker (on lab machines).
- Connects directly to the Controller’s exposed host IP and port.
- Multiple CLIs may be active concurrently.
- Sends high-level operations:
  - `add file-list tag-list`
  - `list tag-query`
  - `delete tag-query`
  - `add-tags tag-query tag-list`
  - `delete-tags tag-query tag-list`
- Displays results and errors.

### 2.2 Controller Node (Docker Container)

**Single logical instance** (single container).

Responsibilities:

- Maintain all file system **metadata**:
  - `file_id → {name, tags, deleted_flag, chunks}`
  - `tag → set of file_id`s
  - `<file_id, chunk_index> → {chunk_id, checksum}`
    - (the physical location is always the single Chunkserver).
- Parse and execute all CLI commands:
  - tag queries,
  - tag updates,
  - deletions.
- Coordinate **file writes**:
  - decide chunk boundaries,
  - send chunks to the Chunkserver,
  - verify acknowledgements.
- Coordinate **file reads**:
  - read chunk descriptors from metadata,
  - fetch each chunk from the Chunkserver and stream to the CLI.
- Handle basic monitoring of the Chunkserver:
  - accept registration and heartbeats,
  - show status to administrators.

The Controller is the **single source of truth** for all metadata.

### 2.3 Chunkserver (Single Storage Node, Docker Container)

There is **exactly one** Chunkserver container on the overlay network.

Responsibilities:

- Store **immutable chunks** on its local filesystem (inside the container, backed by a Docker volume).
- For each chunk, store:
  - `chunk_id`
  - `file_id`
  - `chunk_index`
  - `length`
  - `checksum`
  - `data`
- Verify checksums on write and on read:
  - reject corrupted writes,
  - detect disk corruption and report it to the Controller.
- Serve read and write requests from the Controller only.
- Periodically send **heartbeats** and basic metrics (capacity, used space) to the Controller.

Because there is only one Chunkserver:

- there is no chunk replication across multiple servers,
- all file data is concentrated in one container/volume.

---

## 3. Data Model and On-Disk Storage

### 3.1 Chunk Size

We use a **fixed chunk size of 64 MiB** (67,108,864 bytes):

- Large enough to reduce metadata overhead for large files.
- Small enough to be manageable in memory during transfers.
- The last chunk of a file may be smaller than 64 MiB if the file size is not a multiple of the chunk size.

This chunk size can be made configurable, but `64 MiB` is the **default** used in the design and documentation.

### 3.2 Files and Chunks (Logical View)

Each file has:

- `file_id`: internal unique identifier,
- `name`: human-readable name (not necessarily unique),
- `tags`: set of strings,
- `deleted_flag`: logical deletion flag,
- ordered list of chunks.

Each chunk is described logically by:

- `chunk_id`: globally unique identifier,
- `file_id`: ID of the file it belongs to,
- `chunk_index`: position of this chunk within the file,
- `length`: number of valid bytes (≤ 64 MiB),
- `checksum`: **SHA-256 hash** of the chunk data (32 bytes).

The physical location is implicit:
- all chunks are stored on the single Chunkserver.

### 3.3 On-Disk Layout on the Chunkserver

The Chunkserver stores data under a mounted volume, e.g. `/data`, with:

- a **chunk data directory**, e.g. `/data/chunks/`
- an optional local **index file** (or small embedded KV store), e.g. `/data/index.db`

Proposed layout:

- For each `chunk_id`, create a file:

  ```text
  /data/chunks/<chunk_id>.chk
  ```

  The file contents consist of:

  - a small header (fixed-size struct) with:
    - `file_id`
    - `chunk_index`
    - `length`
    - `checksum`
  - followed by:
    - raw `data` bytes of the chunk.

- Additionally, maintain a **local index** mapping:

  ```text
  chunk_id → {path="/data/chunks/<chunk_id>.chk", file_id, chunk_index, length, checksum}
  ```

  This index can be:
  - in-memory rebuilt at startup by scanning `/data/chunks`, or
  - persisted in a lightweight on-disk database.

The Controller does **not** access `/data` directly; it only talks to the Chunkserver via RPC.  
When the Controller needs a chunk, it sends `chunk_id` to the Chunkserver, which:

- looks up the path and metadata in its local index,
- reads the header and data,
- verifies the checksum,
- streams the data back to the Controller.

### 3.4 Metadata Storage in the Controller

Metadata is stored only in the Controller, for example as:

- in-memory data structures:
  - `files[file_id] = {name, tags, deleted_flag, [chunk_descriptors...]}`,
  - `tag_index[tag] = set(file_id, ...)`,
- periodically persisted to disk (e.g. JSON, binary file, or small embedded DB).

Consistency is trivial because there is only one writer: the Controller process.

### 3.5 Tag Query Semantics

Tag queries use **conjunctive (AND) logic**:

- A tag query is a list of tags: `[tag1, tag2, ...]`
- A file matches the query if it has **all** specified tags
- Implementation: compute the **intersection** of file sets:
  - `S1 = tagIndex[tag1]`
  - `S2 = tagIndex[tag2]`
  - `result = S1 ∩ S2 ∩ ...`
- If a tag does not exist in `tagIndex`, it is treated as an empty set (no files match)
- An empty tag query matches all non-deleted files
- Deleted files (`deleted_flag = true`) are always excluded from results

### 3.6 Operation Idempotency

All operations are **idempotent** and handle edge cases gracefully:

- **DELETE**: Deleting already-deleted files succeeds (no-op). Returns success.
- **ADD-TAGS**: Adding tags that already exist on a file succeeds (no-op). Returns success.
- **DELETE-TAGS**: Removing tags that don't exist on a file succeeds (no-op). Returns success.
- All operations return success with metadata about the operation (e.g., number of files modified).

This simplifies client logic and retry handling.

### 3.7 Deleted File Policy

Files are **logically deleted** and invisible to all operations:

- **LIST**: Excludes deleted files from results
- **ADD-TAGS / DELETE-TAGS**: Only apply to non-deleted files
- **DELETE**: Sets `deleted_flag = true` and removes file from all tag indices
- Deleted files cannot be recovered through normal operations
- Physical deletion (garbage collection) happens asynchronously in the background

---

## 4. Operation Flows

### 4.1 `add file-list tag-list`

For each file:

1. **CLI → Controller**
   - CLI opens a connection and sends `add` with file name and `tag-list`.
   - Controller acknowledges and starts the protocol.

2. **Controller: file and chunk setup**
   - Allocates a new `file_id`.
   - Reads the file stream from the CLI.
   - Splits the file into chunks of **64 MiB** (except the last one).
   - For each chunk:
     - computes `checksum`,
     - assigns `chunk_id` and `chunk_index`.
   - Fills in metadata structures for:
     - file info (name, tags, deletion flag),
     - chunk list (`chunk_id`, `chunk_index`, `length`, `checksum`),
     - tag index (`tag → file_id` mapping).

3. **Controller → Chunkserver**
   - For each chunk, send `(chunk_id, file_id, chunk_index, length, checksum, data)` to the Chunkserver.
   - Chunkserver:
     - verifies the checksum,
     - writes the chunk file under `/data/chunks/<chunk_id>.chk`,
     - updates its local chunk index,
     - replies with success or failure.

4. **Success condition**
   - The Controller considers the file successfully stored when:
     - all chunks have been acknowledged by the Chunkserver,
     - metadata has been updated locally (and optionally flushed to disk).

5. **Final response**
   - Controller returns success (or error) to the CLI.

---

### 4.2 `list tag-query`

1. **CLI → Controller**
   - CLI sends `list tag-query`.

2. **Controller**
   - Evaluates the tag query using the `tag → file_id` index.
   - Filters out deleted files (`deleted_flag = true`).
   - Returns the list of matching files with name and tags.

3. **CLI**
   - Displays the results.

All information required for `list` is in Controller metadata; the Chunkserver is not involved.

---

### 4.3 `delete tag-query`

1. **CLI → Controller**
   - CLI sends `delete tag-query`.

2. **Controller**
   - Evaluates the tag query to obtain matching `file_id`s.
   - For each file:
     - sets `deleted_flag = true`,
     - updates tag index to exclude this file from future queries.
   - Returns success or error.

3. **Background garbage collection**
   - Optionally, the Controller can later instruct the Chunkserver to delete chunk files belonging to deleted files.

---

### 4.4 `add-tags tag-query tag-list`

1. **CLI → Controller**
   - CLI sends `add-tags tag-query tag-list`.

2. **Controller**
   - Finds all `file_id`s matching `tag-query`.
   - For each file:
     - adds the new tags to its tag set,
     - adds `file_id` to each affected tag index entry.
   - Returns success.

### 4.5 `delete-tags tag-query tag-list`

1. **CLI → Controller**
   - CLI sends `delete-tags tag-query tag-list`.

2. **Controller**
   - Finds all `file_id`s matching `tag-query`.
   - For each file:
     - removes the given tags from its tag set,
     - removes `file_id` from the respective tag index entries.
   - Returns success.

Tag operations are completely local to the Controller.

---

## 5. Failure Behaviour

### 5.1 Chunkserver Failure

Because there is only one Chunkserver:

- If it fails or becomes unreachable:
  - new writes cannot be completed,
  - reads cannot be served,
  - the entire system becomes effectively unavailable for data operations.
- Metadata in the Controller still exists, but is not useful without access to chunks.
- Once the Chunkserver is restarted:
  - it reloads its local chunk index from `/data/chunks`,
  - resumes serving read/write requests.

There is **no replication** or automatic failover for chunk data in this design.

### 5.2 Controller Failure

The Controller is a **single point of failure** for metadata and coordination:

- If the Controller container is down:
  - no CLI can perform any operation,
  - Chunkserver might still hold data but has no external interface.
- On restart, the Controller:
  - reloads metadata from disk (if persisted),
  - reconnects to the Chunkserver.

### 5.3 Network Partitions

In any partition scenario:

- The side that contains the **Controller container, Chunkserver container, and at least one CLI** can continue operating.
- Any environment where:
  - CLIs are separated from the Controller, or
  - Controller is separated from the Chunkserver,
  results in the system being effectively unavailable to users.

The centralized design therefore provides **simple, strong consistency** but **poor availability** under partitions.

---

## 6. Comparison to the AP, Multi-Node Design

Relative to the AP, multi-node design:

- **Simplicity**
  - Centralized with one Chunkserver is much simpler to implement:
    - no CRDTs,
    - no gossip,
    - no replica selection.
- **Scalability**
  - Limited: all reads/writes go through a single Chunkserver and Controller.
- **Fault tolerance**
  - Weak: both Controller and Chunkserver are single points of failure.
- **Partition tolerance**
  - Low: partitions that separate any of:
    - CLIs and Controller,
    - Controller and Chunkserver,
    render the system unusable.

This centralized, single-Chunkserver design can be useful:
- as a teaching baseline,
- or for very small setups where availability and partition tolerance are not critical.

For the actual project with explicit AP requirements, the replicated multi-node design remains the primary target.
